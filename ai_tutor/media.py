"""Video and image handling that runs on this computer (SPEC §6.6): ffmpeg for frames and cuts, faster-whisper for the dialogue.

Nothing here touches the network. A clip becomes: a duration, the times where the shot changes, a capped set of keyframes, and a
timestamped transcript. Those four things (never the video itself) are what the model sees.
"""
import itertools
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 2 * 1024**3
MAX_CLIP_S = 180.0                 # about 3 minutes (SPEC §6.6); a clip exactly at the limit is accepted
CLIP_TOLERANCE_S = 0.5
FRAME_EVERY_S = 2.0
MAX_FRAMES = 20                    # frames per clip sent to the model; more are sampled evenly
SCENE_THRESHOLD = 0.3
MODEL_IMAGE_SIDE = 1568            # larger images are shrunk before they are sent
FRAME_WIDTH = 640
THUMB_SIDE = 160
MAX_IMAGES_PER_SUBMISSION = 6
MAX_VIDEOS_PER_SUBMISSION = 2


class MediaError(Exception):
    """A file could not be read or processed. The message says why, in words for the learner."""


def fmt_time(t: float) -> str:
    t = max(0, round(t))
    return f"{t // 60}:{t % 60:02d}"


def fmt_range(a: float, b: float) -> str:
    return fmt_time(a) if round(a) == round(b) else f"{fmt_time(a)}–{fmt_time(b)}"


def kind_of(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    return "image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT else None


# ---------- images

def prepare_image(src: Path, model_out: Path, thumb_out: Path) -> dict:
    """Check that the file really is an image, then write a copy sized for the model and a small thumbnail."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(src) as im:
            im.load()
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            big = im.copy()
            big.thumbnail((MODEL_IMAGE_SIDE, MODEL_IMAGE_SIDE))
            big.save(model_out, "JPEG", quality=85)
            im.thumbnail((THUMB_SIDE * 2, THUMB_SIDE * 2))
            im.save(thumb_out, "JPEG", quality=80)
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise MediaError("This file is not a picture I can read. Use a PNG, JPG, WEBP or GIF.") from e
    return {"width": w, "height": h, "model_file": model_out.name, "thumb_file": thumb_out.name, "downscaled": max(w, h) > MODEL_IMAGE_SIDE}


# ---------- ffmpeg

def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise MediaError(f"{args[0]} is not installed. Install ffmpeg to use video clips.") from e
    except subprocess.TimeoutExpired as e:
        raise MediaError("Reading the clip took too long and was stopped.") from e


@dataclass
class Probe:
    duration: float
    has_audio: bool
    width: int = 0
    height: int = 0


def probe(path: Path) -> Probe:
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=60)
    if r.returncode != 0:
        raise MediaError("I could not read this video. It may be damaged or in a format ffmpeg does not know.")
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("There is no video picture in this file.")
    dur = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if dur <= 0:
        raise MediaError("I could not tell how long this clip is.")
    return Probe(dur, any(s.get("codec_type") == "audio" for s in streams), int(video.get("width") or 0), int(video.get("height") or 0))


def too_long(duration: float) -> bool:
    return duration > MAX_CLIP_S + CLIP_TOLERANCE_S


def detect_cuts(path: Path, duration: float) -> list[float]:
    """Times (seconds) where the picture changes shot, from ffmpeg's scene score."""
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo", "-f", "null", "-"])
    if r.returncode != 0:
        raise MediaError("ffmpeg could not look for cuts in this clip.")
    times = sorted({round(float(m.group(1)), 2) for m in re.finditer(r"pts_time:([0-9.]+)", r.stderr)})
    return [t for t in times if 0.05 < t < duration - 0.05]


def shot_lengths(cuts: list[float], duration: float) -> list[float]:
    edges = [0.0, *cuts, duration]
    return [round(b - a, 2) for a, b in itertools.pairwise(edges)]


def frame_times(duration: float, cuts: list[float], cap: int = MAX_FRAMES) -> list[tuple[float, bool]]:
    """When to take a keyframe: every 2 seconds, plus just after each cut. Over the cap, sample evenly (first and last always kept)."""
    pts: dict[float, bool] = {}
    t = 0.0
    while t < duration - 0.05:
        pts[round(t, 2)] = False
        t += FRAME_EVERY_S
    for c in cuts:
        pts[round(min(c + 0.1, duration - 0.05), 2)] = True
    cut_ts = [t for t, is_cut in pts.items() if is_cut]
    ordered = sorted((t, c) for t, c in pts.items() if c or not any(0 < ct - t < 0.5 or 0 <= t - ct < 0.5 for ct in cut_ts))   # a cut frame replaces a regular one next to it
    if len(ordered) > cap:
        step = (len(ordered) - 1) / (cap - 1)
        ordered = [ordered[round(i * step)] for i in range(cap)]
    return ordered


def extract_frame(path: Path, t: float, out: Path) -> None:
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
              "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "4", str(out)], timeout=120)
    if r.returncode != 0 or not out.exists():
        raise MediaError(f"ffmpeg could not take a picture at {fmt_time(t)}.")


# ---------- speech

Transcriber = Callable[[Path], list[dict]]
_whisper = None


def whisper_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("faster_whisper") is not None


def transcribe(path: Path) -> list[dict]:
    """Dialogue with timestamps, from the local Whisper model. Loads once, uses the downloaded model without contacting the Hub."""
    global _whisper
    if not whisper_available():
        raise MediaError("Whisper is not installed, so the dialogue could not be written down.")
    if _whisper is None:
        from faster_whisper import WhisperModel
        try:
            _whisper = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True)
        except Exception:                                    # noqa: BLE001 - not downloaded yet: the one-time download
            _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    try:
        segments, _info = _whisper.transcribe(str(path), vad_filter=True)
        return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments if s.text.strip()]
    except Exception as e:
        raise MediaError(f"The speech model could not read the audio ({type(e).__name__}).") from e


@dataclass
class Processed:
    duration: float
    cuts: list[float]
    shots: list[float]
    frames: list[dict] = field(default_factory=list)       # {idx, t, is_cut, file}
    transcript: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def process_clip(path: Path, frames_dir: Path, *, report: Callable[[dict], None] = lambda steps: None, transcriber: Transcriber | None = None,
                 pr: Probe | None = None) -> Processed:
    """Frames, cuts and dialogue for one clip. `report` is called with the progress of each step as it moves. A missing audio track or
    missing Whisper only skips the transcript (with a note); an ffmpeg failure raises MediaError."""
    pr = pr or probe(path)
    steps = {"cuts": {"status": "running"}, "frames": {"status": "waiting"}, "transcript": {"status": "waiting"}}
    report(steps)
    cuts = detect_cuts(path, pr.duration)
    shots = shot_lengths(cuts, pr.duration)
    steps["cuts"] = {"status": "done", "count": len(cuts)}
    plan = frame_times(pr.duration, cuts)
    steps["frames"] = {"status": "running", "done": 0, "total": len(plan)}
    report(steps)
    frames_dir.mkdir(parents=True, exist_ok=True)
    out = Processed(pr.duration, cuts, shots)
    for i, (t, is_cut) in enumerate(plan, 1):
        f = frames_dir / f"{i:03d}.jpg"
        extract_frame(path, t, f)
        out.frames.append({"idx": i, "t": t, "is_cut": is_cut, "file": f.name})
        steps["frames"]["done"] = i
        report(steps)
    steps["frames"]["status"] = "done"
    if not pr.has_audio:
        steps["transcript"] = {"status": "skipped", "note": "No audio track."}
        out.notes.append("This clip has no audio, so there is no transcript.")
    else:
        steps["transcript"] = {"status": "running"}
        report(steps)
        try:
            out.transcript = (transcriber or transcribe)(path)
            steps["transcript"] = {"status": "done", "lines": len(out.transcript)}
        except MediaError as e:
            steps["transcript"] = {"status": "skipped", "note": str(e)}
            out.notes.append(f"{e} Feedback uses the frames and cuts only.")
    report(steps)
    return out


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
