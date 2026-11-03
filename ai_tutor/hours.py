"""Practice hours per skill (F1): the sum over the skill's sessions of the time on submitted tasks plus the time on the task in progress.

Worked out from the session rows every time, never added to a running total, so it cannot be counted twice. Only the task timer counts:
paused time does not, overtime does, and a timer left running by a closed app counts only up to its last sign of life.
"""
import sqlite3
from datetime import datetime, timedelta

GRACE_S = 90                 # same grace as the session timer: a running timer counts at most this long past the last heartbeat
TARGET_HOURS = 20


def _parse(s: str | None) -> datetime | None:
    from datetime import UTC
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) if s else None


def skill_seconds(db: sqlite3.Connection, skill_id: int, now: datetime) -> float:
    total = 0.0
    for r in db.execute("SELECT minutes, timer_elapsed_s, timer_since, timer_seen FROM session WHERE skill_id = ?", (skill_id,)):
        total += r["minutes"] * 60 + r["timer_elapsed_s"]
        since = _parse(r["timer_since"])
        if since:
            seen = _parse(r["timer_seen"]) or since
            total += max(0.0, (min(now, seen + timedelta(seconds=GRACE_S)) - since).total_seconds())
    return total


def recompute(db: sqlite3.Connection, skill_id: int, now: datetime) -> float:
    """Store and return the skill's hours."""
    hours = skill_seconds(db, skill_id, now) / 3600
    db.execute("UPDATE learner_skill SET hours_total = ? WHERE skill_id = ?", (hours, skill_id))
    db.commit()
    return hours


def settle_stale_timers(db: sqlite3.Connection, now: datetime) -> int:
    """After the app was closed: any timer still marked running with no sign of life is stopped at its last heartbeat, and the hours
    of every skill are worked out again. Returns how many timers were settled."""
    n = 0
    for r in db.execute("SELECT id, timer_since, timer_seen FROM session WHERE timer_since IS NOT NULL").fetchall():
        since = _parse(r["timer_since"])
        seen = _parse(r["timer_seen"]) or since
        if now - seen > timedelta(seconds=GRACE_S):
            kept = max(0.0, (seen + timedelta(seconds=GRACE_S) - since).total_seconds())
            db.execute("UPDATE session SET timer_elapsed_s = timer_elapsed_s + ?, timer_since = NULL WHERE id = ?", (kept, r["id"]))
            n += 1
    db.commit()
    for (sid,) in db.execute("SELECT skill_id FROM learner_skill").fetchall():
        recompute(db, sid, now)
    return n


def stop_running_timers(db: sqlite3.Connection, skill_id: int) -> None:
    """The learner is leaving this skill (it is being paused): its running timer stops at the last sign of life, and the time so far is kept."""
    for r in db.execute("SELECT id, timer_since, timer_seen FROM session WHERE skill_id = ? AND timer_since IS NOT NULL", (skill_id,)).fetchall():
        since = _parse(r["timer_since"])
        seen = _parse(r["timer_seen"]) or since
        db.execute("UPDATE session SET timer_elapsed_s = timer_elapsed_s + ?, timer_since = NULL WHERE id = ?", (max(0.0, (seen - since).total_seconds()), r["id"]))
    db.commit()
