"""Local embeddings (EmbeddingGemma through sentence-transformers, on the CPU). SPEC §10 prefers a local model.

Adapted from book-to-skills `llm/embeddings.py`: the model loading, idle unload and float32 rule are copied. Chunks are embedded as
*documents* shaped `title: <chapter> | text: <chunk>`, searches as *queries*. Rules from the model card: bfloat16 or float32 only
(never float16).
"""
import hashlib
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np

DIM = 768
MODEL = "google/embeddinggemma-2"
IDLE_UNLOAD_S = 600


class EmbeddingUnavailable(RuntimeError):
    """No embedding model can be loaded. Keyword search still works without it."""


class Embedder(Protocol):
    def queries(self, texts: list[str]) -> np.ndarray: ...
    def documents(self, texts: list[str]) -> np.ndarray: ...


def chunk_document(title: str | None, text: str) -> str:
    return f"title: {(title or 'none').strip()} | text: {text}"


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def cosine_from_distance(d: float) -> float:
    """sqlite-vec returns L2 distance; for unit vectors cos = 1 - d^2 / 2."""
    return 1 - d * d / 2


class GemmaEmbedder:
    """Loads lazily (about 8 s, about 2 GB of memory) and lets go after ten idle minutes."""

    def __init__(self, model: str = MODEL, device: str = "cpu"):
        self.model_name, self.device = model, device
        self._model = None
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    import torch
                    from sentence_transformers import SentenceTransformer
                except ImportError as e:
                    raise EmbeddingUnavailable("The embedding libraries are not installed. Run: uv sync --extra embed") from e
                kw = {"device": self.device, "model_kwargs": {"torch_dtype": torch.float32},
                      "config_kwargs": {"audio_config": None}}      # text only: leaves out the 300M audio encoder
                try:
                    try:                                            # local-only: use the cached model without contacting the Hub
                        self._model = SentenceTransformer(self.model_name, local_files_only=True, **kw)
                    except Exception:                               # noqa: BLE001 - not cached yet: the one-time download
                        self._model = SentenceTransformer(self.model_name, **kw)
                except Exception as e:
                    raise EmbeddingUnavailable(f"The embedding model {self.model_name} could not be loaded: {e}") from e
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(IDLE_UNLOAD_S, self.unload)
            self._timer.daemon = True
            self._timer.start()
            return self._model

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def _encode(self, texts: list[str], prompt: str | None) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        model = self._load()
        with self._lock:
            v = model.encode(texts, prompt_name=prompt, normalize_embeddings=True, convert_to_numpy=True)
        v = np.asarray(v, dtype=np.float32)
        if not np.isfinite(v).all():
            raise EmbeddingUnavailable("The embedding model returned NaN. It must run in float32 or bfloat16, never float16.")
        return v

    def queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "SearchQuery")

    def documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, None)           # documents already carry their own `title: ... | text: ...` prefix


_factory: Callable[[object], Embedder] | None = None
_cache: dict[tuple[str, str], Embedder] = {}


def set_factory(f: Callable[[], Embedder] | None) -> None:
    """Tests (and anyone who wants another model) replace how the embedder is built."""
    global _factory
    _factory = f
    _cache.clear()


def get_embedder(model: str = MODEL, device: str = "cpu") -> Embedder:
    if _factory is not None:
        return _factory()
    key = (model, device)
    if key not in _cache:
        _cache[key] = GemmaEmbedder(*key)
    return _cache[key]
