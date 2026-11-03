"""What the Home screen should show. Pure reads of the database."""
import sqlite3
from datetime import datetime
from typing import Literal

from . import review

HomeState = Literal["empty_library", "no_active_skill", "active_skill", "reviews_due"]


def home_state(db: sqlite3.Connection, now: datetime) -> dict:
    """First match wins: reviews due come first only when a skill is active, since Continue starts with the review (Flow 7)."""
    books = db.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    if books == 0:
        return {"state": "empty_library", "books": 0, "active_skill": None, "reviews_due": 0, "review_first": False}

    active = db.execute(
        "SELECT s.id, s.name, (SELECT id FROM session WHERE skill_id = s.id AND ended_at IS NULL ORDER BY id DESC LIMIT 1) AS session_id "
        "FROM learner_skill ls JOIN skill s ON s.id = ls.skill_id WHERE ls.status = 'active' LIMIT 1"
    ).fetchone()
    due = review.due_count(db, now)

    if active is None:
        state: HomeState = "no_active_skill"
    elif due:
        state = "reviews_due"
    else:
        state = "active_skill"
    return {
        "state": state,
        "books": books,
        "active_skill": {"id": active["id"], "name": active["name"], "session_id": active["session_id"]} if active else None,
        "reviews_due": due,
        "review_first": bool(active) and review.continue_waiting(db, now),          # Continue opens with two questions
    }
