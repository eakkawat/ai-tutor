import io
import time

import pytest
from helpers import NO_SKILLS, TRIAGE_OK, TRIAGE_REF, FakeEmbedder, ScriptedBackend, make_pdf, make_scan

from ai_tutor.llm.client import LLMClient
from ai_tutor.llm.errors import LLMPausedError

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}


@pytest.fixture
def app_with(make_client):
    """Client with a fake embedder and a scripted model. `replies` = what the model says to each triage call."""
    def make(*replies, embedder=None):
        backend = ScriptedBackend(*replies, default=NO_SKILLS)
        emb = embedder or FakeEmbedder()
        c = make_client(check_kwargs=READY, embedder=lambda: emb, llm_client=lambda sid: LLMClient("triage", backend, model="m"), resume=False)
        c.backend, c.emb = backend, emb
        return c
    return make


def pdf_bytes(tmp_path, name="[Book A].pdf", **kw):
    chapters = kw.pop("chapters", [("Chapter 1: Want", 3), ("Chapter 2: Obstacle", 3), ("Chapter 3: Stakes", 2)])
    return make_pdf(tmp_path / name, chapters, **kw)


def upload(c, paths, **form):
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in paths]
    return c.post("/api/library/upload", files=files, data=form)


def finish(c, sid):
    c.app.state.worker.wait(sid, 30)
    return next(s for s in c.get("/api/library").json()["sources"] if s["id"] == sid)


def test_upload_book_becomes_ready_with_cited_chunks(app_with, tmp_path):
    with app_with(TRIAGE_OK) as c:
        r = upload(c, [pdf_bytes(tmp_path)])
        assert r.status_code == 200
        s = finish(c, r.json()["id"])
        assert s["status"] == "ready" and s["title"] == "[Book A]" and s["author"] == "[Author]"
        assert s["pages"] == 8 and s["chunks"] >= 3 and s["triage"]["practicable"] is True
        db = c.app.state.db
        labels = {r[0] for r in db.execute("SELECT DISTINCT label FROM chunk")}
        assert labels == {"Ch. 1", "Ch. 2", "Ch. 3"}
        assert all(r["page_start"] >= 1 and r["page_end"] >= r["page_start"] for r in db.execute("SELECT * FROM chunk"))
        assert db.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == s["chunks"]
        assert db.execute("SELECT COUNT(*) FROM llm_call WHERE job='triage' AND ok=1").fetchone()[0] == 1


def test_triage_prompt_fences_book_text_as_data(app_with, tmp_path):
    with app_with(TRIAGE_OK) as c:
        finish(c, upload(c, [pdf_bytes(tmp_path)]).json()["id"])
        prompt = c.backend.prompts[0][1]
        assert '<data label="outline">' in prompt and "Ch. 2" in prompt
        assert '<data label="chapter samples">' in prompt and "### Ch. 1: Chapter 1: Want" in prompt


def test_no_practicable_skills_is_reference_only_but_still_searchable(app_with, tmp_path):
    with app_with(TRIAGE_REF) as c:
        s = finish(c, upload(c, [pdf_bytes(tmp_path)]).json()["id"])
        assert s["status"] == "reference_only" and s["triage"]["reason"]
        hits = c.get("/api/search", params={"q": "obstacle"}).json()["hits"]
        assert hits and hits[0]["citation"].startswith("[[Book A], ch.")


def test_scanned_pdf_is_flagged_needs_ocr_not_silently_failed(app_with, tmp_path):
    with app_with() as c:
        s = finish(c, upload(c, [make_scan(tmp_path / "scan.pdf")]).json()["id"])
        assert s["status"] == "needs_ocr" and "scanned" in s["message"] and s["chunks"] == 0
        assert c.backend.prompts == []                         # no model call was wasted


def test_partly_scanned_book_names_the_missing_pages(app_with, tmp_path):
    with app_with(TRIAGE_OK) as c:
        s = finish(c, upload(c, [pdf_bytes(tmp_path, chapters=[("Chapter 1: Want", 5)], blank_pages=(3,))]).json()["id"])
        assert s["status"] == "ready" and s["pages_without_text"] == ["3"] and "p. 3" in s["message"]


def test_chapter_pdfs_are_grouped_under_one_book(app_with, tmp_path):
    files = [make_pdf(tmp_path / f"0{i}_Chapter_{w}.pdf", [(f"Chapter {i}: {w}", 2)], title="[Book C]") for i, w in ((1, "One"), (2, "Two"), (3, "Three"))]
    with app_with(TRIAGE_OK) as c:
        r = upload(c, files)
        s = finish(c, r.json()["id"])
        assert s["kind"] == "chapters" and s["files"] == 3 and s["title"] == "[Book C]" and len(c.get("/api/library").json()["sources"]) == 1
        assert {r[0] for r in c.app.state.db.execute("SELECT DISTINCT label FROM chunk")} == {"Ch. 1", "Ch. 2", "Ch. 3"}


def test_duplicate_upload_is_detected(app_with, tmp_path):
    p = pdf_bytes(tmp_path)
    with app_with(TRIAGE_OK) as c:
        sid = upload(c, [p]).json()["id"]
        finish(c, sid)
        r = upload(c, [p])
        assert r.status_code == 409 and r.json()["detail"]["source_id"] == sid
        assert len(c.get("/api/library").json()["sources"]) == 1


def test_non_pdf_is_rejected(app_with):
    with app_with() as c:
        r = c.post("/api/library/upload", files=[("files", ("notes.txt", io.BytesIO(b"hi"), "text/plain"))])
        assert r.status_code == 400


def test_model_down_keeps_the_book_searchable_and_retry_finishes(app_with, tmp_path):
    with app_with(LLMPausedError("down"), TRIAGE_OK) as c:
        sid = upload(c, [pdf_bytes(tmp_path)]).json()["id"]
        s = finish(c, sid)
        assert s["status"] == "error" and "Retry" in s["message"] and s["chunks"] >= 3
        assert c.get("/api/search", params={"q": "stakes"}).json()["hits"]
        calls_before = c.emb.calls
        assert c.post(f"/api/library/{sid}/retry").status_code == 200
        s = finish(c, sid)
        assert s["status"] == "ready"
        assert c.app.state.db.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == s["chunks"]
        assert calls_before > 0


def test_embedding_resumes_without_redoing_finished_passages(app_with, tmp_path):
    from ai_tutor.pipeline.library import Run
    with app_with(TRIAGE_OK) as c:
        sid = upload(c, [pdf_bytes(tmp_path)]).json()["id"]
        finish(c, sid)
        db = c.app.state.db
        total = db.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
        victim = db.execute("SELECT id FROM chunk ORDER BY ord LIMIT 1").fetchone()[0]
        db.execute("DELETE FROM chunk_vec WHERE rowid = ?", (victim,))
        db.commit()
        emb = FakeEmbedder()
        run = Run(db, sid, embedder=emb, llm_factory=None)
        run.embed()
        assert db.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == total and emb.calls == 1


def test_cancel_stops_the_run(make_client, tmp_path):
    from ai_tutor.pipeline.library import Run, create_source
    from ai_tutor.store.conn import open_db
    db = open_db(tmp_path / "x.db")
    folder = tmp_path / "f"
    folder.mkdir()
    sid = create_source(db, folder, "[Book A]", None, [pdf_bytes(folder)])
    Run(db, sid, embedder=FakeEmbedder(), llm_factory=None, is_cancelled=lambda: True).run()
    row = db.execute("SELECT status, message FROM source").fetchone()
    assert row["status"] == "cancelled" and db.execute("SELECT COUNT(*) FROM chunk").fetchone()[0] == 0


def test_missing_embedding_model_is_a_clear_error(app_with, tmp_path):
    with app_with(TRIAGE_OK, embedder=None) as c:
        c.app.state.worker.embedder_factory = lambda: None
        s = finish(c, upload(c, [pdf_bytes(tmp_path)]).json()["id"])
        assert s["status"] == "error" and "uv sync --extra embed" in s["message"]


def test_passage_endpoint_and_citation_target(app_with, tmp_path):
    with app_with(TRIAGE_OK) as c:
        finish(c, upload(c, [pdf_bytes(tmp_path)]).json()["id"])
        hit = c.get("/api/search", params={"q": "obstacle"}).json()["hits"][0]
        p = c.get(f"/api/chunks/{hit['chunk_id']}").json()
        assert p["citation"] == hit["citation"] and p["source_title"] == "[Book A]" and p["text"] and "obstacle" in p["text"]
        assert p["page_start"] >= 1
        assert c.get("/api/chunks/99999").status_code == 404


def test_remove_book_deletes_chunks_vectors_and_files(app_with, tmp_path):
    with app_with(TRIAGE_OK) as c:
        sid = upload(c, [pdf_bytes(tmp_path)]).json()["id"]
        finish(c, sid)
        folder = next(c.app.state.paths.library.iterdir())
        assert c.delete(f"/api/library/{sid}").status_code == 200
        db = c.app.state.db
        assert db.execute("SELECT COUNT(*) FROM chunk").fetchone()[0] == 0 and db.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 0
        assert not folder.exists()
        assert c.get("/api/chunks/1").status_code == 404


def test_interrupted_book_resumes_on_startup(make_client, tmp_path):
    from fastapi.testclient import TestClient

    from ai_tutor.config import Paths
    from ai_tutor.llm.client import LLMClient
    from ai_tutor.pipeline.library import create_source
    from ai_tutor.store.conn import open_db
    from ai_tutor.web.app import create_app
    root = tmp_path / "data"
    paths = Paths(root=root).ensure()
    db = open_db(paths.db)
    folder = paths.library / "abc"
    folder.mkdir()
    sid = create_source(db, folder, "[Book A]", None, [pdf_bytes(folder)])       # left on 'processing': the app closed mid-run
    db.close()
    app = create_app(data_paths=paths, check_kwargs=READY, embedder=lambda: FakeEmbedder(),
                     llm_client=lambda s: LLMClient("triage", ScriptedBackend(TRIAGE_OK, default=NO_SKILLS), model="m"))
    with TestClient(app) as c:
        deadline = time.time() + 30
        while time.time() < deadline and finish(c, sid)["status"] == "processing":
            time.sleep(0.1)
        assert finish(c, sid)["status"] == "ready"
