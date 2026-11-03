import pytest
from helpers import FakeEmbedder, SmartBackend, fb_json
from media_helpers import make_long, make_png, make_video
from session_helpers import WORK

from ai_tutor.llm.client import LLMClient

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}
OFF = {"which": lambda n: None, "has_module": lambda n: True, "model_cached": lambda: True}


@pytest.fixture
def app(make_client):
    def make(check=READY, phase="practice", feedback=None):
        be = SmartBackend(session={"feedback": feedback or (lambda u, c: fb_json(("followed", "followed")))})
        c = make_client(check_kwargs=check, embedder=lambda: FakeEmbedder(), llm_client=lambda sid: LLMClient("t", be, model="m"), resume=False,
                        transcriber=lambda p: [{"start": 3.0, "end": 4.0, "text": "Leave it."}])
        c.be = be
        return c
    return make


def seed(c, phase="practice"):
    db = c.app.state.db
    db.execute("INSERT INTO source(id, title) VALUES (1, 'Book A')")
    db.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (1,1,'Ch. 3','t','Ch. 3',41,41,'t',1)")
    db.execute("INSERT INTO project(id, name, good_enough) VALUES (1, 'P', 'g')")
    db.execute("INSERT INTO skill(id, domain, name, description) VALUES (1, 'd', 's', 'd')")
    db.execute("INSERT INTO skill_principle(skill_id, principle, test, chunk_id, \"order\") VALUES (1, 'p1', 't1', 1, 0), (1, 'p2', 't2', 1, 1)")
    db.execute("INSERT INTO learner_skill(skill_id, status) VALUES (1, 'active')")
    db.execute("INSERT INTO session(id, project_id, skill_id, phase) VALUES (1, 1, 1, ?)", (phase,))
    db.commit()


def up(c, path, name=None):
    return c.post("/api/sessions/1/assets", files=[("file", (name or path.name, path.read_bytes(), "application/octet-stream"))])


def test_a_picture_is_uploaded_listed_and_served_back(app, tmp_path):
    with app() as c:
        seed(c)
        r = up(c, make_png(tmp_path / "board.png"))
        assert r.status_code == 200
        a = r.json()
        assert a["kind"] == "image" and a["status"] == "ready" and a["filename"] == "board.png" and a["thumb"] == f"/api/assets/{a['id']}/file?variant=thumb"
        assert c.get("/api/sessions/1").json()["assets"][0]["id"] == a["id"]
        for variant in ("thumb", "model", "original"):
            got = c.get(f"/api/assets/{a['id']}/file?variant={variant}")
            assert got.status_code == 200 and got.content[:3] in (b"\xff\xd8\xff", b"\x89PN")
        assert c.delete(f"/api/assets/{a['id']}").json() == {"ok": True}
        assert c.get("/api/sessions/1").json()["assets"] == [] and c.get(f"/api/assets/{a['id']}/file?variant=thumb").status_code == 404


def test_things_that_cannot_be_attached_are_refused_with_a_reason(app, tmp_path):
    with app() as c:
        seed(c)
        txt = tmp_path / "notes.txt"
        txt.write_text("hi")
        r = up(c, txt)
        assert r.status_code == 415 and "PNG, JPG, WEBP and GIF pictures, and MP4, MOV, WEBM and MKV clips" in r.json()["detail"]["message"]
        fake = tmp_path / "fake.png"
        fake.write_text("not a picture")
        r = up(c, fake)
        assert r.status_code == 415 and r.json()["detail"]["code"] == "unsupported" and "not a picture" in r.json()["detail"]["message"]
        assert c.post("/api/sessions/9/assets", files=[("file", ("a.png", b"x", "image/png"))]).status_code == 404
        c.app.state.db.execute("UPDATE session SET phase = 'learn'")
        c.app.state.db.commit()
        r = up(c, make_png(tmp_path / "a.png"))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "wrong_phase"


def test_with_media_tools_missing_uploads_are_off_and_text_still_works(app, tmp_path):
    with app(check=OFF) as c:
        seed(c)
        r = up(c, make_png(tmp_path / "a.png"))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "media_off" and "Text practice still works" in r.json()["detail"]["message"]
        assert c.get("/api/setup/status").json()["media_enabled"] is False
        assert c.get("/api/sessions/1").status_code == 200


def test_a_clip_is_accepted_processed_in_the_background_and_its_frames_are_served(app, tmp_path):
    with app() as c:
        seed(c)
        a = up(c, make_video(tmp_path / "take2.mp4", audio=True)).json()
        assert a["kind"] == "video" and a["status"] in ("processing", "ready") and a["duration_s"] == pytest.approx(7.0, abs=0.3)
        c.app.state.media_worker.wait(a["id"])
        a = c.get("/api/sessions/1").json()["assets"][0]
        assert a["status"] == "ready" and a["steps"]["cuts"] == {"status": "done", "count": 2} and a["steps"]["frames"] == {"status": "done", "done": 5, "total": 5}
        assert a["steps"]["transcript"] == {"status": "done", "lines": 1} and a["thumb"].startswith("/api/frames/")
        frame = c.get(a["thumb"])
        assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg" and frame.content[:3] == b"\xff\xd8\xff"
        assert c.get("/api/frames/99999").status_code == 404


def test_a_clip_over_three_minutes_is_rejected_with_a_split_it_message(app, tmp_path):
    with app() as c:
        seed(c)
        r = up(c, make_long(tmp_path / "long_take.mp4", 185))
        assert r.status_code == 422 and r.json()["detail"]["code"] == "too_long"
        assert "3:05 long" in r.json()["detail"]["message"] and "Split it into shorter clips" in r.json()["detail"]["message"]
        assert c.get("/api/sessions/1").json()["assets"] == []
        assert up(c, make_long(tmp_path / "exact.mp4", 180)).status_code == 200


def test_a_failed_clip_can_be_retried(app, tmp_path, monkeypatch):
    from ai_tutor import media
    with app() as c:
        seed(c)
        real = media.extract_frame
        monkeypatch.setattr(media, "extract_frame", lambda *a, **k: (_ for _ in ()).throw(media.MediaError("ffmpeg could not take a picture at 0:00.")))
        a = up(c, make_video(tmp_path / "t.mp4")).json()
        c.app.state.media_worker.wait(a["id"])
        got = c.get("/api/sessions/1").json()["assets"][0]
        assert got["status"] == "error" and "ffmpeg could not take a picture" in got["error"]
        r = c.post("/api/sessions/1/act", json={"action": "submit", "text": WORK})
        assert r.status_code == 409 and "could not be processed" in r.json()["detail"]["message"]
        monkeypatch.setattr(media, "extract_frame", real)
        assert c.post(f"/api/assets/{a['id']}/retry").json() == {"ok": True}
        c.app.state.media_worker.wait(a["id"])
        assert c.get("/api/sessions/1").json()["assets"][0]["status"] == "ready"
        assert c.post(f"/api/assets/{a['id']}/retry").status_code == 409


def test_a_handed_in_attachment_cannot_be_deleted_and_only_files_in_the_data_folder_are_served(app, tmp_path):
    with app() as c:
        seed(c)
        a = up(c, make_png(tmp_path / "a.png")).json()
        r = c.post("/api/sessions/1/act", json={"action": "submit", "text": WORK})
        assert r.status_code == 200 and r.json()["messages"][-2]["meta"]["assets"][0]["id"] == a["id"]
        assert c.delete(f"/api/assets/{a['id']}").status_code == 409
        c.app.state.db.execute("UPDATE submission_asset SET file_path = '/etc/hostname'")
        c.app.state.db.commit()
        assert c.get(f"/api/assets/{a['id']}/file?variant=original").status_code == 404


def test_the_vision_endpoint_reports_what_the_server_says(app, monkeypatch):
    from ai_tutor import setup_check
    with app() as c:
        monkeypatch.setattr(setup_check, "model_supports_images", lambda cfg: False)
        assert c.get("/api/setup/vision").json() == {"vision": False}
