"""What the Progress screen shows (F1, F4): hours toward 20 per skill, skills passed, recurring mistakes and the history of ratings."""
import json
import sqlite3
from datetime import datetime

from . import flow, hours

STATUS_TEXT = {"active": "active", "paused": "paused", "passed": "passed", "needs_practice": "needs practice", "not_started": "not started"}
RATING_TEXT = {"too_easy": "Too easy", "just_right": "Just right", "too_hard": "Too hard"}


def what_changed(r: sqlite3.Row | dict) -> str:
    """The rating's outcome in a few words for the history table."""
    lv = flow.LEVERS.get(r["lever_changed"]) if r["lever_changed"] else None
    if lv:
        label = flow.LABEL[lv.name]
        if lv.op == "add":
            return f"Added {label}"
        return f"Removed {label}" if lv.group == "support" else f"Took away {label}"
    return {"on_target": "No change", "productive_struggle": "Kept level (productive struggle)", "passed": "Skill passed, nothing to change",
            "at_limit": "No change (already at the limit)", "no_lever": "No change (nothing left to adjust)"}.get(r["classification"], "No change")


def build(db: sqlite3.Connection, now: datetime) -> dict:
    skills = []
    total = 0.0
    for r in db.execute("SELECT ls.skill_id, ls.status, s.name FROM learner_skill ls JOIN skill s ON s.id = ls.skill_id WHERE s.status != 'pending' ORDER BY ls.last_session_at DESC, s.name"):
        h = hours.skill_seconds(db, r["skill_id"], now) / 3600
        if h <= 0 and r["status"] == "not_started":
            continue
        total += h
        skills.append({"id": r["skill_id"], "name": r["name"], "status": r["status"], "status_text": STATUS_TEXT.get(r["status"], r["status"]), "hours": round(h, 2),
                       "target": hours.TARGET_HOURS, "bar": round(min(h / hours.TARGET_HOURS, 1.0), 4), "over": round(max(h - hours.TARGET_HOURS, 0.0), 2),
                       "success_rate": flow.success_rate(db, r["skill_id"])})
    passed = sum(s["status"] == "passed" for s in skills)
    rated = db.execute("SELECT rating_used FROM flow_rating WHERE rating_used IS NOT NULL").fetchall()
    answered = db.execute("SELECT result FROM review_result WHERE item_id IS NOT NULL").fetchall()

    mistakes = []
    for m in db.execute("SELECT m.*, s.name AS skill_name FROM mistake m JOIN skill s ON s.id = m.skill_id ORDER BY m.last_seen_at DESC, m.count DESC LIMIT 12"):
        last = db.execute("SELECT f.mistakes_json FROM feedback f JOIN submission su ON su.id = f.submission_id JOIN session se ON se.id = su.session_id "
                          "WHERE se.skill_id = ? ORDER BY f.id DESC LIMIT 1", (m["skill_id"],)).fetchone()
        still = bool(last) and any(x["kind"] == m["kind"] and x["tag"].lower() == m["tag"].lower() for x in json.loads(last["mistakes_json"] or "[]"))
        mistakes.append({"tag": m["tag"], "kind": m["kind"], "count": m["count"], "last_seen": m["last_seen_at"], "skill": m["skill_name"], "fixed": not still})
    mistakes.sort(key=lambda x: (x["fixed"], -x["count"]))

    history = []
    for r in db.execute("SELECT fr.*, s.name AS skill_name FROM flow_rating fr LEFT JOIN skill s ON s.id = fr.skill_id ORDER BY fr.id DESC LIMIT 20"):
        history.append({"id": r["id"], "task": f"Attempt {r['attempt']}" if r["attempt"] else "Task", "skill": r["skill_name"], "felt": RATING_TEXT.get(r["rating_used"] or "", "Not rated"),
                        "inferred": bool(r["inferred"]), "changed": what_changed(r), "at": r["created_at"]})
    return {
        "totals": {"practice_hours": round(total, 2), "skills_passed": passed, "just_right": [sum(x["rating_used"] == "just_right" for x in rated), len(rated)],
                   "reviews_right": [sum(x["result"] == "right" for x in answered), len(answered)]},
        "skills": skills, "mistakes": mistakes, "flow_history": history, "target": hours.TARGET_HOURS,
    }
