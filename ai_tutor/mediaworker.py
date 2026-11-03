"""Background processing of video clips: one at a time, so a heavy clip never blocks the screen, resumable after a restart."""
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from . import assets
from .config import Paths
from .store.conn import open_db

log = logging.getLogger(__name__)


class MediaWorker:
    def __init__(self, paths: Paths, *, transcriber: Callable[[Path], list[dict]] | None = None):
        self.paths, self.transcriber = paths, transcriber
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media")
        self._futures: dict[int, Future] = {}
        self._lock = threading.Lock()

    def submit(self, asset_id: int) -> None:
        with self._lock:
            self._futures[asset_id] = self._pool.submit(self._run, asset_id)

    def wait(self, asset_id: int, timeout: float | None = 60) -> None:
        """For tests."""
        f = self._futures.get(asset_id)
        if f is not None:
            f.result(timeout)

    def resume_interrupted(self, db) -> list[int]:
        """Clips left on 'processing' when the app closed are processed again from the start."""
        ids = [r[0] for r in db.execute("SELECT id FROM submission_asset WHERE kind = 'video' AND status = 'processing' ORDER BY id")]
        for i in ids:
            self.submit(i)
        return ids

    def _run(self, asset_id: int) -> None:
        db = open_db(self.paths.db)
        try:
            assets.process_video(db, self.paths, asset_id, transcriber=self.transcriber)
        finally:
            db.close()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
