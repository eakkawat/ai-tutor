"""Small real pictures and clips for the media tests, made with PIL and ffmpeg (no network, no stored binaries)."""
import subprocess
from pathlib import Path

from PIL import Image

COLORS = {"red": (200, 30, 30), "blue": (30, 30, 200), "green": (30, 160, 30)}


def make_png(path: Path, size=(320, 240), color="red") -> Path:
    Image.new("RGB", size, COLORS[color]).save(path)
    return path


def make_video(path: Path, shots=(("red", 2), ("blue", 3), ("green", 2)), *, audio=False, fps=10, size="160x120") -> Path:
    """A clip of solid-colour shots: the shot changes are hard cuts, so the cut times are exactly where the colours change."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for c, d in shots:
        cmd += ["-f", "lavfi", "-i", f"color=c={c}:s={size}:d={d}:r={fps}"]
    total = sum(d for _, d in shots)
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={total}"]
    n = len(shots)
    graph = "".join(f"[{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    cmd += ["-filter_complex", graph, "-map", "[v]"]
    if audio:
        cmd += ["-map", f"{n}:a", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


def make_long(path: Path, seconds: int) -> Path:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=64x48:d={seconds}:r=1",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path
