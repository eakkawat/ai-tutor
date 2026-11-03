"""Attaching pictures and clips to practice work, and serving them back to the screen."""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from .. import app_settings, assets, media, setup_check

router = APIRouter(prefix="/api")

STATUS = {"too_big": 413, "unsupported": 415, "too_long": 422, "too_many": 409, "gone": 404, "attached": 409}
MEDIA_OFF = "Picture and clip upload are off until ffmpeg, ffprobe and Whisper are installed. Text practice still works."


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def _media_enabled(request: Request) -> bool:
    kw = getattr(request.app.state, "check_kwargs", {})
    return setup_check.summarize(setup_check.check_dependencies(**kw))["media_enabled"]


def _fail(e: assets.AssetError) -> HTTPException:
    return HTTPException(STATUS.get(e.code, 400), {"message": str(e), "code": e.code})


@router.post("/sessions/{session_id}/assets")
async def upload(session_id: int, request: Request, file: UploadFile = File(...)) -> dict:
    db, paths = _db(request), request.app.state.paths
    s = db.execute("SELECT phase, ended_at FROM session WHERE id = ?", (session_id,)).fetchone()
    if s is None:
        raise HTTPException(404, {"message": "This session no longer exists."})
    if s["phase"] not in ("practice", "revise") or s["ended_at"]:
        raise HTTPException(409, {"message": "Add pictures and clips while you are working on a task.", "code": "wrong_phase"})
    if not _media_enabled(request):
        raise HTTPException(409, {"message": MEDIA_OFF, "code": "media_off"})
    name = file.filename or "file"
    kind = media.kind_of(name)
    if kind is None:
        raise HTTPException(415, {"message": "I can read PNG, JPG, WEBP and GIF pictures, and MP4, MOV, WEBM and MKV clips.", "code": "unsupported"})
    try:
        if kind == "image":
            data = await file.read(media.MAX_IMAGE_BYTES + 1)
            aid = assets.add_image(db, paths, session_id, name, data)
        else:
            dest = assets.reserve_video_path(paths, session_id, name)
            size = 0
            with dest.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > media.MAX_VIDEO_BYTES:
                        break
                    out.write(chunk)
            aid = assets.add_video(db, paths, session_id, name, dest)
            request.app.state.media_worker.submit(aid)
    except assets.AssetError as e:
        raise _fail(e) from e
    return assets.view(db, db.execute("SELECT * FROM submission_asset WHERE id = ?", (aid,)).fetchone())


@router.delete("/assets/{asset_id}")
def remove(asset_id: int, request: Request) -> dict:
    try:
        assets.remove(_db(request), request.app.state.paths, asset_id)
    except assets.AssetError as e:
        raise _fail(e) from e
    return {"ok": True}


@router.post("/assets/{asset_id}/retry")
def retry(asset_id: int, request: Request) -> dict:
    db = _db(request)
    a = db.execute("SELECT * FROM submission_asset WHERE id = ? AND kind = 'video'", (asset_id,)).fetchone()
    if a is None:
        raise HTTPException(404, {"message": "This attachment no longer exists."})
    if a["status"] != "error" or a["submission_id"] is not None:
        raise HTTPException(409, {"message": "This clip does not need another try."})
    db.execute("UPDATE submission_asset SET status = 'processing', error = NULL WHERE id = ?", (asset_id,))
    db.commit()
    request.app.state.media_worker.submit(asset_id)
    return {"ok": True}


def _serve(request: Request, path: Path, media_type: str) -> FileResponse:
    root = request.app.state.paths.root.resolve()
    p = path.resolve()
    if root not in p.parents or not p.is_file():                  # only files inside the data folder, never anything else on disk
        raise HTTPException(404, {"message": "This file is gone."})
    return FileResponse(p, media_type=media_type)


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: int, request: Request, variant: str = "model") -> FileResponse:
    a = _db(request).execute("SELECT * FROM submission_asset WHERE id = ? AND kind = 'image'", (asset_id,)).fetchone()
    if a is None:
        raise HTTPException(404, {"message": "This picture no longer exists."})
    suffix = {"thumb": ".thumb.jpg", "model": ".model.jpg"}.get(variant)
    return _serve(request, Path(a["file_path"] + suffix) if suffix else Path(a["file_path"]), "image/jpeg" if suffix else (a["mime"] or "image/png"))


@router.get("/frames/{frame_id}")
def frame_file(frame_id: int, request: Request) -> FileResponse:
    f = _db(request).execute("SELECT * FROM video_frame WHERE id = ?", (frame_id,)).fetchone()
    if f is None:
        raise HTTPException(404, {"message": "This frame no longer exists."})
    return _serve(request, Path(f["file_path"]), "image/jpeg")


@router.get("/setup/vision")
def vision() -> dict:
    """Whether the configured model can read pictures (true, false, or null when the server does not say)."""
    return {"vision": setup_check.model_supports_images(app_settings.llm_config())}
