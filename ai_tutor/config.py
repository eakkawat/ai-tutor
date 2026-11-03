"""Where things live: the data folder (books, submissions, frames, app.db, feedback.log) and machine-local settings."""
import os
from pathlib import Path

from pydantic import BaseModel


def data_dir() -> Path:
    return Path(os.environ.get("AI_TUTOR_DATA") or "data").expanduser().resolve()


class Paths(BaseModel):
    root: Path

    @property
    def library(self) -> Path: return self.root / "library"
    @property
    def submissions(self) -> Path: return self.root / "submissions"
    @property
    def frames(self) -> Path: return self.root / "frames"
    @property
    def db(self) -> Path: return self.root / "app.db"
    @property
    def feedback_log(self) -> Path: return self.root / "feedback.log"

    def ensure(self) -> "Paths":
        for p in (self.library, self.submissions, self.frames):
            p.mkdir(parents=True, exist_ok=True)
        return self


def paths() -> Paths:
    return Paths(root=data_dir()).ensure()
