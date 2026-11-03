import json

import pytest

from ai_tutor import flow
from ai_tutor.flow import BARRIER_HOURS, DEFAULT_STATE, LEVERS, Signals, apply, candidates, choose, decide, infer_rating


def state(*supports, constraints=(), combine=None):
    return {"supports": list(supports), "constraints": list(constraints), "combine_with": combine}


def sig(**kw):
    return Signals(**{"accuracy": 0.5, "attempt": 1, "hours": 1.0, **kw}) if "reasons_stuck" in kw else _with_reasons(**kw)


def _with_reasons(**kw):
    s = Signals(**{"accuracy": 0.5, "attempt": 1, "hours": 1.0, **{k: v for k, v in kw.items() if k != "reasons_stuck"}})
    if s.repeated_mistake:
        s.reasons_stuck.append("made the same mistake twice in a row")
    if s.no_improvement:
        s.reasons_stuck.append("did not improve after revising")
    if s.cant_start:
        s.reasons_stuck.append("said you do not know where to start")
    return s


def diff_size(a, b):
    ka = {("s", x) for x in a["supports"]} | {("c", x) for x in a["constraints"]}
    kb = {("s", x) for x in b["supports"]} | {("c", x) for x in b["constraints"]}
    return len(ka ^ kb)


def go(rating, level=3, st=None, s=None, scores=None, passed=("Write a logline",)):
    return decide(rating, level, st or state("template"), s or sig(), scores or {}, attempt_next=3, passed_skills=list(passed))


# ---------- the levers themselves

def test_every_lever_changes_exactly_one_thing_and_points_the_way_it_says():
    assert len(LEVERS) == 18 and all(lv.direction in ("easier", "harder") for lv in LEVERS.values())
    full = state(*flow.SUPPORTS, constraints=list(flow.CONSTRAINTS), combine="Write a logline")
    for lv in LEVERS.values():
        start = full if lv.op == "remove" else state()
        assert diff_size(start, apply(start, lv, "Write a logline")) == 1, lv.id
    assert LEVERS["remove_template"].direction == "harder" and LEVERS["add_template"].direction == "easier"
    assert LEVERS["add_time_limit"].direction == "harder" and LEVERS["relax_time_limit"].direction == "easier"


def test_a_lever_cannot_be_pulled_twice():
    with pytest.raises(ValueError):
        apply(state("template"), LEVERS["add_template"])
    with pytest.raises(ValueError):
        apply(state(), LEVERS["remove_template"])


def test_easier_takes_back_constraints_first_then_adds_supports_and_harder_takes_away_help_first():
    easy = [lv.id for lv in candidates(state("template", constraints=["constraint", "time_limit"]), "easier", can_combine=False)]
    assert easy[:2] == ["relax_time_limit", "relax_constraint"] and easy[2] == "add_worked_example" and "add_template" not in easy
    hard = [lv.id for lv in candidates(state("template", "hint"), "harder", can_combine=False)]
    assert hard[:2] == ["remove_hint", "remove_template"] and "add_combine" not in hard
    assert "add_combine" in [lv.id for lv in candidates(state(), "harder", can_combine=True)]


def test_history_decides_among_levers_and_a_lever_that_failed_is_a_last_resort():
    cands = candidates(state("template"), "easier", can_combine=False)
    assert choose(cands, {}).id == "add_worked_example"
    assert choose(cands, {"add_smaller_scope": 2}).id == "add_smaller_scope"
    assert choose(cands, {"add_worked_example": -1}).id == "add_smaller_scope"
    assert choose([LEVERS["add_hint"]], {"add_hint": -3}).id == "add_hint"          # nothing else left: use it
    assert choose([], {}) is None


# ---------- the decision

def test_just_right_changes_nothing_and_says_so():
    d = go("just_right")
    assert not d.changed and d.lever is None and d.level_after == 3 and d.message == "No change: difficulty stays at 3."


def test_too_easy_changes_one_lever_and_names_it():
    d = go("too_easy")
    assert d.changed and d.lever.id == "remove_template" and d.level_after == 4 and d.state_after["supports"] == []
    assert d.message == "One change: the beat template is removed for attempt 3. Everything else stays the same."


def test_too_easy_climbs_to_the_top_then_stops_with_a_reason():
    st, level, seen = state("template"), 3, []
    for _ in range(4):
        d = go("too_easy", level, st)
        seen.append(d.lever.id if d.lever else None)
        st, level = d.state_after, d.level_after
    assert seen == ["remove_template", "add_constraint", None, None] and level == 5
    assert "already the hardest setting" in d.message and d.message.startswith("No change:")


def test_combining_a_passed_skill_is_only_offered_when_there_is_one():
    d = go("too_easy", 4, state(constraints=["constraint", "time_limit", "higher_standard"]), passed=[])
    assert d.lever is None and "nothing is left to make it harder" in d.message
    d = go("too_easy", 4, state(constraints=["constraint", "time_limit", "higher_standard"]), passed=["Write a logline"])
    assert d.lever.id == "add_combine" and d.state_after["combine_with"] == "Write a logline" and "Write a logline is combined into attempt 3" in d.message


def test_too_hard_on_a_first_try_inside_three_hours_keeps_the_level_and_explains():
    d = go("too_hard", s=sig(hours=1.2, attempt=1))
    assert not d.changed and d.classification == "productive_struggle" and d.level_after == 3 and d.state_after == state("template")
    assert d.message.startswith("Keeping the level. You're under 3 hours on this skill and this is your first try at this task, so this is productive struggle, not overwhelm.")
    assert "If attempt 3 repeats the same mistake or does not improve, I'll add a worked example." in d.message


def test_too_hard_while_improving_keeps_the_level_and_says_the_work_improved():
    d = go("too_hard", s=sig(hours=2.0, attempt=2, improved=True, prev_accuracy=0.3, accuracy=0.6))
    assert not d.changed and "your work improved between attempts" in d.message


@pytest.mark.parametrize("flag,reason", [("repeated_mistake", "made the same mistake twice in a row"), ("no_improvement", "did not improve after revising"),
                                         ("cant_start", "said you do not know where to start")])
def test_each_stuck_condition_breaks_the_barrier_and_adds_one_support(flag, reason):
    d = go("too_hard", s=sig(hours=1.0, attempt=2, **{flag: True}))
    assert d.changed and d.classification == "overwhelm" and d.lever.id == "add_worked_example" and d.level_after == 2
    assert d.state_after["supports"] == ["template", "worked_example"] and reason in d.message and d.message.startswith("One change: a worked example is added for attempt 3.")


def test_several_stuck_reasons_are_all_named_but_still_one_lever():
    d = go("too_hard", s=sig(repeated_mistake=True, no_improvement=True, attempt=2))
    assert "made the same mistake twice in a row and did not improve after revising" in d.message and diff_size(state("template"), d.state_after) == 1


def test_too_hard_after_three_hours_adds_support_without_asking_why():
    d = go("too_hard", s=sig(hours=BARRIER_HOURS + 0.5, attempt=1))
    assert d.changed and d.classification == "too_hard" and "past the first 3 hours" in d.message


def test_too_hard_at_the_easiest_setting_or_with_nothing_left_holds_and_says_why():
    d = go("too_hard", 1, s=sig(hours=9))
    assert not d.changed and d.level_after == 1 and "already the easiest setting" in d.message
    d = go("too_hard", 3, state(*flow.SUPPORTS), s=sig(hours=9))
    assert not d.changed and d.classification == "no_lever" and "nothing is left to make it easier" in d.message


def test_a_constraint_that_made_it_harder_is_taken_back_before_new_help_is_added():
    d = go("too_hard", 4, state("template", constraints=["constraint"]), s=sig(hours=9))
    assert d.lever.id == "relax_constraint" and d.state_after["constraints"] == [] and d.level_after == 3


def test_a_learner_history_steers_which_lever_is_used():
    d = go("too_hard", s=sig(hours=9), scores={"add_hint": 2.0})
    assert d.lever.id == "add_hint"


def test_every_decision_is_exactly_one_lever_or_none_and_always_explains_itself():
    states = [state("template"), state(), state("template", "hint", "worked_example"), state(constraints=["constraint"]), state(*flow.SUPPORTS)]
    for rating in ("just_right", "too_easy", "too_hard"):
        for st in states:
            for level in (1, 3, 5):
                for s in (sig(hours=1), sig(hours=9), sig(hours=1, cant_start=True, attempt=2)):
                    d = go(rating, level, st, s)
                    assert (d.lever is None) == (not d.changed)
                    assert diff_size(st, d.state_after) == (1 if d.changed else 0)
                    assert d.message.startswith(("One change:", "No change:", "Keeping the level.")) and d.message.strip()
                    assert abs(d.level_after - level) == (1 if d.changed else 0) and 1 <= d.level_after <= 5


# ---------- inferred ratings

def test_a_rating_is_inferred_from_the_work_when_there_was_no_tap():
    assert infer_rating(Signals(accuracy=1.0, attempt=1, time_ratio=0.4)) == "too_easy"
    assert infer_rating(Signals(accuracy=1.0, attempt=1, time_ratio=0.9)) == "just_right"
    assert infer_rating(Signals(accuracy=0.2, attempt=1)) == "too_hard"
    assert infer_rating(Signals(accuracy=0.6, attempt=3, no_improvement=True)) == "too_hard"
    assert infer_rating(Signals(accuracy=0.6, attempt=2, improved=True)) == "just_right"
    assert flow.DEFAULT_STATE == DEFAULT_STATE == {"supports": ["template"], "constraints": [], "combine_with": None}
    assert json.dumps(flow.get_state(None)) == json.dumps(DEFAULT_STATE)
