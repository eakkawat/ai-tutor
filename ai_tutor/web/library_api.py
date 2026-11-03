"""Library endpoints: upload, list, cancel/retry/remove, and the passage behind a citation."""
import json
import re
import shutil
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from .. import skills as sk
from ..citations import cite
from ..ingest.pdfinfo import read_pdf
from ..ingest.roles import split_filename
from ..pipeline.library import create_source, file_hash
from ..search import search

router = APIRouter(prefix="/api")


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def _guess_title(paths: list[Path]) -> tuple[str, str | None]:
    infos = [read_pdf(p) for p in paths]
    titles = [i.title for i in infos if i.title]
    authors = [i.author for i in infos if i.author]
    if titles:
        return max(set(titles), key=titles.count), (max(set(authors), key=authors.count) if authors else None)
    stem = split_filename(paths[0].name)[1]
    return re.sub(r"\s+\(\d+\)$", "", stem) or paths[0].stem, None


def source_view(db: sqlite3.Connection, r: sqlite3.Row) -> dict:
    d = dict(r)
    detected = json.loads(d.pop("detected_json") or "{}")
    return {
        "id": d["id"], "title": d["title"], "author": d["author"], "kind": d["kind"], "pages": d["pages"],
        "status": d["status"], "stage": d["stage"], "progress": d["progress"], "message": d["message"], "estimate_s": d["estimate_s"],
        "triage": json.loads(d["triage_json"]) if d["triage_json"] else None,
        "chunks": db.execute("SELECT COUNT(*) FROM chunk WHERE source_id = ?", (d["id"],)).fetchone()[0],
        "files": db.execute("SELECT COUNT(*) FROM source_file WHERE source_id = ?", (d["id"],)).fetchone()[0],
        "pages_without_text": detected.get("pages_without_text") or [],
        "skills": db.execute("SELECT COUNT(*) FROM skill WHERE source_id = ? AND status = 'active'", (d["id"],)).fetchone()[0],
        "pending_skills": db.execute("SELECT COUNT(*) FROM skill WHERE source_id = ? AND status = 'pending'", (d["id"],)).fetchone()[0],
    }


@router.post("/library/upload")
async def upload(request: Request, files: list[UploadFile] = File(...), title: str | None = Form(None), author: str | None = Form(None)) -> dict:
    db, root = _db(request), request.app.state.paths.library
    pdfs = [f for f in files if (f.filename or "").lower().endswith(".pdf")]
    if not pdfs:
        raise HTTPException(400, {"message": "Choose a PDF file.", "field": "files"})
    folder = root / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    saved: list[Path] = []
    for f in pdfs:
        dest = folder / Path(f.filename).name              # basename only: no '../' tricks
        dest.write_bytes(await f.read())
        saved.append(dest)
    digest = file_hash(saved)
    dup = db.execute("SELECT id, title FROM source WHERE file_hash = ?", (digest,)).fetchone()
    if dup:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(409, {"message": f"“{dup['title']}” is already in your library.", "field": "duplicate", "source_id": dup["id"]})
    guess_title, guess_author = _guess_title(saved)
    sid = create_source(db, folder, (title or "").strip() or guess_title, (author or "").strip() or guess_author, saved)
    request.app.state.worker.submit(sid)
    return {"id": sid, "skipped": [f.filename for f in files if f not in pdfs]}


@router.get("/library")
def library(request: Request) -> dict:
    db = _db(request)
    rows = db.execute("SELECT * FROM source ORDER BY id DESC").fetchall()
    return {"sources": [source_view(db, r) for r in rows]}


@router.post("/library/{source_id}/cancel")
def cancel(source_id: int, request: Request) -> dict:
    if not request.app.state.worker.cancel(source_id):
        raise HTTPException(409, {"message": "This book is not being processed."})
    return {"ok": True}


@router.post("/library/{source_id}/retry")
def retry(source_id: int, request: Request) -> dict:
    db = _db(request)
    r = db.execute("SELECT status FROM source WHERE id = ?", (source_id,)).fetchone()
    if r is None:
        raise HTTPException(404, {"message": "This book no longer exists."})
    if r["status"] not in ("error", "cancelled", "needs_ocr"):
        raise HTTPException(409, {"message": "This book does not need a retry."})
    db.execute("UPDATE source SET status = 'processing', message = 'Waiting to start' WHERE id = ?", (source_id,))
    db.commit()
    request.app.state.worker.submit(source_id)
    return {"ok": True}


@router.post("/library/{source_id}/find-skills")
def find_skills(source_id: int, request: Request) -> dict:
    """"Look for skills again": run only the skill stage, even for a book triage called reference-only."""
    db = _db(request)
    r = db.execute("SELECT status, triage_json FROM source WHERE id = ?", (source_id,)).fetchone()
    if r is None:
        raise HTTPException(404, {"message": "This book no longer exists."})
    if r["status"] not in ("ready", "reference_only") or not r["triage_json"]:
        raise HTTPException(409, {"message": "This book is not ready for another look."})
    db.execute("UPDATE source SET status = 'processing', message = 'Waiting to start' WHERE id = ?", (source_id,))
    db.commit()
    request.app.state.worker.submit(source_id, only="skills")
    return {"ok": True}


@router.delete("/library/{source_id}")
def remove(source_id: int, request: Request) -> dict:
    db = _db(request)
    r = db.execute("SELECT file_path FROM source WHERE id = ?", (source_id,)).fetchone()
    if r is None:
        raise HTTPException(404, {"message": "This book no longer exists."})
    request.app.state.worker.cancel(source_id)
    sk.purge_source_citations(db, source_id)       # skills, principles and concepts must not point at passages that are about to go
    for (cid,) in db.execute("SELECT id FROM chunk WHERE source_id = ?", (source_id,)).fetchall():
        db.execute("DELETE FROM chunk_vec WHERE rowid = ?", (cid,))
    db.execute("DELETE FROM source WHERE id = ?", (source_id,))        # cascades to source_file and chunk
    db.commit()
    if r["file_path"]:
        folder = Path(r["file_path"]).resolve()
        if request.app.state.paths.library.resolve() in folder.parents:      # never delete outside data/library
            shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True}


@router.get("/chunks/{chunk_id}")
def passage(chunk_id: int, request: Request) -> dict:
    """The passage behind a citation, with the text just before and after it (B6)."""
    db = _db(request)
    c = db.execute("SELECT c.*, s.title AS source_title, s.author AS source_author FROM chunk c JOIN source s ON s.id = c.source_id WHERE c.id = ?",
                   (chunk_id,)).fetchone()
    if c is None:
        raise HTTPException(404, {"message": "This passage no longer exists. The book may have been removed."})
    prev = db.execute("SELECT id, text, page_end FROM chunk WHERE source_id = ? AND ord < ? ORDER BY ord DESC LIMIT 1", (c["source_id"], c["ord"])).fetchone()
    nxt = db.execute("SELECT id, text, page_start FROM chunk WHERE source_id = ? AND ord > ? ORDER BY ord LIMIT 1", (c["source_id"], c["ord"])).fetchone()
    return {
        "id": c["id"], "source_id": c["source_id"], "source_title": c["source_title"], "author": c["source_author"],
        "label": c["label"], "title": c["title"], "page_start": c["page_start"], "page_end": c["page_end"], "citation": cite(c), "text": c["text"],
        "before": prev["text"][-600:] if prev else None, "after": nxt["text"][:600] if nxt else None,
        "prev_id": prev["id"] if prev else None, "next_id": nxt["id"] if nxt else None,
    }


@router.get("/search")
def find(q: str, request: Request, k: int = 8) -> dict:
    hits = search(_db(request), request.app.state.embedder(), q, k=min(max(k, 1), 20))
    return {"hits": [{"chunk_id": h.chunk_id, "citation": cite(h), "score": round(h.score, 4), "text": h.text[:300]} for h in hits]}
