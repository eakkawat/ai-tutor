import itertools
import json
from pathlib import Path

import pytest
from media_helpers import make_long, make_png, make_video
from PIL import Image

from ai_tutor import assets, media
from ai_tutor.config import Paths
from ai_tutor.store.conn import open_db


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    return {"three": make_video(d / "three.mp4"), "audio": make_video(d / "audio.mp4", audio=True), "exact": make_long(d / "exact.mp4", 180),
            "long": make_long(d / "long.mp4", 185)}


# ---------- ffmpeg pieces

def test_probe_reads_length_and_audio(clips):
    p = media.probe(clips["three"])
    assert p.duration == pytest.approx(7.0, abs=0.2) and p.has_audio is False and (p.width, p.height) == (160, 120)
    assert media.probe(clips["audio"]).has_audio is True


def test_cuts_are_found_where_the_shot_changes_and_shot_lengths_follow(clips):
    cuts = media.detect_cuts(clips["three"], 7.0)
    assert cuts == [2.0, 5.0]
    assert media.shot_lengths(cuts, 7.0) == [2.0, 3.0, 2.0]
    assert media.shot_lengths([], 5.0) == [5.0]


def test_frames_every_two_seconds_plus_one_after_each_cut_without_near_duplicates():
    plan = media.frame_times(7.0, [2.0, 5.0])
    assert plan == [(0.0, False), (2.1, True), (4.0, False), (5.1, True), (6.0, False)]


def test_over_the_cap_frames_are_sampled_evenly_and_keep_the_first_and_last():
    plan = media.frame_times(170.0, [30.0, 90.0], cap=20)
    assert len(plan) == 20 and plan[0][0] == 0.0
    ts = [t for t, _ in plan]
    assert ts == sorted(ts) and ts[-1] >= 160.0
    gaps = [b - a for a, b in itertools.pairwise(ts)]
    assert max(gaps) < 12                                             # no big hole: the sampling is even
    assert len(media.frame_times(2.0, [], cap=20)) == 1               # a very short clip still gets a frame


def test_the_length_limit_is_about_three_minutes_and_the_limit_itself_is_fine(clips):
    assert not media.too_long(media.probe(clips["exact"]).duration)   # exactly at the limit
    assert not media.too_long(180.4) and media.too_long(181.0)
    assert media.too_long(media.probe(clips["long"]).duration)


def test_time_formats():
    assert media.fmt_time(75.4) == "1:15" and media.fmt_range(12, 18) == "0:12–0:18" and media.fmt_range(12.1, 12.4) == "0:12"


def test_unreadable_files_say_so():
    with pytest.raises(media.MediaError, match="could not read this video"):
        media.probe(Path(__file__))


def test_kinds_by_extension():
    assert [media.kind_of(n) for n in ("a.PNG", "b.jpeg", "c.mov", "d.MP4", "e.txt", "f")] == ["image", "image", "video", "video", None, None]


# ---------- pictures

def test_a_big_picture_is_shrunk_for_the_model_and_a_thumbnail_is_made(tmp_path):
    src = make_png(tmp_path / "big.png", (3200, 1800))
    info = media.prepare_image(src, tmp_path / "m.jpg", tmp_path / "t.jpg")
    assert info["downscaled"] is True and info["width"] == 3200
    assert max(Image.open(tmp_path / "m.jpg").size) == media.MODEL_IMAGE_SIDE and max(Image.open(tmp_path / "t.jpg").size) <= media.THUMB_SIDE * 2


def test_a_small_picture_is_not_enlarged_and_a_text_file_is_refused(tmp_path):
    src = make_png(tmp_path / "s.png", (300, 200))
    assert media.prepare_image(src, tmp_path / "m.jpg", tmp_path / "t.jpg")["downscaled"] is False
    assert Image.open(tmp_path / "m.jpg").size == (300, 200)
    bad = tmp_path / "notes.png"
    bad.write_text("not a picture")
    with pytest.raises(media.MediaError, match="not a picture"):
        media.prepare_image(bad, tmp_path / "m2.jpg", tmp_path / "t2.jpg")


# ---------- attachments in the database

@pytest.fixture
def lib(tmp_path):
    paths = Paths(root=tmp_path / "data").ensure()
    db = open_db(paths.db)
    db.execute("INSERT INTO project(id, name, good_enough) VALUES (1, 'P', 'g')")
    db.execute("INSERT INTO skill(id, domain, name, description) VALUES (1, 'd', 's', 'd')")
    db.execute("INSERT INTO session(id, project_id, skill_id, phase) VALUES (1, 1, 1, 'practice')")
    db.commit()
    return type("Lib", (), {"db": db, "paths": paths, "dir": tmp_path})


def video_asset(lib, clip, name="clip.mp4"):
    dest = assets.reserve_video_path(lib.paths, 1, name)
    dest.write_bytes(Path(clip).read_bytes())
    return assets.add_video(lib.db, lib.paths, 1, name, dest)


def test_an_image_is_saved_with_a_thumbnail_and_listed_as_a_draft(lib):
    aid = assets.add_image(lib.db, lib.paths, 1, "frame 01.png", make_png(lib.dir / "a.png").read_bytes())
    [a] = assets.draft_assets(lib.db, 1)
    assert a["id"] == aid and a["kind"] == "image" and a["status"] == "ready" and a["thumb"] == f"/api/assets/{aid}/file?variant=thumb" and (a["width"], a["height"]) == (320, 240)
    row = lib.db.execute("SELECT file_path FROM submission_asset").fetchone()[0]
    assert Path(row).exists() and Path(row + ".model.jpg").exists() and Path(row + ".thumb.jpg").exists() and "submissions" in row


def test_not_a_picture_and_too_many_pictures_are_refused(lib):
    with pytest.raises(assets.AssetError) as e:
        assets.add_image(lib.db, lib.paths, 1, "x.png", b"nope")
    assert e.value.code == "unsupported" and "not a picture" in str(e.value)
    assert lib.db.execute("SELECT COUNT(*) FROM submission_asset").fetchone()[0] == 0
    png = make_png(lib.dir / "a.png").read_bytes()
    for _ in range(media.MAX_IMAGES_PER_SUBMISSION):
        assets.add_image(lib.db, lib.paths, 1, "a.png", png)
    with pytest.raises(assets.AssetError) as e:
        assets.add_image(lib.db, lib.paths, 1, "a.png", png)
    assert e.value.code == "too_many"


def test_a_clip_over_three_minutes_is_rejected_with_a_split_it_message_and_nothing_is_kept(lib, clips):
    with pytest.raises(assets.AssetError) as e:
        video_asset(lib, clips["long"])
    assert e.value.code == "too_long" and "3:05 long" in str(e.value) and "Split it" in str(e.value)
    assert lib.db.execute("SELECT COUNT(*) FROM submission_asset").fetchone()[0] == 0
    assert not list((lib.paths.submissions / "1").glob("*")) or all(not p.name.endswith("clip.mp4") for p in (lib.paths.submissions / "1").glob("*"))


def test_a_clip_exactly_at_the_limit_is_accepted(lib, clips):
    aid = video_asset(lib, clips["exact"])
    a = lib.db.execute("SELECT status, duration_s FROM submission_asset WHERE id = ?", (aid,)).fetchone()
    assert a["status"] == "processing" and a["duration_s"] == pytest.approx(180.0, abs=0.5)


def test_a_clip_that_is_not_video_is_refused(lib):
    dest = assets.reserve_video_path(lib.paths, 1, "fake.mp4")
    dest.write_text("not a video")
    with pytest.raises(assets.AssetError, match="could not read this video"):
        assets.add_video(lib.db, lib.paths, 1, "fake.mp4", dest)
    assert not dest.exists()


def test_processing_a_clip_stores_frames_cuts_shots_and_dialogue(lib, clips):
    aid = video_asset(lib, clips["audio"])
    seen = []
    assets.process_video(lib.db, lib.paths, aid, transcriber=lambda p: [{"start": 0.5, "end": 2.0, "text": "Leave it."}])
    a = lib.db.execute("SELECT * FROM submission_asset WHERE id = ?", (aid,)).fetchone()
    p = json.loads(a["processed_json"])
    assert a["status"] == "ready" and p["cuts"] == [2.0, 5.0] and p["shots"] == [2.0, 3.0, 2.0] and p["transcript"][0]["text"] == "Leave it."
    frames = lib.db.execute("SELECT * FROM video_frame WHERE asset_id = ? ORDER BY idx", (aid,)).fetchall()
    assert [f["idx"] for f in frames] == [1, 2, 3, 4, 5] and [bool(f["is_cut"]) for f in frames] == [False, True, False, True, False]
    assert all(Path(f["file_path"]).exists() and Path(f["file_path"]).stat().st_size > 0 for f in frames) and frames[1]["timestamp_s"] == pytest.approx(2.1)
    assert p["steps"]["cuts"] == {"status": "done", "count": 2} and p["steps"]["frames"]["status"] == "done" and p["steps"]["transcript"] == {"status": "done", "lines": 1}
    assert seen == []


def test_progress_is_reported_step_by_step(lib, clips):
    aid = video_asset(lib, clips["three"])
    snapshots = []
    orig = assets.media.process_clip

    def spy(path, frames_dir, *, report, transcriber=None, pr=None):
        return orig(path, frames_dir, report=lambda steps: (snapshots.append(json.loads(json.dumps(steps))), report(steps))[1], transcriber=transcriber, pr=pr)

    assets.media.process_clip = spy
    try:
        assets.process_video(lib.db, lib.paths, aid)
    finally:
        assets.media.process_clip = orig
    assert snapshots[0]["cuts"]["status"] == "running"
    assert any(s["frames"].get("status") == "running" and s["frames"].get("done") for s in snapshots)
    assert snapshots[-1]["frames"]["status"] == "done"


def test_a_clip_with_no_audio_skips_the_transcript_and_says_so(lib, clips):
    aid = video_asset(lib, clips["three"])
    assets.process_video(lib.db, lib.paths, aid, transcriber=lambda p: pytest.fail("no audio: nothing to transcribe"))
    p = json.loads(lib.db.execute("SELECT processed_json FROM submission_asset").fetchone()[0])
    assert lib.db.execute("SELECT status FROM submission_asset").fetchone()[0] == "ready"
    assert p["steps"]["transcript"] == {"status": "skipped", "note": "No audio track."} and "no audio" in p["notes"][0]


def test_without_whisper_the_clip_still_processes_frames_and_cuts(lib, clips):
    aid = video_asset(lib, clips["audio"])

    def no_whisper(path):
        raise media.MediaError("Whisper is not installed, so the dialogue could not be written down.")

    assets.process_video(lib.db, lib.paths, aid, transcriber=no_whisper)
    a = lib.db.execute("SELECT * FROM submission_asset").fetchone()
    p = json.loads(a["processed_json"])
    assert a["status"] == "ready" and p["transcript"] == [] and p["steps"]["transcript"]["status"] == "skipped" and "Feedback uses the frames and cuts only" in p["notes"][0]
    assert lib.db.execute("SELECT COUNT(*) FROM video_frame").fetchone()[0] == 5


def test_an_ffmpeg_failure_keeps_the_upload_and_says_why_and_a_retry_works(lib, clips, monkeypatch):
    aid = video_asset(lib, clips["three"])
    monkeypatch.setattr(media, "extract_frame", lambda *a, **k: (_ for _ in ()).throw(media.MediaError("ffmpeg could not take a picture at 0:02.")))
    assets.process_video(lib.db, lib.paths, aid)
    a = lib.db.execute("SELECT * FROM submission_asset").fetchone()
    assert a["status"] == "error" and a["error"] == "ffmpeg could not take a picture at 0:02." and Path(a["file_path"]).exists()
    with pytest.raises(assets.AssetError, match="could not be processed: ffmpeg could not take a picture"):
        assets.check_ready(lib.db, 1)
    monkeypatch.undo()
    assets.process_video(lib.db, lib.paths, aid)
    assert lib.db.execute("SELECT status, error FROM submission_asset").fetchone()[:] == ("ready", None)
    assert lib.db.execute("SELECT COUNT(*) FROM video_frame").fetchone()[0] == 5          # no duplicates from the first attempt


def test_a_very_short_clip_still_gets_a_frame_and_a_clip_still_processing_holds_the_submission(lib, tmp_path):
    short = make_video(tmp_path / "short.mp4", (("red", 1),))
    aid = video_asset(lib, short)
    with pytest.raises(assets.AssetError, match="still being processed"):
        assets.check_ready(lib.db, 1)
    assets.process_video(lib.db, lib.paths, aid)
    assert lib.db.execute("SELECT COUNT(*) FROM video_frame").fetchone()[0] == 1
    assert len(assets.check_ready(lib.db, 1)) == 1


def test_removing_a_draft_deletes_its_files_but_a_handed_in_attachment_stays(lib, clips):
    aid = assets.add_image(lib.db, lib.paths, 1, "a.png", make_png(lib.dir / "a.png").read_bytes())
    path = lib.db.execute("SELECT file_path FROM submission_asset").fetchone()[0]
    vid = video_asset(lib, clips["three"])
    assets.process_video(lib.db, lib.paths, vid)
    assets.remove(lib.db, lib.paths, aid)
    assets.remove(lib.db, lib.paths, vid)
    assert not Path(path).exists() and not assets.frames_dir(lib.paths, vid).exists()
    assert lib.db.execute("SELECT COUNT(*) FROM submission_asset").fetchone()[0] == 0 and lib.db.execute("SELECT COUNT(*) FROM video_frame").fetchone()[0] == 0
    kept = assets.add_image(lib.db, lib.paths, 1, "b.png", make_png(lib.dir / "b.png").read_bytes())
    lib.db.execute("INSERT INTO submission(id, session_id, version, text) VALUES (1, 1, 1, 'x')")
    assets.attach(lib.db, 1, 1)
    with pytest.raises(assets.AssetError, match="already handed in"):
        assets.remove(lib.db, lib.paths, kept)


def test_the_bundle_labels_match_the_order_of_the_pictures_sent(lib, clips):
    assets.add_image(lib.db, lib.paths, 1, "board.png", make_png(lib.dir / "a.png").read_bytes())
    vid = video_asset(lib, clips["audio"], "take2.mp4")
    assets.process_video(lib.db, lib.paths, vid, transcriber=lambda p: [{"start": 3.0, "end": 4.0, "text": "You said that last New Year."}])
    lib.db.execute("INSERT INTO submission(id, session_id, version, text) VALUES (1, 1, 1, 'x')")
    assets.attach(lib.db, 1, 1)
    b = assets.bundle_for(lib.db, 1)
    labels = [label for label, _ in b.pictures()]
    assert labels[0] == "IMAGE 1 (board.png)" and labels[1] == "VIDEO 1 · frame 1 · 0:00" and "(shot change)" in labels[2] and "(shot change)" in labels[4] and len(labels) == 6
    text = b.prompt_text()
    assert text.index("IMAGE 1") < text.index("VIDEO 1 · frame 1") and "Shot changes at: 0:02, 0:05" in text and "[0:03] You said that last New Year." in text
    assert "Shot lengths in seconds: 2, 3, 2" in text and len(b.data_urls()) == 6 and b.data_urls()[0].startswith("data:image/jpeg;base64,")
    assert assets.Bundle().prompt_text() == "(no pictures or clips)"


def test_pictures_and_clips_are_processed_with_the_network_blocked(lib, clips, monkeypatch):
    """Everything on this computer: with no sockets allowed, an image and a clip still process, and the model's input is built."""
    import socket

    def no_network(*a, **k):
        raise AssertionError("media processing must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    assets.add_image(lib.db, lib.paths, 1, "a.png", make_png(lib.dir / "a.png").read_bytes())
    vid = video_asset(lib, clips["audio"])
    assets.process_video(lib.db, lib.paths, vid, transcriber=lambda p: [{"start": 1.0, "end": 2.0, "text": "Leave it."}])
    lib.db.execute("INSERT INTO submission(id, session_id, version, text) VALUES (1, 1, 1, 'x')")
    assets.attach(lib.db, 1, 1)
    b = assets.bundle_for(lib.db, 1)
    assert lib.db.execute("SELECT status FROM submission_asset WHERE kind = 'video'").fetchone()[0] == "ready" and len(b.data_urls()) == 6
