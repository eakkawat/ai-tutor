import json

import pytest
from helpers import SmartBackend, fb_json
from session_helpers import PRACTICE, WORK, to_practice
from test_check_feedback import check_script

from ai_tutor import flow
from ai_tutor.session import TransitionError
from ai_tutor.teaching import TutorError

MISTAKE = [{"n": 2, "kind": "execution", "concept": None, "tag": "weak push back"}]


def sequence(*replies):
    """Feedback replies in order, then the last one forever."""
    box = list(replies)
    return lambda u, c: box.pop(0) if len(box) > 1 else box[0]


def practicing(env, *fbs, hours=0.0):
    s = check_script(feedback=sequence(*fbs) if fbs else (lambda u, c: fb_json()))
    be = SmartBackend(session=s)
    svc = to_practice(env, env.make(be))
    env.db.execute("UPDATE learner_skill SET hours_total = ? WHERE skill_id = ?", (hours, env.skill))
    env.db.commit()
    return svc, be


def submit(svc, env, extra=""):
    return svc.act(env.sid, "submit", WORK + extra)


def last_rating(env):
    return env.db.execute("SELECT * FROM flow_rating ORDER BY id DESC LIMIT 1").fetchone()


def task(svc, env):
    return svc.view(env.sid)["task"]


def test_the_rating_is_offered_after_feedback_and_recorded_once(env):
    svc, _ = practicing(env)
    v = submit(svc, env)
    assert v["flow"]["can_rate"] is True and v["flow"]["rating"] is None and v["flow"]["level"] == 3 and v["flow"]["early"] is True
    v = svc.rate(env.sid, "just_right")
    r = v["flow"]["rating"]
    assert v["flow"]["can_rate"] is False and r["rating"] == "just_right" and r["verdict"] == "No change:" and r["message"] == "No change: difficulty stays at 3."
    row = last_rating(env)
    assert (row["self_rating"], row["rating_used"], row["inferred"], row["skill_id"], row["attempt"], row["difficulty_before"], row["difficulty_after"]) == ("just_right", "just_right", 0, env.skill, 1, 3, 3)
    assert row["accuracy"] == pytest.approx(0.75) and row["time_ratio"] == pytest.approx(0.0, abs=0.01) and json.loads(row["signals_json"])["attempt"] == 1
    with pytest.raises(TransitionError, match="already rated"):
        svc.rate(env.sid, "too_easy")


def test_a_rating_needs_feedback_to_rate_and_a_real_choice(env):
    svc, _ = practicing(env)
    with pytest.raises(TransitionError, match="right after its feedback"):
        svc.rate(env.sid, "too_easy")
    submit(svc, env)
    with pytest.raises(TransitionError, match="Choose Too easy"):
        svc.rate(env.sid, "bored")


def test_too_easy_removes_the_template_without_asking_the_model_and_everything_else_stays(env):
    svc, be = practicing(env)
    before = task(svc, env)
    submit(svc, env)
    v = svc.rate(env.sid, "too_easy")
    assert v["flow"]["rating"]["message"] == "One change: the beat template is removed for attempt 2. Everything else stays the same."
    assert v["flow"]["rating"]["lever"] == "remove_template" and v["flow"]["rating"]["level_before"] == 3 and v["flow"]["rating"]["level_after"] == 4 and v["difficulty"] == 4
    after = v["task"]
    assert after["template"] == [] and after["support"] is None and after["instructions"] == before["instructions"] and after["title"] == before["title"]
    assert be.calls["task_adjust"] == 0 and v["flow"]["supports"] == []
    assert svc.act(env.sid, "revise")["timer"]["limit_s"] == after["minutes"] * 60


def test_too_hard_on_a_first_attempt_inside_three_hours_keeps_the_level_and_says_why(env):
    svc, be = practicing(env)
    before = task(svc, env)
    submit(svc, env)
    v = svc.rate(env.sid, "too_hard")
    r = v["flow"]["rating"]
    assert r["verdict"] == "Keeping the level." and r["classification"] == "productive_struggle" and "productive struggle, not overwhelm" in r["message"]
    assert v["difficulty"] == 3 and v["task"] == before and be.calls["task_adjust"] == 0 and last_rating(env)["lever_changed"] is None


def test_the_same_mistake_twice_in_a_row_makes_the_next_too_hard_add_one_support(env):
    weak = fb_json(("followed", "not"), mistakes=MISTAKE)
    svc, be = practicing(env, weak)
    submit(svc, env)
    svc.rate(env.sid, "just_right")
    svc.act(env.sid, "revise")
    v = submit(svc, env, "\nMai: You said that last New Year.")
    v = svc.rate(env.sid, "too_hard")
    r = v["flow"]["rating"]
    assert r["lever"] == "add_worked_example" and r["classification"] == "overwhelm" and r["level_after"] == 2
    assert r["message"].startswith("One change: a worked example is added for attempt 3. Everything else stays the same.")
    assert "made the same mistake twice in a row" in r["message"] and "did not improve after revising" in r["message"]
    t = v["task"]
    assert t["extras"]["worked_example"] == "A made-up piece." and t["support"] == "beat template, worked example" and t["template"] == PRACTICE["template"]
    assert be.calls["task_adjust"] == 1 and "Add a short worked example" in next(u for u in be.users if "Adjusting a task" in u)


def test_saying_you_dont_know_where_to_start_counts_as_stuck_even_on_a_first_try(env):
    svc, _ = practicing(env)
    submit(svc, env)
    r = svc.rate(env.sid, "too_hard", cant_start=True)["flow"]["rating"]
    assert r["lever"] == "add_worked_example" and "said you do not know where to start" in r["message"]
    assert json.loads(last_rating(env)["signals_json"])["cant_start"] is True


def test_past_three_hours_too_hard_adds_support_straight_away(env):
    svc, _ = practicing(env, hours=3.5)
    submit(svc, env)
    r = svc.rate(env.sid, "too_hard")["flow"]["rating"]
    assert r["lever"] == "add_worked_example" and "past the first 3 hours" in r["message"]


def test_cant_start_is_ignored_for_other_ratings(env):
    svc, _ = practicing(env)
    submit(svc, env)
    svc.rate(env.sid, "just_right", cant_start=True)
    assert json.loads(last_rating(env)["signals_json"])["cant_start"] is False


def test_a_failed_model_call_while_adding_support_changes_and_saves_nothing_and_can_be_repeated(env):
    svc, be = practicing(env, hours=5.0)
    submit(svc, env)
    before = task(svc, env)
    be.fail_on = "task_adjust"
    with pytest.raises(TutorError):
        svc.rate(env.sid, "too_hard")
    v = svc.view(env.sid)
    assert v["flow"]["can_rate"] is True and v["task"] == before and v["difficulty"] == 3 and env.db.execute("SELECT COUNT(*) FROM flow_rating").fetchone()[0] == 0
    assert svc.rate(env.sid, "too_hard")["flow"]["rating"]["lever"] == "add_worked_example"


def test_moving_on_without_a_tap_judges_from_the_work_and_marks_it_inferred(env):
    svc, _ = practicing(env, fb_json(("not", "not"), ("", ""), mistakes=[]))
    submit(svc, env)
    svc.act(env.sid, "revise")
    row = last_rating(env)
    assert row["inferred"] == 1 and row["self_rating"] is None and row["rating_used"] == "too_hard" and row["classification"] == "productive_struggle"
    assert svc.view(env.sid)["phase"] == "revise"


def test_an_inferred_rating_never_blocks_moving_on(env):
    svc, be = practicing(env, fb_json(("not", "not"), ("", ""), mistakes=[]), hours=5.0)
    submit(svc, env)
    be.fail_on = "task_adjust"
    assert svc.act(env.sid, "revise")["phase"] == "revise"                         # the inferred change could not be written, so it is skipped
    assert env.db.execute("SELECT COUNT(*) FROM flow_rating").fetchone()[0] == 0


def test_a_passed_task_is_recorded_but_changes_nothing(env):
    svc, be = practicing(env, fb_json(("followed", "followed")))
    v = submit(svc, env)
    assert v["route"] == "pass"
    r = svc.rate(env.sid, "too_easy")["flow"]["rating"]
    assert r["classification"] == "passed" and "no next task to change" in r["message"] and r["level_after"] == 3 and be.calls["task_adjust"] == 0


def test_passing_without_a_tap_still_records_the_rating(env):
    svc, _ = practicing(env, fb_json(("followed", "followed")))
    submit(svc, env)
    svc.act(env.sid, "pass")
    row = last_rating(env)
    assert row["inferred"] == 1 and row["classification"] == "passed" and row["lever_changed"] is None


def test_a_shorter_time_limit_shortens_the_task_and_taking_it_back_restores_it(env):
    svc, _ = practicing(env)
    env.db.execute("UPDATE learner_skill SET difficulty_current = 4, levers_json = ? WHERE skill_id = ?", (json.dumps(flow.get_state(json.dumps({"supports": [], "constraints": ["constraint"]}))), env.skill))
    env.db.commit()
    submit(svc, env)
    env.db.execute("UPDATE session SET task_json = json_set(task_json, '$.extras.constraint', 'No dialogue in the first beat')")
    r = svc.rate(env.sid, "too_easy")["flow"]["rating"]
    assert r["lever"] == "add_time_limit" and r["message"].startswith("One change: the time limit is shortened for attempt 2.")
    assert task(svc, env)["minutes"] == 15 and task(svc, env)["base_minutes"] == 20
    svc.act(env.sid, "revise")
    assert svc.view(env.sid)["timer"]["limit_s"] == 15 * 60
    submit(svc, env, "\nmore")
    r = svc.rate(env.sid, "too_hard", cant_start=True)["flow"]["rating"]
    assert r["lever"] == "relax_time_limit" and task(svc, env)["minutes"] == 20 and svc.view(env.sid)["difficulty"] == 4


def test_removing_a_constraint_deletes_its_text_and_one_lever_is_all_that_moves(env):
    svc, _ = practicing(env)
    env.db.execute("UPDATE learner_skill SET difficulty_current = 4, levers_json = ? WHERE skill_id = ?", (json.dumps({"supports": ["template"], "constraints": ["constraint"], "combine_with": None}), env.skill))
    env.db.execute("UPDATE session SET task_json = json_set(task_json, '$.extras.constraint', 'No dialogue in the first beat')")
    env.db.commit()
    submit(svc, env)
    before = svc.view(env.sid)["flow"]
    svc.rate(env.sid, "too_hard", cant_start=True)
    after = svc.view(env.sid)
    assert "constraint" in before["constraints"] and after["flow"]["constraints"] == [] and after["flow"]["supports"] == ["template"]
    assert "constraint" not in after["task"]["extras"] and after["difficulty"] == 3


def test_the_next_task_is_built_from_the_levers_and_missing_pieces_are_asked_for_separately(env):
    svc, be = practicing(env)
    env.db.execute("UPDATE learner_skill SET levers_json = ? WHERE skill_id = ?", (json.dumps({"supports": ["worked_example"], "constraints": [], "combine_with": None}), env.skill))
    env.db.execute("UPDATE session SET task_json = NULL")
    env.db.commit()
    svc._ensure_task(svc.row(env.sid))
    prompt = next(u for u in reversed(be.users) if "## Phase: Practice" in u)
    assert "a worked example: ON" in prompt and "a beat template: off" in prompt and "Favour quantity and speed over polish" in prompt
    t = task(svc, env)
    assert t["extras"] == {"worked_example": "A made-up piece."} and t["template"] == [] and t["support"] == "worked example"      # the model gave none, so it was asked for on its own
    assert be.calls["task_adjust"] == 1


def test_after_three_hours_the_task_asks_for_one_considered_piece_not_speed(env):
    svc, be = practicing(env, hours=4.0)
    env.db.execute("UPDATE session SET task_json = NULL")
    env.db.commit()
    svc._ensure_task(svc.row(env.sid))
    prompt = next(u for u in reversed(be.users) if "## Phase: Practice" in u)
    assert "Ask for one considered piece of work" in prompt and "Favour quantity" not in prompt
    assert svc.view(env.sid)["flow"]["early"] is False


def test_what_worked_before_steers_the_next_lever(env):
    for i, (used, lever) in enumerate([("too_hard", "add_hint"), ("just_right", None), ("too_hard", "add_hint"), ("just_right", None)], 1):
        env.db.execute("INSERT INTO flow_rating(session_id, skill_id, rating_used, lever_changed) VALUES (?,?,?,?)", (env.sid, env.skill, used, lever))
    env.db.commit()
    assert flow.lever_scores(env.db) == {"add_hint": 2.0}
    env.db.execute("INSERT INTO flow_rating(session_id, skill_id, rating_used, lever_changed) VALUES (?,?,?,?)", (env.sid, env.skill, "too_hard", "add_smaller_scope"))
    env.db.execute("INSERT INTO flow_rating(session_id, skill_id, rating_used, lever_changed) VALUES (?,?,?,?)", (env.sid, env.skill, "too_hard", None))
    env.db.commit()
    assert flow.lever_scores(env.db)["add_smaller_scope"] == -1.0                    # the same complaint came back
    svc, _ = practicing(env, hours=5.0)
    submit(svc, env)
    assert svc.rate(env.sid, "too_hard")["flow"]["rating"]["lever"] == "add_hint"


def test_signals_come_from_the_feedback_the_time_and_the_attempts(env):
    svc, _ = practicing(env, fb_json(("followed", "not"), mistakes=MISTAKE), fb_json(("followed", "partly"), mistakes=MISTAKE))
    submit(svc, env)
    fb1 = env.db.execute("SELECT id FROM feedback ORDER BY id").fetchone()[0]
    s1 = flow.collect(env.db, fb1)
    assert (s1.accuracy, s1.attempt, s1.improved, s1.repeated_mistake, s1.stuck) == (0.5, 1, None, False, False)
    svc.act(env.sid, "revise")
    for _ in range(10):
        env.clock.tick(minutes=1)
        svc.act(env.sid, "heartbeat")
    submit(svc, env, "\nmore")
    fb2 = env.db.execute("SELECT id FROM feedback ORDER BY id DESC").fetchone()[0]
    s2 = flow.collect(env.db, fb2, cant_start=True)
    assert (s2.accuracy, s2.prev_accuracy, s2.attempt, s2.improved, s2.no_improvement, s2.repeated_mistake) == (0.75, 0.5, 2, True, False, True)
    assert s2.time_ratio == pytest.approx(0.5, abs=0.02) and s2.reasons_stuck == ["made the same mistake twice in a row", "said you do not know where to start"]
    assert s2.success_rate == 0.5 and flow.TARGET_SUCCESS == (0.7, 0.85)


def test_success_rate_counts_attempts_with_most_principles_followed(env):
    assert flow.success_rate(env.db, env.skill) is None
    svc, _ = practicing(env, fb_json(("followed", "followed")), fb_json(("followed", "followed")), fb_json(("not", "not"), ("", ""), mistakes=[]))
    submit(svc, env)
    assert flow.success_rate(env.db, env.skill) == 1.0
    assert svc.view(env.sid)["flow"]["success_rate"] == 1.0
    assert PRACTICE["minutes"] == 20


# ---------- through the API

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}


def test_rating_endpoint(make_client):
    from helpers import FakeEmbedder

    from ai_tutor import picker, projects
    from ai_tutor import skills as sk
    from ai_tutor.llm.client import LLMClient
    be = SmartBackend(session=check_script())
    with make_client(check_kwargs=READY, embedder=lambda: FakeEmbedder(), llm_client=lambda sid: LLMClient("t", be, model="m"), resume=False) as c:
        db = c.app.state.db
        db.execute("INSERT INTO source(id, title) VALUES (1, 'Book A')")
        db.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (1,1,'Ch. 3','t','Ch. 3',41,41,'Mai reaches for the tin',1)")
        s = sk.add_skill(db, domain="d", name="Write a scene", description="d", practice_type="scene", source_id=1, unit_label=None, status="active",
                         principles=[("p1", "t1", 1), ("p2", "t2", 1)], concepts=[])
        p = projects.create(db, name="P", description="d", good_enough="g", minutes_per_session=25)
        sid = picker.start_skill(db, p, s)["session_id"]
        db.execute("UPDATE session SET phase = 'practice', timer_limit_s = 1200, task_json = ?", (json.dumps({"title": "t", "instructions": "i", "minutes": 20, "extras": {}, "template": []}),))
        db.commit()
        assert c.post(f"/api/sessions/{sid}/rating", json={"rating": "just_right"}).status_code == 409
        assert c.post("/api/sessions/99/rating", json={"rating": "just_right"}).status_code == 404
        assert c.post(f"/api/sessions/{sid}/act", json={"action": "submit", "text": WORK}).status_code == 200
        r = c.post(f"/api/sessions/{sid}/rating", json={"rating": "too_hard", "cant_start": True})
        assert r.status_code == 200 and r.json()["flow"]["rating"]["lever"] == "add_worked_example"
        again = c.post(f"/api/sessions/{sid}/rating", json={"rating": "just_right"})
        assert again.status_code == 409 and "already rated" in again.json()["detail"]["message"]
