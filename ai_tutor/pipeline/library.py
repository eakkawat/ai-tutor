"""Book pipeline (Flow 2, up to triage): extract → chunk → embed → triage. Each stage can be re-run; a retry skips what is done.

Runs in a background thread with its own database connection. `check()` raises `Cancelled` when the user cancels.
"""
import hashlib
import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from .. import app_settings
from ..embeddings import Embedder, EmbeddingUnavailable, chunk_document
from ..ingest.front_matter import find_front_matter
from ..ingest.pdfinfo import PdfInfo, page_text, read_pdf
from ..ingest.roles import FRONT_MATTER, detect_role, split_filename
from ..llm.client import LLMClient
from ..llm.errors import LLMError, LLMOutputError, LLMPausedError
from ..llm.prompts import DATA_RULE, fence, load_prompt
from .chunking import SKIP_ROLES, Unit, chunk_unit, ranges, units_from_bookmarks, units_from_windows
from .skills import Extractor

log = logging.getLogger(__name__)

EMBED_BATCH = 16
FRONT_MATTER_CHARS = 12000
SAMPLE_CHAPTERS = 8
SAMPLE_CHARS = 1500
STAGES = ("extracting", "chunking", "embedding", "triage", "skills")
# Rough shares of the whole run, for the progress bar.
_SHARE = {"extracting": (0.0, 0.05), "chunking": (0.05, 0.15), "embedding": (0.15, 0.6), "triage": (0.6, 0.65), "skills": (0.65, 1.0)}


class Cancelled(Exception):
    """The user pressed Cancel."""


class Finished(Exception):
    """A stage already set the book's final status (for example 'needs OCR'); stop without touching it."""


class PipelineError(Exception):
    """Shown to the user as the book's status message."""


class Triage(BaseModel):
    book_type: str = Field(description="practical | theory | reference | narrative")
    practicable: bool
    domain: str = "general"
    likely_skills: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(min_length=1)


def file_hash(paths: list[Path]) -> str:
    """Same bytes in the same set of files = same book, whatever the upload is called."""
    parts = sorted(hashlib.sha1(p.read_bytes()).hexdigest() for p in paths)
    return hashlib.sha1("".join(parts).encode()).hexdigest()


def estimate_seconds(pages: int) -> int:
    """A rough guess for the progress message (extract + embed on the CPU + one model call). Not measured; shown as 'about'."""
    return int(15 + pages * 0.35)


def create_source(db: sqlite3.Connection, folder: Path, title: str, author: str | None, paths: list[Path]) -> int:
    """Register uploaded PDFs as one book. `paths` are already inside `folder`."""
    infos = [(p, read_pdf(p)) for p in paths]
    kind = "chapters" if len(paths) > 1 else "single"
    pages = sum(i.pages for _, i in infos)
    cur = db.execute(
        "INSERT INTO source(title, author, type, file_path, file_hash, status, kind, pages, estimate_s, message) "
        "VALUES (?,?,?,?,?, 'processing', ?,?,?, 'Waiting to start')",
        (title, author, "book", str(folder), file_hash(paths), kind, pages, estimate_seconds(pages)),
    )
    sid = cur.lastrowid
    ordered = sorted(infos, key=lambda pi: (split_filename(pi[0].name)[0] is None, split_filename(pi[0].name)[0] or 0, pi[0].name))
    for idx, (p, info) in enumerate(ordered):
        g = detect_role(p.name, info if kind == "chapters" else None)
        db.execute(
            "INSERT INTO source_file(source_id, filename, path, order_idx, role, role_number, pages, include, note) VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, p.name, str(p), idx, "chapter" if kind == "single" else g.role, g.number, info.pages, int(g.include or kind == "single"),
             g.note if kind == "chapters" else (None if info.has_text else "needs_ocr")),
        )
    db.commit()
    return sid


class Run:
    def __init__(self, db: sqlite3.Connection, source_id: int, *, embedder: Embedder | None, llm_factory: Callable[[], LLMClient] | None,
                 is_cancelled: Callable[[], bool] = lambda: False):
        self.db, self.sid, self.embedder, self.llm_factory, self.is_cancelled = db, source_id, embedder, llm_factory, is_cancelled
        self.source = dict(db.execute("SELECT * FROM source WHERE id = ?", (source_id,)).fetchone())
        self.files = [dict(r) for r in db.execute("SELECT * FROM source_file WHERE source_id = ? ORDER BY order_idx, id", (source_id,))]

    # --- plumbing
    def check(self) -> None:
        if self.is_cancelled():
            raise Cancelled()

    def say(self, stage: str, frac: float, message: str) -> None:
        a, b = _SHARE[stage]
        self.db.execute("UPDATE source SET stage = ?, progress = ?, message = ? WHERE id = ?", (stage, round(a + (b - a) * frac, 3), message, self.sid))
        self.db.commit()

    def finish(self, status: str, message: str | None, **cols) -> None:
        sets = ", ".join(f"{k} = ?" for k in cols)
        self.db.execute(f"UPDATE source SET status = ?, message = ?, stage = NULL{', ' + sets if sets else ''} WHERE id = ?",
                        (status, message, *cols.values(), self.sid))
        self.db.commit()

    # --- stages
    def run(self, only: str | None = None) -> None:
        """`only="skills"` runs just the skill stage (the "Look for skills again" button). It forces the stage even for reference-only books."""
        try:
            if only == "skills":
                self._triage_report = Triage.model_validate_json(self.source["triage_json"]) if self.source["triage_json"] else None
                if self._triage_report is None:
                    raise PipelineError("This book has not been triaged yet. Press Retry first.")
                self.db.execute("DELETE FROM extraction_done WHERE source_id = ?", (self.sid,))
                self.db.commit()
                self.skills(force=True)
                return
            self.extract()
            self.chunk()
            self.embed()
            self.triage()
            self.skills()
        except Finished:
            pass
        except Cancelled:
            self.finish("cancelled", "Cancelled. Press Retry to start again.")
        except PipelineError as e:
            self.finish("error", str(e))
        except LLMPausedError as e:
            self.finish("error", f"The language model could not be reached ({e}). Press Retry when the server is up.")
        except (LLMError, LLMOutputError) as e:
            self.finish("error", f"The language model could not triage this book: {e}")
        except Exception as e:
            log.exception("pipeline failed for source %s", self.sid)
            self.finish("error", f"Something went wrong: {e}")

    def extract(self) -> None:
        """Read each file's facts. A book with no text at all is flagged 'needs OCR' and the run stops (B1)."""
        self.say("extracting", 0, "Reading the PDF…")
        included = [f for f in self.files if f["include"]]
        infos: dict[int, PdfInfo] = {}
        for i, f in enumerate(included):
            self.check()
            infos[f["id"]] = read_pdf(f["path"])
            self.say("extracting", (i + 1) / max(len(included), 1), f"Reading file {i + 1} of {len(included)}…")
        broken = [f["filename"] for f in included if infos[f["id"]].error]
        if included and len(broken) == len(included):
            raise PipelineError(infos[included[0]["id"]].error or "Cannot read this PDF.")
        if not any(i.has_text for i in infos.values()):
            self.finish("needs_ocr", "No text found. This looks like a scanned book, so it can't be taught from yet.")
            raise Finished
        if self.source["kind"] == "single":
            info = infos[included[0]["id"]]
            self.db.execute("UPDATE source SET detected_json = ? WHERE id = ?",
                            (json.dumps({"front_matter": find_front_matter(included[0]["path"], info)}), self.sid))
            self.db.commit()
        self._infos = infos

    def _detected(self) -> dict:
        raw = self.db.execute("SELECT detected_json FROM source WHERE id = ?", (self.sid,)).fetchone()[0]
        return json.loads(raw or "{}")

    def units(self) -> list[Unit]:
        included = [f for f in self.files if f["include"]]
        if self.source["kind"] == "single":
            f = included[0]
            path, info = Path(f["path"]), self._infos[f["id"]]
            units = units_from_bookmarks(path, info.toc, info.pages)
            if len(units) < 2:
                detected = self._detected().get("front_matter", {})
                start = max((r[1] for r in detected.values()), default=0) + 1
                units = units_from_windows(path, info.pages, start)
            for u in units:
                u.file_id = f["id"]
            return units
        out = []
        for f in included:
            if f["role"] in SKIP_ROLES:
                continue
            title = split_filename(f["filename"])[1] or f["filename"]
            u = Unit(Path(f["path"]), title, f["role_number"] if f["role"] == "chapter" else None, 1, f["pages"])
            u.file_id = f["id"]
            out.append(u)
        return out

    def chunk(self) -> None:
        if self.db.execute("SELECT chunked FROM source WHERE id = ?", (self.sid,)).fetchone()[0]:
            self._gaps = self._detected().get("pages_without_text") or []        # already done: skills may cite these passages
            return
        self.say("chunking", 0, "Splitting into chapters and pages…")
        self._delete_chunks()
        units = self.units()
        total_chunks = 0
        gaps: list[str] = []
        for i, u in enumerate(units):
            self.check()
            pieces, missing = chunk_unit(u)
            if missing and len(missing) < (u.last - u.first + 1):
                gaps.append(ranges(missing))        # a partly scanned chapter; fully empty ones are just skipped
            for p in pieces:
                self.db.execute(
                    "INSERT INTO chunk(source_id, source_file_id, chapter, page_start, page_end, text, title, label, ord) VALUES (?,?,?,?,?,?,?,?,?)",
                    (self.sid, u.file_id, p.label, p.pages[0], p.pages[1], p.text, p.title, p.label, total_chunks))
                total_chunks += 1
            self.say("chunking", (i + 1) / max(len(units), 1), f"Splitting… {total_chunks} passages so far")
        self.db.commit()
        if not total_chunks:
            self.finish("needs_ocr", "No readable chapter text found. The pages may be scans that need OCR.")
            raise Finished
        self.db.execute("UPDATE source SET detected_json = json_set(COALESCE(detected_json, '{}'), '$.pages_without_text', json(?)) WHERE id = ?",
                        (json.dumps(gaps), self.sid))
        self.db.execute("UPDATE source SET chunked = 1 WHERE id = ?", (self.sid,))
        self.db.commit()
        self._gaps = gaps

    def _delete_chunks(self) -> None:
        ids = [r[0] for r in self.db.execute("SELECT id FROM chunk WHERE source_id = ?", (self.sid,))]
        for cid in ids:
            self.db.execute("DELETE FROM chunk_vec WHERE rowid = ?", (cid,))
        self.db.execute("DELETE FROM chunk WHERE source_id = ?", (self.sid,))
        self.db.commit()

    def embed(self) -> None:
        """Resumable: only chunks without a vector are embedded."""
        if self.embedder is None:
            raise PipelineError("The embedding model is not installed. Run: uv sync --extra embed")
        todo = [dict(r) for r in self.db.execute(
            "SELECT id, title, text FROM chunk WHERE source_id = ? AND id NOT IN (SELECT rowid FROM chunk_vec) ORDER BY ord", (self.sid,))]
        total = len(todo)
        for i in range(0, total, EMBED_BATCH):
            self.check()
            batch = todo[i:i + EMBED_BATCH]
            try:
                vecs = self.embedder.documents([chunk_document(c["title"], c["text"]) for c in batch])
            except EmbeddingUnavailable as e:
                raise PipelineError(str(e)) from e
            for c, v in zip(batch, vecs, strict=True):
                self.db.execute("INSERT INTO chunk_vec(rowid, embedding) VALUES (?, ?)", (c["id"], np.asarray(v, dtype=np.float32).tobytes()))
            self.db.commit()
            self.say("embedding", min(i + EMBED_BATCH, total) / total, f"Indexing… {min(i + EMBED_BATCH, total)} of {total} passages")

    def triage(self) -> None:
        """One model call: what kind of book is this, and is it worth teaching from? Reference-only books stay searchable."""
        self.say("triage", 0, "Checking what this book is good for…")
        if self.llm_factory is None:
            raise PipelineError("The language model is not set up. Open Setup, then press Retry.")
        self.check()
        outline, evidence = self._outline(), self._front_matter()
        prompt = load_prompt("triage")
        report = self.llm_factory().json(
            Triage,
            prompt.render(rule=DATA_RULE, title=self.source["title"], author=self.source["author"] or "unknown",
                          outline=fence("outline", outline or "(no outline found)"),
                          evidence=fence("front matter", evidence or "(no contents, preface or introduction found)"),
                          samples=fence("chapter samples", self._samples() or "(none)"),
                          domains=", ".join(r[0] for r in self.db.execute("SELECT DISTINCT domain FROM skill WHERE status != 'archived'")) or "(none yet)"),
            prompt_version=prompt.version, source_id=self.sid)
        self.db.execute("UPDATE source SET triage_json = ? WHERE id = ?", (report.model_dump_json(), self.sid))
        self.db.commit()
        self._triage_report = report

    def skills(self, force: bool = False) -> None:
        """Extract skills and concepts when triage says the book is practicable (or the user asked again). Then set the final status."""
        report = self._triage_report
        gaps = getattr(self, "_gaps", None) or []
        note = f"{len(gaps)} chapter(s) have pages without text (p. {'; '.join(gaps)}); those pages were skipped." if gaps else None
        if not report.practicable and not force:
            self.finish("reference_only", note, progress=1.0)
            return
        if self.llm_factory is None:
            raise PipelineError("The language model is not set up. Open Setup, then press Retry.")
        self.say("skills", 0, "Finding skills…")
        stats = Extractor(self.db, self.sid, report.domain, llm=self.llm_factory(), embedder=self.embedder, mode=app_settings.skill_mode(),
                          check=self.check, say=lambda f, m: self.say("skills", f, m)).run()
        msg = stats.message()
        produced = stats.added or stats.merges or stats.merged_quietly
        self.finish("ready" if (report.practicable or produced) else "reference_only", " ".join(x for x in (msg, note) if x) or None, progress=1.0)

    def _samples(self) -> str:
        """The first lines of up to 8 chapters, spread through the book, so triage can see exercises and steps, not just titles."""
        rows = self.db.execute("SELECT label, title, text FROM chunk WHERE source_id = ? AND ord IN "
                               "(SELECT MIN(ord) FROM chunk WHERE source_id = ? GROUP BY label) ORDER BY ord", (self.sid, self.sid)).fetchall()
        if len(rows) > SAMPLE_CHAPTERS:
            step = len(rows) / SAMPLE_CHAPTERS
            rows = [rows[int(i * step)] for i in range(SAMPLE_CHAPTERS)]
        return "\n\n".join(f"### {r['label']}: {r['title']}\n{r['text'][:SAMPLE_CHARS]}" for r in rows)

    def _outline(self) -> str:
        rows = self.db.execute("SELECT DISTINCT label, title FROM chunk WHERE source_id = ? ORDER BY ord", (self.sid,)).fetchall()
        return "\n".join(f"- {r['label']}: {r['title']}" if r["label"] != r["title"] else f"- {r['title']}" for r in rows)[:6000]

    def _front_matter(self) -> str:
        parts: list[str] = []
        if self.source["kind"] == "single":
            f = next(f for f in self.files if f["include"])
            for role, (a, b) in self._detected().get("front_matter", {}).items():
                if role in FRONT_MATTER:
                    parts.append(f"## {role}\n" + "\n".join(page_text(f["path"], n) for n in range(a, min(b, a + 9) + 1)))
        else:
            for f in self.files:
                if f["role"] in FRONT_MATTER and f["include"]:
                    parts.append(f"## {f['role']}\n" + "\n".join(page_text(f["path"], n) for n in range(1, min(f["pages"], 8) + 1)))
        return "\n\n".join(parts)[:FRONT_MATTER_CHARS]
