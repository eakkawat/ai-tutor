"""Spaced review (SPEC §5.3, §5.4; Flows 7 and 8) and the 3-minute concept check (Flow 5).

Items are skills the learner passed and concepts they were checked on. An SM-2 style schedule decides when each comes back:
right answers push it out (1 → 3 → 7 days, then longer by the ease factor), a miss brings it back tomorrow with a lower ease.
A *run* is one sitting of questions. It is stored, so closing the app in the middle of a review loses nothing.

Rules for what a result does:
- Concept right: the concept rises to the level asked (never lowered by a right answer).
- Concept wrong: it drops to the level below the one missed (at most "define" after a missed spot, at most "spot" after a missed use).
- Skill wrong twice in a row: the skill goes back to "needs practice" (picker offers it again).
Only the learner's answers do any of this. The model judges meaning; the schedule, levels and status are set here, in code.
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta

from pydantic import BaseModel

from . import check as chk
from . import projects
from . import skills as sk
from .citations import cite
from .llm.prompts import fence
from .search import hit_by_id
from .teaching import Ctx, _ask, trim_words

CONTINUE_QUESTIONS = 2
REVIEW_CAP = 8                              # one sitting of Review mode
CONTINUE_COOLDOWN = timedelta(hours=4)      # after a Continue review, the next Continue goes straight to the work
MISS_INTERVAL_DAYS = 1.0
MIN_EASE, MAX_EASE = 1.3, 3.0
FAILS_TO_NEEDS_PRACTICE = 2
CHECK_LEVELS = ("define", "spot", "use")
WRONG_BEFORE_REVEAL = 2
LEVELS_DOWN = {"define": None, "spot": "define", "use": "spot"}     # where a concept drops to after missing that level


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse(s: str | None) -> datetime | None:
    from datetime import UTC
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) if s else None


class ReviewError(Exception):
    """The learner asked for something this review state does not allow. The message is shown as is."""


class UseOut(BaseModel):
    prompt: str
    answer_key: str


# ---------- the schedule

def next_schedule(reps: int, interval_days: float, ease: float, *, right: bool) -> dict:
    """SM-2 style. Right: 1st → 3 days, 2nd → 7 days, then the last interval times the ease. Wrong: back tomorrow, ease down."""
    if not right:
        return {"reps": 0, "interval_days": MISS_INTERVAL_DAYS, "ease": max(MIN_EASE, round(ease - 0.2, 2))}
    reps += 1
    ease = min(MAX_EASE, round(ease + 0.05, 2))
    days = {1: 3.0, 2: 7.0}.get(reps) or max(7.0, round(interval_days * ease, 1))
    return {"reps": reps, "interval_days": days, "ease": ease}


def schedule_item(db: sqlite3.Connection, item_id: int, right: bool, now: datetime) -> dict:
    r = db.execute("SELECT * FROM review_item WHERE id = ?", (item_id,)).fetchone()
    s = next_schedule(r["reps"], r["interval_days"], r["ease"], right=right)
    due = now + timedelta(days=s["interval_days"])
    db.execute("UPDATE review_item SET reps = ?, interval_days = ?, ease = ?, due_at = ?, last_result = ?, misses = misses + ? WHERE id = ?",
               (s["reps"], s["interval_days"], s["ease"], iso(due), "right" if right else "wrong", 0 if right else 1, item_id))
    return {**s, "due_at": iso(due)}


# ---------- creating items (at pass time and when a concept is checked)

def _concept_question(db: sqlite3.Connection, concept_id: int) -> sqlite3.Row | None:
    return (db.execute("SELECT * FROM concept_question WHERE concept_id = ? AND level = 'spot' ORDER BY id LIMIT 1", (concept_id,)).fetchone()
            or db.execute("SELECT * FROM concept_question WHERE concept_id = ? AND level = 'define' ORDER BY id LIMIT 1", (concept_id,)).fetchone())


def ensure_concept_item(db: sqlite3.Connection, concept_id: int, skill_id: int | None, now: datetime, *, due: datetime | None = None) -> None:
    """One review item per concept, shared by every skill that uses it. Does nothing if it has one or has no question to ask."""
    if db.execute("SELECT 1 FROM review_item WHERE concept_id = ?", (concept_id,)).fetchone():
        return
    q = _concept_question(db, concept_id)
    if q is None:
        return
    db.execute("INSERT INTO review_item(skill_id, concept_id, level, question, answer, due_at) VALUES (?,?,?,?,?,?)",
               (skill_id, concept_id, q["level"], q["prompt"], q["answer_key"], iso(due or now + timedelta(days=1))))


def create_for_passed_skill(db: sqlite3.Connection, skill: dict, now: datetime, first_interval: timedelta) -> None:
    """A skill that was just passed (again): one question about its principles, plus a question for each of its concepts."""
    due = now + first_interval
    question = f"What must work on “{skill['name']}” do to pass? Name the principles."
    answer = "; ".join(p["principle"] for p in skill["principles"])
    old = db.execute("SELECT id FROM review_item WHERE skill_id = ? AND concept_id IS NULL", (skill["id"],)).fetchone()
    if old:
        db.execute("UPDATE review_item SET question = ?, answer = ?, due_at = ?, reps = 0, interval_days = 0 WHERE id = ?", (question, answer, iso(due), old["id"]))
    else:
        db.execute("INSERT INTO review_item(skill_id, level, question, answer, due_at) VALUES (?,?,?,?,?)", (skill["id"], "use", question, answer, iso(due)))
    for c in skill["concepts"]:
        ensure_concept_item(db, c["id"], skill["id"], now, due=due)
    db.commit()


# ---------- which questions

def _due_rows(db: sqlite3.Connection, now: datetime) -> list[sqlite3.Row]:
    """Due items. A skill's own question needs the skill to be passed; a concept's question comes whatever skill taught it."""
    return db.execute(
        "SELECT ri.* FROM review_item ri LEFT JOIN learner_skill ls ON ls.skill_id = ri.skill_id "
        "WHERE ri.due_at <= ? AND (ri.concept_id IS NOT NULL OR ls.status = 'passed') ORDER BY ri.due_at, ri.id", (iso(now),)).fetchall()


def _reserved(db: sqlite3.Connection) -> set[int]:
    """Items that already sit in a sitting that is still open."""
    out: set[int] = set()
    for r in db.execute("SELECT questions_json FROM review_run WHERE ended_at IS NULL AND mode != 'concept'"):
        out |= {q["item_id"] for q in json.loads(r["questions_json"]) if q.get("item_id")}
    return out


def due_count(db: sqlite3.Connection, now: datetime) -> int:
    reserved = _reserved(db)
    return sum(1 for r in _due_rows(db, now) if r["id"] not in reserved)


def weight(db: sqlite3.Connection, item: sqlite3.Row, now: datetime) -> float:
    """How much this question deserves to be asked now: past mistakes first, then shaky concepts, then how long it has waited."""
    if item["concept_id"]:
        mistakes = db.execute("SELECT COALESCE(SUM(count), 0) FROM mistake WHERE concept_id = ?", (item["concept_id"],)).fetchone()[0]
        m = db.execute("SELECT level, confusions_json FROM concept_mastery WHERE concept_id = ?", (item["concept_id"],)).fetchone()
        shaky = 2.0 * bool(m and m["confusions_json"]) + 2.0 * bool(m is None or sk.LEVEL_ORDER[m["level"]] < sk.LEVEL_ORDER["spot"])
    else:
        mistakes = db.execute("SELECT COALESCE(SUM(count), 0) FROM mistake WHERE skill_id = ?", (item["skill_id"],)).fetchone()[0]
        shaky = 0.0
    overdue = min(5.0, max(0.0, (now - parse(item["due_at"])).total_seconds() / 86400))
    return 2.0 * min(mistakes, 3) + 1.5 * min(item["misses"], 3) + shaky + overdue


def pick(db: sqlite3.Connection, now: datetime, n: int) -> list[sqlite3.Row]:
    """The n due questions that best use the learner's time, mixed: a skill and a concept, from different skills, when there is a choice."""
    reserved = _reserved(db)
    pool = [r for r in _due_rows(db, now) if r["id"] not in reserved]
    scored = {r["id"]: weight(db, r, now) for r in pool}
    chosen: list[sqlite3.Row] = []
    while pool and len(chosen) < n:
        # mixed: after a skill question comes a concept question and the other way round, whenever the pool has both
        other = [r for r in pool if bool(r["concept_id"]) != bool(chosen[-1]["concept_id"])] if chosen else []
        best = max(other or pool, key=lambda r: (scored[r["id"]] + 1.0 * (r["skill_id"] not in {c["skill_id"] for c in chosen}), -r["id"]))
        chosen.append(best)
        pool.remove(best)
    return chosen


# ---------- concept and skill effects of one answer

def drop_after_miss(db: sqlite3.Connection, concept_id: int, missed_level: str) -> str | None:
    """A concept the learner could not answer at `missed_level` falls to the level below it. Returns the new level if it moved."""
    cap = LEVELS_DOWN.get(missed_level)
    row = db.execute("SELECT level FROM concept_mastery WHERE concept_id = ?", (concept_id,)).fetchone()
    if cap is None or row is None or sk.LEVEL_ORDER[row["level"]] <= sk.LEVEL_ORDER[cap]:
        return None
    db.execute("UPDATE concept_mastery SET level = ? WHERE concept_id = ?", (cap, concept_id))
    return cap


def skill_failing(db: sqlite3.Connection, skill_id: int) -> bool:
    """The skill's own question missed twice in a row."""
    last = [r["result"] for r in db.execute(
        "SELECT result FROM review_result WHERE skill_id = ? AND concept_id IS NULL ORDER BY id DESC LIMIT ?", (skill_id, FAILS_TO_NEEDS_PRACTICE))]
    return len(last) == FAILS_TO_NEEDS_PRACTICE and all(x == "wrong" for x in last)


# ---------- building a sitting

def _age(then: str | None, now: datetime) -> str:
    t = parse(then)
    days = max(0, (now - t).days) if t else 0
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def _question(db: sqlite3.Connection, item: sqlite3.Row, now: datetime) -> dict:
    if item["concept_id"]:
        c = db.execute("SELECT name FROM concept WHERE id = ?", (item["concept_id"],)).fetchone()
        s = db.execute("SELECT name FROM skill WHERE id = ?", (item["skill_id"],)).fetchone() if item["skill_id"] else None
        context = f"Concept · {c['name']}" + (f" · from {s['name']}" if s else "")
        level = item["level"] or "spot"
    else:
        s = db.execute("SELECT s.name, ls.last_session_at FROM skill s LEFT JOIN learner_skill ls ON ls.skill_id = s.id WHERE s.id = ?", (item["skill_id"],)).fetchone()
        context = f"{s['name']} · passed {_age(s['last_session_at'], now)}"
        level = "use"
    return {"item_id": item["id"], "kind": "concept" if item["concept_id"] else "skill", "skill_id": item["skill_id"], "concept_id": item["concept_id"],
            "level": level, "prompt": item["question"], "answer_key": item["answer"], "context": context}


def _new_run(db: sqlite3.Connection, mode: str, questions: list[dict], now: datetime, *, session_id=None, concept_id=None) -> int:
    cur = db.execute("INSERT INTO review_run(mode, session_id, concept_id, questions_json, started_at) VALUES (?,?,?,?,?)",
                     (mode, session_id, concept_id, json.dumps(questions), iso(now)))
    db.commit()
    return cur.lastrowid


def _open_run(db: sqlite3.Connection, mode: str, concept_id: int | None = None) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM review_run WHERE mode = ? AND ended_at IS NULL AND COALESCE(concept_id, 0) = ? ORDER BY id DESC LIMIT 1",
                      (mode, concept_id or 0)).fetchone()


def _cooling_down(db: sqlite3.Connection, now: datetime) -> bool:
    r = db.execute("SELECT ended_at FROM review_run WHERE mode = 'continue' AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 1").fetchone()
    return bool(r) and now - parse(r["ended_at"]) < CONTINUE_COOLDOWN


def continue_waiting(db: sqlite3.Connection, now: datetime) -> bool:
    """Should Continue begin with a short review? Yes if one is open, or questions are due and no Continue review ran in the last hours."""
    return _open_run(db, "continue") is not None or (not _cooling_down(db, now) and due_count(db, now) > 0)


class ReviewService:
    def __init__(self, db: sqlite3.Connection, *, llm, embedder=None, clock):
        self.db, self.llm, self.embedder, self.clock = db, llm, embedder, clock

    # ---- starting
    def start(self, mode: str, *, session_id: int | None = None, concept_id: int | None = None) -> dict | None:
        """Open (or resume) a sitting. Returns None when there is nothing to ask."""
        now = self.clock()
        if mode not in ("continue", "review", "concept"):
            raise ReviewError("Unknown review mode.")
        if mode == "concept":
            if concept_id is None or self.db.execute("SELECT 1 FROM concept WHERE id = ?", (concept_id,)).fetchone() is None:
                raise ReviewError("This concept no longer exists.")
            run = _open_run(self.db, "concept", concept_id)
            if run:
                return self.view(run["id"])
            qs = [{"item_id": None, "kind": "concept", "skill_id": None, "concept_id": concept_id, "level": lv, "pending": True} for lv in CHECK_LEVELS]
            return self.view(_new_run(self.db, "concept", qs, now, concept_id=concept_id))
        run = _open_run(self.db, mode)
        if run:
            return self.view(run["id"])
        if mode == "continue" and _cooling_down(self.db, now):
            return None
        items = pick(self.db, now, CONTINUE_QUESTIONS if mode == "continue" else REVIEW_CAP)
        if not items:
            return None
        return self.view(_new_run(self.db, mode, [_question(self.db, i, now) for i in items], now, session_id=session_id))

    # ---- reading
    def _run(self, run_id: int) -> sqlite3.Row:
        r = self.db.execute("SELECT * FROM review_run WHERE id = ?", (run_id,)).fetchone()
        if r is None:
            raise ReviewError("This review no longer exists.")
        return r

    def ctx(self, skill_id: int | None, concept_id: int | None) -> Ctx:
        if not skill_id and concept_id:
            r = self.db.execute("SELECT s.id FROM skill_concept sc JOIN skill s ON s.id = sc.skill_id WHERE sc.concept_id = ? AND s.status = 'active' ORDER BY s.id LIMIT 1",
                                (concept_id,)).fetchone()
            skill_id = r["id"] if r else None
        skill = sk.skill_detail(self.db, skill_id) if skill_id else {"id": 0, "name": "(any skill)", "description": "", "principles": [], "concepts": []}
        project = projects.active(self.db) or {"name": "(no project)", "description": "", "good_enough": ""}
        from .profile import profile_summary
        return Ctx(self.db, self.llm, self.embedder, skill, project, 0, profile=profile_summary(self.db, skill_id) if skill_id else "")

    def _save(self, run_id: int, *, idx=None, state=None, questions=None, results=None) -> None:
        sets, vals = [], []
        for col, v in (("idx", idx), ("state_json", None if state is None else json.dumps(state)), ("questions_json", None if questions is None else json.dumps(questions)),
                       ("results_json", None if results is None else json.dumps(results))):
            if v is not None:
                sets.append(f"{col} = ?")
                vals.append(v)
        if sets:
            self.db.execute(f"UPDATE review_run SET {', '.join(sets)} WHERE id = ?", (*vals, run_id))
            self.db.commit()

    def _materialize(self, run: sqlite3.Row, questions: list[dict], i: int) -> dict:
        """A concept-check question is made when it is reached: the stored one, else a fresh one, so a missed define never pays for the rest."""
        q = questions[i]
        if not q.get("pending"):
            return q
        c = self.db.execute("SELECT c.id, c.name, c.definition, COALESCE(m.level, 'none') AS level FROM concept c LEFT JOIN concept_mastery m ON m.concept_id = c.id WHERE c.id = ?",
                            (q["concept_id"],)).fetchone()
        concept = dict(c)
        ctx = self.ctx(None, concept["id"])
        asked = [x.get("prompt", "") for x in questions if x.get("prompt")]
        if q["level"] == "use":
            stored = chk.stored_question(self.db, concept, "use", asked)
            if stored:
                made = {"prompt": stored[0], "answer_key": stored[1]}
            else:
                block, _ = chk.definition_block(self.db, concept)
                out = _ask(ctx, UseOut, "concept_use", "concept_use", name=concept["name"], definition=block, asked=fence("asked", "\n---\n".join(asked) or "(none)"))
                made = {"prompt": out.prompt.strip(), "answer_key": out.answer_key.strip()}
        else:
            made = chk.make_question(ctx, concept, q["level"], asked)
        q.update(prompt=made["prompt"], answer_key=made["answer_key"], context=f"Concept · {concept['name']}", pending=False)
        self._save(run["id"], questions=questions)
        return q

    def view(self, run_id: int) -> dict:
        run = self._run(run_id)
        qs = json.loads(run["questions_json"])
        results = json.loads(run["results_json"])
        total = len(qs)
        base = {"id": run["id"], "mode": run["mode"], "session_id": run["session_id"], "concept_id": run["concept_id"], "total": total, "answered": len(results)}
        if run["ended_at"] or run["idx"] >= total:
            return {**base, "ended": True, "current": None, "summary": self.summary(run, qs, results)}
        i = run["idx"]
        q = self._materialize(run, qs, i)
        st = json.loads(run["state_json"]) if run["state_json"] else {"attempts": 0, "hint": None, "shown": False, "correct": False, "feedback": ""}
        finished = st["shown"] or st["correct"]
        cur = {"n": i + 1, "context": q["context"], "level": q["level"], "kind": q["kind"], "prompt": q["prompt"], "options": chk.options(q["prompt"]),
               "attempts": st["attempts"], "hint": st["hint"], "feedback": st["feedback"], "correct": st["correct"], "finished": finished,
               "first": results_first(st), "answer": q["answer_key"] if finished else None, "citations": self._citations(q) if finished else []}
        return {**base, "ended": False, "current": cur, "summary": None}

    def _citations(self, q: dict) -> list[dict]:
        if q["concept_id"]:
            ids = [r["chunk_id"] for r in self.db.execute("SELECT chunk_id FROM concept_source WHERE concept_id = ? ORDER BY chunk_id LIMIT 2", (q["concept_id"],))]
        else:
            ids = list(dict.fromkeys(r["chunk_id"] for r in self.db.execute("SELECT chunk_id FROM skill_principle WHERE skill_id = ? ORDER BY \"order\"", (q["skill_id"],))))[:2]
        return [{"citation": cite(h), "chunk_id": h.chunk_id} for i in ids if (h := hit_by_id(self.db, i))]

    # ---- answering
    def _judge(self, q: dict, answer: str) -> chk.Judge:
        ctx = self.ctx(q["skill_id"], q["concept_id"])
        if q["concept_id"]:
            concept = dict(self.db.execute("SELECT c.id, c.name, c.definition FROM concept c WHERE c.id = ?", (q["concept_id"],)).fetchone())
            return chk.judge(ctx, concept, q["level"], q, answer)
        return _ask(ctx, chk.Judge, "review_check", "review_check", question=fence("question", q["prompt"]), answer_key=fence("answer key", q["answer_key"]),
                    answer=fence("learner answer", answer))

    def _hint(self, q: dict, verdict: chk.Judge) -> str:
        hint = plain(verdict.hint)
        if hint:
            return trim_words(hint, 25)
        if q["concept_id"]:
            concept = dict(self.db.execute("SELECT c.id, c.name, c.definition FROM concept c WHERE c.id = ?", (q["concept_id"],)).fetchone())
            return chk.make_hint(self.ctx(q["skill_id"], q["concept_id"]), concept, q)
        return "Think about what each principle asks you to check in your own work."

    def _current(self, run_id: int) -> tuple[sqlite3.Row, list[dict], dict, dict]:
        run = self._run(run_id)
        if run["ended_at"]:
            raise ReviewError("This review is over.")
        qs = json.loads(run["questions_json"])
        if run["idx"] >= len(qs):
            raise ReviewError("This review is over.")
        q = self._materialize(run, qs, run["idx"])
        st = json.loads(run["state_json"]) if run["state_json"] else {"attempts": 0, "hint": None, "shown": False, "correct": False, "feedback": ""}
        if st["shown"] or st["correct"]:
            raise ReviewError("This question is finished. Go on to the next one.")
        return run, qs, q, st

    def answer(self, run_id: int, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise ReviewError("Write your answer first.")
        run, qs, q, st = self._current(run_id)
        verdict = self._judge(q, text)                                      # model first: a failure changes nothing
        now = self.clock()
        wrong = st["attempts"] + 1
        first = st["attempts"] == 0
        if verdict.correct:
            st.update(correct=True, feedback=plain(verdict.feedback) or "Right.", attempts=wrong)
            if first:
                self._record(run, qs, q, "right", now)
            else:
                st["feedback"] = f"Right this time. It still counts as a miss, so it comes back sooner. {st['feedback']}".strip()
        else:
            if first:
                self._record(run, qs, q, "wrong", now, confused=verdict.confused_with)
            st.update(attempts=wrong, feedback=plain(verdict.feedback) or "Not quite.")
            if wrong >= WRONG_BEFORE_REVEAL:
                st["shown"] = True
            else:
                st["hint"] = self._hint(q, verdict)
        self._save(run_id, state=st)
        return self.view(run_id)

    def hint(self, run_id: int) -> dict:
        _run, _qs, q, st = self._current(run_id)
        if st["hint"]:
            raise ReviewError("You already have a hint for this question.")
        st["hint"] = self._hint(q, chk.Judge(correct=False))
        self._save(run_id, state=st)
        return self.view(run_id)

    def show(self, run_id: int) -> dict:
        """Give up on this question: the answer is shown, and it counts as a miss."""
        run, qs, q, st = self._current(run_id)
        if st["attempts"] == 0:
            self._record(run, qs, q, "wrong", self.clock())
        st["shown"] = True
        self._save(run_id, state=st)
        return self.view(run_id)

    def next(self, run_id: int) -> dict:
        run = self._run(run_id)
        qs = json.loads(run["questions_json"])
        st = json.loads(run["state_json"]) if run["state_json"] else None
        if run["ended_at"]:
            return self.view(run_id)
        if not st or not (st["shown"] or st["correct"]):
            raise ReviewError("Answer this question first, or press “Show answer”.")
        idx = run["idx"] + 1
        results = json.loads(run["results_json"])
        stop = run["mode"] == "concept" and results and results[-1]["result"] == "wrong"           # one missed level ends a concept check
        self.db.execute("UPDATE review_run SET idx = ?, state_json = NULL WHERE id = ?", (idx, run_id))
        if idx >= len(qs) or stop:
            self.db.execute("UPDATE review_run SET ended_at = ? WHERE id = ?", (iso(self.clock()), run_id))
        self.db.commit()
        return self.view(run_id)

    def end(self, run_id: int) -> dict:
        """End a sitting early. What was answered is kept; the rest stays due."""
        self._run(run_id)
        self.db.execute("UPDATE review_run SET ended_at = COALESCE(ended_at, ?) WHERE id = ?", (iso(self.clock()), run_id))
        self.db.commit()
        return self.view(run_id)

    # ---- recording
    def _record(self, run: sqlite3.Row, qs: list[dict], q: dict, result: str, now: datetime, *, confused: str | None = None) -> None:
        """The first answer to a question is the one that counts. Schedule, concept level and skill status all follow from it."""
        db = self.db
        right = result == "right"
        out: dict = {"i": run["idx"], "result": result, "context": q["context"], "level": q["level"]}
        if q.get("item_id"):
            s = schedule_item(db, q["item_id"], right, now)
            out["next"] = s["interval_days"]
        db.execute("INSERT INTO review_result(run_id, item_id, skill_id, concept_id, level, result, at) VALUES (?,?,?,?,?,?,?)",
                   (run["id"], q.get("item_id"), q["skill_id"], q["concept_id"], q["level"], result, iso(now)))
        if q["concept_id"]:
            if right:
                chk.set_level(db, q["concept_id"], q["level"], now)
            else:
                chk.set_level(db, q["concept_id"], "none", now, confused_with=confused)         # records the check time and the confusion, never lowers
                to = drop_after_miss(db, q["concept_id"], q["level"])
                if to:
                    out["dropped_to"] = to
            if run["mode"] == "concept":
                ensure_concept_item(db, q["concept_id"], self._any_skill(q["concept_id"]), now)
        elif not right and q["skill_id"] and skill_failing(db, q["skill_id"]):
            db.execute("UPDATE learner_skill SET status = 'needs_practice' WHERE skill_id = ? AND status = 'passed'", (q["skill_id"],))
            out["needs_practice"] = True
        results = json.loads(run["results_json"]) + [out]
        db.execute("UPDATE review_run SET results_json = ? WHERE id = ?", (json.dumps(results), run["id"]))
        db.commit()

    def _any_skill(self, concept_id: int) -> int | None:
        r = self.db.execute("SELECT skill_id FROM skill_concept WHERE concept_id = ? LIMIT 1", (concept_id,)).fetchone()
        return r["skill_id"] if r else None

    # ---- the end of a sitting
    def summary(self, run: sqlite3.Row, qs: list[dict], results: list[dict]) -> dict:
        right = sum(r["result"] == "right" for r in results)
        wrong = len(results) - right
        rows = [{"context": r["context"], "result": r["result"],
                 "when": ("back tomorrow" if r.get("next", 0) <= 1 else f"back in {int(r['next'])} days") if r.get("next") else None,
                 "dropped_to": r.get("dropped_to")} for r in results]
        notes = []
        for r in results:
            if r.get("needs_practice"):
                notes.append(f"{r['context'].split(' · ')[0]} is back on your skill map as needs practice. You missed it twice in a row.")
            if r.get("dropped_to"):
                notes.append(f"{r['context'].replace('Concept · ', '').split(' · ')[0]} goes back to {r['dropped_to'].capitalize()}. Check it again when you are ready.")
        level = None
        if run["mode"] == "concept":
            m = self.db.execute("SELECT level FROM concept_mastery WHERE concept_id = ?", (run["concept_id"],)).fetchone()
            level = m["level"] if m else "none"
        return {"right": right, "wrong": wrong, "rows": rows, "notes": notes, "level": level, "skipped": len(qs) - len(results) if run["mode"] != "concept" else 0}


def plain(text: str) -> str:
    """Model remarks carry no citations of their own: the app attaches the real ones. Drops anything that looks like one."""
    text = re.sub(r"\s*\[[^\[\]]*\]\]?", "", text or "")
    text = re.sub(r",?\s*ch\.\s*\S+,\s*p\.\s*\d+", "", text)
    return re.sub(r"\s+([.,;])", r"\1", text).strip()


def results_first(st: dict) -> str | None:
    """How the first attempt went: None before any answer."""
    if st["attempts"] == 0 and not st["shown"]:
        return None
    return "right" if st["correct"] and st["attempts"] == 1 else "wrong"
