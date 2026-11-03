"""Background runner for the book pipeline: one job at a time (the embedder is CPU-heavy), cancellable, resumable after a restart."""
import logging
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .embeddings import Embedder
from .llm.client import LLMClient
from .pipeline.library import Run
from .store.conn import open_db

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, db_path: Path, *, embedder_factory: Callable[[], Embedder | None], llm_factory: Callable[[int], LLMClient | None]):
        self.db_path, self.embedder_factory, self.llm_factory = db_path, embedder_factory, llm_factory
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
        self._cancel: dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        self._futures: dict[int, object] = {}

    def submit(self, source_id: int, only: str | None = None) -> None:
        with self._lock:
            ev = self._cancel[source_id] = threading.Event()
            self._futures[source_id] = self._pool.submit(self._run, source_id, ev, only)

    def cancel(self, source_id: int) -> bool:
        ev = self._cancel.get(source_id)
        if ev is None:
            return False
        ev.set()
        return True

    def wait(self, source_id: int, timeout: float | None = None) -> None:
        """For tests."""
        f = self._futures.get(source_id)
        if f is not None:
            f.result(timeout)

    def resume_interrupted(self, db: sqlite3.Connection) -> list[int]:
        """Books left on 'processing' when the app closed continue from where they were (embedding skips finished passages)."""
        ids = [r[0] for r in db.execute("SELECT id FROM source WHERE status = 'processing' ORDER BY id")]
        for i in ids:
            self.submit(i)
        return ids

    def _run(self, source_id: int, ev: threading.Event, only: str | None = None) -> None:
        db = open_db(self.db_path)
        try:
            db.execute("UPDATE source SET status = 'processing', message = 'Starting…' WHERE id = ?", (source_id,))
            db.commit()
            call_log = self._call_logger(db)
            Run(db, source_id, embedder=self.embedder_factory(), llm_factory=lambda: self.llm_factory_for(source_id, call_log),
                is_cancelled=ev.is_set).run(only)
        finally:
            db.close()
            self._cancel.pop(source_id, None)

    def llm_factory_for(self, source_id: int, call_log) -> LLMClient:
        client = self.llm_factory(source_id)
        if client is None:
            from .llm.errors import LLMError
            raise LLMError("The language model is not set up.")
        client.call_log = call_log
        return client

    @staticmethod
    def _call_logger(db: sqlite3.Connection):
        def log_call(row: dict) -> None:
            db.execute(
                "INSERT INTO llm_call(job, model, prompt_version, source_id, ok, error, prompt_tokens, completion_tokens, seconds, raw_response) "
                "VALUES (:job,:model,:prompt_version,:source_id,:ok,:error,:prompt_tokens,:completion_tokens,:seconds,:raw_response)",
                {"error": None, "prompt_tokens": None, "completion_tokens": None, "raw_response": None, **row})
            db.commit()
        return log_call

    def shutdown(self) -> None:
        for ev in self._cancel.values():
            ev.set()
        self._pool.shutdown(wait=True, cancel_futures=True)
