"""Startup dependency check (A1): language model server, ffmpeg, ffprobe, Whisper. Each item is ready or missing, with a one-line fix.

Text learning needs only the language model. ffmpeg, ffprobe and Whisper only gate media upload (`media_enabled`, see DECISIONS.md D-002).
Probes are injectable so tests need no network and no installed tools.
"""
import importlib.util
import os
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from . import app_settings

Status = Literal["ready", "missing", "invalid", "unreachable"]
KeyVerdict = Literal["ok", "invalid", "unreachable"]
LLM_LABEL = "Language model"
LLM_PURPOSE = "Teaching, quizzes and feedback (any OpenAI-compatible server)"


@dataclass
class Check:
    id: str
    label: str
    purpose: str
    required: bool
    status: Status
    fix: str | None = None
    detail: str | None = None


def verify_llm(cfg: app_settings.LlmConfig) -> KeyVerdict:
    """One cheap call to the configured server (`GET /models`). The only network use in this module."""
    import openai

    try:
        openai.OpenAI(base_url=cfg.base_url, api_key=cfg.api_key or "none", max_retries=0, timeout=10).models.list()
    except (openai.AuthenticationError, openai.PermissionDeniedError):
        return "invalid"
    except openai.NotFoundError:
        return "ok"                      # reachable, but the server has no model list endpoint
    except (openai.APIConnectionError, openai.APIStatusError):
        return "unreachable"
    return "ok"


def whisper_model_cached() -> bool:
    """faster-whisper downloads its model from Hugging Face on first use. Look for one in the local cache."""
    hub = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or "~/.cache/huggingface").expanduser() / "hub")
    return any(hub.glob("models--*faster-whisper*")) if hub.exists() else False


def check_dependencies(
    *,
    verify: bool = False,
    llm_config: Callable[[], app_settings.LlmConfig | None] = app_settings.llm_config,
    verify_llm: Callable[[app_settings.LlmConfig], KeyVerdict] = verify_llm,
    which: Callable[[str], str | None] = shutil.which,
    has_module: Callable[[str], bool] = lambda name: importlib.util.find_spec(name) is not None,
    model_cached: Callable[[], bool] = whisper_model_cached,
) -> list[Check]:
    cfg = llm_config()
    if cfg is None:
        llm = Check("llm", LLM_LABEL, LLM_PURPOSE, True, "missing", "Enter the server URL and model name below, or set LLM_BASE_URL and LLM_MODEL.")
    else:
        verdict = verify_llm(cfg) if verify else "ok"
        llm = {
            "ok": Check("llm", LLM_LABEL, LLM_PURPOSE, True, "ready"),
            "invalid": Check("llm", LLM_LABEL, LLM_PURPOSE, True, "invalid", "The server rejected the API key. Enter it again below."),
            "unreachable": Check("llm", LLM_LABEL, LLM_PURPOSE, True, "unreachable",
                                 "Could not reach the server. Check the URL and your connection; the rest of the app still opens.",
                                 "Settings saved but not verified."),
        }[verdict]

    ffmpeg = Check("ffmpeg", "ffmpeg", "Pulls frames and cuts from video clips", False,
                   "ready" if which("ffmpeg") else "missing", None if which("ffmpeg") else "sudo apt install ffmpeg")
    ffprobe = Check("ffprobe", "ffprobe", "Reads clip length", False,
                    "ready" if which("ffprobe") else "missing", None if which("ffprobe") else "sudo apt install ffmpeg")

    if not has_module("faster_whisper"):
        whisper = Check("whisper", "Whisper", "Transcribes dialogue in video clips", False, "missing", "uv sync --extra media")
    elif not model_cached():
        whisper = Check("whisper", "Whisper", "Transcribes dialogue in video clips", False, "missing",
                        'uv run python -c "from faster_whisper import WhisperModel; WhisperModel(\'small\')"',
                        "Installed, but the speech model is not downloaded yet. Run this once.")
    else:
        whisper = Check("whisper", "Whisper", "Transcribes dialogue in video clips", False, "ready")

    return [llm, ffmpeg, ffprobe, whisper]


def summarize(checks: list[Check]) -> dict:
    """What the app does with the result: block on setup, or open with or without media."""
    by_id = {c.id: c for c in checks}
    llm_ok = by_id["llm"].status in ("ready", "unreachable")      # offline must not lock the user out of non-LLM screens
    media = all(by_id[i].status == "ready" for i in ("ffmpeg", "ffprobe", "whisper"))
    return {
        "checks": [asdict(c) for c in checks],
        "can_continue": llm_ok,
        "media_enabled": media,
        "media_note": None if media else "Image and video upload are off until ffmpeg, ffprobe and Whisper are installed. Text practice still works.",
    }
