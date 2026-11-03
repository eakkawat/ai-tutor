"""LLM errors. Copied from book-to-skills `llm/errors.py` (names kept)."""


class LLMError(RuntimeError):
    """The server refused the request (bad model name, bad key, bad request). Retrying will not help."""


class LLMPausedError(LLMError):
    """The server is down, busy or timing out. Work can resume later."""


class LLMOutputError(LLMError):
    """The reply was not valid JSON for the schema, even after one retry. `raw` holds the last reply."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw
