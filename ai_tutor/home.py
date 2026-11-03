"""What the Home screen should show. Pure reads of the database."""
import sqlite3
from typing import Literal

HomeState = Literal["empty_library", "no_active_skill", "active_skill", "reviews_due"]


def home_state(db: sqlite3.Connection) -> dict:
    """First match wins: reviews due come first only when a skill is active, since Continue starts with the review (Flow 7)."""
    books = db.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    if books == 0:
        return {"state": "empty_library", "books": 0, "active_skill": None, "reviews_due": 0}

    active = db.execute(
        "SELECT s.id, s.name, (SELECT id FROM session WHERE skill_id = s.id AND ended_at IS NULL ORDER BY id DESC LIMIT 1) AS session_id "
        "FROM learner_skill ls JOIN skill s ON s.id = ls.skill_id WHERE ls.status = 'active' LIMIT 1"
    ).fetchone()
    due = db.execute("SELECT COUNT(*) FROM review_item WHERE due_at <= datetime('now')").fetchone()[0]

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
    }
