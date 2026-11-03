"""Choosing one skill (C2, C3): a short list for the project, then starting it. Never the whole map, never more than 10 skills.

The list: skills are pre-filtered by how close they are to the project text (embeddings), ranked by the language model with a reason
each, and checked in code (real ids only, no repeats, at most 10, a recommended skill that does not need anything first if there is one).
If the model cannot be reached, the list falls back to the similarity order and says so.
"""
import logging
import sqlite3

import numpy as np
from pydantic import BaseModel, Field

from . import projects
from . import skills as sk
from .embeddings import Embedder, EmbeddingUnavailable, chunk_document
from .llm.client import LLMClient
from .llm.errors import LLMError
from .llm.prompts import DATA_RULE, fence, load_prompt

log = logging.getLogger(__name__)

MIN_PICKS, MAX_PICKS = 5, 10
POOL = 14           # candidates shown to the model when the library is bigger than this


class Pick(BaseModel):
    skill_id: int
    reason: str = ""


class Recommendation(BaseModel):
    picks: list[Pick] = Field(default_factory=list)
    recommended_id: int | None = None


class PickerError(ValueError):
    pass


class ActiveSkillError(Exception):
    """Another skill is active; the caller must ask the learner to pause it."""

    def __init__(self, active: dict):
        super().__init__("Another skill is active.")
        self.active = active


def project_text(p: dict) -> str:
    return f"{p['name']}. {p['description']}. Good enough: {p['good_enough']}"


def unmet_prereqs(db: sqlite3.Connection, skill_id: int) -> list[dict]:
    """Prerequisites that are on the map and not passed yet."""
    return [{"id": r["id"], "name": r["name"]} for r in db.execute(
        "SELECT s.id, s.name FROM skill_prereq p JOIN skill s ON s.id = p.prereq_skill_id LEFT JOIN learner_skill ls ON ls.skill_id = s.id "
        "WHERE p.skill_id = ? AND s.status = 'active' AND COALESCE(ls.status, 'not_started') != 'passed'", (skill_id,))]


def candidates(db: sqlite3.Connection) -> tuple[list[dict], int]:
    """Skills that could be practised now: on the map, not passed, not the active one. Also returns how many are passed."""
    passed = db.execute("SELECT COUNT(*) FROM skill s JOIN learner_skill ls ON ls.skill_id = s.id WHERE s.status = 'active' AND ls.status = 'passed'").fetchone()[0]
    rows = db.execute(
        "SELECT s.id FROM skill s LEFT JOIN learner_skill ls ON ls.skill_id = s.id WHERE s.status = 'active' "
        "AND COALESCE(ls.status, 'not_started') NOT IN ('passed', 'active') ORDER BY s.name").fetchall()
    return [sk.skill_detail(db, r["id"]) for r in rows], passed


def _similarity_order(items: list[dict], project: dict, embedder: Embedder | None) -> list[dict]:
    if embedder is None or len(items) < 2:
        return items
    try:
        q = embedder.queries([project_text(project)])[0]
        docs = embedder.documents([chunk_document(s["name"], s["description"]) for s in items])
    except EmbeddingUnavailable:
        return items
    scores = [float(np.dot(q, d)) for d in docs]
    return [items[i] for i in sorted(range(len(items)), key=lambda i: scores[i], reverse=True)]


def _card(db: sqlite3.Connection, s: dict, minutes: int, *, why: str | None, recommended: bool) -> dict:
    return {
        "id": s["id"], "name": s["name"], "description": s["description"], "practice_type": s["practice_type"], "domain": s["domain"],
        "learning_status": s["learning_status"], "hours": s["hours"], "why": why, "recommended": recommended,
        "needs": unmet_prereqs(db, s["id"]), "principles": [{"principle": p["principle"], "citation": p["citation"], "chunk_id": p["chunk_id"]} for p in s["principles"]],
        "minutes": minutes,
    }


def shortlist(db: sqlite3.Connection, project_id: int, *, embedder: Embedder | None, llm: LLMClient | None) -> dict:
    p = projects.view(db, projects.get(db, project_id))
    items, passed = candidates(db)
    out = {"project": p, "skills": [], "ranked_by": "tutor", "note": None, "all_passed": False, "total_available": len(items)}
    if not items:
        out["all_passed"] = passed > 0
        out["note"] = ("You have passed every skill in your library. Review them, or add another book." if passed
                       else "There are no skills yet. Add a book in the Library first.")
        return out

    ordered = _similarity_order(items, p, embedder)[:POOL]
    by_id = {s["id"]: s for s in ordered}
    want = min(len(ordered), MAX_PICKS)
    picks: list[Pick] = []
    recommended_id = None
    if llm is not None:
        prompt = load_prompt("skill_recommendation")
        lines = []
        for s in ordered:
            needs = ", ".join(x["name"] for x in unmet_prereqs(db, s["id"])) or "nothing"
            lines.append(f"- id {s['id']}: {s['name']}: {s['description']} (needs first: {needs})")
        try:
            rec = llm.json(Recommendation, prompt.render(rule=DATA_RULE, project=fence("project", project_text(p)), skills=fence("skills", "\n".join(lines)),
                                                         min_picks=min(MIN_PICKS, len(ordered)), max_picks=MAX_PICKS),
                           prompt_version=prompt.version, job="skill_recommendation")
            seen: set[int] = set()
            for pk in rec.picks:
                if pk.skill_id in by_id and pk.skill_id not in seen:
                    seen.add(pk.skill_id)
                    picks.append(pk)
            recommended_id = rec.recommended_id
        except LLMError as e:
            log.warning("recommendation fell back to similarity order: %s", e)
            out["ranked_by"] = "similarity"
    else:
        out["ranked_by"] = "similarity"

    # Fill up from the similarity order when the model gave too few, so the learner always sees a useful list.
    need = min(want, MIN_PICKS) if picks else want
    if len(picks) < need:
        have = {pk.skill_id for pk in picks}
        picks += [Pick(skill_id=s["id"]) for s in ordered if s["id"] not in have][: need - len(picks)]
    picks = picks[:MAX_PICKS]

    cards = [_card(db, by_id[pk.skill_id], p["minutes_per_session"], why=pk.reason.strip() or None, recommended=False) for pk in picks]
    # The skill to start with: the model's choice if it needs nothing first; else the first pick that needs nothing; else the first pick.
    ids = [c["id"] for c in cards]
    ready = [c for c in cards if not c["needs"]]
    chosen = recommended_id if recommended_id in ids and not next(c for c in cards if c["id"] == recommended_id)["needs"] else (ready[0]["id"] if ready else ids[0])
    for c in cards:
        c["recommended"] = c["id"] == chosen
    cards.sort(key=lambda c: not c["recommended"])          # the recommended one first, the rest keep their order
    out["skills"] = cards
    if len(items) < MIN_PICKS:
        out["note"] = f"Only {len(items)} {'skill' if len(items) == 1 else 'skills'} in your library so far. Add more books to see more choices."
    return out


# ---------- starting a skill (one at a time)

def active_skill(db: sqlite3.Connection) -> dict | None:
    r = db.execute("SELECT ls.skill_id, ls.hours_total, s.name FROM learner_skill ls JOIN skill s ON s.id = ls.skill_id WHERE ls.status = 'active'").fetchone()
    if r is None:
        return None
    sess = db.execute("SELECT id, phase, project_id FROM session WHERE skill_id = ? AND ended_at IS NULL ORDER BY id DESC LIMIT 1", (r["skill_id"],)).fetchone()
    attempts = db.execute("SELECT COUNT(*) FROM submission su JOIN session se ON se.id = su.session_id WHERE se.skill_id = ?", (r["skill_id"],)).fetchone()[0]
    return {"id": r["skill_id"], "name": r["name"], "hours": round(r["hours_total"], 1), "attempt_next": attempts + 1,
            "session_id": sess["id"] if sess else None, "phase": sess["phase"] if sess else None}


def start_skill(db: sqlite3.Connection, project_id: int, skill_id: int, *, pause_current: bool = False) -> dict:
    """Make `skill_id` the one active skill and give it a session at the right phase. Another active skill must be paused first."""
    projects.get(db, project_id)
    s = db.execute("SELECT id, status FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if s is None or s["status"] != "active":
        raise PickerError("This skill is not on your skill map.")
    mine = db.execute("SELECT status FROM learner_skill WHERE skill_id = ?", (skill_id,)).fetchone()
    if mine and mine["status"] == "passed":
        raise PickerError("You have already passed this skill. Use Review to keep it fresh.")
    current = active_skill(db)
    if current and current["id"] != skill_id:
        if not pause_current:
            raise ActiveSkillError(current)
        db.execute("UPDATE learner_skill SET status = 'paused' WHERE skill_id = ?", (current["id"],))     # its session, hours and phase stay as they are
    db.execute("INSERT INTO learner_skill(skill_id, status) VALUES (?, 'active') ON CONFLICT(skill_id) DO UPDATE SET status = 'active'", (skill_id,))
    sess = db.execute("SELECT id, phase FROM session WHERE skill_id = ? AND ended_at IS NULL ORDER BY id DESC LIMIT 1", (skill_id,)).fetchone()
    if sess is None:
        sid = db.execute("INSERT INTO session(project_id, skill_id, phase) VALUES (?,?, 'diagnose')", (project_id, skill_id)).lastrowid
        phase = "diagnose"
    else:
        sid, phase = sess["id"], sess["phase"]
    projects.activate(db, project_id)
    db.commit()
    return {"session_id": sid, "skill_id": skill_id, "phase": phase}
