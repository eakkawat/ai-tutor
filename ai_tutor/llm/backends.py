"""The model backend: any server that speaks the OpenAI chat API.

Adapted from book-to-skills `llm/backends.py`. Added: image parts for vision (TASKS_007), config from `app_settings.LlmConfig`.
"""
import re
from dataclasses import dataclass
from typing import Protocol

from ..app_settings import LlmConfig
from .errors import LLMError, LLMPausedError


@dataclass
class Completion:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None


class Backend(Protocol):
    def complete(self, system: str | None, user: str, *, json_mode: bool, images: list[str] | None = None) -> Completion: ...


_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Some servers leave the model's reasoning in the reply as <think>…</think>. It is not part of the answer."""
    return _THINK.sub("", text, count=1)


def user_content(user: str, images: list[str] | None):
    """Plain text, or text plus `image_url` parts (data URLs) for vision models."""
    if not images:
        return user
    return [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]


class OpenAICompatBackend:
    def __init__(self, cfg: LlmConfig, *, temperature: float = 0.2, max_tokens: int = 4096, thinking: bool = False,
                 timeout: float = 300, max_retries: int = 2, http_client=None):
        from openai import OpenAI

        self.cfg, self.temperature, self.max_tokens, self.thinking = cfg, temperature, max_tokens, thinking
        self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key or "none", timeout=timeout, max_retries=max_retries,
                              http_client=http_client)

    def complete(self, system: str | None, user: str, *, json_mode: bool, images: list[str] | None = None) -> Completion:
        import openai

        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user_content(user, images)}]
        kwargs: dict = {"model": self.cfg.model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        # Qwen thinking mode is a chat-template switch. Always send it so "off" really means off.
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": self.thinking}}
        try:
            r = self._client.chat.completions.create(**kwargs)
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError) as e:
            raise LLMPausedError(f"{type(e).__name__}: {e}") from e
        except openai.APIStatusError as e:
            if e.status_code >= 500:
                raise LLMPausedError(f"server error {e.status_code}: {e}") from e
            raise LLMError(f"{e.status_code}: {e}") from e
        choice = r.choices[0]
        return Completion(
            text=strip_thinking(choice.message.content or ""),
            prompt_tokens=getattr(r.usage, "prompt_tokens", None),
            completion_tokens=getattr(r.usage, "completion_tokens", None),
            finish_reason=choice.finish_reason,
        )
