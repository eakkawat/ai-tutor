"""The foundations check (SPEC §6.1.2, Flow 10): each concept a skill rests on, tested define → spot before practice.

Only the learner's answers move a concept up. Defining a concept never counts as spotting it: define answers lift a concept to
'define' at most, and only a correct spot answer reaches 'spot'. 'use' comes from practice work (feedback). One question at a time,
a hint before the answer is shown, and a short re-teach from a new angle after two wrong answers on the same question.
"""
import json
import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from . import skills as sk
from .citations import cite, validate
from .llm.prompts import fence
from .search import hit_by_id
from .teaching import Ctx, TutorError, _ask, trim_words

MAX_QUESTIONS_PER_SITTING = 12        # keeps one check to a few minutes
MINUTES_PER_QUESTION = 1
WRONG_BEFORE_RETEACH = 2
MAX_RETEACH_WORDS = 80


class Judge(BaseModel):
    correct: bool
    feedback: str = ""
    hint: str = ""
    confused_with: str | None = None


class HintOut(BaseModel):
    hint: str = Field(min_length=3)


class SpotOut(BaseModel):
    prompt: str = Field(min_length=10)
    answer_key: str = Field(min_length=1)


class ReteachOut(BaseModel):
    body: str
    example: str = ""


def new_state() -> dict:
    return {"current": None, "wrong": {}, "asked": {}, "total": 0}


def load_state(raw: str | None) -> dict:
    return {**new_state(), **json.loads(raw)} if raw else new_state()


def concept_rows(db: sqlite3.Connection, skill_id: int) -> list[dict]:
    rows = db.execute(
        "SELECT c.id, c.name, c.definition, COALESCE(m.level, 'none') AS level FROM skill_concept sc JOIN concept c ON c.id = sc.concept_id "
        "LEFT JOIN concept_mastery m ON m.concept_id = c.id WHERE sc.skill_id = ? ORDER BY c.name", (skill_id,)).fetchall()
    return [dict(r) for r in rows]


def target(db: sqlite3.Connection, skill_id: int) -> tuple[dict, str] | None:
    """The next concept to work on and the level to ask: define for one never checked, spot for one that is only defined."""
    for c in concept_rows(db, skill_id):
        if sk.LEVEL_ORDER[c["level"]] < sk.LEVEL_ORDER["spot"]:
            return c, ("define" if c["level"] == "none" else "spot")
    return None


def remaining(db: sqlite3.Connection, skill_id: int) -> int:
    """Questions left if every answer is right: define + spot for unchecked concepts, spot for defined ones."""
    n = 0
    for c in concept_rows(db, skill_id):
        n += {"none": 2, "define": 1}.get(c["level"], 0)
    return n


def definition_block(db: sqlite3.Connection, concept: dict) -> tuple[str, list]:
    """The concept's definition with the exact citation strings of the passages it comes from."""
    hits = [h for r in db.execute("SELECT chunk_id FROM concept_source WHERE concept_id = ?", (concept["id"],)) if (h := hit_by_id(db, r["chunk_id"]))]
    lines = [f"{concept['name']}: {concept['definition']}"] + [f"CITATION: {cite(h)}" for h in hits]
    return fence("definition", "\n".join(lines)), hits


# ---------- questions

def stored_question(db: sqlite3.Connection, concept: dict, level: str, asked: list[str]) -> tuple[str, str] | None:
    for q in db.execute("SELECT prompt, answer_key FROM concept_question WHERE concept_id = ? AND level = ? ORDER BY id", (concept["id"], level)):
        if q["prompt"] not in asked:
            return q["prompt"], q["answer_key"]
    return None


def make_question(ctx: Ctx, concept: dict, level: str, asked: list[str]) -> dict:
    """The next question for a concept: one the library already holds, else a fresh one (a new example for 'spot')."""
    q = stored_question(ctx.db, concept, level, asked)
    if q:
        return {"prompt": q[0], "answer_key": q[1], "source": "stored"}
    if level == "define":
        return {"prompt": f"In your own words, what is “{concept['name']}”? Use an example from your project if you can.",
                "answer_key": concept["definition"], "source": "generic"}
    block, _ = definition_block(ctx.db, concept)
    out = _ask(ctx, SpotOut, "concept_spot", "concept_spot", name=concept["name"], definition=block,
               asked=fence("asked", "\n---\n".join(asked) or "(none)"))
    return {"prompt": out.prompt.strip(), "answer_key": out.answer_key.strip(), "source": "generated"}


def judge(ctx: Ctx, concept: dict, level: str, question: dict, answer: str) -> Judge:
    block, _ = definition_block(ctx.db, concept)
    return _ask(ctx, Judge, "concept_check", "concept_check", name=concept["name"], level=level, definition=block,
                question=fence("question", question["prompt"]), answer_key=fence("answer key", question["answer_key"]),
                answer=fence("learner answer", answer))


def make_hint(ctx: Ctx, concept: dict, question: dict) -> str:
    block, _ = definition_block(ctx.db, concept)
    out = _ask(ctx, HintOut, "concept_hint", "concept_hint", name=concept["name"], definition=block, question=fence("question", question["prompt"]),
               answer_key=fence("answer key", question["answer_key"]))
    return trim_words(out.hint.strip(), 25)


def reteach(ctx: Ctx, concept: dict, trouble: str) -> dict:
    """A short second explanation from a new angle, cited to the concept's own passages."""
    block, hits = definition_block(ctx.db, concept)
    out = _ask(ctx, ReteachOut, "concept_reteach", "concept_reteach", name=concept["name"], definition=block, trouble=fence("trouble", trouble))
    checked = validate(trim_words(out.body.strip(), MAX_RETEACH_WORDS), hits)
    text, citations = checked.text, checked.valid
    if not citations and hits:                       # keep the re-teach grounded in the concept's own passage
        text = f"{text} {cite(hits[0])}"
        citations = validate(text, hits).valid
    if not citations:
        raise TutorError("I could not ground this explanation in your books, so I am not showing it. Try again.")
    return {"text": text, "example": out.example.strip(), "citations": citations}


# ---------- mastery

def set_level(db: sqlite3.Connection, concept_id: int, level: str, now: datetime, *, confused_with: str | None = None) -> None:
    """Raise a concept to `level` (never lower it here) and record when it was checked and what it was confused with."""
    row = db.execute("SELECT level, confusions_json FROM concept_mastery WHERE concept_id = ?", (concept_id,)).fetchone()
    if row is None:
        db.execute("INSERT INTO concept_mastery(concept_id, level) VALUES (?, 'none')", (concept_id,))
        row = {"level": "none", "confusions_json": None}
    cur = row["level"]
    new = level if sk.LEVEL_ORDER[level] > sk.LEVEL_ORDER[cur] else cur
    confusions = json.loads(row["confusions_json"]) if row["confusions_json"] else []
    if confused_with and confused_with.strip():
        name = confused_with.strip()
        hit = next((c for c in confusions if isinstance(c, dict) and c["with"].lower() == name.lower()), None)
        if hit:
            hit["count"] += 1
        else:
            confusions.append({"with": name, "count": 1})
    db.execute("UPDATE concept_mastery SET level = ?, last_checked_at = ?, confusions_json = ? WHERE concept_id = ?",
               (new, now.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(confusions) if confusions else None, concept_id))
    db.commit()


def demote(db: sqlite3.Connection, concept_id: int, to: str = "define") -> None:
    """A concept the learner misunderstood in their work must be checked again: it goes back to 'define' so Spot is asked once more."""
    db.execute("UPDATE concept_mastery SET level = ? WHERE concept_id = ? AND level IN ('spot', 'use')", (to, concept_id))
    db.commit()


def options(prompt: str) -> list[str]:
    """The choices in a spot question: lines like 'B. MAI: ...', or labels run together on one line ('A: ... B: ... C: ...')."""
    import re
    lines = [m.group(0).strip() for m in re.finditer(r"^[A-D][.:)]\s+.+$", prompt, re.MULTILINE)]
    if len(lines) >= 2:
        return lines
    marks = list(re.finditer(r"(?:^|(?<=\s))([A-D])[.:)]\s+", prompt))
    letters = [m.group(1) for m in marks]
    if len(marks) < 2 or letters != sorted(set(letters)) or letters[0] != "A":      # must read A, B, C... in order, or it is not a list of choices
        return []
    return [f"{m.group(1)}. {prompt[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(prompt)].strip()}" for i, m in enumerate(marks)]
