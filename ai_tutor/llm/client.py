"""One client for every job: validate JSON against a Pydantic model, retry once with the error, log every call.

Adapted from book-to-skills `llm/client.py`. Logging goes to the `llm_call` table through a callable, so tests need no database.
"""
import json
import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..app_settings import LlmConfig, llm_config
from .backends import Backend, Completion, OpenAICompatBackend
from .errors import LLMError, LLMOutputError, LLMPausedError

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger(__name__)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

CallLog = Callable[[dict], None]


def extract_json(text: str) -> str:
    """Models often wrap JSON in ```json fences or add a sentence around it. Return just the JSON text."""
    m = _FENCE.match(text)
    if m:
        return m.group(1)
    text = text.strip()
    if text[:1] in "{[":
        return text
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return text
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start:end + 1] if end > start else text


class LLMClient:
    def __init__(self, job: str, backend: Backend, *, model: str, call_log: CallLog | None = None):
        self.job, self.backend, self.model, self.call_log = job, backend, model, call_log

    @classmethod
    def for_job(cls, job: str, *, cfg: LlmConfig | None = None, backend: Backend | None = None, call_log: CallLog | None = None,
                **backend_opts) -> "LLMClient":
        cfg = cfg or llm_config()
        if cfg is None and backend is None:
            raise LLMError("The language model is not set up. Open Setup and enter the server URL and model name.")
        return cls(job, backend or OpenAICompatBackend(cfg, **backend_opts), model=cfg.model if cfg else "test", call_log=call_log)

    def _call(self, system, user, *, json_mode, prompt_version, images, source_id, job=None) -> Completion:
        t0 = time.monotonic()
        row = {"job": job or self.job, "model": self.model, "prompt_version": prompt_version, "source_id": source_id}
        try:
            c = self.backend.complete(system, user, json_mode=json_mode, images=images)
        except LLMError as e:
            log.warning("model call failed", extra={**row, "error": str(e)})
            self._record({**row, "ok": 0, "error": str(e), "seconds": round(time.monotonic() - t0, 2)})
            raise
        self._record({**row, "ok": 1, "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens,
                      "seconds": round(time.monotonic() - t0, 2), "raw_response": c.text})
        return c

    def _record(self, row: dict) -> None:
        if self.call_log:
            self.call_log(row)

    def text(self, user: str, *, system: str | None = None, prompt_version: str = "0", images: list[str] | None = None,
             source_id: int | None = None, job: str | None = None) -> str:
        return self._call(system, user, json_mode=False, prompt_version=prompt_version, images=images, source_id=source_id, job=job).text

    def json(self, schema: type[T], user: str, *, system: str | None = None, prompt_version: str = "0",
             images: list[str] | None = None, source_id: int | None = None, job: str | None = None) -> T:
        """Ask for JSON that fits `schema`. On a bad reply, retry once with the error; then raise LLMOutputError."""
        instruction = ("Reply with a single JSON object that matches this JSON Schema. No prose, no code fences.\n"
                       + json.dumps(schema.model_json_schema()))
        system = f"{system}\n\n{instruction}" if system else instruction
        prompt = user
        raw = ""
        for attempt in (1, 2):
            c = self._call(system, prompt, json_mode=True, prompt_version=prompt_version, images=images, source_id=source_id, job=job)
            raw = c.text
            try:
                if c.finish_reason == "length":
                    raise ValueError("the reply was cut off at the token limit")
                return schema.model_validate_json(extract_json(raw))
            except (ValidationError, ValueError) as e:
                if attempt == 2:
                    raise LLMOutputError(f"job '{job or self.job}': invalid JSON after retry: {e}", raw) from e
                prompt = (f"{user}\n\nYour previous reply was rejected:\n{e}\n"
                          "Reply again with only the corrected JSON object.")
        raise AssertionError("unreachable")


__all__ = ["LLMClient", "LLMError", "LLMOutputError", "LLMPausedError", "extract_json"]
