"""Pictures and clips attached to practice work (SPEC §6.6).

An attachment belongs to the session from the moment it is uploaded and to a submission once the work is handed in. Images are
checked and shrunk for the model; clips are measured and then processed in the background (frames, cuts, dialogue). The model never
receives a video: it receives frames with timestamps, a transcript and the cut times.
"""
import base64
import json
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import media
from .config import Paths


class AssetError(Exception):
    """An upload that cannot be accepted, or an attachment that cannot be used yet. The message is shown as is."""

    def __init__(self, message: str, code: str = "bad_file"):
        super().__init__(message)
        self.code = code


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)[:80] or "file"


def _counts(db: sqlite3.Connection, session_id: int) -> dict[str, int]:
    rows = db.execute("SELECT kind, COUNT(*) AS n FROM submission_asset WHERE session_id = ? AND submission_id IS NULL GROUP BY kind", (session_id,)).fetchall()
    return {r["kind"]: r["n"] for r in rows}


def view(db: sqlite3.Connection, a: sqlite3.Row) -> dict:
    p = json.loads(a["processed_json"] or "{}")
    thumb = None
    if a["kind"] == "image":
        thumb = f"/api/assets/{a['id']}/file?variant=thumb"
    else:
        first = db.execute("SELECT id FROM video_frame WHERE asset_id = ? ORDER BY idx LIMIT 1", (a["id"],)).fetchone()
        thumb = f"/api/frames/{first['id']}" if first else None
    return {"id": a["id"], "kind": a["kind"], "filename": a["filename"], "status": a["status"], "error": a["error"], "duration_s": a["duration_s"],
            "size_bytes": a["size_bytes"], "steps": p.get("steps"), "notes": p.get("notes", []), "width": p.get("width"), "height": p.get("height"),
            "downscaled": p.get("downscaled", False), "thumb": thumb, "attached": a["submission_id"] is not None}


def draft_assets(db: sqlite3.Connection, session_id: int) -> list[dict]:
    return [view(db, a) for a in db.execute("SELECT * FROM submission_asset WHERE session_id = ? AND submission_id IS NULL ORDER BY id", (session_id,))]


def add_image(db: sqlite3.Connection, paths: Paths, session_id: int, filename: str, data: bytes) -> int:
    if len(data) > media.MAX_IMAGE_BYTES:
        raise AssetError(f"This picture is {len(data) // (1024 * 1024)} MB. Pictures can be up to {media.MAX_IMAGE_BYTES // (1024 * 1024)} MB.", "too_big")
    if _counts(db, session_id).get("image", 0) >= media.MAX_IMAGES_PER_SUBMISSION:
        raise AssetError(f"You can attach up to {media.MAX_IMAGES_PER_SUBMISSION} pictures to one attempt.", "too_many")
    folder = paths.submissions / str(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{uuid.uuid4().hex[:8]}_{_safe(filename)}"
    src = folder / stem
    src.write_bytes(data)
    try:
        info = media.prepare_image(src, folder / f"{stem}.model.jpg", folder / f"{stem}.thumb.jpg")
    except media.MediaError as e:
        src.unlink(missing_ok=True)
        raise AssetError(str(e), "unsupported") from e
    aid = db.execute(
        "INSERT INTO submission_asset(session_id, kind, filename, file_path, mime, size_bytes, status, processed_json) VALUES (?, 'image', ?, ?, ?, ?, 'ready', ?)",
        (session_id, filename, str(src), f"image/{src.suffix.lstrip('.').lower() or 'png'}", len(data), json.dumps(info))).lastrowid
    db.commit()
    return aid


def add_video(db: sqlite3.Connection, paths: Paths, session_id: int, filename: str, src: Path) -> int:
    """`src` is the uploaded file already on disk. A clip over about 3 minutes is rejected here, before any processing."""
    size = src.stat().st_size
    if size > media.MAX_VIDEO_BYTES:
        src.unlink(missing_ok=True)
        raise AssetError("This file is very large. Clips should be a few minutes long; split it and add the parts.", "too_big")
    if _counts(db, session_id).get("video", 0) >= media.MAX_VIDEOS_PER_SUBMISSION:
        src.unlink(missing_ok=True)
        raise AssetError(f"You can attach up to {media.MAX_VIDEOS_PER_SUBMISSION} clips to one attempt.", "too_many")
    try:
        pr = media.probe(src)
    except media.MediaError as e:
        src.unlink(missing_ok=True)
        raise AssetError(str(e), "unsupported") from e
    if media.too_long(pr.duration):
        src.unlink(missing_ok=True)
        raise AssetError(f"This clip is {media.fmt_time(pr.duration)} long. Clips can be up to 3 minutes. Split it into shorter clips and add them again.", "too_long")
    aid = db.execute(
        "INSERT INTO submission_asset(session_id, kind, filename, file_path, mime, size_bytes, duration_s, status, processed_json) VALUES (?, 'video', ?, ?, ?, ?, ?, 'processing', ?)",
        (session_id, filename, str(src), f"video/{src.suffix.lstrip('.').lower()}", size, pr.duration,
         json.dumps({"steps": {"cuts": {"status": "waiting"}, "frames": {"status": "waiting"}, "transcript": {"status": "waiting"}}, "has_audio": pr.has_audio}))).lastrowid
    db.commit()                                                     # the background worker reads this row through its own connection
    return aid


def reserve_video_path(paths: Paths, session_id: int, filename: str) -> Path:
    folder = paths.submissions / str(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4().hex[:8]}_{_safe(filename)}"


def frames_dir(paths: Paths, asset_id: int) -> Path:
    return paths.frames / str(asset_id)


def process_video(db: sqlite3.Connection, paths: Paths, asset_id: int, *, transcriber=None) -> None:
    """Run the local processing for one clip and store the result. A failure keeps the file and says why, so the learner can retry."""
    a = db.execute("SELECT * FROM submission_asset WHERE id = ? AND kind = 'video'", (asset_id,)).fetchone()
    if a is None:
        return
    prior = json.loads(a["processed_json"] or "{}")

    def save(status: str, data: dict, error: str | None = None) -> None:
        db.execute("UPDATE submission_asset SET status = ?, error = ?, processed_json = ? WHERE id = ?", (status, error, json.dumps({**prior, **data}), asset_id))
        db.commit()

    db.execute("DELETE FROM video_frame WHERE asset_id = ?", (asset_id,))
    shutil.rmtree(frames_dir(paths, asset_id), ignore_errors=True)
    save("processing", {"steps": {"cuts": {"status": "running"}, "frames": {"status": "waiting"}, "transcript": {"status": "waiting"}}})
    try:
        out = media.process_clip(Path(a["file_path"]), frames_dir(paths, asset_id), report=lambda steps: save("processing", {"steps": steps}), transcriber=transcriber)
    except media.MediaError as e:
        save("error", {}, str(e))
        return
    except Exception as e:  # noqa: BLE001 - never leave a clip stuck on "processing"
        save("error", {}, f"Something went wrong while processing this clip: {e}")
        return
    for f in out.frames:
        db.execute("INSERT INTO video_frame(asset_id, timestamp_s, file_path, idx, is_cut) VALUES (?,?,?,?,?)",
                   (asset_id, f["t"], str(frames_dir(paths, asset_id) / f["file"]), f["idx"], int(f["is_cut"])))
    steps = json.loads(db.execute("SELECT processed_json FROM submission_asset WHERE id = ?", (asset_id,)).fetchone()[0]).get("steps")
    save("ready", {"steps": steps, "duration": out.duration, "cuts": out.cuts, "shots": out.shots, "transcript": out.transcript, "notes": out.notes})


def remove(db: sqlite3.Connection, paths: Paths, asset_id: int) -> None:
    a = db.execute("SELECT * FROM submission_asset WHERE id = ?", (asset_id,)).fetchone()
    if a is None:
        raise AssetError("This attachment no longer exists.", "gone")
    if a["submission_id"] is not None:
        raise AssetError("This attachment was already handed in with an attempt.", "attached")
    for suffix in ("", ".model.jpg", ".thumb.jpg"):
        Path(str(a["file_path"]) + suffix).unlink(missing_ok=True)
    shutil.rmtree(frames_dir(paths, asset_id), ignore_errors=True)
    db.execute("DELETE FROM submission_asset WHERE id = ?", (asset_id,))
    db.commit()


def check_ready(db: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    """The attachments that go with the next submission. A clip still processing, or one that failed, holds the submission back."""
    rows = db.execute("SELECT * FROM submission_asset WHERE session_id = ? AND submission_id IS NULL ORDER BY id", (session_id,)).fetchall()
    for a in rows:
        if a["status"] == "processing":
            raise AssetError(f"“{a['filename']}” is still being processed on this computer. It sends when that finishes.", "processing")
        if a["status"] == "error":
            raise AssetError(f"“{a['filename']}” could not be processed: {a['error']} Remove it or try it again.", "failed")
    return rows


def attach(db: sqlite3.Connection, session_id: int, submission_id: int) -> list[dict]:
    db.execute("UPDATE submission_asset SET submission_id = ? WHERE session_id = ? AND submission_id IS NULL", (submission_id, session_id))
    db.commit()
    return [view(db, a) for a in db.execute("SELECT * FROM submission_asset WHERE submission_id = ? ORDER BY id", (submission_id,))]


# ---------- what the model is shown

@dataclass
class Bundle:
    images: list[dict] = field(default_factory=list)      # {n, asset_id, filename, path, width, height}
    videos: list[dict] = field(default_factory=list)      # {n, asset_id, filename, duration, frames, transcript, cuts, shots, notes}

    def empty(self) -> bool:
        return not self.images and not self.videos

    def image(self, n: int | None) -> dict | None:
        return next((i for i in self.images if i["n"] == n), None)

    def video(self, n: int | None) -> dict | None:
        return next((v for v in self.videos if v["n"] == n), None)

    def pictures(self) -> list[tuple[str, Path]]:
        """Every picture the model will see, in the order its label appears in the prompt text."""
        out = [(f"IMAGE {i['n']} ({i['filename']})", Path(i["path"])) for i in self.images]
        for v in self.videos:
            for f in v["frames"]:
                out.append((f"VIDEO {v['n']} · frame {f['idx']} · {media.fmt_time(f['t'])}{' (shot change)' if f['is_cut'] else ''}", Path(f["path"])))
        return out

    def prompt_text(self) -> str:
        if self.empty():
            return "(no pictures or clips)"
        lines = ["The pictures follow this text, in this order:"] + [f"{i}. {label}" for i, (label, _) in enumerate(self.pictures(), 1)]
        for v in self.videos:
            lines.append(f"\nVIDEO {v['n']} ({v['filename']}), {media.fmt_time(v['duration'])} long. "
                         f"Shot changes at: {', '.join(media.fmt_time(c) for c in v['cuts']) or 'none'}. "
                         f"Shot lengths in seconds: {', '.join(f'{s:g}' for s in v['shots'])}.")
            lines += [f"[{media.fmt_time(t['start'])}] {t['text']}" for t in v["transcript"]] or ["(no dialogue transcript)"]
            lines += [f"Note: {n}" for n in v["notes"]]
        return "\n".join(lines)

    def data_urls(self) -> list[str]:
        return ["data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode() for _, p in self.pictures()]


def bundle_for(db: sqlite3.Connection, submission_id: int) -> Bundle:
    b = Bundle()
    for a in db.execute("SELECT * FROM submission_asset WHERE submission_id = ? ORDER BY id", (submission_id,)):
        p = json.loads(a["processed_json"] or "{}")
        if a["kind"] == "image":
            b.images.append({"n": len(b.images) + 1, "asset_id": a["id"], "filename": a["filename"], "path": f"{a['file_path']}.model.jpg",
                             "width": p.get("width"), "height": p.get("height")})
        else:
            frames = [{"id": f["id"], "idx": f["idx"], "t": f["timestamp_s"], "is_cut": bool(f["is_cut"]), "path": f["file_path"]}
                      for f in db.execute("SELECT * FROM video_frame WHERE asset_id = ? ORDER BY idx", (a["id"],))]
            b.videos.append({"n": len(b.videos) + 1, "asset_id": a["id"], "filename": a["filename"], "duration": a["duration_s"] or p.get("duration", 0),
                             "frames": frames, "transcript": p.get("transcript", []), "cuts": p.get("cuts", []), "shots": p.get("shots", []), "notes": p.get("notes", [])})
    return b
