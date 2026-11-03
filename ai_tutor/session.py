"""The teaching session (SPEC §6.1): a server-side state machine, one phase at a time, advanced only by the learner's own actions.

Phases: diagnose → learn → check → practice → feedback → revise → pass. The phase is stored on `session.phase`, so closing the app
and coming back resumes exactly. A failed model call changes nothing: state is only written after the reply has been checked.
Feedback, the foundations check and the pass check are TASKS_006; their guards are enforced here already.
"""
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from . import assets as assetlib
from . import check as chk
from . import feedback as fbk
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
    "check": {"check", "check_answer", "check_hint", "check_more", "unlock"},
    "practice": {"submit"},
    "feedback": {"feedback", "revise", "reteach", "pass"},
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
                 log_path=None, vision: Callable[[], bool | None] = lambda: None):
        self.db, self.llm, self.embedder, self.clock, self.log_path, self.vision = db, llm, embedder, clock, log_path, vision

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
            "gate": practice_gate(self.db, r["skill_id"]), "messages": msgs, "assets": assetlib.draft_assets(self.db, session_id), **self._extras(r, msgs),
            "allowed": sorted(ALLOWED[r["phase"]] | ANYTIME) if not r["ended_at"] else ["ask"],
        }

    def _extras(self, r: sqlite3.Row, msgs: list[dict]) -> dict:
        """What the screen needs for the check and for what to do after feedback."""
        out: dict = {"check": None, "feedback_pending": False, "feedback_error": None, "route": None, "route_concepts": []}
        if r["phase"] == "check":
            st = chk.load_state(r["check_json"])
            cur = st["current"]
            concept = self._concept(cur["concept_id"]) if cur else None
            out["check"] = {
                "current": {"concept": concept["name"], "concept_id": concept["id"], "level": cur["level"], "prompt": cur["prompt"], "options": chk.options(cur["prompt"]),
                            "attempts": cur["attempts"], "hint_shown": cur["hint_shown"]} if cur else None,
                "remaining_minutes": chk.remaining(self.db, r["skill_id"]) * chk.MINUTES_PER_QUESTION,
                "budget_left": max(0, chk.MAX_QUESTIONS_PER_SITTING - st["total"]), "all_done": chk.target(self.db, r["skill_id"]) is None}
        if r["phase"] == "feedback" and not r["ended_at"]:
            sub = self._latest_submission(r["id"])
            fb = self._latest_feedback(r["id"])
            if sub is not None and (fb is None or fb["submission_id"] != sub["id"]):
                out["feedback_pending"] = True
                err = next((m for m in reversed(msgs) if m["kind"] == "feedback_error"), None)
                out["feedback_error"] = err["content"] if err else None
            elif fb is not None:
                cm = self._concept_mistakes(fb)
                out["route"] = "pass" if fb["passed"] else ("reteach" if cm else "revise")
                out["route_concepts"] = sorted({m["concept"] for m in cm})
        return out

    def compare(self, session_id: int, a: int, b: int) -> dict:
        """Two attempts side by side: both texts and a line-by-line difference (D7)."""
        rows = {v: self.db.execute("SELECT version, text FROM submission WHERE session_id = ? AND version = ?", (session_id, v)).fetchone() for v in (a, b)}
        if not all(rows.values()):
            raise TransitionError("One of those attempts does not exist.")
        return {"a": {"version": a, "text": rows[a]["text"]}, "b": {"version": b, "text": rows[b]["text"]}, "lines": fbk.line_diff(rows[a]["text"] or "", rows[b]["text"] or "")}

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
        self.db.execute("UPDATE session SET check_json = ? WHERE id = ?", (json.dumps(chk.new_state()), r["id"]))
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
        revising = r["attempt"] > 0                          # back from a re-teach: the same task, a new attempt
        now = iso(self.clock())
        self.db.execute("UPDATE session SET phase = ?, timer_limit_s = ?, timer_elapsed_s = 0, timer_since = ?, timer_seen = ?, check_json = NULL WHERE id = ?",
                        ("revise" if revising else "practice", task["minutes"] * 60, now, now, r["id"]))
        self.db.commit()
        if not revising:
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
        try:
            attached = assetlib.check_ready(self.db, r["id"])      # a clip still processing, or one that failed, holds the submission back
        except assetlib.AssetError as e:
            raise TransitionError(str(e)) from e
        if not text and not attached:
            raise TransitionError("Write something, or add a picture or clip, to submit first.")
        if not attached and fbk.too_short(text):
            raise TransitionError("That is too short to give feedback on. Add more of your work, then submit again.")
        elapsed = self._elapsed(r)
        limit = r["timer_limit_s"]
        over = max(0.0, elapsed - limit) if limit else 0.0
        attempt = r["attempt"] + 1
        sub = self.db.execute("INSERT INTO submission(session_id, version, text) VALUES (?,?,?)", (r["id"], attempt, text)).lastrowid
        snapshot = assetlib.attach(self.db, r["id"], sub)
        self.db.execute(
            "UPDATE session SET attempt = ?, phase = 'feedback', draft_text = '', timer_elapsed_s = 0, timer_since = NULL, "
            "overtime_s = overtime_s + ?, minutes = minutes + ? WHERE id = ?", (attempt, over, elapsed / 60, r["id"]))
        self.db.execute("UPDATE learner_skill SET hours_total = hours_total + ?, last_session_at = ? WHERE skill_id = ?",
                        (elapsed / 3600, iso(self.clock()), r["skill_id"]))
        self.add_message(r["id"], "user", text, kind="submission", phase=r["phase"],
                         meta={"submission_id": sub, "version": attempt, "minutes": round(elapsed / 60, 1), "overtime_s": int(over), "assets": snapshot})
        self.db.commit()
        try:                                                  # feedback right after every submission; the work is kept even if it cannot be given now
            self._give_feedback(r["id"])
        except TutorError as e:
            self.add_message(r["id"], "tutor", str(e), kind="feedback_error", phase="feedback", meta={"retryable": e.retryable})

    # --- feedback → revise / re-teach / pass
    def _latest_feedback(self, session_id: int) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT f.* FROM feedback f JOIN submission su ON su.id = f.submission_id WHERE su.session_id = ? ORDER BY su.version DESC, f.id DESC LIMIT 1",
            (session_id,)).fetchone()

    def _latest_submission(self, session_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM submission WHERE session_id = ? ORDER BY version DESC LIMIT 1", (session_id,)).fetchone()

    def _concept_mistakes(self, fb: sqlite3.Row | None) -> list[dict]:
        """Mistakes in the latest feedback that come from misunderstanding a concept: they are re-taught before another attempt (D11)."""
        if fb is None or not fb["mistakes_json"]:
            return []
        return [m for m in json.loads(fb["mistakes_json"]) if m["kind"] == "concept" and m.get("concept_id")]

    def _give_feedback(self, session_id: int) -> None:
        """Judge the latest submission against the checklist, then store the verdicts. Nothing is written if the model's reply is unusable."""
        r = self.row(session_id)
        sub = self._latest_submission(session_id)
        ctx = self.ctx(r)
        bundle = assetlib.bundle_for(self.db, sub["id"])
        if not bundle.empty():
            ctx.vision = self.vision()                         # False only when the server says the model cannot read pictures
        prev_text, before = fbk.previous_text(self.db, session_id, sub["version"])
        out = fbk.generate(ctx, task=json.loads(r["task_json"]) if r["task_json"] else None, work=sub["text"] or "", attempt=sub["version"],
                           previous=prev_text, bundle=bundle)
        diff, since = None, ""
        if sub["version"] > 1 and before:
            old = self.db.execute("SELECT text FROM submission WHERE session_id = ? AND version < ? ORDER BY version DESC LIMIT 1", (session_id, sub["version"])).fetchone()
            diff = fbk.revision_diff(old["text"] or "", sub["text"] or "", before, {x["n"]: x["result"] for x in out["results"]})
            since = out["since_last"] or fbk.diff_sentence(diff)
        now = self.clock()
        fid = fbk.save(self.db, sub["id"], r["skill_id"], out, now)
        blocked = {m["concept_id"] for m in out["mistakes"] if m["kind"] == "concept"}
        for cid in out["concepts_shown"]:                     # applying a concept in the work shows 'use', but only for one already at 'spot'
            lvl = self.db.execute("SELECT level FROM concept_mastery WHERE concept_id = ?", (cid,)).fetchone()
            if cid not in blocked and lvl and sk.LEVEL_ORDER[lvl["level"]] >= sk.LEVEL_ORDER["spot"]:
                chk.set_level(self.db, cid, "use", now)
        cites = list({x["citation"]: {"citation": x["citation"], "chunk_id": x["chunk_id"]} for x in out["results"] if x["citation"]}.values())
        self.add_message(session_id, "tutor", out["summary"], kind="feedback", phase="feedback", citations=cites,
                         meta={"feedback_id": fid, "version": sub["version"], "passed": out["passed"], "summary": out["summary"], "results": out["results"],
                               "fixes": out["fixes"], "mistakes": out["mistakes"], "diff": diff, "since": since})

    def _do_feedback(self, r, _text):
        sub = self._latest_submission(r["id"])
        if sub is None:
            raise TransitionError("There is no work to give feedback on yet.")
        if self.db.execute("SELECT 1 FROM feedback WHERE submission_id = ?", (sub["id"],)).fetchone():
            raise TransitionError("Feedback has already been given on this attempt.")
        self._give_feedback(r["id"])

    def _do_revise(self, r, _text):
        fb = self._latest_feedback(r["id"])
        if fb is None:
            raise TransitionError("Feedback has not been given yet.")
        if fb["passed"]:
            raise TransitionError("Every principle is followed. Finish the skill instead.")
        pending = self._concept_mistakes(fb)
        if pending:
            names = ", ".join(sorted({m["concept"] for m in pending}))
            raise TransitionError(f"A concept needs another look before your next attempt: {names}. Re-teach it first.")
        task = self._ensure_task(r)
        now = iso(self.clock())
        self.db.execute("UPDATE session SET phase = 'revise', timer_limit_s = ?, timer_elapsed_s = 0, timer_since = ?, timer_seen = ? WHERE id = ?",
                        (task["minutes"] * 60, now, now, r["id"]))
        self.db.commit()

    def _do_reteach(self, r, _text):
        """A concept mistake: teach that concept again from a new angle, send it back to be checked, then revise (D11)."""
        mistakes = self._concept_mistakes(self._latest_feedback(r["id"]))
        if not mistakes:
            raise TransitionError("No concept needs re-teaching. Revise your work instead.")
        ctx = self.ctx(r)
        picked: dict[int, dict] = {}
        for m in mistakes:
            picked.setdefault(m["concept_id"], m)
        done = []
        for cid, m in picked.items():                         # all model calls first: a failure leaves the session as it was
            concept = self.db.execute("SELECT id, name, definition FROM concept WHERE id = ?", (cid,)).fetchone()
            done.append((dict(concept), chk.reteach(ctx, dict(concept), f"In their work: {m['tag']}.")))
        for concept, rt in done:
            chk.demote(self.db, concept["id"])
            body = rt["text"] + (f"\n\nExample: {rt['example']}" if rt["example"] else "")
            self.add_message(r["id"], "tutor", body, kind="reteach", phase="check", citations=rt["citations"], meta={"concept": concept["name"]})
        self.db.execute("UPDATE session SET phase = 'check', check_json = ?, timer_since = NULL WHERE id = ?", (json.dumps(chk.new_state()), r["id"]))
        self.db.commit()

    def _do_pass(self, r, _text):
        fb = self._latest_feedback(r["id"])
        if fb is None or not fb["passed"]:
            raise TransitionError("Not passed yet: every principle must be followed.")
        self._complete(r)

    # --- the foundations check (Flow 10)
    def _concept(self, cid: int) -> dict:
        row = self.db.execute("SELECT c.id, c.name, c.definition, COALESCE(m.level, 'none') AS level FROM concept c LEFT JOIN concept_mastery m ON m.concept_id = c.id "
                              "WHERE c.id = ?", (cid,)).fetchone()
        return dict(row)

    def _save_check(self, session_id: int, state: dict) -> None:
        self.db.execute("UPDATE session SET check_json = ? WHERE id = ?", (json.dumps(state), session_id))
        self.db.commit()

    def _do_check(self, r, _text):
        """Ask the next question. Idempotent: if one is open, nothing changes."""
        state = chk.load_state(r["check_json"])
        if state["current"]:
            return
        t = chk.target(self.db, r["skill_id"])
        if t is None:
            last = self.db.execute("SELECT kind FROM message WHERE session_id = ? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
            if not last or last["kind"] != "check_done":
                self.add_message(r["id"], "tutor", "Every concept is at Spot. Practice is unlocked.", kind="check_done", phase="check")
            return
        if state["total"] >= chk.MAX_QUESTIONS_PER_SITTING:
            raise TransitionError("That is enough for one sitting. Take a short break, then press “Keep checking”.")
        concept, level = t
        asked = state["asked"].get(str(concept["id"]), [])
        q = chk.make_question(self.ctx(r), concept, level, asked)
        state["current"] = {"concept_id": concept["id"], "level": level, "prompt": q["prompt"], "answer_key": q["answer_key"], "attempts": 0, "hint_shown": False}
        state["asked"].setdefault(str(concept["id"]), []).append(q["prompt"])
        state["total"] += 1
        self.add_message(r["id"], "tutor", q["prompt"], kind="check_question", phase="check",
                         meta={"concept": concept["name"], "concept_id": concept["id"], "level": level, "options": chk.options(q["prompt"]), "n": state["total"]})
        self._save_check(r["id"], state)

    def _do_check_answer(self, r, text):
        state = chk.load_state(r["check_json"])
        cur = state["current"]
        if not cur:
            raise TransitionError("There is no question to answer. Press “Next question”.")
        if not text:
            raise TransitionError("Write your answer first.")
        concept = self._concept(cur["concept_id"])
        ctx = self.ctx(r)
        verdict = chk.judge(ctx, concept, cur["level"], cur, text)            # model calls first, so a failure writes nothing
        now = self.clock()
        wrong_total = cur["attempts"] + 1
        reteach = None
        if not verdict.correct and wrong_total >= chk.WRONG_BEFORE_RETEACH:
            reteach = chk.reteach(ctx, concept, f"They answered: {text[:300]}")
        hint = ""
        if not verdict.correct and reteach is None:
            hint = (verdict.hint or "").strip() or chk.make_hint(ctx, concept, cur)
        self.add_message(r["id"], "user", text, kind="check_answer", phase="check")
        if verdict.correct:
            chk.set_level(self.db, concept["id"], "define" if cur["level"] == "define" else "spot", now)
            state["current"] = None
            self.add_message(r["id"], "tutor", verdict.feedback.strip() or "Correct.", kind="check_result", phase="check",
                             meta={"correct": True, "concept": concept["name"], "level": cur["level"]})
        elif reteach is None:
            chk.set_level(self.db, concept["id"], "none", now, confused_with=verdict.confused_with)
            cur["attempts"], cur["hint_shown"] = wrong_total, True
            self.add_message(r["id"], "tutor", f"{verdict.feedback.strip()}\nHint: {hint}".strip(), kind="check_result", phase="check",
                             meta={"correct": False, "concept": concept["name"], "level": cur["level"], "hint": hint})
        else:
            chk.set_level(self.db, concept["id"], "none", now, confused_with=verdict.confused_with)
            _, hits = chk.definition_block(self.db, concept)
            cites = [{"citation": cite(h), "chunk_id": h.chunk_id} for h in hits[:1]]
            answer = f"{verdict.feedback.strip()}\nThe answer: {cur['answer_key']} {cites[0]['citation'] if cites else ''}".strip()
            self.add_message(r["id"], "tutor", answer, kind="check_result", phase="check", citations=cites,
                             meta={"correct": False, "revealed": True, "concept": concept["name"], "level": cur["level"]})
            body = reteach["text"] + (f"\n\nExample: {reteach['example']}" if reteach["example"] else "")
            self.add_message(r["id"], "tutor", body, kind="check_reteach", phase="check", citations=reteach["citations"], meta={"concept": concept["name"]})
            state["current"] = None
        self._save_check(r["id"], state)

    def _do_check_hint(self, r, _text):
        state = chk.load_state(r["check_json"])
        cur = state["current"]
        if not cur:
            raise TransitionError("There is no question to give a hint for.")
        if cur["hint_shown"]:
            raise TransitionError("You already have a hint for this question.")
        hint = chk.make_hint(self.ctx(r), self._concept(cur["concept_id"]), cur)
        cur["hint_shown"] = True
        self.add_message(r["id"], "tutor", f"Hint: {hint}", kind="check_hint", phase="check", meta={"concept": self._concept(cur["concept_id"])["name"]})
        self._save_check(r["id"], state)

    def _do_check_more(self, r, _text):
        state = chk.load_state(r["check_json"])
        state["total"] = 0
        self._save_check(r["id"], state)

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
