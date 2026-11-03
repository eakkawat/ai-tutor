import json

import pytest
from helpers import FakeEmbedder, SmartBackend, fb_json
from media_helpers import make_png, make_video
from session_helpers import WORK, to_practice
from test_check_feedback import check_script

from ai_tutor import assets, setup_check
from ai_tutor.config import Paths
from ai_tutor.llm.client import LLMClient
from ai_tutor.session import SessionService, TransitionError


@pytest.fixture
def ctx(env, tmp_path):
    paths = Paths(root=tmp_path / "data").ensure()

    def service(backend, vision=lambda: None):
        svc = SessionService(env.db, llm=LLMClient("t", backend, model="m"), embedder=FakeEmbedder(), clock=env.clock, log_path=env.log, vision=vision)
        svc.be = backend
        return svc

    def image(name="frame_01.png"):
        return assets.add_image(env.db, paths, env.sid, name, make_png(tmp_path / name).read_bytes())

    def clip(shots=(("red", 2), ("blue", 3), ("green", 2)), name="take2.mp4", audio=True):
        src = make_video(tmp_path / name, shots, audio=audio)
        dest = assets.reserve_video_path(paths, env.sid, name)
        dest.write_bytes(src.read_bytes())
        aid = assets.add_video(env.db, paths, env.sid, name, dest)
        assets.process_video(env.db, paths, aid, transcriber=lambda p: [{"start": 3.0, "end": 4.5, "text": "You said that last New Year."}])
        return aid

    return type("Ctx", (), {"service": staticmethod(service), "image": staticmethod(image), "clip": staticmethod(clip), "paths": paths})


def practicing(env, ctx, fb=None, vision=lambda: None):
    s = check_script()
    if fb is not None:
        s["feedback"] = fb
    be = SmartBackend(session=s)
    to_practice(env, env.make(be))
    svc2 = ctx.service(be, vision)
    return svc2, be


def results(view):
    return view["messages"][-1]["meta"]["results"]


def test_a_picture_alone_is_a_valid_submission_and_is_shown_to_the_model(env, ctx):
    svc, be = practicing(env, ctx)
    ctx.image()
    v = svc.act(env.sid, "submit", "")
    sub = v["messages"][-2]
    assert sub["kind"] == "submission" and [a["filename"] for a in sub["meta"]["assets"]] == ["frame_01.png"] and v["assets"] == []        # handed in, no longer a draft
    assert len(be.images_seen[-1]) == 1 and be.images_seen[-1][0].startswith("data:image/jpeg;base64,")
    prompt = next(u for u in be.users if "## Phase: Feedback" in u)
    assert "IMAGE 1 (frame_01.png)" in prompt and "(no text: the work is in the pictures or clips)" in prompt and '<data label="attachments">' in prompt


def test_text_only_work_sends_no_pictures(env, ctx):
    svc, be = practicing(env, ctx)
    svc.act(env.sid, "submit", WORK)
    assert be.images_seen[-1] == [] and "(no pictures or clips)" in next(u for u in be.users if "## Phase: Feedback" in u)


def test_image_evidence_names_the_picture_and_the_part_of_it(env, ctx):
    fb = lambda u, c: fb_json(("followed", "followed"), ("", ""), fixes=[], mistakes=[]) | {"principles": [
        {"n": 1, "result": "followed", "kind": "image", "asset": 1, "region": [0.1, 0.1, 0.3, 0.3], "comment": "The tin is the focus."},
        {"n": 2, "result": "followed", "kind": "image", "asset": 1, "region": [0.6, 0.7, 0.3, 0.2], "comment": "The shadow blocks her."}]}
    svc, _ = practicing(env, ctx, fb=fb)
    ctx.image()
    r1, r2 = results(svc.act(env.sid, "submit", ""))
    assert r1["result"] == "followed" and r1["locator"] == "Image 1, upper left" and r1["evidence"]["region"] == [0.1, 0.1, 0.3, 0.3]
    assert r2["locator"] == "Image 1, lower right" and r2["evidence"]["filename"] == "frame_01.png"
    ev = json.loads(env.db.execute("SELECT evidence_ref FROM principle_check ORDER BY id").fetchone()[0])
    assert ev["kind"] == "image" and ev["asset_id"] == r1["evidence"]["asset_id"]


def test_evidence_pointing_at_a_picture_that_is_not_there_does_not_count(env, ctx):
    fb = lambda u, c: {"principles": [
        {"n": 1, "result": "followed", "kind": "image", "asset": 4, "region": [0.1, 0.1, 0.3, 0.3], "comment": "x"},
        {"n": 2, "result": "followed", "kind": "image", "asset": 1, "region": [0.9, 0.9, 0, 0], "comment": "region is nonsense"}], "fixes": [], "mistakes": []}
    svc, _ = practicing(env, ctx, fb=fb)
    ctx.image()
    r1, r2 = results(svc.act(env.sid, "submit", ""))
    assert r1["result"] == "partly" and r1["evidence"] is None and "could not find the evidence" in r1["comment"]
    assert r2["result"] == "followed" and r2["locator"] == "Image 1" and r2["evidence"]["region"] is None          # a real picture, a bad box: the box is dropped


def test_a_box_that_runs_off_the_edge_is_clipped(env, ctx):
    fb = lambda u, c: {"principles": [{"n": n, "result": "partly", "kind": "image", "asset": 1, "region": [0.8, 0.5, 0.5, 0.9]} for n in (1, 2)], "fixes": [], "mistakes": []}
    svc, _ = practicing(env, ctx, fb=fb)
    ctx.image()
    assert results(svc.act(env.sid, "submit", ""))[0]["evidence"]["region"] == [0.8, 0.5, 0.2, 0.5]


def test_video_evidence_cites_a_time_range_and_the_stored_frames_in_it(env, ctx):
    fb = lambda u, c: {"principles": [
        {"n": 1, "result": "followed", "kind": "video", "asset": 1, "start_s": 2.0, "end_s": 5.0, "comment": "The reaction comes first."},
        {"n": 2, "result": "partly", "kind": "video", "asset": 1, "start_s": 6.5, "end_s": 99.0, "comment": "Runs to the end."}], "fixes": [], "mistakes": []}
    svc, _ = practicing(env, ctx, fb=fb)
    ctx.clip()
    r1, r2 = results(svc.act(env.sid, "submit", ""))
    assert r1["locator"] == "Video 1 · 0:02–0:05" and r1["evidence"]["start_s"] == 2.0
    ids = [f["id"] for f in r1["evidence"]["frames"]]
    assert 1 <= len(ids) <= 4 and all(env.db.execute("SELECT 1 FROM video_frame WHERE id = ?", (i,)).fetchone() for i in ids)
    assert all(1.0 <= f["t"] <= 6.0 for f in r1["evidence"]["frames"])                                      # frames from inside the range (± 1 s)
    assert r2["evidence"]["end_s"] == pytest.approx(7.0, abs=0.2) and r2["locator"].startswith("Video 1 · 0:06–0:07")      # a time past the end is clipped to the clip


def test_video_evidence_outside_the_clip_or_for_a_missing_clip_is_refused(env, ctx):
    fb = lambda u, c: {"principles": [
        {"n": 1, "result": "followed", "kind": "video", "asset": 1, "start_s": 50, "end_s": 60},
        {"n": 2, "result": "followed", "kind": "video", "asset": 3, "start_s": 1, "end_s": 2}], "fixes": [], "mistakes": []}
    svc, _ = practicing(env, ctx, fb=fb)
    ctx.clip()
    assert [r["result"] for r in results(svc.act(env.sid, "submit", ""))] == ["partly", "partly"]


def test_the_model_gets_the_frames_timestamps_transcript_and_cuts_not_the_video(env, ctx):
    svc, be = practicing(env, ctx)
    ctx.clip()
    svc.act(env.sid, "submit", "")
    prompt = next(u for u in be.users if "## Phase: Feedback" in u)
    assert "VIDEO 1 · frame 1 · 0:00" in prompt and "(shot change)" in prompt and "Shot changes at: 0:02, 0:05" in prompt
    assert "[0:03] You said that last New Year." in prompt and "Shot lengths in seconds: 2, 3, 2" in prompt
    assert len(be.images_seen[-1]) == 5


def test_text_pictures_and_clips_are_judged_together_in_one_request(env, ctx):
    fb = lambda u, c: fb_json(("followed", "followed"), ("Mai reaches for the tin", "x")) | {"principles": [
        {"n": 1, "result": "followed", "quote": "Mai reaches for the tin", "comment": "In the text."},
        {"n": 2, "result": "followed", "kind": "video", "asset": 1, "start_s": 0, "end_s": 2, "comment": "In the clip."}]}
    svc, be = practicing(env, ctx, fb=fb)
    ctx.image()
    ctx.clip()
    v = svc.act(env.sid, "submit", WORK)
    assert be.calls["feedback"] == 1 and len(be.images_seen[-1]) == 6                                      # 1 picture + 5 frames, one call
    r1, r2 = results(v)
    assert r1["locator"] == "Line 2" and r2["locator"].startswith("Video 1") and v["messages"][-1]["meta"]["passed"] is True


def test_a_model_that_cannot_read_pictures_is_said_so_and_the_work_is_kept(env, ctx):
    svc, be = practicing(env, ctx, vision=lambda: False)
    ctx.image()
    v = svc.act(env.sid, "submit", WORK)
    assert v["phase"] == "feedback" and v["feedback_pending"] and "cannot read pictures" in v["feedback_error"] and be.calls["feedback"] == 0
    assert v["messages"][-1]["meta"]["retryable"] is False
    svc_ok = ctx.service(be, vision=lambda: True)                                                           # switched to a vision model
    assert svc_ok.act(env.sid, "feedback")["messages"][-1]["kind"] == "feedback"


def test_text_only_work_never_asks_whether_the_model_can_see(env, ctx):
    svc, _ = practicing(env, ctx, vision=lambda: pytest.fail("not needed for text"))
    assert svc.act(env.sid, "submit", WORK)["messages"][-1]["kind"] == "feedback"


def test_a_clip_still_processing_or_failed_holds_the_submission_back(env, ctx):
    svc, _ = practicing(env, ctx)
    ctx.image()
    aid = env.db.execute("SELECT id FROM submission_asset").fetchone()[0]
    env.db.execute("UPDATE submission_asset SET status = 'processing'")
    env.db.commit()
    with pytest.raises(TransitionError, match="still being processed"):
        svc.act(env.sid, "submit", WORK)
    env.db.execute("UPDATE submission_asset SET status = 'error', error = 'ffmpeg could not take a picture at 0:02.'")
    env.db.commit()
    with pytest.raises(TransitionError, match="could not be processed"):
        svc.act(env.sid, "submit", WORK)
    assert env.db.execute("SELECT COUNT(*) FROM submission").fetchone()[0] == 0 and aid
    env.db.execute("UPDATE submission_asset SET status = 'ready', error = NULL")
    env.db.commit()
    assert svc.act(env.sid, "submit", WORK)["attempt"] == 1


def test_nothing_to_submit_and_tiny_text_without_attachments_are_refused_but_tiny_text_with_a_picture_is_fine(env, ctx):
    svc, _ = practicing(env, ctx)
    with pytest.raises(TransitionError, match="Write something, or add a picture or clip"):
        svc.act(env.sid, "submit", "")
    with pytest.raises(TransitionError, match="too short"):
        svc.act(env.sid, "submit", "ok")
    ctx.image()
    assert svc.act(env.sid, "submit", "see the board")["attempt"] == 1


def test_a_revision_starts_with_no_old_attachments_and_the_old_ones_stay_with_their_attempt(env, ctx):
    svc, be = practicing(env, ctx)
    ctx.image("first.png")
    svc.act(env.sid, "submit", WORK)
    v = svc.act(env.sid, "revise")
    assert v["assets"] == []
    ctx.image("second.png")
    v = svc.act(env.sid, "submit", WORK + "\nmore")
    names = [(m["meta"]["version"], [a["filename"] for a in m["meta"]["assets"]]) for m in v["messages"] if m["kind"] == "submission"]
    assert names == [(1, ["first.png"]), (2, ["second.png"])]
    assert len(be.images_seen[-1]) == 1                                                                     # only the new picture is sent for attempt 2


def test_which_model_can_see_comes_from_the_servers_model_list(monkeypatch):
    class Model:
        def __init__(self, id, mods):
            self.id, self.model_extra = id, ({"architecture": {"input_modalities": mods}} if mods is not None else {})

    class Fake:
        def __init__(self, **kw):
            self.models = self

        def list(self):
            return type("R", (), {"data": [Model("vision-model", ["text", "image"]), Model("text-model", ["text"]), Model("silent-model", None)]})()

    import openai
    monkeypatch.setattr(openai, "OpenAI", Fake)
    setup_check._vision_cache.clear()
    from ai_tutor.app_settings import LlmConfig
    cfg = lambda m: LlmConfig("http://x/v1", m)
    assert setup_check.model_supports_images(cfg("vision-model")) is True
    assert setup_check.model_supports_images(cfg("text-model")) is False
    assert setup_check.model_supports_images(cfg("silent-model")) is None and setup_check.model_supports_images(cfg("unknown")) is None
    assert setup_check.model_supports_images(None) is None
