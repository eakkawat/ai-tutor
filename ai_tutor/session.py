"""The teaching session (SPEC §6.1): a server-side state machine, one phase at a time, advanced only by the learner's own actions.

Phases: diagnose → learn → check → practice → feedback → revise → pass. The phase is stored on `session.phase`, so closing the app
and coming back resumes exactly. A failed model call changes nothing: state is only written after the reply has been checked.
Feedback, the foundations check and the pass check are TASKS_006; their guards are enforced here already.
"""
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from . import skills as sk
from .citations import cite
from .embeddings import Embedder
from .llm.client import LLMClient
from .teaching import Ctx, TutorError, profile_summary

PHASES = ("diagnose", "learn", "check", "practice", "feedback", "revise", "pass")
# Which learner actions each phase accepts. The app waits for the learner between phases.
ALLOWED: dict[str, set[str]] = {
    "diagnose": {"begin", "answer", "advance"},
    "learn": {"continue"},
    "check": {"unlock"},
    "practice": {"submit"},
    "feedback": {"revise", "pass"},
    "revise": {"submit"},
    "pass": set(),
}
ANYTIME = {"ask", "pause_timer", "resume_timer", "heartbeat"}
TIMED = {"practice", "revise"}
HEARTBEAT_GRACE_S = 90          # a running timer counts at most this long past the last sign of life from the screen
DEFAULT_TASK_MINUTES = 20
REVIEW_FIRST_INTERVAL = timedelta(days=1)


class TransitionError(Exception):
    """The learner asked for something this phase does not allow. The message is shown as is."""


Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse(s: str | None) -> datetime | None:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) if s else None


# ---------- the practice gate (SPEC §6.1.2)

def practice_gate(db: sqlite3.Connection, skill_id: int) -> dict:
    """Practice needs every concept of the skill at 'spot' or better. Says which ones are missing."""
    rows = db.execute(
        "SELECT c.id, c.name, COALESCE(m.level, 'none') AS level FROM skill_concept sc JOIN concept c ON c.id = sc.concept_id "
        "LEFT JOIN concept_mastery m ON m.concept_id = c.id WHERE sc.skill_id = ? ORDER BY c.name", (skill_id,)).fetchall()
    missing = [{"id": r["id"], "name": r["name"], "level": r["level"]} for r in rows if sk.LEVEL_ORDER[r["level"]] < sk.LEVEL_ORDER["spot"]]
    total = len(rows)
    done = total - len(missing)
    msg = None if not missing else (f"Practice unlocks when all {total} concept{'s' if total != 1 else ''} reach Spot. {done} of {total} done. "
                                    f"Missing: {', '.join(m['name'] for m in missing)}.")
    return {"unlocked": not missing, "done": done, "total": total, "missing": missing, "message": msg,
            "concepts": [{"id": r["id"], "name": r["name"], "level": r["level"]} for r in rows]}


class SessionService:
    def __init__(self, db: sqlite3.Connection, *, llm: LLMClient | None, embedder: Embedder | None, clock: Clock = utcnow,
                 log_path=None):
        self.db, self.llm, self.embedder, self.clock, self.log_path = db, llm, embedder, clock, log_path

    # ---------- reading
    def row(self, session_id: int) -> sqlite3.Row:
        r = self.db.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
        if r is None:
            raise TransitionError("This session no longer exists.")
        return r

    def ctx(self, r: sqlite3.Row) -> Ctx:
        from . import projects
        skill = sk.skill_detail(self.db, r["skill_id"])
        project = projects.view(self.db, projects.get(self.db, r["project_id"]))
        return Ctx(self.db, self.llm, self.embedder, skill, project, r["id"], profile=profile_summary(self.db))

    def timer(self, r: sqlite3.Row) -> dict:
        now, since, seen = self.clock(), parse(r["timer_since"]), parse(r["timer_seen"])
        elapsed = r["timer_elapsed_s"]
        if since:
            end = min(now, (seen or since) + timedelta(seconds=HEARTBEAT_GRACE_S))
            elapsed += max(0.0, (end - since).total_seconds())
        limit = r["timer_limit_s"]
        return {"limit_s": limit, "elapsed_s": int(elapsed), "running": since is not None, "left_s": int(limit - elapsed) if limit else None,
                "overtime_s": int(max(0.0, elapsed - limit)) if limit else 0}

    def view(self, session_id: int) -> dict:
        r = self.row(session_id)
        self._seen(r)
        r = self.row(session_id)
        skill = sk.skill_detail(self.db, r["skill_id"])
        ls = self.db.execute("SELECT difficulty_current, hours_total, level FROM learner_skill WHERE skill_id = ?", (r["skill_id"],)).fetchone()
        proj = self.db.execute("SELECT id, name, minutes_per_session FROM project WHERE id = ?", (r["project_id"],)).fetchone()
        msgs = [{"id": m["id"], "role": m["role"], "kind": m["kind"], "phase": m["phase"], "content": m["content"],
                 "citations": json.loads(m["citations_json"] or "[]"), "meta": json.loads(m["meta_json"] or "{}"), "at": m["created_at"]}
                for m in self.db.execute("SELECT * FROM message WHERE session_id = ? ORDER BY id", (session_id,))]
        return {
            "id": r["id"], "phase": r["phase"], "ended": r["ended_at"] is not None, "attempt": r["attempt"], "next_attempt": r["attempt"] + 1,
            "skill": {"id": skill["id"], "name": skill["name"], "description": skill["description"], "principles": skill["principles"],
                      "concepts": skill["concepts"]},
            "project": {"id": proj["id"], "name": proj["name"], "minutes_per_session": proj["minutes_per_session"]},
            "difficulty": ls["difficulty_current"] if ls else 3, "hours": round(ls["hours_total"], 2) if ls else 0.0,
            "task": json.loads(r["task_json"]) if r["task_json"] else None, "draft": r["draft_text"], "timer": self.timer(r),
            "diagnosis": json.loads(r["diagnosis_json"]) if r["diagnosis_json"] else None,
            "gate": practice_gate(self.db, r["skill_id"]), "messages": msgs,
            "allowed": sorted(ALLOWED[r["phase"]] | ANYTIME) if not r["ended_at"] else ["ask"],
        }

    # ---------- small writes
    def _seen(self, r: sqlite3.Row) -> None:
        """The screen is open: a running timer keeps counting.

        If the screen was away longer than the grace period (the app was closed), the timer stopped when it was last seen: the time
        until then is kept and the timer is paused, so a closed laptop never counts as practice."""
        if not r["timer_since"]:
            return
        now, since = self.clock(), parse(r["timer_since"])
        seen = parse(r["timer_seen"]) or since
        if now - seen > timedelta(seconds=HEARTBEAT_GRACE_S):
            kept = max(0.0, (seen + timedelta(seconds=HEARTBEAT_GRACE_S) - since).total_seconds())
            self.db.execute("UPDATE session SET timer_elapsed_s = timer_elapsed_s + ?, timer_since = NULL WHERE id = ?", (kept, r["id"]))
        else:
            self.db.execute("UPDATE session SET timer_seen = ? WHERE id = ?", (iso(now), r["id"]))
        self.db.commit()

    def add_message(self, session_id: int, role: str, content: str, *, kind: str, phase: str, citations: list[dict] | None = None,
                    meta: dict | None = None) -> int:
        mid = self.db.execute(
            "INSERT INTO message(session_id, role, content, citations_json, phase, kind, meta_json) VALUES (?,?,?,?,?,?,?)",
            (session_id, role, content, json.dumps(citations or []), phase, kind, json.dumps(meta or {}))).lastrowid
        self.db.commit()
        return mid

    def save_draft(self, session_id: int, text: str) -> None:
        r = self.row(session_id)
        if r["phase"] in TIMED:
            self.db.execute("UPDATE session SET draft_text = ? WHERE id = ?", (text, session_id))
            self._seen(r)
            self.db.commit()

    def _set_phase(self, session_id: int, phase: str) -> None:
        self.db.execute("UPDATE session SET phase = ? WHERE id = ?", (phase, session_id))
        self.db.commit()

    # ---------- the one entry point for learner actions
    def act(self, session_id: int, action: str, text: str = "") -> dict:
        r = self.row(session_id)
        if r["ended_at"] and action != "ask":
            raise TransitionError("This session is finished. Start a new skill from Home.")
        if action not in ALLOWED[r["phase"]] | ANYTIME:
            raise TransitionError(f"“{action}” is not available in the {r['phase']} phase.")
        self._seen(r)
        r = self.row(session_id)
        getattr(self, f"_do_{action}")(r, text.strip())
        return self.view(session_id)

    # --- diagnose
    def _do_begin(self, r, _text):
        if self._has(r["id"], "diagnose_task"):
            return                                           # asked already: opening the screen again must not ask twice
        from .teaching import make_diagnose_task
        task = make_diagnose_task(self.ctx(r))
        self.add_message(r["id"], "tutor", task, kind="diagnose_task", phase="diagnose")

    def _do_answer(self, r, text):
        if not text:
            raise TransitionError("Write your answer first.")
        task = self.db.execute("SELECT content FROM message WHERE session_id = ? AND kind = 'diagnose_task' ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
        if task is None:
            raise TransitionError("There is no task to answer yet.")
        if r["diagnosis_json"]:
            raise TransitionError("You have already answered. Continue to the lesson.")
        from .teaching import evaluate_diagnosis
        d = evaluate_diagnosis(self.ctx(r), task["content"], text)
        self.add_message(r["id"], "user", text, kind="answer", phase="diagnose")
        self.db.execute("UPDATE session SET diagnosis_json = ? WHERE id = ?", (json.dumps(d), r["id"]))
        self.db.execute("UPDATE learner_skill SET level = ? WHERE skill_id = ?", (d["level"], r["skill_id"]))
        self.add_message(r["id"], "tutor", f"{d['can_do']}\nGap: {d['gap']}", kind="diagnosis", phase="diagnose", meta=d)

    def _do_advance(self, r, _text):
        if not r["diagnosis_json"]:
            raise TransitionError("Answer the diagnostic task first.")
        d = json.loads(r["diagnosis_json"])
        if d["meets_all"]:
            self.add_message(r["id"], "tutor", "Your work already follows every principle for this skill. There is nothing to teach you here.", kind="note", phase="diagnose")
            self._complete(r)
            return
        self._enter_learn(r)

    def _enter_learn(self, r):
        from .teaching import make_lesson
        lesson = make_lesson(self.ctx(r))                    # raises before anything is written if it cannot be grounded
        body = lesson.body + (f"\n\nExample: {lesson.example}" if lesson.example else "")
        self.add_message(r["id"], "tutor", body, kind="learn", phase="learn", citations=lesson.citations,
                         meta={"title": lesson.title, "example": lesson.example, "outside": lesson.outside})
        self._set_phase(r["id"], "learn")

    # --- learn → check → practice
    def _do_continue(self, r, _text):
        self._set_phase(r["id"], "check")
        try:                                                 # have the practice task ready before the learner needs it
            self._ensure_task(self.row(r["id"]))
        except TutorError:
            pass                                             # generated again when practice unlocks

    def _do_unlock(self, r, _text):
        gate = practice_gate(self.db, r["skill_id"])
        if not gate["unlocked"]:
            raise TransitionError(gate["message"])
        r = self.row(r["id"])
        task = self._ensure_task(r)
        now = iso(self.clock())
        self.db.execute("UPDATE session SET phase = 'practice', timer_limit_s = ?, timer_elapsed_s = 0, timer_since = ?, timer_seen = ? WHERE id = ?",
                        (task["minutes"] * 60, now, now, r["id"]))
        self.db.commit()
        self._task_message(r["id"], task, "practice")

    def _ensure_task(self, r) -> dict:
        if r["task_json"]:
            return json.loads(r["task_json"])
        from .teaching import make_practice_task
        ls = self.db.execute("SELECT difficulty_current FROM learner_skill WHERE skill_id = ?", (r["skill_id"],)).fetchone()
        task = make_practice_task(self.ctx(r), r["attempt"] + 1, ls["difficulty_current"] if ls else 3)
        self.db.execute("UPDATE session SET task_json = ? WHERE id = ?", (json.dumps(task), r["id"]))
        self.db.commit()
        return task

    def _task_message(self, session_id: int, task: dict, phase: str) -> None:
        self.add_message(session_id, "tutor", f"{task['title']}\n{task['instructions']}", kind="practice_task", phase=phase, meta=task)

    # --- practice and revise: the timer and the submission
    def _elapsed(self, r) -> float:
        return float(self.timer(r)["elapsed_s"])

    def _do_pause_timer(self, r, _text):
        if r["phase"] not in TIMED or not r["timer_since"]:
            raise TransitionError("There is no running timer.")
        self.db.execute("UPDATE session SET timer_elapsed_s = ?, timer_since = NULL WHERE id = ?", (self._elapsed(r), r["id"]))
        self.db.commit()

    def _do_resume_timer(self, r, _text):
        if r["phase"] not in TIMED or r["timer_since"]:
            raise TransitionError("The timer is already running.")
        now = iso(self.clock())
        self.db.execute("UPDATE session SET timer_since = ?, timer_seen = ? WHERE id = ?", (now, now, r["id"]))
        self.db.commit()

    def _do_heartbeat(self, r, _text):
        self._seen(r)

    def _do_submit(self, r, text):
        if not text:
            raise TransitionError("Write something to submit first.")
        elapsed = self._elapsed(r)
        limit = r["timer_limit_s"]
        over = max(0.0, elapsed - limit) if limit else 0.0
        attempt = r["attempt"] + 1
        sub = self.db.execute("INSERT INTO submission(session_id, version, text) VALUES (?,?,?)", (r["id"], attempt, text)).lastrowid
        self.db.execute(
            "UPDATE session SET attempt = ?, phase = 'feedback', draft_text = '', timer_elapsed_s = 0, timer_since = NULL, "
            "overtime_s = overtime_s + ?, minutes = minutes + ? WHERE id = ?", (attempt, over, elapsed / 60, r["id"]))
        self.db.execute("UPDATE learner_skill SET hours_total = hours_total + ?, last_session_at = ? WHERE skill_id = ?",
                        (elapsed / 3600, iso(self.clock()), r["skill_id"]))
        self.add_message(r["id"], "user", text, kind="submission", phase=r["phase"],
                         meta={"submission_id": sub, "version": attempt, "minutes": round(elapsed / 60, 1), "overtime_s": int(over)})
        self.db.commit()

    # --- feedback → revise / pass (their content is TASKS_006; the guards are enforced now)
    def _latest_feedback(self, session_id: int) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT f.* FROM feedback f JOIN submission su ON su.id = f.submission_id WHERE su.session_id = ? ORDER BY su.version DESC, f.id DESC LIMIT 1",
            (session_id,)).fetchone()

    def _do_revise(self, r, _text):
        if self._latest_feedback(r["id"]) is None:
            raise TransitionError("Feedback has not been given yet.")
        task = self._ensure_task(r)
        now = iso(self.clock())
        self.db.execute("UPDATE session SET phase = 'revise', timer_limit_s = ?, timer_elapsed_s = 0, timer_since = ?, timer_seen = ? WHERE id = ?",
                        (task["minutes"] * 60, now, now, r["id"]))
        self.db.commit()

    def _do_pass(self, r, _text):
        fb = self._latest_feedback(r["id"])
        if fb is None or not fb["passed"]:
            raise TransitionError("Not passed yet: every principle must be followed.")
        self._complete(r)

    # --- pass
    def _complete(self, r) -> None:
        """Mark the skill passed, close the session, and schedule its first reviews. Hours were logged as each task was submitted."""
        now = self.clock()
        self.db.execute("UPDATE learner_skill SET status = 'passed', last_session_at = ? WHERE skill_id = ?", (iso(now), r["skill_id"]))
        self.db.execute("UPDATE session SET phase = 'pass', ended_at = ?, timer_since = NULL WHERE id = ?", (iso(now), r["id"]))
        due = iso(now + REVIEW_FIRST_INTERVAL)
        skill = sk.skill_detail(self.db, r["skill_id"])
        self.db.execute("INSERT INTO review_item(skill_id, level, question, answer, due_at) VALUES (?,?,?,?,?)",
                        (skill["id"], "use", f"What must work on “{skill['name']}” do to pass? Name the principles.",
                         "; ".join(p["principle"] for p in skill["principles"]), due))
        for c in skill["concepts"]:
            q = (self.db.execute("SELECT * FROM concept_question WHERE concept_id = ? AND level = 'spot' LIMIT 1", (c["id"],)).fetchone()
                 or self.db.execute("SELECT * FROM concept_question WHERE concept_id = ? AND level = 'define' LIMIT 1", (c["id"],)).fetchone())
            if q:
                self.db.execute("INSERT INTO review_item(skill_id, concept_id, level, question, answer, due_at) VALUES (?,?,?,?,?,?)",
                                (skill["id"], c["id"], q["level"], q["prompt"], q["answer_key"], due))
        self.db.commit()

    # --- questions at any time (D9, D10)
    def _do_ask(self, r, text):
        if not text:
            raise TransitionError("Type your question first.")
        from .teaching import answer_question
        ans = answer_question(self.ctx(r), text, r["phase"])
        self.add_message(r["id"], "user", text, kind="question", phase=r["phase"])
        self.add_message(r["id"], "tutor", ans.text, kind="qa", phase=r["phase"], citations=ans.citations, meta={"steered": ans.steered, "outside": ans.outside})

    def _has(self, session_id: int, kind: str) -> bool:
        return self.db.execute("SELECT 1 FROM message WHERE session_id = ? AND kind = ? LIMIT 1", (session_id, kind)).fetchone() is not None

    # ---------- "This felt wrong" (G1)
    def felt_wrong(self, message_id: int, note: str) -> dict:
        m = self.db.execute("SELECT * FROM message WHERE id = ?", (message_id,)).fetchone()
        if m is None:
            raise TransitionError("This message no longer exists.")
        entry = {"at": iso(self.clock()), "message_id": m["id"], "session_id": m["session_id"], "phase": m["phase"], "note": note.strip(),
                 "message": m["content"]}
        if self.log_path is None:
            raise TransitionError("The feedback log is not set up.")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"ok": True}

    def citation_for(self, chunk_id: int) -> str | None:
        r = self.db.execute("SELECT c.*, s.title AS source_title FROM chunk c JOIN source s ON s.id = c.source_id WHERE c.id = ?", (chunk_id,)).fetchone()
        return cite(r) if r else None
