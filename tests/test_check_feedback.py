import json
import re

import pytest
from helpers import SmartBackend, fb_json
from session_helpers import CITE1, CITE2, WORK, script, to_learn, to_practice

from ai_tutor import check as chk
from ai_tutor import feedback as fbk
from ai_tutor.session import TransitionError
from ai_tutor.teaching import TutorError


def learner_answer(user):
    return re.search(r'<data label="learner answer">\n(.*?)\n</data>', user, re.DOTALL).group(1)


def judge_by(word="right", **extra):
    return lambda u, c: {"correct": word in learner_answer(u), "feedback": "That is the idea." if word in learner_answer(u) else "Not quite.",
                         "hint": "Look at who pushes back.", "confused_with": None, **extra}


SPOT = {"prompt": "Which line shows an obstacle?\nA. MAI: Hi.\nB. GRANDMA: Leave it.\nC. MAI: Fine.", "answer_key": "B, because Grandma pushes back."}
RETEACH = lambda u, c: {"body": f"Think of an obstacle as a door that answers back {c[0]}.", "example": "Made-up example: a locked drawer."}


def check_script(**over):
    return script(**{"concept_check": judge_by(), "concept_hint": {"hint": "Think about who pushes back."}, "concept_spot": SPOT, "concept_reteach": RETEACH,
                     "feedback": lambda u, c: fb_json(), **over})


def to_check(env, **over):
    svc = to_learn(env, env.make(SmartBackend(session=check_script(**over))))
    svc.act(env.sid, "continue")
    return svc


def answer(svc, env, text):
    return svc.act(env.sid, "check_answer", text)


def level(env, name):
    return env.db.execute("SELECT m.level FROM concept_mastery m JOIN concept c ON c.id = m.concept_id WHERE c.name = ?", (name,)).fetchone()[0]


# ---------- the foundations check

def test_one_question_at_a_time_define_first_and_asking_twice_changes_nothing(env):
    svc = to_check(env)
    v = svc.act(env.sid, "check")
    svc.act(env.sid, "check")
    qs = [m for m in svc.view(env.sid)["messages"] if m["kind"] == "check_question"]
    assert len(qs) == 1 and qs[0]["meta"]["level"] == "define" and qs[0]["meta"]["concept"] == "obstacle"
    assert qs[0]["content"] == "What is an obstacle?"                        # the library's own question
    assert v["check"]["current"]["level"] == "define" and v["check"]["remaining_minutes"] == 4 and v["check"]["budget_left"] == 11
    assert v["phase"] == "check" and v["gate"]["unlocked"] is False


def test_defining_a_concept_never_counts_as_spotting_it(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    v = answer(svc, env, "a right answer: the force that pushes back")
    assert level(env, "obstacle") == "define" and v["gate"]["done"] == 0       # define only: practice stays locked
    assert v["messages"][-1]["meta"]["correct"] is True
    assert v["check"]["current"] is None
    v = svc.act(env.sid, "check")
    assert v["check"]["current"]["level"] == "spot" and v["check"]["current"]["concept"] == "obstacle"
    assert level(env, "obstacle") == "define"
    answer(svc, env, "B, that is right")
    assert level(env, "obstacle") == "spot"
    assert env.db.execute("SELECT last_checked_at FROM concept_mastery WHERE concept_id = ?", (env.c2,)).fetchone()[0] == "2026-11-03 10:00:00"


def test_concepts_already_at_the_required_level_are_skipped(env):
    env.db.execute("UPDATE concept_mastery SET level = 'use' WHERE concept_id = ?", (env.c2,))        # obstacle
    env.db.commit()
    svc = to_check(env)
    v = svc.act(env.sid, "check")
    assert v["check"]["current"]["concept"] == "want" and v["check"]["remaining_minutes"] == 2


def test_the_whole_check_unlocks_practice_only_when_every_concept_is_at_spot(env):
    svc = to_check(env)
    for _ in range(8):
        v = svc.act(env.sid, "check")
        if v["check"]["current"] is None:
            break
        answer(svc, env, "right")
    v = svc.view(env.sid)
    assert v["check"]["all_done"] is True and v["gate"]["unlocked"] is True and v["messages"][-1]["kind"] == "check_done"
    assert level(env, "want") == "spot" and level(env, "obstacle") == "spot"
    assert svc.act(env.sid, "unlock")["phase"] == "practice"


def test_a_wrong_answer_gets_a_hint_and_the_same_question_again(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    v = answer(svc, env, "no idea")
    last = v["messages"][-1]
    assert last["meta"]["correct"] is False and "Hint: Look at who pushes back." in last["content"]
    cur = v["check"]["current"]
    assert cur["prompt"] == "What is an obstacle?" and cur["attempts"] == 1 and cur["hint_shown"] is True
    assert level(env, "obstacle") == "none"


def test_a_second_wrong_answer_shows_the_answer_with_a_citation_and_re_teaches(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    answer(svc, env, "no idea")
    v = answer(svc, env, "still no idea")
    result, reteach = v["messages"][-2:]
    assert result["kind"] == "check_result" and "The answer: force" in result["content"] and result["citations"][0]["citation"] == CITE2
    assert reteach["kind"] == "check_reteach" and reteach["citations"][0]["citation"] == CITE2 and "Made-up example" in reteach["content"]
    assert v["check"]["current"] is None and svc.be.calls["concept_reteach"] == 1
    assert level(env, "obstacle") == "none"                                   # the learner has not got it yet; the next question tries again


def test_after_two_misses_on_spot_the_next_question_is_a_new_example(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    answer(svc, env, "right")                                                    # define passes
    svc.act(env.sid, "check")                                                    # spot: no stored question for obstacle, so one is generated
    first = svc.view(env.sid)["check"]["current"]["prompt"]
    answer(svc, env, "A")
    answer(svc, env, "A again")
    svc.be.session["concept_spot"] = {"prompt": "A different moment?\nA. x\nB. y", "answer_key": "A"}
    v = svc.act(env.sid, "check")
    assert v["check"]["current"]["prompt"] == "A different moment?\nA. x\nB. y" != first
    assert [o[:2] for o in v["check"]["current"]["options"]] == ["A.", "B."]
    assert "Which line shows an obstacle?" in svc.be.users[-1]                    # the earlier example is passed in so it is not repeated


def test_an_explicit_hint_comes_once_before_any_answer(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    v = svc.act(env.sid, "check_hint")
    assert v["messages"][-1]["kind"] == "check_hint" and v["messages"][-1]["content"] == "Hint: Think about who pushes back."
    with pytest.raises(TransitionError, match="already have a hint"):
        svc.act(env.sid, "check_hint")


def test_what_a_concept_is_confused_with_is_remembered_and_counted(env):
    svc = to_check(env, concept_check=judge_by(confused_with="exposition"))
    svc.act(env.sid, "check")
    answer(svc, env, "nope")
    answer(svc, env, "nope again")
    got = json.loads(env.db.execute("SELECT confusions_json FROM concept_mastery WHERE concept_id = ?", (env.c2,)).fetchone()[0])
    assert got == [{"with": "exposition", "count": 2}]


def test_the_question_budget_ends_a_long_sitting_and_can_be_extended(env):
    svc = to_check(env, concept_check=judge_by("zzz"))
    state = chk.new_state()
    state["total"] = chk.MAX_QUESTIONS_PER_SITTING
    env.db.execute("UPDATE session SET check_json = ?", (json.dumps(state),))
    env.db.commit()
    with pytest.raises(TransitionError, match="enough for one sitting"):
        svc.act(env.sid, "check")
    assert svc.act(env.sid, "check_more")["check"]["budget_left"] == chk.MAX_QUESTIONS_PER_SITTING
    assert svc.act(env.sid, "check")["check"]["current"]


def test_answers_are_judged_on_meaning_against_the_cited_definition(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    answer(svc, env, "The thing that pushes back, in my words")
    prompt = next(u for u in svc.be.users if "judging one answer" in u)
    assert "Judge the **meaning**" in prompt and "never the wording" in prompt
    assert f"CITATION: {CITE2}" in prompt and "what pushes back" in prompt and '<data label="learner answer">' in prompt


def test_a_model_failure_while_judging_writes_nothing(env):
    svc = to_check(env)
    svc.act(env.sid, "check")
    svc.be.fail_on = "concept_check"
    before = len(svc.view(env.sid)["messages"])
    with pytest.raises(TutorError):
        answer(svc, env, "right")
    v = svc.view(env.sid)
    assert len(v["messages"]) == before and v["check"]["current"]["attempts"] == 0 and level(env, "obstacle") == "none"


def test_answering_with_no_question_or_no_text_is_refused(env):
    svc = to_check(env)
    with pytest.raises(TransitionError, match="no question"):
        answer(svc, env, "x")
    svc.act(env.sid, "check")
    with pytest.raises(TransitionError, match="Write your answer"):
        answer(svc, env, "  ")


def test_options_are_read_from_a_spot_question():
    assert chk.options("Which?\nA. one\nB) two\nsome text") == ["A. one", "B) two"]
    assert chk.options("Explain it") == []
    inline = "Which shows a want? A: 'I want to be happy.' B: 'I need to sign this before noon.' C: 'I hope things get better.'"
    assert chk.options(inline) == ["A. 'I want to be happy.'", "B. 'I need to sign this before noon.'", "C. 'I hope things get better.'"]


# ---------- feedback

def submit(svc, env, text=WORK):
    return svc.act(env.sid, "submit", text)


def practice(env, fb=None, **over):
    s = check_script(**over)
    if fb is not None:
        s["feedback"] = fb
    return to_practice(env, env.make(SmartBackend(session=s)))


def test_every_principle_gets_a_verdict_with_evidence_a_line_and_a_citation(env):
    svc = practice(env)
    v = submit(svc, env)
    fb = v["messages"][-1]
    assert fb["kind"] == "feedback" and fb["meta"]["summary"] == "Not passed yet: 1 of 2 principles followed." and fb["meta"]["passed"] is False
    r1, r2 = fb["meta"]["results"]
    assert (r1["result"], r1["locator"], r1["quote"], r1["citation"]) == ("followed", "Line 2", "Mai reaches for the tin", CITE1)
    assert (r2["result"], r2["locator"], r2["citation"]) == ("partly", "Line 3", CITE2)
    rows = env.db.execute("SELECT result, locator, evidence_ref FROM principle_check ORDER BY id").fetchall()
    assert [r["result"] for r in rows] == ["followed", "partly"] and json.loads(rows[0]["evidence_ref"]) == {"kind": "line", "quote": "Mai reaches for the tin", "start": 2, "end": 2}
    assert env.db.execute("SELECT passed, content FROM feedback").fetchone()[:] == (0, "Not passed yet: 1 of 2 principles followed.")
    assert v["route"] == "revise" and {c["citation"] for c in fb["citations"]} == {CITE1, CITE2}


def test_the_checklist_prompt_has_the_principles_the_numbered_work_and_the_rules(env):
    svc = practice(env)
    submit(svc, env)
    p = next(u for u in svc.be.users if "## Phase: Feedback" in u)
    assert "only** against the principle checklist" in p and "No comments on taste" in p and "Do not rewrite their work" in p
    assert f"1. The want is clear in the first beat (test: Can you name the want after beat one?) {CITE1}" in p
    assert "2: Mai reaches for the tin on the top shelf." in p and '<data label="learner work">' in p


def test_pass_needs_every_principle_followed_with_evidence(env):
    svc = practice(env, fb=lambda u, c: fb_json(("followed", "followed")))
    v = submit(svc, env)
    assert v["messages"][-1]["meta"]["passed"] is True and v["route"] == "pass"
    assert svc.act(env.sid, "pass")["phase"] == "pass"


def test_followed_without_findable_evidence_is_downgraded(env):
    svc = practice(env, fb=lambda u, c: fb_json(("followed", "followed"), ("A line the learner never wrote", "Grandma slides the tin")))
    fb = submit(svc, env)["messages"][-1]["meta"]
    assert fb["results"][0]["result"] == "partly" and "could not find the evidence" in fb["results"][0]["comment"]
    assert fb["passed"] is False and fb["summary"] == "Not passed yet: 1 of 2 principles followed."
    with pytest.raises(TransitionError, match="Not passed yet"):
        svc.act(env.sid, "pass")


def test_feedback_that_skips_a_principle_is_rejected_nothing_is_saved_and_the_work_is_kept(env):
    incomplete = lambda u, c: {"principles": [{"n": 1, "result": "followed", "quote": "Mai reaches for the tin"}], "fixes": [], "mistakes": []}
    svc = practice(env, fb=incomplete)
    v = submit(svc, env)                                                           # does not raise: the submission is safe
    assert svc.be.calls["feedback"] == 2 and "not every principle got a verdict" in v["messages"][-1]["content"]
    assert v["feedback_pending"] is True and "not every principle" in v["feedback_error"] and v["phase"] == "feedback"
    assert env.db.execute("SELECT COUNT(*) FROM submission").fetchone()[0] == 1 and env.db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 0
    assert "missing: [2]" in svc.be.users[-1]
    svc.be.session["feedback"] = lambda u, c: fb_json()
    v = svc.act(env.sid, "feedback")
    assert v["feedback_pending"] is False and v["messages"][-1]["kind"] == "feedback" and env.db.execute("SELECT COUNT(*) FROM submission").fetchone()[0] == 1
    with pytest.raises(TransitionError, match="already been given"):
        svc.act(env.sid, "feedback")


def test_repeated_or_unknown_principle_numbers_are_rejected(env):
    dup = lambda u, c: {"principles": [{"n": 1, "result": "followed", "quote": "x"}, {"n": 1, "result": "not"}, {"n": 2, "result": "not"}]}
    assert submit(practice(env, fb=dup), env)["feedback_pending"] is True


def test_unknown_principle_numbers_are_rejected_too(env):
    wrong = lambda u, c: {"principles": [{"n": 1, "result": "not"}, {"n": 7, "result": "not"}]}
    assert submit(practice(env, fb=wrong), env)["feedback_pending"] is True


def test_a_model_failure_after_submitting_keeps_the_attempt_and_can_be_retried(env):
    svc = practice(env)
    svc.be.fail_on = "feedback"
    v = submit(svc, env)
    assert v["phase"] == "feedback" and v["attempt"] == 1 and v["feedback_pending"] and "could not be reached" in v["feedback_error"]
    assert svc.act(env.sid, "feedback")["messages"][-1]["kind"] == "feedback"


def test_citations_in_the_models_prose_are_removed_only_the_principles_own_are_shown(env):
    fb = lambda u, c: fb_json(("followed", "partly"), comments={1: "Good [Book Z, p. 9] start.", 2: "Mixed."},
                              fixes=[{"n": 2, "fix": "Do it again [Book Z, ch. 1, p. 1] please.", "example": ""}])
    meta = submit(practice(env, fb=fb), env)["messages"][-1]["meta"]
    assert "Book Z" not in json.dumps(meta) and meta["results"][0]["comment"] == "Good start."
    assert meta["fixes"][0]["fix"] == "Do it again please." and meta["fixes"][0]["citation"] == CITE2


def test_at_most_two_fixes_each_for_a_failing_principle_and_none_for_followed_ones(env):
    env.db.execute("INSERT INTO skill_principle(skill_id, principle, test, chunk_id, \"order\") VALUES (?, 'Third', 't3', 1, 2), (?, 'Fourth', 't4', 2, 3)", (env.skill, env.skill))
    env.db.commit()
    fb = lambda u, c: fb_json(("followed", "not", "not", "partly"), ("Mai reaches for the tin", "", "", "Grandma slides"),
                              fixes=[{"n": 1, "fix": "wrong target", "example": ""}, {"n": 2, "fix": "a", "example": ""}, {"n": 3, "fix": "b", "example": ""}, {"n": 4, "fix": "c", "example": ""}])
    meta = submit(practice(env, fb=fb), env)["messages"][-1]["meta"]
    assert [f["n"] for f in meta["fixes"]] == [2, 3] and meta["summary"] == "Not passed yet: 1 of 4 principles followed."


def test_a_failing_principle_without_a_fix_from_the_model_still_gets_one(env):
    svc = practice(env, fb=lambda u, c: fb_json(("followed", "not"), fixes=[]))
    meta = submit(svc, env)["messages"][-1]["meta"]
    assert [f["n"] for f in meta["fixes"]] == [2] and "Make this true of your work" in meta["fixes"][0]["fix"] and meta["fixes"][0]["citation"] == CITE2


def test_too_short_work_is_not_judged(env):
    svc = practice(env)
    for tiny in ("ok", "a b", "short one"):
        with pytest.raises(TransitionError, match="too short"):
            submit(svc, env, tiny)
    assert env.db.execute("SELECT COUNT(*) FROM submission").fetchone()[0] == 0 and svc.be.calls["feedback"] == 0
    assert svc.view(env.sid)["phase"] == "practice"


# ---------- concept or execution

def mistakes_fb(kind, concept="obstacle", tag="weak push back"):
    return lambda u, c: fb_json(("followed", "not"), mistakes=[{"n": 2, "kind": kind, "concept": concept, "tag": tag}])


def test_mistakes_are_tagged_and_saved_with_the_principle_passage(env):
    svc = practice(env, fb=mistakes_fb("concept"))
    meta = submit(svc, env)["messages"][-1]["meta"]
    assert meta["mistakes"] == [{"n": 2, "kind": "concept", "concept_id": env.c2, "concept": "obstacle", "tag": "weak push back", "count": 1}]
    row = env.db.execute("SELECT skill_id, concept_id, kind, tag, principle_chunk_id, count FROM mistake").fetchone()
    assert tuple(row) == (env.skill, env.c2, "concept", "weak push back", 2, 1)


def test_a_concept_mistake_naming_no_concept_of_this_skill_counts_as_execution(env):
    svc = practice(env, fb=mistakes_fb("concept", concept="a concept from elsewhere"))
    assert submit(svc, env)["messages"][-1]["meta"]["mistakes"][0]["kind"] == "execution"
    assert svc.view(env.sid)["route"] == "revise"


def test_a_repeated_mistake_is_counted_for_the_frustration_barrier(env):
    svc = practice(env, fb=mistakes_fb("execution", None, "weak ending"))
    submit(svc, env)
    svc.act(env.sid, "revise")
    meta = submit(svc, env, WORK + "\nMai: You said that last New Year.")["messages"][-1]["meta"]
    assert meta["mistakes"][0]["count"] == 2 and env.db.execute("SELECT count FROM mistake").fetchone()[0] == 2


def test_an_execution_mistake_goes_straight_back_to_revise(env):
    svc = practice(env, fb=mistakes_fb("execution", None, "weak ending"))
    v = submit(svc, env)
    assert v["route"] == "revise" and v["route_concepts"] == []
    with pytest.raises(TransitionError, match="No concept needs re-teaching"):
        svc.act(env.sid, "reteach")
    assert svc.act(env.sid, "revise")["phase"] == "revise"


def test_a_concept_mistake_is_re_taught_and_checked_before_the_next_attempt(env):
    svc = practice(env, fb=mistakes_fb("concept"))
    v = submit(svc, env)
    assert v["route"] == "reteach" and v["route_concepts"] == ["obstacle"]
    with pytest.raises(TransitionError, match="needs another look before your next attempt: obstacle"):
        svc.act(env.sid, "revise")                                              # no skipping straight to another attempt
    v = svc.act(env.sid, "reteach")
    rt = v["messages"][-1]
    assert v["phase"] == "check" and rt["kind"] == "reteach" and rt["citations"][0]["citation"] == CITE2 and rt["meta"]["concept"] == "obstacle"
    assert level(env, "obstacle") == "define" and v["gate"]["unlocked"] is False and "Missing: obstacle" in v["gate"]["message"]
    with pytest.raises(TransitionError, match="Practice unlocks"):
        svc.act(env.sid, "unlock")
    q = svc.act(env.sid, "check")["check"]["current"]
    assert q["concept"] == "obstacle" and q["level"] == "spot"                    # only the misunderstood concept is asked again, at Spot
    answer(svc, env, "B, right")
    v = svc.act(env.sid, "unlock")
    assert v["phase"] == "revise" and v["timer"]["running"] and v["task"]["title"] == "Rewrite the kitchen scene"
    assert sum(m["kind"] == "practice_task" for m in v["messages"]) == 1          # the same task, no new one
    svc.be.session["feedback"] = lambda u, c: fb_json(("followed", "followed"))
    assert submit(svc, env, WORK + "\nMai: You said that last New Year.")["route"] == "pass"


def test_a_model_failure_while_re_teaching_leaves_the_session_as_it_was(env):
    svc = practice(env, fb=mistakes_fb("concept"))
    submit(svc, env)
    svc.be.fail_on = "concept_reteach"
    with pytest.raises(TutorError):
        svc.act(env.sid, "reteach")
    v = svc.view(env.sid)
    assert v["phase"] == "feedback" and level(env, "obstacle") == "spot" and v["route"] == "reteach"


def test_applying_a_concept_in_the_work_marks_it_use_but_never_skips_spot(env):
    svc = practice(env, fb=lambda u, c: fb_json(("followed", "followed"), shown=["want", "obstacle"]))
    submit(svc, env)
    assert level(env, "want") == "use" and level(env, "obstacle") == "use"
    env.db.execute("UPDATE concept_mastery SET level = 'define' WHERE concept_id = ?", (env.c1,))
    env.db.execute("UPDATE session SET phase = 'practice', ended_at = NULL")
    env.db.commit()
    svc2 = env.make(SmartBackend(session=check_script(feedback=lambda u, c: fb_json(("followed", "followed"), shown=["want"]))))
    svc2.act(env.sid, "submit", WORK + "\nanother line")
    assert level(env, "want") == "define"                                           # it was not at Spot: the work cannot lift it past the check


def test_a_concept_the_work_misunderstood_is_not_marked_use(env):
    fb = lambda u, c: fb_json(("followed", "not"), shown=["obstacle"], mistakes=[{"n": 2, "kind": "concept", "concept": "obstacle", "tag": "x"}])
    submit(practice(env, fb=fb), env)
    assert level(env, "obstacle") == "spot"


# ---------- revise and compare

def test_a_resubmission_names_what_improved(env):
    svc = practice(env, fb=lambda u, c: fb_json(("followed", "not"), mistakes=[{"n": 2, "kind": "execution", "concept": None, "tag": "weak"}]))
    submit(svc, env)
    svc.act(env.sid, "revise")
    svc.be.session["feedback"] = lambda u, c: fb_json(("followed", "partly"), ("Mai reaches for the tin", "Grandma slides"))
    v = submit(svc, env, WORK + "\nMai: You said that last New Year.\nGrandma turns off the light.")
    meta = v["messages"][-1]["meta"]
    assert meta["version"] == 2 and meta["diff"]["principles"] == [{"n": 1, "before": "followed", "after": "followed", "change": "same"},
                                                                  {"n": 2, "before": "not", "after": "partly", "change": "improved"}]
    assert meta["diff"]["lines_added"] == 2 and meta["diff"]["lines_removed"] == 0 and meta["since"] == "Improved: principle 2."
    assert "Not followed" in next(u for u in svc.be.users if "## Phase: Feedback" in u and "Attempt: 2" in u)         # the previous verdicts are given as context
    svc.be.session["feedback"] = lambda u, c: fb_json(("followed", "partly"), since="The second push now changes who has the upper hand.")
    svc.act(env.sid, "revise")
    again = submit(svc, env, WORK + "\nMai: And again, three times.\nGrandma sighs.")
    assert again["messages"][-1]["meta"]["since"] == "The second push now changes who has the upper hand."


def test_comparing_two_attempts_shows_every_line_added_or_removed(env):
    svc = practice(env)
    submit(svc, env, "line one\nline two kept\nline three old")
    svc.act(env.sid, "revise")
    submit(svc, env, "line one\nline two kept\nline three new\nline four")
    c = svc.compare(env.sid, 1, 2)
    assert c["a"]["version"] == 1 and c["b"]["text"].endswith("line four")
    assert c["lines"] == [{"op": " ", "text": "line one"}, {"op": " ", "text": "line two kept"}, {"op": "-", "text": "line three old"},
                          {"op": "+", "text": "line three new"}, {"op": "+", "text": "line four"}]
    with pytest.raises(TransitionError, match="does not exist"):
        svc.compare(env.sid, 1, 9)


def test_locating_a_quote_in_the_work():
    work = "INT. KITCHEN\nMai reaches for the\n  old recipe tin\nGrandma: Leave it."
    assert fbk.locate("mai reaches for the old RECIPE tin", work) == (2, 3)
    assert fbk.locate("Leave it.", work) == (4, 4)
    assert fbk.locate("never said", work) is None and fbk.locate("  ", work) is None
    assert fbk.locator_text((2, 3)) == "Lines 2–3" and fbk.locator_text((4, 4)) == "Line 4" and fbk.locator_text(None) is None
