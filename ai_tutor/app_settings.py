"""Machine-local settings saved by the setup screen. The LLM key lives here, never in `data/` and never in git.

Adapted from book-to-skills `app_settings.py`. File: `$AI_TUTOR_HOME/settings.json` (default `~/.config/ai-tutor/`), mode 600.
The LLM is any OpenAI-compatible server (OpenAI, a local server, a LAN server). Environment variables are the fallback:
`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel


def home() -> Path:
    return Path(os.environ.get("AI_TUTOR_HOME") or "~/.config/ai-tutor").expanduser()


def settings_path() -> Path:
    return home() / "settings.json"


class AppSettings(BaseModel):
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    skill_mode: str | None = None          # auto | manual


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    model: str
    api_key: str | None = None      # local servers often need none


def load() -> AppSettings:
    p = settings_path()
    return AppSettings.model_validate_json(p.read_text("utf-8")) if p.exists() else AppSettings()


def save(s: AppSettings) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s.model_dump(exclude_none=True), indent=2), encoding="utf-8")
    p.chmod(0o600)


def llm_config() -> LlmConfig | None:
    """Saved values first, then the environment. None until both the server URL and the model name are known."""
    s = load()
    base = (s.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")
    model = (s.llm_model or os.environ.get("LLM_MODEL") or "").strip()
    if not base or not model:
        return None
    return LlmConfig(base, model, s.llm_api_key or os.environ.get("LLM_API_KEY") or None)


def skill_mode() -> str:
    """"manual" (ask me first) unless the user chose "auto" (add skills straight to the map). Merges are always shown."""
    return "auto" if load().skill_mode == "auto" else "manual"
