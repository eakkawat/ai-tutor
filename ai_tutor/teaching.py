"""What the tutor says: prompt assembly and the checks on what comes back (SPEC §6.1, §6.5, §7).

Every teaching prompt gets: persona and style rules, the phase's instructions, the skill and its principles, retrieved passages,
the learner profile and recent messages. Books, submissions and the profile go in fenced as data. Output is JSON validated by
Pydantic; lessons and answers are then checked in code: word limit, and every citation must match a retrieved passage.
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import skills as sk
from .citations import OUTSIDE, cite, validate
from .embeddings import Embedder
from .llm.client import LLMClient
from .llm.errors import LLMError
from .llm.prompts import DATA_RULE, fence, load_prompt
from .search import Hit, hit_by_id, search

MAX_LESSON_WORDS = 300
MAX_ANSWER_WORDS = 120
PASSAGES = 6


class TutorError(Exception):
    """The tutor could not do this now. The state did not change; `retryable` says whether pressing the button again may help."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


# ---------- outputs

class DiagnoseTask(BaseModel):
    task: str = Field(min_length=5)


class PrincipleResult(BaseModel):
    n: int
    result: str
    evidence: str = ""


class DiagnoseEval(BaseModel):
    principles: list[PrincipleResult] = Field(default_factory=list)
    can_do: str
    gap: str
    level: int = Field(ge=0, le=3)


class LessonOut(BaseModel):
    title: str
    body: str
    example: str = ""


class QAOut(BaseModel):
    answer: str
    drift: bool = False


@dataclass
class Lesson:
    title: str
    body: str
    example: str
    citations: list[dict]
    outside: bool


@dataclass
class Answer:
    text: str
    citations: list[dict]
    outside: bool
    steered: bool = False


@dataclass
class Ctx:
    """Everything a teaching prompt is built from."""
    db: sqlite3.Connection
    llm: LLMClient | None
    embedder: Embedder | None
    skill: dict
    project: dict
    session_id: int
    profile: str = ""
    vision: bool | None = None          # can the configured model read pictures? None = not known
    extra: dict = field(default_factory=dict)


# ---------- words

def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def trim_words(text: str, limit: int) -> str:
    """Cut at the last whole sentence that fits in `limit` words (or at the word limit when no sentence fits)."""
    if count_words(text) <= limit:
        return text
    words = re.findall(r"\S+\s*", text)
    cut = "".join(words[:limit]).rstrip()
    m = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind('."'), cut.rfind(".]"))
    return cut[: m + 1].rstrip() if m > len(cut) // 3 else cut


# ---------- quotes: the tutor may quote a book only if the words are in a retrieved passage

QUOTE = re.compile(r"[“\"]([^“”\"]+?)[”\"]")
MIN_QUOTE_WORDS = 5          # shorter quoted bits are scare quotes and terms, not quotations


def _plain(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def unverified_quotes(text: str, hits: list[Hit]) -> list[str]:
    corpus = " ".join(_plain(h.text) for h in hits)
    return [q for q in QUOTE.findall(text) if count_words(q) >= MIN_QUOTE_WORDS and _plain(q) not in corpus]


def drop_sentences_with(text: str, quotes: list[str]) -> str:
    """Remove every sentence that contains one of the quotes. No invented quotes survive (SPEC §7)."""
    if not quotes:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(p for p in parts if not any(q in p for q in quotes)).strip()


# ---------- prompt parts

def persona() -> str:
    return load_prompt("persona").render(rule=DATA_RULE)


def profile_summary(db: sqlite3.Connection) -> str:
    """What the app has learned about how this learner learns (grows in TASKS_009)."""
    rows = db.execute("SELECT key, value FROM profile_note ORDER BY updated_at DESC LIMIT 20").fetchall()
    return "\n".join(f"- {r['key']}: {r['value']}" for r in rows) or "(nothing learned yet)"


def principles_text(skill: dict) -> str:
    return "\n".join(f"{i}. {p['principle']} (test: {p['test']})" for i, p in enumerate(skill["principles"], 1))


def concepts_text(db: sqlite3.Connection, skill_id: int, *, unmastered_only: bool = False) -> str:
    rows = db.execute(
        "SELECT c.name, c.definition, COALESCE(m.level, 'none') AS level FROM skill_concept sc JOIN concept c ON c.id = sc.concept_id "
        "LEFT JOIN concept_mastery m ON m.concept_id = c.id WHERE sc.skill_id = ? ORDER BY c.name", (skill_id,)).fetchall()
    if unmastered_only:
        rows = [r for r in rows if sk.LEVEL_ORDER[r["level"]] < sk.LEVEL_ORDER["spot"]]
    return "\n".join(f"- {r['name']}: {r['definition']}" for r in rows) or "(none)"


def project_text(p: dict) -> str:
    return f"{p['name']}: {p['description']}"


def hits_for_skill(ctx: Ctx, query: str, k: int = PASSAGES) -> list[Hit]:
    """The skill's own principle passages first, then the best search results, preferring the skill's books (SPEC §7)."""
    db = ctx.db
    ids = [p["chunk_id"] for p in ctx.skill["principles"]]
    seen: dict[int, Hit] = {}
    for cid in ids:
        h = hit_by_id(db, cid)
        if h:
            seen[cid] = h
    books = {s["source_id"] for s in ctx.skill["sources"]}
    for h in search(db, ctx.embedder, query, k=k, prefer_sources=books or None):
        seen.setdefault(h.chunk_id, h)
    return list(seen.values())[: max(k, len(ids))]


def passages_text(hits: list[Hit]) -> str:
    return fence("passages", "\n\n".join(f"CITATION: {cite(h)}\n{h.text[:1800]}" for h in hits) or "(no passages found)")


def diagnosis_text(db: sqlite3.Connection, session_id: int) -> str:
    row = db.execute("SELECT diagnosis_json FROM session WHERE id = ?", (session_id,)).fetchone()
    if not row or not row[0]:
        return "(not diagnosed)"
    d = json.loads(row[0])
    return f"Can do: {d['can_do']}\nGap: {d['gap']}"


def base_values(ctx: Ctx) -> dict:
    return {"persona": persona(), "skill": f"{ctx.skill['name']}: {ctx.skill['description']}",
            "project": fence("project", project_text(ctx.project)), "good_enough": fence("good enough", ctx.project["good_enough"]),
            "principles": principles_text(ctx.skill), "profile": fence("learner profile", ctx.profile or "(nothing learned yet)")}


def _llm(ctx: Ctx) -> LLMClient:
    if ctx.llm is None:
        raise TutorError("The language model is not set up. Open Setup and enter the server URL and model name.", retryable=False)
    return ctx.llm


def _ask(ctx: Ctx, schema, prompt_name: str, job: str, images: list[str] | None = None, **values):
    prompt = load_prompt(prompt_name)
    try:
        return _llm(ctx).json(schema, prompt.render(**{**base_values(ctx), **values}), prompt_version=prompt.version, job=job, images=images)
    except LLMError as e:
        kind = "could not be reached" if type(e).__name__ == "LLMPausedError" else "gave an answer I could not use"
        raise TutorError(f"The language model {kind}. Nothing was changed; try again. ({e})") from e


# ---------- the phases

def make_diagnose_task(ctx: Ctx) -> str:
    out = _ask(ctx, DiagnoseTask, "diagnose", "diagnose", concepts=concepts_text(ctx.db, ctx.skill["id"], unmastered_only=True))
    return out.task.strip()


def evaluate_diagnosis(ctx: Ctx, task: str, answer: str) -> dict:
    out = _ask(ctx, DiagnoseEval, "diagnose_eval", "diagnose_eval", task=fence("task", task), answer=fence("learner answer", answer))
    n = len(ctx.skill["principles"])
    results = {p.n: p for p in out.principles if 1 <= p.n <= n and p.result in ("followed", "partly", "not")}
    # "meets every principle" needs a verdict and some evidence for each one; anything missing counts as not followed
    meets_all = n > 0 and len(results) == n and all(r.result == "followed" and r.evidence.strip() for r in results.values())
    return {"can_do": out.can_do.strip(), "gap": out.gap.strip(), "level": out.level, "meets_all": meets_all,
            "principles": [{"n": i, "result": results[i].result if i in results else "not", "evidence": results[i].evidence if i in results else ""}
                           for i in range(1, n + 1)]}


def make_lesson(ctx: Ctx) -> Lesson:
    """At most 300 words, one example, every claim cited to a retrieved passage. A reply with no valid citation is not shown."""
    hits = hits_for_skill(ctx, f"{ctx.skill['name']}. {ctx.skill['description']}. {ctx.project['name']}")
    note = ""
    for attempt in (1, 2):
        out = _ask(ctx, LessonOut, "teach", "teach", diagnosis=fence("diagnosis", diagnosis_text(ctx.db, ctx.session_id)),
                   concepts=concepts_text(ctx.db, ctx.skill["id"], unmastered_only=True), passages=passages_text(hits) + note)
        body = out.body.strip()
        bad = unverified_quotes(body, hits)
        if bad and attempt == 1:
            note = "\n\nYour last reply quoted words that are not in the passages. Quote only words that appear in them, or paraphrase."
            continue
        body = drop_sentences_with(body, bad)
        checked = validate(body, hits)                     # strips any citation that is not a retrieved passage
        words = count_words(checked.text)
        if checked.valid and (words <= MAX_LESSON_WORDS or attempt == 2):
            text = trim_words(checked.text, MAX_LESSON_WORDS)
            if not validate(text, hits).valid:             # trimming cut off every citation: keep the lesson grounded in what it used
                text = f"{text} {checked.valid[0]['citation']}"
            final = validate(text, hits)
            if final.valid:
                ex = validate(out.example.strip(), hits)
                return Lesson(out.title.strip(), final.text, ex.text, final.valid + [v for v in ex.valid if v not in final.valid],
                              OUTSIDE in body or OUTSIDE in out.example)
        if not checked.valid:
            note = "\n\nYour last reply had no valid citation. Cite with the exact CITATION strings above."
        else:
            note = f"\n\nYour last `body` had {words} words. Keep it to {MAX_LESSON_WORDS} words or fewer."
    raise TutorError("I could not ground this lesson in your books, so I am not showing it. Try again, or add a book that covers this skill.")


class PracticeTaskOut(BaseModel):
    title: str
    instructions: str
    template: list[str] = Field(default_factory=list)
    worked_example: str = ""
    hint: str = ""
    steps: list[str] = Field(default_factory=list)
    smaller_scope: str = ""
    constraint: str = ""
    higher_standard: str = ""
    combine: str = ""
    minutes: int = 20


class PieceOut(BaseModel):
    text: str = ""
    items: list[str] = Field(default_factory=list)


EARLY_HOURS = 3.0
TIME_LIMIT_FACTOR = 0.75
MIN_TASK_MINUTES = 10


def setup_text(state: dict) -> str:
    """The task's set-up as plain lines for the prompt: every support and constraint, on or off."""
    from .flow import CONSTRAINTS, LABEL, SUPPORTS
    lines = [f"- {LABEL[k]}: {'ON' if k in state['supports'] else 'off'}" for k in SUPPORTS]
    lines += [f"- {LABEL[k]}: {'ON' + (' (' + str(state.get('combine_with')) + ')' if k == 'combine' and state.get('combine_with') else '') if k in state['constraints'] else 'off'}"
              for k in CONSTRAINTS if k != "time_limit"]
    return "\n".join(lines)


def stage_note(hours: float) -> str:
    return ("This is an early stage on this skill (under 3 hours). Favour quantity and speed over polish: ask for several quick short attempts "
            "rather than one polished piece.") if hours < EARLY_HOURS else "Ask for one considered piece of work."


def derive_support(task: dict, state: dict) -> str | None:
    from .flow import SHORT
    names = [SHORT[k].lower() for k in state["supports"]]
    return ", ".join(names) or None


def _clean_list(items: list[str], lo: int, hi: int) -> list[str]:
    out = [t.strip() for t in items if t.strip()][:hi]
    return out if len(out) >= lo else []


def make_practice_task(ctx: Ctx, attempt: int, difficulty: int, state: dict | None = None, hours: float = 0.0) -> dict:
    """A task set up exactly as the levers say. A piece the model leaves out for a lever that is on is asked for on its own, so a
    promised support is never missing, and a piece for a lever that is off is dropped."""
    from .flow import DEFAULT_STATE
    state = state or dict(DEFAULT_STATE)
    out = _ask(ctx, PracticeTaskOut, "practice_task", "practice_task", attempt=str(attempt), difficulty=str(difficulty), setup=setup_text(state),
               stage_note=stage_note(hours), diagnosis=fence("diagnosis", diagnosis_text(ctx.db, ctx.session_id)))
    on = set(state["supports"]) | set(state["constraints"])
    extras: dict = {}
    if "template" in on:
        extras["template"] = _clean_list(out.template, 3, 6)
    if "split_steps" in on:
        extras["split_steps"] = _clean_list(out.steps, 3, 5)
    for kind, val in (("worked_example", out.worked_example), ("hint", out.hint), ("smaller_scope", out.smaller_scope), ("constraint", out.constraint),
                      ("higher_standard", out.higher_standard), ("combine", out.combine)):
        if kind in on and val.strip():
            extras[kind] = val.strip()
    minutes = min(max(out.minutes, 15), 25)
    task = {"title": out.title.strip(), "instructions": out.instructions.strip(), "extras": extras, "minutes": minutes, "base_minutes": minutes, "attempt": attempt}
    for kind in on - {"time_limit"}:
        if not extras.get(kind):
            task = add_piece(ctx, task, kind, state)
    if "time_limit" in on:
        task["minutes"] = max(MIN_TASK_MINUTES, round(task["base_minutes"] * TIME_LIMIT_FACTOR))
    return _finish(task, state)


def _finish(task: dict, state: dict) -> dict:
    task["template"] = task["extras"].get("template", [])
    task["support"] = derive_support(task, state)
    return task


def adjust_task(ctx: Ctx, task: dict, lv, state_after: dict) -> dict:
    """The same task with exactly one lever pulled. Taking something away needs no model; adding a support or constraint writes only that one
    new piece. Raises TutorError (and changes nothing) if the piece cannot be written."""
    import copy
    t = copy.deepcopy(task)
    t.setdefault("extras", {})
    if "template" not in t["extras"] and t.get("template"):
        t["extras"]["template"] = t["template"]
    t.setdefault("base_minutes", t["minutes"])
    if lv.name == "time_limit":
        t["minutes"] = max(MIN_TASK_MINUTES, round(t["base_minutes"] * TIME_LIMIT_FACTOR)) if lv.op == "add" else t["base_minutes"]
    elif lv.op == "remove":
        t["extras"].pop(lv.name, None)
    else:
        t = add_piece(ctx, t, lv.name, state_after)
    return _finish(t, state_after)


CHANGE_TEXT = {
    "worked_example": "Add a short worked example of the skill on a made-up case, not the learner's own work.",
    "template": "Add a beat template: 3 to 6 short beat labels in `items`.",
    "smaller_scope": "Narrow the task to a smaller piece, in one sentence.",
    "hint": "Add one hint that points without giving the answer.",
    "split_steps": "Split the task into 3 to 5 short steps, in `items`.",
    "constraint": "Add one extra constraint that makes the task harder, for example a rule about what may not be used.",
    "higher_standard": "Raise the bar: one sentence on how strictly the principles must be applied.",
    "combine": "Also ask the learner to use the skill named below, inside this same task, in one sentence.",
}


def add_piece(ctx: Ctx, task: dict, kind: str, state: dict) -> dict:
    """Write the one new piece a lever needs and put it in the task. Nothing else in the task changes."""
    change = CHANGE_TEXT[kind] + (f"\nThe skill to combine: {state.get('combine_with')}" if kind == "combine" else "")
    out = _ask(ctx, PieceOut, "task_adjust", "task_adjust", task=fence("task", f"{task['title']}\n{task['instructions']}"), change=change)
    if kind in ("template", "split_steps"):
        items = _clean_list(out.items, 3, 6 if kind == "template" else 5)
        if not items:
            raise TutorError("I could not write that part of the task. Nothing was changed; try again.")
        task["extras"][kind] = items
    else:
        if not out.text.strip():
            raise TutorError("I could not write that part of the task. Nothing was changed; try again.")
        task["extras"][kind] = out.text.strip()
    return task


def answer_question(ctx: Ctx, question: str, phase: str) -> Answer:
    hits = hits_for_skill(ctx, f"{question}. {ctx.skill['name']}")
    out = _ask(ctx, QAOut, "qa", "qa", phase=phase, question=fence("learner question", question), passages=passages_text(hits))
    checked = validate(drop_sentences_with(out.answer.strip(), unverified_quotes(out.answer, hits)), hits)
    steer = out.drift and phase in ("practice", "revise")
    if steer:
        # Stay on the work: no teaching, no citations, just the redirect.
        return Answer(trim_words(re.sub(r"\[[^\[\]]+\]", "", out.answer).strip(), 40), [], False, steered=True)
    text = trim_words(checked.text, MAX_ANSWER_WORDS)
    if not checked.valid and OUTSIDE not in text:       # nothing from the books backs this: say so rather than pass it off as theirs
        text = f"{text} {OUTSIDE}"
    return Answer(text, checked.valid, OUTSIDE in text)
