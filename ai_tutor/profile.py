"""The learner profile (SPEC §6.4): what the app knows about how this learner learns, shown to the learner and read before every lesson.

Notes come from three places: the app counts things (which lever moved the learner to "just right", what task length fits, what kind of task
bores them), the model writes a few preference notes from a finished session (only ones the counted facts support), and the learner writes their
own. The learner always has the last word: an edited or user-written note is never overwritten, and a removed one is never learned again.
Notes shape how the tutor teaches; they never change what it takes to pass.
"""
import re
import sqlite3
import statistics
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from . import flow
from .llm.client import LLMClient
from .llm.errors import LLMError
from .llm.prompts import DATA_RULE, fence, load_prompt

SECTIONS = {"understand": "What helps me understand", "flow": "Keeping me in the flow zone"}
TOPICS = {"explanation_style", "examples_vs_rules", "explanation_length", "pacing", "task_type", "session_length", "other"}
MAX_NOTE_WORDS = 25
MAX_NOTE_CHARS = 300
MAX_LLM_NOTES = 3
MAX_NOTES_IN_PROMPT = 12
MAX_PROFILE_CHARS = 1600
NOTHING_YET = "(nothing learned yet)"
# A learned note may not be about passing: the checklist alone decides that.
BANNED = re.compile(r"\b(pass|passes|passing|passed|checklist|lower the bar|skip|skipping|shortcut)\b", re.IGNORECASE)


class ProfileError(ValueError):
    """A change to the profile that cannot be made. The message is shown as is."""


class NoteOut(BaseModel):
    section: str
    topic: str = "other"
    text: str
    evidence: str = ""


class NotesOut(BaseModel):
    notes: list[NoteOut] = Field(default_factory=list)


def stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _view(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "text": r["value"], "section": r["section"], "topic": r["topic"], "evidence": r["evidence"], "source": r["source"],
            "edited": bool(r["edited"]), "updated_at": r["updated_at"]}


def list_notes(db: sqlite3.Connection) -> list[dict]:
    return [_view(r) for r in db.execute("SELECT * FROM profile_note WHERE removed = 0 ORDER BY updated_at DESC, id DESC")]


def sections(db: sqlite3.Connection) -> list[dict]:
    notes = list_notes(db)
    return [{"key": k, "title": t, "notes": [n for n in notes if n["section"] == k]} for k, t in SECTIONS.items()]


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        raise ProfileError("Write the note first.")
    if len(text) > MAX_NOTE_CHARS:
        raise ProfileError(f"Keep a note under {MAX_NOTE_CHARS} characters.")
    return text


def add_user_note(db: sqlite3.Connection, text: str, section: str, now: datetime) -> int:
    if section not in SECTIONS:
        raise ProfileError("Choose where the note belongs.")
    nid = db.execute("INSERT INTO profile_note(key, value, updated_at, section, source, evidence, edited) VALUES (?,?,?,?, 'user', 'You added this', 1)",
                     (f"user:{uuid.uuid4().hex[:10]}", _clean(text), stamp(now), section)).lastrowid
    db.commit()
    return nid


def edit_note(db: sqlite3.Connection, note_id: int, text: str, now: datetime) -> None:
    """The wording is the learner's from now on: automatic updates will not touch it."""
    cur = db.execute("UPDATE profile_note SET value = ?, edited = 1, updated_at = ? WHERE id = ? AND removed = 0", (_clean(text), stamp(now), note_id))
    if cur.rowcount == 0:
        raise ProfileError("This note no longer exists.")
    db.commit()


def remove_note(db: sqlite3.Connection, note_id: int) -> None:
    """A note the learner wrote is deleted. A learned one is kept as a marker so it is not learned again."""
    r = db.execute("SELECT source FROM profile_note WHERE id = ? AND removed = 0", (note_id,)).fetchone()
    if r is None:
        raise ProfileError("This note no longer exists.")
    if r["source"] == "user":
        db.execute("DELETE FROM profile_note WHERE id = ?", (note_id,))
    else:
        db.execute("UPDATE profile_note SET removed = 1 WHERE id = ?", (note_id,))
    db.commit()


def upsert_auto(db: sqlite3.Connection, key: str, section: str, topic: str | None, text: str, evidence: str, now: datetime) -> bool:
    """Write a learned note. Returns False when it was left alone: the learner edited, removed or wrote something on that key, or the
    learner owns a note on the same topic (an edited note wins, otherwise the newest does)."""
    row = db.execute("SELECT * FROM profile_note WHERE key = ?", (key,)).fetchone()
    if row is not None and (row["edited"] or row["removed"] or row["source"] == "user"):
        return False
    if topic and topic != "other" and db.execute(
            "SELECT 1 FROM profile_note WHERE topic = ? AND key != ? AND (edited = 1 OR source = 'user') AND removed = 0", (topic, key)).fetchone():
        return False
    if row is None:
        db.execute("INSERT INTO profile_note(key, value, updated_at, section, topic, source, evidence) VALUES (?,?,?,?,?, 'auto', ?)",
                   (key, text, stamp(now), section, topic, evidence))
    elif row["value"] != text or row["evidence"] != evidence:
        db.execute("UPDATE profile_note SET value = ?, evidence = ?, section = ?, topic = ?, updated_at = ? WHERE key = ?", (text, evidence, section, topic, stamp(now), key))
    db.commit()
    return True


# ---------- notes the app works out by counting

def _lever_note(lv: flow.Lever) -> str:
    label = flow.LABEL[lv.name]
    if lv.group == "support" and lv.op == "add":
        return f"{flow.cap(label)} helps when a task feels too hard."
    if lv.group == "support":
        return f"Taking away {label} works when a task feels too easy."
    if lv.op == "add":
        return f"{flow.cap(label)} works when a task feels too easy."
    return f"Taking away {label} helps when a task feels too hard."


def derived_notes(db: sqlite3.Connection) -> dict[str, dict]:
    """What the learner's own ratings say, as notes. Keyed so a refresh updates the same note instead of adding another."""
    out: dict[str, dict] = {}
    good, bad = flow.lever_outcomes(db)
    for lid, n in good.items():
        if n > bad.get(lid, 0):
            lv = flow.LEVERS[lid]
            out[f"lever:{lid}"] = {"section": "flow", "topic": f"lever:{lid}", "text": _lever_note(lv),
                                   "evidence": f"Learned from {n} flow rating{'s' if n != 1 else ''} · lever: {flow.SHORT[lv.name].lower()}"}
    rows = db.execute("SELECT fr.rating_used, fr.attempt, fr.session_id, s.practice_type FROM flow_rating fr JOIN skill s ON s.id = fr.skill_id WHERE fr.rating_used IS NOT NULL").fetchall()
    by_type: dict[str, list[str]] = {}
    for r in rows:
        if r["practice_type"]:
            by_type.setdefault(r["practice_type"].strip().lower(), []).append(r["rating_used"])
    for t, ratings in by_type.items():
        for word, rating in (("easy", "too_easy"), ("hard", "too_hard")):
            n = ratings.count(rating)
            if len(ratings) >= 2 and n >= 2 and n / len(ratings) >= 2 / 3:
                out[f"type:{t}:{word}"] = {"section": "flow", "topic": "task_type", "text": f"{t.capitalize()} tasks often feel too {word}.",
                                           "evidence": f"Learned from {n} of {len(ratings)} flow ratings"}
    mins = []
    for r in rows:
        if r["rating_used"] == "just_right":
            m = db.execute("SELECT meta_json FROM message WHERE session_id = ? AND kind = 'submission' AND json_extract(meta_json, '$.version') = ?", (r["session_id"], r["attempt"])).fetchone()
            if m:
                import json
                minutes = json.loads(m["meta_json"]).get("minutes")
                if minutes:
                    mins.append(float(minutes))
    if len(mins) >= 3:
        out["pref:task_minutes"] = {"section": "flow", "topic": "session_length", "text": f"Tasks of about {round(statistics.median(mins))} minutes feel right.",
                                    "evidence": f"Learned from {len(mins)} tasks that felt just right"}
    return out


def refresh_derived(db: sqlite3.Connection, now: datetime) -> None:
    """Bring the counted notes up to date. A note whose evidence has gone is dropped, unless the learner edited it."""
    want = derived_notes(db)
    for key, n in want.items():
        upsert_auto(db, key, n["section"], n["topic"], n["text"], n["evidence"], now)
    for r in db.execute("SELECT key FROM profile_note WHERE source = 'auto' AND edited = 0 AND removed = 0 AND (key LIKE 'lever:%' OR key LIKE 'type:%' OR key LIKE 'pref:%')").fetchall():
        if r["key"] not in want:
            db.execute("DELETE FROM profile_note WHERE key = ?", (r["key"],))
    db.commit()


# ---------- notes the model writes from a finished session

def session_facts(db: sqlite3.Connection, session_id: int) -> str:
    s = db.execute("SELECT se.*, sk.name AS skill_name FROM session se JOIN skill sk ON sk.id = se.skill_id WHERE se.id = ?", (session_id,)).fetchone()
    lines = [f"Attempts: {s['attempt']}. Practice time: {round(s['minutes'])} minutes. Time over the limit: {round(s['overtime_s'] / 60)} minutes."]
    import json
    checks = [json.loads(m["meta_json"]) for m in db.execute("SELECT meta_json FROM message WHERE session_id = ? AND kind = 'check_result'", (session_id,))]
    if checks:
        for level in ("define", "spot"):
            of = [c for c in checks if c.get("level") == level]
            if of:
                lines.append(f"Concept check, {level} questions: {sum(bool(c.get('correct')) for c in of)} right of {len(of)} answers.")
    n_re = db.execute("SELECT COUNT(*) FROM message WHERE session_id = ? AND kind IN ('check_reteach', 'reteach')", (session_id,)).fetchone()[0]
    if n_re:
        lines.append(f"Concepts re-taught from a new angle: {n_re}.")
    n_q = db.execute("SELECT COUNT(*) FROM message WHERE session_id = ? AND kind = 'question'", (session_id,)).fetchone()[0]
    if n_q:
        lines.append(f"Questions the learner asked: {n_q}.")
    for r in db.execute("SELECT * FROM flow_rating WHERE session_id = ? ORDER BY id", (session_id,)):
        lv = flow.LEVERS.get(r["lever_changed"]) if r["lever_changed"] else None
        lines.append(f"Attempt {r['attempt']}: felt {r['rating_used']}{' (judged by the app)' if r['inferred'] else ''}; "
                     f"{'lever ' + flow.SHORT[lv.name].lower() + ' ' + lv.op if lv else 'no lever changed'}; accuracy {round(r['accuracy'] or 0, 2)}.")
    for m in db.execute("SELECT tag, kind, count FROM mistake WHERE skill_id = ? ORDER BY count DESC LIMIT 3", (s["skill_id"],)):
        lines.append(f"Mistake: {m['tag']} ({m['kind']}), seen {m['count']} time{'s' if m['count'] != 1 else ''}.")
    return "\n".join(lines)


def accept_llm_notes(db: sqlite3.Connection, notes: list[NoteOut], now: datetime) -> int:
    """Keep only notes that are short, on a known topic, backed by evidence, and not about passing. At most three. Returns how many were written."""
    n = 0
    for note in notes:
        text, ev = re.sub(r"\s+", " ", note.text).strip(), re.sub(r"\s+", " ", note.evidence).strip()
        if n >= MAX_LLM_NOTES or note.section not in SECTIONS or note.topic not in TOPICS or not text or not ev:
            continue
        if len(text.split()) > MAX_NOTE_WORDS or BANNED.search(text):
            continue
        key = f"auto:{note.topic}" if note.topic != "other" else f"auto:other:{abs(hash(text)) % 10**6}"
        if upsert_auto(db, key, note.section, note.topic, text, ev, now):
            n += 1
    return n


def update_after_session(db: sqlite3.Connection, llm: LLMClient | None, session_id: int, now: datetime) -> int:
    """After a skill is finished: learn what the facts of the session support. Best effort; a model failure just means no new notes."""
    refresh_derived(db, now)
    if llm is None:
        return 0
    prompt = load_prompt("profile_update")
    from .teaching import persona
    s = db.execute("SELECT sk.name FROM session se JOIN skill sk ON sk.id = se.skill_id WHERE se.id = ?", (session_id,)).fetchone()
    existing = "\n".join(f"- [{n['topic'] or 'other'}] {n['text']}" for n in list_notes(db)) or "(none)"
    try:
        out = llm.json(NotesOut, prompt.render(persona=persona(), rule=DATA_RULE, skill=s["name"], facts=fence("session facts", session_facts(db, session_id)),
                                               existing=fence("existing notes", existing)), prompt_version=prompt.version, job="profile_update")
    except LLMError:
        return 0
    return accept_llm_notes(db, out.notes, now)


# ---------- what goes into every teaching prompt

def _trim(s: str, n: int = 220) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def profile_summary(db: sqlite3.Connection, skill_id: int | None = None) -> str:
    """The notes (the learner's own first, then the newest), one per topic, plus a few counted facts about the current skill. Bounded."""
    rows = db.execute("SELECT * FROM profile_note WHERE removed = 0 ORDER BY (edited = 1 OR source = 'user') DESC, updated_at DESC, id DESC").fetchall()
    seen: set[str] = set()
    lines: list[str] = []
    for r in rows:
        if r["topic"] and r["topic"] != "other":
            if r["topic"] in seen:
                continue                              # one note per topic: the learner's own, else the newest
            seen.add(r["topic"])
        lines.append(f"- {_trim(r['value'])}")
        if len(lines) >= MAX_NOTES_IN_PROMPT:
            break
    if skill_id is not None:
        for m in db.execute("SELECT tag, kind, count FROM mistake WHERE skill_id = ? AND count >= 2 ORDER BY count DESC, last_seen_at DESC LIMIT 3", (skill_id,)):
            lines.append(f"- Keeps making this mistake on this skill ({m['kind']}): {_trim(m['tag'], 80)}, {m['count']} times.")
        for c in db.execute("SELECT c.name, m.confusions_json FROM skill_concept sc JOIN concept c ON c.id = sc.concept_id JOIN concept_mastery m ON m.concept_id = c.id "
                            "WHERE sc.skill_id = ? AND m.confusions_json IS NOT NULL LIMIT 3", (skill_id,)):
            import json
            for conf in json.loads(c["confusions_json"])[:1]:
                if isinstance(conf, dict):
                    lines.append(f"- Mixes up {c['name']} with {conf['with']} ({conf['count']} times).")
    text = "\n".join(lines)
    if len(text) > MAX_PROFILE_CHARS:
        text = text[:MAX_PROFILE_CHARS].rsplit("\n", 1)[0]
    return text or NOTHING_YET
