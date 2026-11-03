"""Flow calibration (SPEC §6.3): keep each task in the learner's flow zone, one lever at a time.

After a task the learner taps Too easy / Just right / Too hard. Objective signals from the work back it up (accuracy, time, revisions,
repeated mistakes). The rules are explicit in the spec, so they run in code, not in a model call:

* Just right: nothing changes.
* Too easy: make it harder by exactly one lever.
* Too hard: make it easier by exactly one lever, except in the first ~3 hours on a skill (the frustration barrier). There the level is
  kept unless the learner is truly stuck: the same mistake twice in a row, no improvement after a revision, or "I don't know where to start".

A lever is one thing in the task's set-up: a support (worked example, beat template, smaller scope, hint, split into steps) that can be
added or removed, or a constraint (extra constraint, shorter time limit, higher standard, another skill combined in) that can be added
or taken away. Every decision says in one line what changed, or why nothing did.
"""
import copy
import itertools
import json
import sqlite3
from dataclasses import asdict, dataclass, field

BARRIER_HOURS = 3.0
LEVEL_MIN, LEVEL_MAX = 1, 5
DEFAULT_LEVEL = 3
SUCCESS_AT = 0.7                     # a task counts as a success when this share of the principles is followed
TARGET_SUCCESS = (0.70, 0.85)        # "succeed most of the time, but only with a stretch"
SUCCESS_WINDOW = 5
DEFAULT_STATE = {"supports": ["template"], "constraints": [], "combine_with": None}

SUPPORTS = {"worked_example": "a worked example", "template": "a beat template", "smaller_scope": "a smaller scope", "hint": "a hint",
            "split_steps": "the task split into steps"}
CONSTRAINTS = {"constraint": "an extra constraint", "time_limit": "a shorter time limit", "higher_standard": "a higher standard", "combine": "another skill combined in"}
LABEL = {**SUPPORTS, **CONSTRAINTS}
SHORT = {"worked_example": "Worked example", "template": "Beat template", "smaller_scope": "Smaller scope", "hint": "Hint", "split_steps": "Split into steps",
         "constraint": "Extra constraint", "time_limit": "Shorter time limit", "higher_standard": "Higher standard", "combine": "Combined skill"}
ADD_ORDER = ["worked_example", "smaller_scope", "hint", "split_steps", "template"]      # which support to add first when it has to get easier
CONSTRAINT_ORDER = ["constraint", "time_limit", "higher_standard", "combine"]            # which constraint to add first when it has to get harder


SENTENCES = {
    "add_worked_example": "A worked example is added for {n}.", "add_template": "A beat template is added for {n}.",
    "add_smaller_scope": "The scope is made smaller for {n}.", "add_hint": "A hint is added for {n}.", "add_split_steps": "The task is split into steps for {n}.",
    "remove_worked_example": "The worked example is removed for {n}.", "remove_template": "The beat template is removed for {n}.",
    "remove_smaller_scope": "The smaller scope is removed for {n}.", "remove_hint": "The hint is removed for {n}.", "remove_split_steps": "The split into steps is removed for {n}.",
    "add_constraint": "One extra constraint is added for {n}.", "add_time_limit": "The time limit is shortened for {n}.",
    "add_higher_standard": "A higher standard is asked for in {n}.", "add_combine": "{skill} is combined into {n}.",
    "relax_constraint": "The extra constraint is removed for {n}.", "relax_time_limit": "The shorter time limit is removed for {n}.",
    "relax_higher_standard": "The higher standard is relaxed for {n}.", "relax_combine": "The combined skill is removed for {n}.",
}


@dataclass(frozen=True)
class Lever:
    id: str
    name: str                         # the support or constraint it touches
    op: str                           # add | remove
    group: str                        # support | constraint

    @property
    def direction(self) -> str:
        return "easier" if (self.group == "support") == (self.op == "add") else "harder"

    def sentence(self, attempt: int, combine_with: str | None = None) -> str:
        """What changed, in one plain sentence for the learner."""
        n = f"attempt {attempt}"
        return SENTENCES[self.id].format(n=n, skill=combine_with or "Another skill you have passed")


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def lever(op: str, name: str) -> Lever:
    group = "support" if name in SUPPORTS else "constraint"
    prefix = {("support", "add"): "add_", ("support", "remove"): "remove_", ("constraint", "add"): "add_", ("constraint", "remove"): "relax_"}[(group, op)]
    return Lever(prefix + name, name, op, group)


def all_levers() -> list[Lever]:
    return [lever(op, n) for n in LABEL for op in ("add", "remove")]


LEVERS = {lv.id: lv for lv in all_levers()}


def get_state(raw: str | None) -> dict:
    s = json.loads(raw) if raw else copy.deepcopy(DEFAULT_STATE)
    return {"supports": list(s.get("supports", [])), "constraints": list(s.get("constraints", [])), "combine_with": s.get("combine_with")}


def apply(state: dict, lv: Lever, combine_with: str | None = None) -> dict:
    """The set-up after pulling one lever. Exactly one entry in `supports` or `constraints` is added or removed."""
    s = copy.deepcopy(state)
    key = "supports" if lv.group == "support" else "constraints"
    if lv.op == "add":
        if lv.name in s[key]:
            raise ValueError(f"{lv.name} is already on")
        s[key].append(lv.name)
        if lv.name == "combine":
            s["combine_with"] = combine_with
    else:
        if lv.name not in s[key]:
            raise ValueError(f"{lv.name} is not on")
        s[key].remove(lv.name)
        if lv.name == "combine":
            s["combine_with"] = None
    return s


def candidates(state: dict, direction: str, *, can_combine: bool) -> list[Lever]:
    """Every lever that would make the task easier or harder from here, in the order they are tried when there is no history to go on."""
    out: list[Lever] = []
    if direction == "easier":
        out += [lever("remove", c) for c in reversed(state["constraints"])]                 # first take back what made it harder, latest first
        out += [lever("add", s) for s in ADD_ORDER if s not in state["supports"]]
    else:
        out += [lever("remove", s) for s in reversed(state["supports"])]                    # first take away help, latest first
        out += [lever("add", c) for c in CONSTRAINT_ORDER if c not in state["constraints"] and (c != "combine" or can_combine)]
    return out


def choose(cands: list[Lever], scores: dict[str, float]) -> Lever | None:
    """The lever that has moved this learner to 'just right' before; with no history, the first in the default order. Levers that
    failed before are only used when nothing else is left."""
    if not cands:
        return None
    order = {lv.id: i for i, lv in enumerate(cands)}
    good = [lv for lv in cands if scores.get(lv.id, 0) >= 0]
    return min(good or cands, key=lambda lv: (-scores.get(lv.id, 0), order[lv.id]))


# ---------- signals

@dataclass
class Signals:
    accuracy: float = 0.0                 # followed = 1, partly = 0.5, not followed = 0, averaged over the principles
    prev_accuracy: float | None = None
    time_ratio: float | None = None       # time on the task over the time given
    attempt: int = 1
    repeated_mistake: bool = False        # the same kind of mistake on the same principle in two feedbacks in a row
    improved: bool | None = None          # None on a first attempt
    no_improvement: bool = False          # a revision that did not move forward
    cant_start: bool = False              # the learner said so
    hours: float = 0.0
    success_rate: float | None = None
    reasons_stuck: list[str] = field(default_factory=list)

    @property
    def stuck(self) -> bool:
        return bool(self.reasons_stuck)


def _score(results: list[str]) -> float:
    return sum({"followed": 1.0, "partly": 0.5}.get(r, 0.0) for r in results) / max(len(results), 1)


def _verdicts(db: sqlite3.Connection, feedback_id: int) -> list[str]:
    return [r["result"] for r in db.execute(
        "SELECT pc.result FROM principle_check pc JOIN skill_principle sp ON sp.id = pc.principle_id WHERE pc.feedback_id = ? ORDER BY sp.\"order\", sp.id", (feedback_id,))]


def success_rate(db: sqlite3.Connection, skill_id: int) -> float | None:
    """Share of the last few attempts at this skill that were a success (most principles followed). Aim: 70 to 85 percent."""
    rows = db.execute(
        "SELECT f.id FROM feedback f JOIN submission su ON su.id = f.submission_id JOIN session se ON se.id = su.session_id WHERE se.skill_id = ? ORDER BY f.id DESC LIMIT ?",
        (skill_id, SUCCESS_WINDOW)).fetchall()
    if not rows:
        return None
    wins = sum(_score(_verdicts(db, r["id"])) >= SUCCESS_AT for r in rows)
    return wins / len(rows)


def collect(db: sqlite3.Connection, feedback_id: int, *, cant_start: bool = False) -> Signals:
    fb = db.execute("SELECT f.*, su.session_id, su.version FROM feedback f JOIN submission su ON su.id = f.submission_id WHERE f.id = ?", (feedback_id,)).fetchone()
    sess = db.execute("SELECT * FROM session WHERE id = ?", (fb["session_id"],)).fetchone()
    ls = db.execute("SELECT hours_total FROM learner_skill WHERE skill_id = ?", (sess["skill_id"],)).fetchone()
    now = _verdicts(db, feedback_id)
    sig = Signals(accuracy=_score(now), attempt=fb["version"], cant_start=cant_start, hours=ls["hours_total"] if ls else 0.0, success_rate=success_rate(db, sess["skill_id"]))
    msg = db.execute("SELECT meta_json FROM message WHERE session_id = ? AND kind = 'submission' ORDER BY id DESC LIMIT 1", (fb["session_id"],)).fetchone()
    if msg and sess["timer_limit_s"]:
        sig.time_ratio = round(json.loads(msg["meta_json"]).get("minutes", 0) * 60 / sess["timer_limit_s"], 2)
    prev = db.execute(
        "SELECT f.* FROM feedback f JOIN submission su ON su.id = f.submission_id WHERE su.session_id = ? AND su.version < ? ORDER BY su.version DESC LIMIT 1",
        (fb["session_id"], fb["version"])).fetchone()
    if prev is not None:
        before = _verdicts(db, prev["id"])
        sig.prev_accuracy = _score(before)
        rank = {"not": 0, "partly": 1, "followed": 2}
        better = any(rank[a] > rank[b] for a, b in zip(now, before, strict=False))
        worse = any(rank[a] < rank[b] for a, b in zip(now, before, strict=False))
        sig.improved = sig.accuracy > sig.prev_accuracy or (better and not worse)
        sig.no_improvement = not sig.improved
        keys = lambda row: {(m["n"], m["kind"]) for m in json.loads(row["mistakes_json"] or "[]")}
        tags = lambda row: {m["tag"].lower() for m in json.loads(row["mistakes_json"] or "[]")}
        sig.repeated_mistake = bool(keys(fb) & keys(prev)) or bool(tags(fb) & tags(prev))
    if sig.repeated_mistake:
        sig.reasons_stuck.append("made the same mistake twice in a row")
    if sig.no_improvement:
        sig.reasons_stuck.append("did not improve after revising")
    if cant_start:
        sig.reasons_stuck.append("said you do not know where to start")
    return sig


def infer_rating(sig: Signals) -> str:
    """When the learner moves on without tapping: judge from the work. Easy = a perfect first attempt done well inside the time;
    hard = most principles missed, or revising again and again without moving forward."""
    if sig.attempt == 1 and sig.accuracy >= 0.99 and (sig.time_ratio is None or sig.time_ratio <= 0.6):
        return "too_easy"
    if sig.accuracy < 0.4 or (sig.attempt >= 3 and sig.no_improvement):
        return "too_hard"
    return "just_right"


# ---------- the decision

@dataclass
class Decision:
    changed: bool
    lever: Lever | None
    classification: str                  # on_target | productive_struggle | overwhelm | too_easy | too_hard | at_limit | no_lever
    message: str
    level_after: int
    state_after: dict
    verdict: str = ""                    # "One change:" | "No change:" | "Keeping the level."


def lever_scores(db: sqlite3.Connection) -> dict[str, float]:
    """What has worked for this learner: a lever is credited when the next rating after it was 'just right', and debited when the
    same complaint came back (a smaller debit when it swung the other way)."""
    scores: dict[str, float] = {}
    rows = db.execute("SELECT id, skill_id, rating_used, lever_changed FROM flow_rating WHERE skill_id IS NOT NULL ORDER BY skill_id, id").fetchall()
    for a, b in itertools.pairwise(rows):
        if a["skill_id"] != b["skill_id"] or not a["lever_changed"]:
            continue
        delta = 1.0 if b["rating_used"] == "just_right" else (-1.0 if b["rating_used"] == a["rating_used"] else -0.5)
        scores[a["lever_changed"]] = scores.get(a["lever_changed"], 0.0) + delta
    return scores


def decide(rating: str, level: int, state: dict, sig: Signals, scores: dict[str, float], *, attempt_next: int, passed_skills: list[str]) -> Decision:
    def hold(cls: str, verdict: str, text: str) -> Decision:
        return Decision(False, None, cls, f"{verdict} {text}", level, state)

    def change(direction: str, cls: str, why: str = "") -> Decision:
        cands = candidates(state, direction, can_combine=bool(passed_skills))
        lv = choose(cands, scores)
        if lv is None:
            return hold("no_lever", "No change:", f"nothing is left to make it {direction}, so difficulty stays at {level}.")
        after = apply(state, lv, passed_skills[0] if passed_skills else None)
        new_level = min(LEVEL_MAX, max(LEVEL_MIN, level + (1 if direction == "harder" else -1)))
        sentence = lv.sentence(attempt_next, after.get("combine_with"))
        if sentence.startswith(("A ", "The ", "One ")):               # "One change: the beat template is removed...", but a skill's name keeps its capital
            sentence = sentence[0].lower() + sentence[1:]
        return Decision(True, lv, cls, f"One change: {sentence} Everything else stays the same.{(' ' + why) if why else ''}",
                        new_level, after, "One change:")

    if rating == "just_right":
        return hold("on_target", "No change:", f"difficulty stays at {level}.")
    if rating == "too_easy":
        if level >= LEVEL_MAX:
            return hold("at_limit", "No change:", f"this is already the hardest setting, so difficulty stays at {LEVEL_MAX}.")
        return change("harder", "too_easy")
    # too_hard
    if level <= LEVEL_MIN:
        return hold("at_limit", "No change:", f"this is already the easiest setting, so difficulty stays at {LEVEL_MIN}.")
    if sig.hours < BARRIER_HOURS and not sig.stuck:                           # the frustration barrier: productive struggle keeps the level
        first = choose(candidates(state, "easier", can_combine=False), scores)
        nxt = f" If attempt {attempt_next} repeats the same mistake or does not improve, I'll add {LABEL[first.name]}." if first and first.op == "add" else ""
        why = "your work improved between attempts" if sig.improved else "this is your first try at this task" if sig.attempt == 1 else "your last attempt moved forward"
        return Decision(False, None, "productive_struggle",
                        f"Keeping the level. You're under {BARRIER_HOURS:g} hours on this skill and {why}, so this is productive struggle, not overwhelm.{nxt}",
                        level, state, "Keeping the level.")
    if sig.hours < BARRIER_HOURS:
        return change("easier", "overwhelm", f"You {' and '.join(sig.reasons_stuck)}, so I am adding support.")
    return change("easier", "too_hard", f"You are past the first {BARRIER_HOURS:g} hours on this skill, so I am adding support.")


# ---------- storing

def passed_skill_names(db: sqlite3.Connection, skill_id: int) -> list[str]:
    """Skills already passed, same domain first and most recent first: what can be combined into a harder task."""
    dom = db.execute("SELECT domain FROM skill WHERE id = ?", (skill_id,)).fetchone()["domain"]
    rows = db.execute("SELECT s.name, s.domain FROM learner_skill ls JOIN skill s ON s.id = ls.skill_id WHERE ls.status = 'passed' AND s.id != ? AND s.status = 'active' "
                      "ORDER BY ls.last_session_at DESC", (skill_id,)).fetchall()
    return [r["name"] for r in sorted(rows, key=lambda r: r["domain"] != dom)]


def skill_state(db: sqlite3.Connection, skill_id: int) -> tuple[int, dict]:
    ls = db.execute("SELECT difficulty_current, levers_json FROM learner_skill WHERE skill_id = ?", (skill_id,)).fetchone()
    return (ls["difficulty_current"] if ls else DEFAULT_LEVEL), get_state(ls["levers_json"] if ls else None)


def record(db: sqlite3.Connection, *, session_id: int, skill_id: int, feedback_id: int, rating: str | None, rating_used: str, inferred: bool, sig: Signals,
           dec: Decision, level_before: int, now: str) -> int:
    rid = db.execute(
        "INSERT INTO flow_rating(session_id, skill_id, feedback_id, attempt, self_rating, rating_used, inferred, accuracy, time_ratio, classification, lever_changed, "
        "difficulty_before, difficulty_after, message, signals_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (session_id, skill_id, feedback_id, sig.attempt, rating, rating_used, int(inferred), sig.accuracy, sig.time_ratio, dec.classification,
         dec.lever.id if dec.lever else None, level_before, dec.level_after, dec.message, json.dumps(asdict(sig)), now)).lastrowid
    db.execute("UPDATE learner_skill SET difficulty_current = ?, levers_json = ? WHERE skill_id = ?", (dec.level_after, json.dumps(dec.state_after), skill_id))
    db.commit()
    return rid


def rating_for_feedback(db: sqlite3.Connection, feedback_id: int) -> dict | None:
    r = db.execute("SELECT * FROM flow_rating WHERE feedback_id = ?", (feedback_id,)).fetchone()
    if r is None:
        return None
    lv = LEVERS.get(r["lever_changed"]) if r["lever_changed"] else None
    return {"id": r["id"], "rating": r["rating_used"], "tapped": r["self_rating"], "inferred": bool(r["inferred"]), "classification": r["classification"],
            "lever": lv.id if lv else None, "lever_label": SHORT.get(lv.name) if lv else None, "level_before": r["difficulty_before"], "level_after": r["difficulty_after"],
            "message": r["message"], "verdict": next((v for v in ("One change:", "No change:", "Keeping the level.") if (r["message"] or "").startswith(v)), ""),
            "signals": json.loads(r["signals_json"] or "{}")}
