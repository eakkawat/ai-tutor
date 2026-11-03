import json
from datetime import timedelta

import pytest
from helpers import SmartBackend, fb_json
from session_helpers import T0, WORK, to_practice, wait
from test_check_feedback import check_script
from test_flow_session import practicing

from ai_tutor import flow, hours, picker, profile, progress
from ai_tutor.llm.client import LLMClient
from ai_tutor.teaching import persona


def stored_hours(env):
    return env.db.execute("SELECT hours_total FROM learner_skill WHERE skill_id = ?", (env.skill,)).fetchone()[0]


# ---------- hours (F1)

def test_hours_add_up_across_attempts_and_include_overtime(env):
    svc, _ = practicing(env)
    wait(env, svc, 25)                                                    # the task is 20 minutes: 5 over
    svc.act(env.sid, "submit", WORK)
    assert stored_hours(env) == pytest.approx(25 / 60, abs=0.001) and env.db.execute("SELECT overtime_s FROM session").fetchone()[0] == pytest.approx(300, abs=1)
    svc.act(env.sid, "revise")
    wait(env, svc, 7)
    v = svc.act(env.sid, "submit", WORK + "\nmore")
    assert stored_hours(env) == pytest.approx(32 / 60, abs=0.001) and v["hours"] == pytest.approx(32 / 60, abs=0.01)


def test_paused_time_does_not_count(env):
    svc, _ = practicing(env)
    wait(env, svc, 5)
    svc.act(env.sid, "pause_timer")
    assert stored_hours(env) == pytest.approx(5 / 60, abs=0.001)           # a pause settles what was done so far
    env.clock.tick(minutes=30)
    svc.act(env.sid, "resume_timer")
    wait(env, svc, 5)
    svc.act(env.sid, "submit", WORK)
    assert stored_hours(env) == pytest.approx(10 / 60, abs=0.001)


def test_the_screen_shows_the_running_time_live(env):
    svc, _ = practicing(env)
    wait(env, svc, 12)
    assert svc.view(env.sid)["hours"] == pytest.approx(12 / 60, abs=0.01)


def test_a_session_ended_by_closing_the_app_keeps_the_time_up_to_its_last_sign_of_life_and_is_not_counted_twice(env):
    svc, _ = practicing(env)
    wait(env, svc, 3)
    env.clock.tick(hours=8)                                               # nobody was there
    assert hours.settle_stale_timers(env.db, env.clock()) == 1
    row = env.db.execute("SELECT timer_since, timer_elapsed_s FROM session").fetchone()
    assert row["timer_since"] is None and 180 <= row["timer_elapsed_s"] <= 270
    h = stored_hours(env)
    assert h == pytest.approx(row["timer_elapsed_s"] / 3600, abs=0.001) and hours.settle_stale_timers(env.db, env.clock()) == 0 and stored_hours(env) == h
    svc.act(env.sid, "resume_timer")
    wait(env, svc, 2)
    svc.act(env.sid, "submit", WORK)
    assert stored_hours(env) == pytest.approx((row["timer_elapsed_s"] + 120) / 3600, abs=0.001)      # the settled time is not added a second time


def test_hours_sum_over_every_session_of_a_skill_and_stay_apart_between_skills(env):
    env.db.execute("INSERT INTO session(project_id, skill_id, phase, minutes, ended_at) VALUES (1, ?, 'pass', 90, '2026-11-02 10:00:00')", (env.skill,))
    env.db.execute("INSERT INTO session(project_id, skill_id, phase, minutes, ended_at) VALUES (1, ?, 'pass', 30, '2026-11-02 11:00:00')", (env.other,))
    env.db.execute("UPDATE session SET minutes = 45 WHERE id = ?", (env.sid,))
    env.db.commit()
    assert hours.skill_seconds(env.db, env.skill, T0) / 3600 == pytest.approx((90 + 45) / 60)
    assert hours.skill_seconds(env.db, env.other, T0) / 3600 == pytest.approx(0.5)
    assert hours.recompute(env.db, env.skill, T0) == pytest.approx(2.25) and stored_hours(env) == pytest.approx(2.25)


def test_pausing_a_skill_for_another_keeps_its_hours(env):
    svc, _ = practicing(env)
    wait(env, svc, 6)
    picker.start_skill(env.db, 1, env.other, pause_current=True)
    assert stored_hours(env) == pytest.approx(6 / 60, abs=0.01)
    assert env.db.execute("SELECT status FROM learner_skill WHERE skill_id = ?", (env.skill,)).fetchone()[0] == "paused"


# ---------- the notes

def test_an_empty_profile_is_said_plainly(env):
    assert profile.profile_summary(env.db) == profile.NOTHING_YET
    assert [s["notes"] for s in profile.sections(env.db)] == [[], []] and [s["title"] for s in profile.sections(env.db)] == ["What helps me understand", "Keeping me in the flow zone"]


def test_the_learner_adds_edits_and_removes_their_own_notes(env):
    nid = profile.add_user_note(env.db, "  Short explanations;   I'd rather try and get corrected. ", "understand", T0)
    [n] = profile.list_notes(env.db)
    assert n["text"] == "Short explanations; I'd rather try and get corrected." and n["source"] == "user" and n["evidence"] == "You added this" and n["edited"]
    profile.edit_note(env.db, nid, "Short explanations, then let me try.", T0)
    assert profile.list_notes(env.db)[0]["text"] == "Short explanations, then let me try."
    profile.remove_note(env.db, nid)
    assert profile.list_notes(env.db) == [] and env.db.execute("SELECT COUNT(*) FROM profile_note").fetchone()[0] == 0
    for bad, msg in [("  ", "Write the note"), ("x" * 301, "under 300")]:
        with pytest.raises(profile.ProfileError, match=msg):
            profile.add_user_note(env.db, bad, "flow", T0)
    with pytest.raises(profile.ProfileError, match="where the note belongs"):
        profile.add_user_note(env.db, "ok", "nowhere", T0)
    with pytest.raises(profile.ProfileError, match="no longer exists"):
        profile.edit_note(env.db, 999, "x", T0)


def test_a_learned_note_is_updated_but_never_over_the_learners_edit(env):
    assert profile.upsert_auto(env.db, "auto:examples_vs_rules", "understand", "examples_vs_rules", "A scene example works better than a rule.", "Learned from 4 recall checks", T0)
    assert profile.upsert_auto(env.db, "auto:examples_vs_rules", "understand", "examples_vs_rules", "Examples beat rules for me.", "Learned from 6 recall checks", T0)
    [n] = profile.list_notes(env.db)
    assert n["text"] == "Examples beat rules for me." and n["evidence"] == "Learned from 6 recall checks" and n["source"] == "auto" and not n["edited"]
    profile.edit_note(env.db, n["id"], "Show me a scene first, then name the rule.", T0)
    assert profile.upsert_auto(env.db, "auto:examples_vs_rules", "understand", "examples_vs_rules", "Something the app now thinks.", "x", T0) is False
    assert profile.list_notes(env.db)[0]["text"] == "Show me a scene first, then name the rule."              # edits persist after the next automatic update


def test_a_removed_learned_note_is_not_learned_again(env):
    profile.upsert_auto(env.db, "auto:pacing", "flow", "pacing", "I like short tasks.", "Learned from task times", T0)
    profile.remove_note(env.db, profile.list_notes(env.db)[0]["id"])
    assert profile.list_notes(env.db) == [] and env.db.execute("SELECT removed FROM profile_note").fetchone()[0] == 1
    assert profile.upsert_auto(env.db, "auto:pacing", "flow", "pacing", "I like short tasks.", "Learned again", T0) is False
    assert profile.list_notes(env.db) == []


def test_on_one_topic_the_learners_note_wins_else_the_newest(env):
    profile.upsert_auto(env.db, "auto:explanation_length", "understand", "explanation_length", "Long explanations help me.", "Learned from 3 lessons", T0)
    profile.upsert_auto(env.db, "auto:explanation_length_b", "understand", "explanation_length", "Short explanations help me.", "Learned from 2 lessons", T0 + timedelta(hours=1))
    assert profile.profile_summary(env.db).count("explanations help me") == 1 and "Short explanations help me." in profile.profile_summary(env.db)    # newest
    mine = profile.add_user_note(env.db, "Long explanations are fine if they have a film example.", "understand", T0 - timedelta(days=3))
    env.db.execute("UPDATE profile_note SET topic = 'explanation_length' WHERE id = ?", (mine,))
    env.db.commit()
    s = profile.profile_summary(env.db)
    assert "Long explanations are fine if they have a film example." in s and "Short explanations help me." not in s          # the learner's wins even though it is older
    assert profile.upsert_auto(env.db, "auto:explanation_length_c", "understand", "explanation_length", "Medium length.", "x", T0) is False


# ---------- notes worked out from the ratings

def rating(env, used, lever=None, attempt=1, session=None):
    env.db.execute("INSERT INTO flow_rating(session_id, skill_id, attempt, rating_used, lever_changed, accuracy) VALUES (?,?,?,?,?,0.5)", (session or env.sid, env.skill, attempt, used, lever))
    env.db.commit()


def test_a_lever_that_moved_the_learner_to_just_right_becomes_a_note_and_goes_when_the_evidence_does(env):
    rating(env, "too_hard", "add_worked_example")
    rating(env, "just_right")
    rating(env, "too_hard", "add_worked_example")
    rating(env, "just_right")
    profile.refresh_derived(env.db, T0)
    [n] = profile.list_notes(env.db)
    assert n["text"] == "A worked example helps when a task feels too hard." and n["section"] == "flow" and n["evidence"] == "Learned from 2 flow ratings · lever: worked example"
    env.db.execute("DELETE FROM flow_rating")
    env.db.commit()
    profile.refresh_derived(env.db, T0)
    assert profile.list_notes(env.db) == []
    rating(env, "too_hard", "add_hint")
    rating(env, "just_right")
    profile.refresh_derived(env.db, T0)
    profile.edit_note(env.db, profile.list_notes(env.db)[0]["id"], "A hint, but only a small one.", T0)
    env.db.execute("DELETE FROM flow_rating")
    env.db.commit()
    profile.refresh_derived(env.db, T0)
    assert profile.list_notes(env.db)[0]["text"] == "A hint, but only a small one."                              # an edited note stays even when the evidence goes


def test_a_lever_that_did_not_help_is_not_remembered_as_helpful(env):
    rating(env, "too_hard", "add_hint")
    rating(env, "too_hard")
    profile.refresh_derived(env.db, T0)
    assert [n for n in profile.list_notes(env.db) if (n["topic"] or "").startswith("lever:")] == []


def test_each_lever_has_wording_for_what_it_does(env):
    for lid in flow.LEVERS:
        assert profile._lever_note(flow.LEVERS[lid]).endswith(("too hard.", "too easy."))


def test_a_kind_of_task_that_keeps_feeling_too_easy_is_noticed(env):
    rating(env, "too_easy", attempt=1)
    rating(env, "too_easy", attempt=2)
    rating(env, "just_right", attempt=3)
    profile.refresh_derived(env.db, T0)
    [n] = profile.list_notes(env.db)
    assert n["text"] == "Scene tasks often feel too easy." and n["evidence"] == "Learned from 2 of 3 flow ratings" and n["topic"] == "task_type"


def test_the_task_length_that_feels_right_is_noticed_after_three_tasks(env):
    for v, mins in ((1, 18), (2, 22), (3, 20)):
        env.db.execute("INSERT INTO message(session_id, role, content, kind, meta_json) VALUES (?, 'user', 'x', 'submission', ?)", (env.sid, json.dumps({"version": v, "minutes": mins})))
        rating(env, "just_right", attempt=v)
    profile.refresh_derived(env.db, T0)
    [n] = [x for x in profile.list_notes(env.db) if x["topic"] == "session_length"]
    assert n["text"] == "Tasks of about 20 minutes feel right." and n["evidence"] == "Learned from 3 tasks that felt just right"


# ---------- notes the model writes

def note(**kw):
    return profile.NoteOut(**{"section": "understand", "topic": "examples_vs_rules", "text": "A film scene example works better than a rule on its own.", "evidence": "Learned from 4 recall checks", **kw})


def test_only_short_backed_on_topic_notes_that_are_not_about_passing_are_kept(env):
    bad = [note(text="I should pass without the checklist."), note(text="Lower the bar for me."), note(text="x " * 40), note(evidence=""), note(topic="invented"),
           note(section="nowhere"), note(text="Please skip the concept check.")]
    assert profile.accept_llm_notes(env.db, bad, T0) == 0
    good = [note(), note(topic="pacing", section="flow", text="Short tasks keep me going.", evidence="Learned from task times"), note(topic="task_type", text="b"), note(topic="other", text="c"), note(topic="explanation_style", text="d")]
    assert profile.accept_llm_notes(env.db, good, T0) == 3                                         # at most three
    assert {n["topic"] for n in profile.list_notes(env.db)} == {"examples_vs_rules", "pacing", "task_type"}


def test_a_model_note_never_overrides_what_the_learner_wrote_on_that_topic(env):
    mine = profile.add_user_note(env.db, "Rules first, then examples.", "understand", T0)
    env.db.execute("UPDATE profile_note SET topic = 'examples_vs_rules' WHERE id = ?", (mine,))
    env.db.commit()
    assert profile.accept_llm_notes(env.db, [note()], T0) == 0
    assert [n["text"] for n in profile.list_notes(env.db)] == ["Rules first, then examples."]


def test_the_session_facts_are_counted_by_the_app(env):
    svc, _ = practicing(env, fb_json(("followed", "not"), mistakes=[{"n": 2, "kind": "execution", "concept": None, "tag": "weak push back"}]))
    svc.act(env.sid, "submit", WORK)
    svc.rate(env.sid, "just_right")
    env.db.execute("INSERT INTO message(session_id, role, content, kind, meta_json) VALUES (?, 'tutor', 'x', 'check_result', ?)", (env.sid, json.dumps({"correct": True, "level": "spot"})))
    env.db.execute("INSERT INTO message(session_id, role, content, kind, meta_json) VALUES (?, 'tutor', 'x', 'check_result', ?)", (env.sid, json.dumps({"correct": False, "level": "spot"})))
    env.db.commit()
    facts = profile.session_facts(env.db, env.sid)
    assert "Attempts: 1." in facts and "Concept check, spot questions: 1 right of 2 answers." in facts and "Attempt 1: felt just_right; no lever changed; accuracy 0.5." in facts
    assert "Mistake: weak push back (execution), seen 1 time." in facts


def test_after_a_finished_session_the_model_adds_notes_and_a_failure_adds_none(env):
    be = SmartBackend(session={"profile_update": {"notes": [{"section": "understand", "topic": "examples_vs_rules", "text": "A film scene example works better than a rule.",
                                                            "evidence": "Learned from 4 recall checks"}]}})
    llm = LLMClient("t", be, model="m")
    env.db.execute("INSERT INTO profile_note(key, value, updated_at, section, source, edited) VALUES ('user:1', 'Short explanations.', '2026-11-01 10:00:00', 'understand', 'user', 1)")
    env.db.commit()
    assert profile.update_after_session(env.db, llm, env.sid, T0) == 1
    prompt = be.users[-1]
    assert "Short explanations." in prompt and '<data label="session facts">' in prompt and "never change what it takes to pass" in prompt and "never write about passing" in prompt
    assert {n["text"] for n in profile.list_notes(env.db)} == {"Short explanations.", "A film scene example works better than a rule."}
    be.fail_on = "profile_update"
    assert profile.update_after_session(env.db, llm, env.sid, T0) == 0
    assert profile.update_after_session(env.db, None, env.sid, T0) == 0


# ---------- into every prompt

def test_the_profile_is_in_the_assembled_prompt_fenced_as_data(env):
    profile.add_user_note(env.db, "Short explanations; I'd rather try and get corrected.", "understand", T0)
    be = SmartBackend(session=check_script())
    svc = env.make(be)
    svc.act(env.sid, "begin")
    prompt = be.users[0]
    assert '<data label="learner profile">' in prompt and "Short explanations; I'd rather try and get corrected." in prompt.split('<data label="learner profile">')[1].split("</data>")[0]


def test_the_first_session_gets_the_empty_marker(env):
    be = SmartBackend(session=check_script())
    env.make(be).act(env.sid, "begin")
    assert profile.NOTHING_YET in be.users[0].split('<data label="learner profile">')[1]


def test_the_profile_in_a_prompt_is_bounded_with_the_learners_notes_first(env):
    for i in range(40):
        profile.upsert_auto(env.db, f"auto:other:{i}", "flow", "other", f"Learned note {i} " + "word " * 30, "e", T0 + timedelta(minutes=i))
    profile.add_user_note(env.db, "My own note, written first in time.", "understand", T0 - timedelta(days=9))
    s = profile.profile_summary(env.db)
    lines = s.splitlines()
    assert len(lines) <= profile.MAX_NOTES_IN_PROMPT and len(s) <= profile.MAX_PROFILE_CHARS and lines[0] == "- My own note, written first in time."
    assert all(len(line) <= 225 for line in lines)


def test_counted_facts_about_the_current_skill_join_the_notes(env):
    env.db.execute("INSERT INTO mistake(skill_id, kind, tag, count) VALUES (?, 'execution', 'weak ending', 3)", (env.skill,))
    env.db.execute("UPDATE concept_mastery SET confusions_json = ? WHERE concept_id = ?", (json.dumps([{"with": "exposition", "count": 2}]), env.c1))
    env.db.commit()
    s = profile.profile_summary(env.db, env.skill)
    assert "Keeps making this mistake on this skill (execution): weak ending, 3 times." in s and "Mixes up want with exposition (2 times)." in s
    assert "weak ending" not in profile.profile_summary(env.db)


def test_notes_shape_teaching_but_never_the_pass_rule():
    assert "never change what it takes to pass" in persona() and "the principle checklist alone decides" in persona()


# ---------- the Progress screen

def test_progress_shows_hours_per_skill_toward_twenty_status_in_words_and_totals(env):
    env.db.execute("UPDATE session SET minutes = 174 WHERE id = ?", (env.sid,))                  # 2.9 hours
    env.db.execute("UPDATE learner_skill SET status = 'active' WHERE skill_id = ?", (env.skill,))
    env.db.execute("INSERT INTO learner_skill(skill_id, status, last_session_at) VALUES (?, 'passed', '2026-11-01 10:00:00')", (env.other,))
    env.db.execute("INSERT INTO session(project_id, skill_id, phase, minutes) VALUES (1, ?, 'pass', 204)", (env.other,))                    # 3.4 hours
    env.db.commit()
    p = progress.build(env.db, T0)
    by = {s["name"]: s for s in p["skills"]}
    assert by["Write a want and obstacle scene"]["hours"] == 2.9 and by["Write a want and obstacle scene"]["status_text"] == "active" and by["Write a want and obstacle scene"]["bar"] == pytest.approx(0.145)
    assert by["Cut on action"]["hours"] == 3.4 and by["Cut on action"]["status_text"] == "passed"
    assert p["totals"]["practice_hours"] == 6.3 and p["totals"]["skills_passed"] == 1 and p["target"] == 20


def test_more_than_twenty_hours_is_shown_in_full_without_breaking_the_bar(env):
    env.db.execute("UPDATE session SET minutes = 21.4 * 60")
    env.db.commit()
    s = progress.build(env.db, T0)["skills"][0]
    assert s["hours"] == 21.4 and s["bar"] == 1.0 and s["over"] == 1.4


def test_a_skill_with_no_practice_is_left_off_and_the_empty_screen_is_all_zero(env):
    env.db.execute("UPDATE session SET minutes = 0")
    env.db.execute("DELETE FROM learner_skill")
    env.db.commit()
    p = progress.build(env.db, T0)
    assert p["skills"] == [] and p["totals"] == {"practice_hours": 0, "skills_passed": 0, "just_right": [0, 0], "reviews_right": [0, 0]} and p["mistakes"] == [] and p["flow_history"] == []


def test_recurring_mistakes_are_counted_and_marked_fixed_when_the_last_feedback_no_longer_has_them(env):
    svc, _ = practicing(env, fb_json(("followed", "not"), mistakes=[{"n": 2, "kind": "execution", "concept": None, "tag": "weak ending"}]),
                        fb_json(("followed", "followed")))
    svc.act(env.sid, "submit", WORK)
    assert [(m["tag"], m["count"], m["fixed"]) for m in progress.build(env.db, T0)["mistakes"]] == [("weak ending", 1, False)]
    svc.rate(env.sid, "just_right")
    svc.act(env.sid, "revise")
    svc.act(env.sid, "submit", WORK + "\nmore")
    assert [(m["tag"], m["fixed"]) for m in progress.build(env.db, T0)["mistakes"]] == [("weak ending", True)]


def test_flow_history_says_what_felt_how_and_what_changed(env):
    svc, _ = practicing(env)
    svc.act(env.sid, "submit", WORK)
    svc.rate(env.sid, "too_hard")
    svc.act(env.sid, "revise")
    svc.act(env.sid, "submit", WORK + "\nmore")
    svc.rate(env.sid, "too_easy")
    h = progress.build(env.db, T0)["flow_history"]
    assert [(x["task"], x["felt"], x["changed"]) for x in h] == [("Attempt 2", "Too easy", "Removed a beat template"), ("Attempt 1", "Too hard", "Kept level (productive struggle)")]
    assert progress.build(env.db, T0)["totals"]["just_right"] == [0, 2]


def test_every_kind_of_change_has_words(env):
    class R(dict):
        pass
    for lid, lv in flow.LEVERS.items():
        text = progress.what_changed({"lever_changed": lid, "classification": "x"})
        assert text.startswith(("Added", "Removed", "Took away")) and flow.LABEL[lv.name] in text
    assert progress.what_changed({"lever_changed": None, "classification": "on_target"}) == "No change"


# ---------- through the API

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}


def test_profile_and_progress_endpoints(make_client):
    with make_client(check_kwargs=READY) as c:
        assert c.get("/api/profile").json()["sections"][0]["notes"] == []
        n = c.post("/api/profile/notes", json={"text": "Short explanations.", "section": "understand"}).json()
        assert n["source"] == "user" and n["evidence"] == "You added this"
        assert c.post("/api/profile/notes", json={"text": " ", "section": "flow"}).json()["detail"]["message"] == "Write the note first."
        assert c.patch(f"/api/profile/notes/{n['id']}", json={"text": "Short, then let me try."}).json()["text"] == "Short, then let me try."
        assert c.patch("/api/profile/notes/999", json={"text": "x"}).status_code == 400
        assert c.delete(f"/api/profile/notes/{n['id']}").json() == {"ok": True}
        assert c.get("/api/profile").json()["sections"][0]["notes"] == []
        p = c.get("/api/progress").json()
        assert p["totals"]["practice_hours"] == 0 and p["target"] == 20


def test_finishing_a_skill_learns_from_the_session_after_the_reply(make_client):
    from helpers import FakeEmbedder

    from ai_tutor import skills as sk
    be = SmartBackend(session={**check_script(), "diagnose_eval": lambda u, c: {"principles": [{"n": 1, "result": "followed", "evidence": "q"}, {"n": 2, "result": "followed", "evidence": "q"}],
                                                                              "can_do": "all", "gap": "none", "level": 3},
                               "profile_update": {"notes": [{"section": "flow", "topic": "pacing", "text": "Short tasks keep me going.", "evidence": "Learned from task times"}]}})
    with make_client(check_kwargs=READY, embedder=lambda: FakeEmbedder(), llm_client=lambda sid: LLMClient("t", be, model="m"), resume=False) as c:
        db = c.app.state.db
        db.execute("INSERT INTO source(id, title) VALUES (1, 'Book A')")
        db.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (1,1,'Ch. 3','t','Ch. 3',41,41,'A scene needs a want.',1)")
        s = sk.add_skill(db, domain="d", name="Write a scene", description="d", practice_type="scene", source_id=1, unit_label=None, status="active",
                         principles=[("p1", "t1", 1), ("p2", "t2", 1)], concepts=[])
        from ai_tutor import projects
        sid = picker.start_skill(db, projects.create(db, name="P", description="d", good_enough="g", minutes_per_session=25), s)["session_id"]
        c.post(f"/api/sessions/{sid}/act", json={"action": "begin"})
        c.post(f"/api/sessions/{sid}/act", json={"action": "answer", "text": "a strong answer"})
        done = c.post(f"/api/sessions/{sid}/act", json={"action": "advance"}).json()
        assert done["ended"] is True
        assert [n["text"] for n in c.get("/api/profile").json()["sections"][1]["notes"]] == ["Short tasks keep me going."]       # the background task ran after the reply


def test_to_practice_is_importable():
    assert to_practice
