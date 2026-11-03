"""Spaced review, Continue's two questions, Review mode and the 3-minute concept check. No network: the model is scripted."""
import json
import re
from datetime import timedelta

import pytest
from helpers import SmartBackend
from session_helpers import T0, script, to_learn

from ai_tutor import review
from ai_tutor.review import ReviewError, ReviewService, next_schedule
from ai_tutor.session import REVIEW_FIRST_INTERVAL, TransitionError  # noqa: F401
from ai_tutor.teaching import TutorError


def learner_answer(user):
    return re.search(r'<data label="learner answer">\n(.*?)\n</data>', user, re.DOTALL).group(1)


def judge_by(word="right"):
    ok = lambda u: word in learner_answer(u)
    return lambda u, c: {"correct": ok(u), "feedback": "That is the idea." if ok(u) else "Not quite.", "hint": "Think about who pushes back.", "confused_with": None}


SPOT = {"prompt": "Which line shows an obstacle?\nA. MAI: Hi.\nB. GRANDMA: Leave it.", "answer_key": "B, because Grandma pushes back."}
USE = {"prompt": "Write one line where Grandma blocks Mai.", "answer_key": "A line that pushes back on Mai's want."}


def review_script(**over):
    return script(**{"review_check": judge_by(), "concept_check": judge_by(), "concept_hint": {"hint": "Look at who pushes back."}, "concept_spot": SPOT,
                     "concept_use": USE, **over})


def svc_for(env, **over):
    be = SmartBackend(session=review_script(**over))
    from ai_tutor.llm.client import LLMClient
    s = ReviewService(env.db, llm=LLMClient("t", be, model="m"), embedder=None, clock=env.clock)
    s.be = be
    return s


def pass_skill(env, skill_id=None, *, concepts=True):
    """Mark a skill passed and schedule its reviews, as passing does."""
    from ai_tutor import skills as sk
    skill_id = skill_id or env.skill
    env.db.execute("INSERT INTO learner_skill(skill_id, status, last_session_at) VALUES (?, 'passed', ?) ON CONFLICT(skill_id) DO UPDATE SET status = 'passed', last_session_at = excluded.last_session_at",
                   (skill_id, review.iso(env.clock())))
    detail = sk.skill_detail(env.db, skill_id)
    if not concepts:
        detail["concepts"] = []
    review.create_for_passed_skill(env.db, detail, env.clock(), REVIEW_FIRST_INTERVAL)


def due(env, days=1):
    env.clock.tick(days=days, minutes=1)


def items(env):
    return [dict(r) for r in env.db.execute("SELECT * FROM review_item ORDER BY id")]


def level(env, cid):
    return env.db.execute("SELECT level FROM concept_mastery WHERE concept_id = ?", (cid,)).fetchone()["level"]


# ---------- the schedule

def test_right_answers_push_the_item_out_and_a_miss_brings_it_back_tomorrow():
    s1 = next_schedule(0, 0, 2.5, right=True)
    s2 = next_schedule(s1["reps"], s1["interval_days"], s1["ease"], right=True)
    s3 = next_schedule(s2["reps"], s2["interval_days"], s2["ease"], right=True)
    s4 = next_schedule(s3["reps"], s3["interval_days"], s3["ease"], right=True)
    assert [s1["interval_days"], s2["interval_days"]] == [3.0, 7.0]
    assert s3["interval_days"] > 7 and s4["interval_days"] > s3["interval_days"]
    miss = next_schedule(s4["reps"], s4["interval_days"], s4["ease"], right=False)
    assert miss["interval_days"] == 1.0 and miss["reps"] == 0 and miss["ease"] < s4["ease"]


def test_ease_never_falls_below_the_floor_or_climbs_past_the_ceiling():
    e = 2.5
    for _ in range(20):
        e = next_schedule(0, 1, e, right=False)["ease"]
    assert e == review.MIN_EASE
    e = 2.9
    for _ in range(20):
        e = next_schedule(3, 10, e, right=True)["ease"]
    assert e == review.MAX_EASE


# ---------- items are created at pass and check time

def test_passing_a_skill_schedules_its_question_and_one_per_concept_for_tomorrow(env):
    pass_skill(env)
    rows = items(env)
    assert len(rows) == 3 and sum(r["concept_id"] is None for r in rows) == 1
    assert {r["due_at"] for r in rows} == {review.iso(T0 + timedelta(days=1))}
    assert next(r for r in rows if r["concept_id"] == env.c1)["level"] == "spot"        # the stored spot question
    assert next(r for r in rows if r["concept_id"] == env.c2)["level"] == "define"      # no spot question stored: the define one


def test_passing_again_does_not_duplicate_items(env):
    pass_skill(env)
    pass_skill(env)
    assert len(items(env)) == 3


def test_a_concept_shared_by_two_skills_has_one_item(env):
    from ai_tutor import skills as sk
    env.db.execute("INSERT INTO skill_concept(skill_id, concept_id, required_level) VALUES (?,?, 'spot')", (env.other, env.c1))
    env.db.commit()
    pass_skill(env)
    pass_skill(env, env.other)
    assert sum(r["concept_id"] == env.c1 for r in items(env)) == 1
    assert sk.skill_detail(env.db, env.other)["concepts"]


def test_a_skill_question_is_only_asked_while_the_skill_is_passed(env):
    pass_skill(env)
    due(env)
    assert review.due_count(env.db, env.clock()) == 3
    env.db.execute("UPDATE learner_skill SET status = 'needs_practice' WHERE skill_id = ?", (env.skill,))
    assert review.due_count(env.db, env.clock()) == 2          # concepts stay in the mix


def test_nothing_is_due_before_its_day(env):
    pass_skill(env)
    assert review.due_count(env.db, env.clock()) == 0


# ---------- which two questions

def test_the_pick_mixes_a_skill_and_a_concept(env):
    pass_skill(env)
    due(env)
    picked = review.pick(env.db, env.clock(), 2)
    assert len(picked) == 2 and {bool(p["concept_id"]) for p in picked} == {True, False}


def test_past_mistakes_are_asked_first(env):
    pass_skill(env)
    pass_skill(env, env.other)
    due(env)
    env.db.execute("INSERT INTO mistake(skill_id, concept_id, kind, tag, count) VALUES (?,?, 'concept', 'x', 3)", (env.skill, env.c2))
    env.db.commit()
    first = review.pick(env.db, env.clock(), 1)[0]
    assert first["concept_id"] == env.c2


def test_a_shaky_concept_is_asked_before_a_secure_one(env):
    pass_skill(env)
    due(env)
    env.db.execute("UPDATE concept_mastery SET level = 'spot' WHERE concept_id = ?", (env.c1,))
    env.db.execute("UPDATE concept_mastery SET level = 'define', confusions_json = ? WHERE concept_id = ?", (json.dumps([{"with": "exposition", "count": 2}]), env.c2))
    env.db.commit()
    concepts = [p for p in review.pick(env.db, env.clock(), 3) if p["concept_id"]]
    assert concepts[0]["concept_id"] == env.c2


# ---------- Continue: two questions, then the work

def test_continue_asks_two_questions_and_nothing_when_nothing_is_due(env):
    s = svc_for(env)
    assert s.start("continue", session_id=env.sid) is None
    pass_skill(env)
    due(env)
    v = s.start("continue", session_id=env.sid)
    assert v["total"] == 2 and v["current"]["n"] == 1 and v["session_id"] == env.sid


def test_a_right_answer_schedules_later_and_raises_the_concept(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    run = s.start("review")["id"]
    v = s.view(run)
    while v["current"]["kind"] != "concept":              # answer the skill question wrongly to reach a concept
        s.show(run)
        v = s.next(run)
    cid = next(q for q in json.loads(env.db.execute("SELECT questions_json FROM review_run").fetchone()[0]) if q["kind"] == "concept")["concept_id"]
    v = s.answer(run, "this is right")
    assert v["current"]["correct"] and v["current"]["finished"] and v["current"]["citations"]
    item = env.db.execute("SELECT * FROM review_item WHERE concept_id = ?", (cid,)).fetchone()
    assert item["last_result"] == "right" and item["interval_days"] == 3.0 and item["due_at"] > review.iso(env.clock())
    assert level(env, cid) in ("define", "spot")


def test_a_wrong_answer_gives_a_hint_then_a_second_wrong_shows_the_answer_with_a_citation(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    v = s.start("review")
    run = v["id"]
    v = s.answer(run, "zzz")
    assert not v["current"]["correct"] and v["current"]["hint"] and not v["current"]["finished"] and v["current"]["answer"] is None
    v = s.answer(run, "still nothing")
    c = v["current"]
    assert c["finished"] and c["answer"] and re.match(r"\[Book A, ch\. \d+, p\. \d+\]", c["citations"][0]["citation"])
    item = env.db.execute("SELECT * FROM review_item WHERE id = ?", (json.loads(env.db.execute("SELECT questions_json FROM review_run").fetchone()[0])[0]["item_id"],)).fetchone()
    assert item["last_result"] == "wrong" and item["misses"] == 1 and item["interval_days"] == 1.0
    assert env.db.execute("SELECT COUNT(*) FROM review_result").fetchone()[0] == 1          # the first answer is the one that counts


def test_right_after_a_hint_still_counts_as_a_miss(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    run = s.start("review")["id"]
    s.answer(run, "zzz")
    v = s.answer(run, "right now")
    assert v["current"]["correct"] and "still counts as a miss" in v["current"]["feedback"]
    assert env.db.execute("SELECT result FROM review_result").fetchall()[0]["result"] == "wrong"


def test_show_answer_counts_as_a_miss_and_next_needs_an_answer_first(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    run = s.start("review")["id"]
    with pytest.raises(ReviewError, match="Answer this question first"):
        s.next(run)
    v = s.show(run)
    assert v["current"]["finished"] and v["current"]["answer"]
    assert env.db.execute("SELECT result FROM review_result").fetchone()["result"] == "wrong"
    with pytest.raises(ReviewError):
        s.answer(run, "right")


def test_a_failed_concept_drops_to_the_level_below(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    env.db.execute("UPDATE concept_mastery SET level = 'use' WHERE concept_id = ?", (env.c1,))
    env.db.commit()
    run = s.start("review")["id"]
    for _ in range(3):
        v = s.show(run)
        if v["current"]["context"].startswith("Concept · want"):
            break
        v = s.next(run)
    assert level(env, env.c1) == "define"
    assert review_summary_note(s, run)


def review_summary_note(s, run):
    return "want goes back to Define" in " ".join(s.end(run)["summary"]["notes"])


def test_missing_a_skill_twice_in_a_row_sends_it_back_to_needs_practice(env):
    s = svc_for(env)
    pass_skill(env, concepts=False)
    due(env)
    run = s.start("review")["id"]
    s.show(run)
    s.next(run)
    assert env.db.execute("SELECT status FROM learner_skill WHERE skill_id = ?", (env.skill,)).fetchone()["status"] == "passed"
    due(env)
    run = s.start("review")["id"]
    s.show(run)
    v = s.next(run)
    assert env.db.execute("SELECT status FROM learner_skill WHERE skill_id = ?", (env.skill,)).fetchone()["status"] == "needs_practice"
    assert any("needs practice" in n for n in v["summary"]["notes"])


def test_a_right_answer_in_between_resets_the_count(env):
    s = svc_for(env)
    pass_skill(env, concepts=False)
    for word in ("zzz", "right", "zzz"):
        due(env, 30)
        run = s.start("review")["id"]
        if word == "right":
            s.answer(run, word)
        else:
            s.show(run)
        s.next(run)
    assert env.db.execute("SELECT status FROM learner_skill WHERE skill_id = ?", (env.skill,)).fetchone()["status"] == "passed"


# ---------- closing and reopening

def test_a_sitting_survives_closing_the_app(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    first = s.start("continue", session_id=env.sid)
    s.show(first["id"])
    s.next(first["id"])
    again = svc_for(env).start("continue", session_id=env.sid)          # a new service: the app was closed and reopened
    assert again["id"] == first["id"] and again["current"]["n"] == 2 and again["answered"] == 1


def test_continue_resumes_the_exact_phase_and_task_after_two_questions(env):
    s = svc_for(env)
    svc = to_learn(env, env.make(SmartBackend(session=script())))
    before = env.db.execute("SELECT * FROM session WHERE id = ?", (env.sid,)).fetchone()
    pass_skill(env)
    due(env)
    run = s.start("continue", session_id=env.sid)["id"]
    s.show(run)
    s.next(run)
    v = s.show(run)
    v = s.next(run)
    assert v["ended"] and v["session_id"] == env.sid
    after = env.db.execute("SELECT * FROM session WHERE id = ?", (env.sid,)).fetchone()
    assert tuple(before) == tuple(after)
    assert svc.view(env.sid)["phase"] == before["phase"]


def test_after_a_continue_review_the_next_continue_goes_straight_to_the_work(env):
    s = svc_for(env)
    pass_skill(env)
    pass_skill(env, env.other)
    due(env)
    assert review.continue_waiting(env.db, env.clock())
    run = s.start("continue", session_id=env.sid)["id"]
    for _ in range(2):
        s.show(run)
        s.next(run)
    assert review.due_count(env.db, env.clock()) > 0           # more is due, but not today's Continue
    assert not review.continue_waiting(env.db, env.clock()) and s.start("continue", session_id=env.sid) is None
    env.clock.tick(hours=5)
    assert review.continue_waiting(env.db, env.clock())


# ---------- Review mode

def test_review_mode_is_capped_and_ends_with_a_summary(env):
    s = svc_for(env)
    for i in range(12):
        env.db.execute("INSERT INTO review_item(skill_id, concept_id, level, question, answer, due_at) VALUES (NULL, ?, 'define', ?, 'a', ?)", (env.c1, f"q{i}", review.iso(T0)))
    env.db.commit()
    v = s.start("review")
    assert v["total"] == review.REVIEW_CAP
    s.answer(v["id"], "right")
    s.next(v["id"])
    s.show(v["id"])
    s.next(v["id"])
    out = s.end(v["id"])
    assert out["ended"] and out["summary"]["right"] == 1 and out["summary"]["wrong"] == 1 and out["summary"]["skipped"] == review.REVIEW_CAP - 2
    assert {r["when"] for r in out["summary"]["rows"]} == {"back in 3 days", "back tomorrow"}
    assert review.due_count(env.db, env.clock()) == 12 - 2          # unanswered items stay due


def test_review_covers_concepts_mixed_across_skills(env):
    s = svc_for(env)
    pass_skill(env)
    pass_skill(env, env.other)
    env.db.execute("INSERT INTO skill_concept(skill_id, concept_id, required_level) VALUES (?,?, 'spot')", (env.other, env.c2))
    env.db.commit()
    due(env)
    run = json.loads(env.db.execute("SELECT questions_json FROM review_run WHERE id = ?", (s.start("review")["id"],)).fetchone()[0])
    assert {q["kind"] for q in run} == {"skill", "concept"} and len({q["skill_id"] for q in run}) == 2


def test_two_open_sittings_never_share_a_question(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    a = s.start("continue", session_id=env.sid)
    b = s.start("review")
    ids = lambda v: {q["item_id"] for q in json.loads(env.db.execute("SELECT questions_json FROM review_run WHERE id = ?", (v["id"],)).fetchone()[0])}
    assert not ids(a) & ids(b)


def test_a_model_failure_changes_nothing_and_a_retry_works(env):
    s = svc_for(env)
    pass_skill(env)
    due(env)
    run = s.start("review")["id"]
    s.be.fail_on = "review_check"
    first = json.loads(env.db.execute("SELECT questions_json FROM review_run").fetchone()[0])[0]
    if first["kind"] == "concept":
        s.be.fail_on = "concept_check"
    with pytest.raises(TutorError):
        s.answer(run, "right")
    assert env.db.execute("SELECT COUNT(*) FROM review_result").fetchone()[0] == 0
    assert env.db.execute("SELECT state_json FROM review_run WHERE id = ?", (run,)).fetchone()[0] is None
    assert s.answer(run, "right")["current"]["correct"]


# ---------- the 3-minute concept check

def test_the_concept_check_runs_define_spot_use_and_updates_the_level(env):
    s = svc_for(env)
    v = s.start("concept", concept_id=env.c2)
    assert v["total"] == 3 and v["current"]["level"] == "define"
    run = v["id"]
    for expect in ("spot", "use"):
        s.answer(run, "right")
        v = s.next(run)
        assert v["current"]["level"] == expect
    v = s.answer(run, "right")
    v = s.next(run)
    assert v["ended"] and level(env, env.c2) == "use" and v["summary"]["level"] == "use"
    assert env.db.execute("SELECT COUNT(*) FROM review_item WHERE concept_id = ?", (env.c2,)).fetchone()[0] == 1          # now it comes back in review


def test_a_concept_with_no_spot_question_gets_one_before_it_is_checked(env):
    s = svc_for(env)
    assert env.db.execute("SELECT COUNT(*) FROM concept_question WHERE concept_id = ? AND level = 'spot'", (env.c2,)).fetchone()[0] == 0
    run = s.start("concept", concept_id=env.c2)["id"]
    s.answer(run, "right")
    v = s.next(run)
    assert v["current"]["prompt"] == SPOT["prompt"] and v["current"]["options"] and s.be.calls["concept_spot"] == 1


def test_a_missed_level_ends_the_check_and_the_levels_above_are_not_asked(env):
    s = svc_for(env)
    run = s.start("concept", concept_id=env.c1)["id"]
    s.answer(run, "right")
    s.next(run)
    s.show(run)
    v = s.next(run)
    assert v["ended"] and v["summary"]["right"] == 1 and v["summary"]["wrong"] == 1 and s.be.calls["concept_use"] == 0
    assert level(env, env.c1) == "define"


def test_a_concept_check_can_be_resumed(env):
    s = svc_for(env)
    first = s.start("concept", concept_id=env.c1)
    assert svc_for(env).start("concept", concept_id=env.c1)["id"] == first["id"]
    assert s.start("concept", concept_id=env.c2)["id"] != first["id"]


def test_an_unknown_concept_is_refused(env):
    with pytest.raises(ReviewError, match="no longer exists"):
        svc_for(env).start("concept", concept_id=9999)


# ---------- the screens' data

def test_progress_counts_review_answers(env):
    from ai_tutor import progress
    s = svc_for(env)
    pass_skill(env)
    due(env)
    run = s.start("review")["id"]
    s.answer(run, "right")
    s.next(run)
    s.show(run)
    assert progress.build(env.db, env.clock())["totals"]["reviews_right"] == [1, 2]


def test_home_says_when_continue_starts_with_a_review(env):
    from ai_tutor.home import home_state
    pass_skill(env, env.other)
    h = home_state(env.db, env.clock())
    assert h["state"] == "active_skill" and h["review_first"] is False
    due(env)
    h = home_state(env.db, env.clock())
    assert h["state"] == "reviews_due" and h["reviews_due"] >= 1 and h["review_first"] is True


# ---------- through the API

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}


def test_review_endpoints(make_client):
    from helpers import FakeEmbedder

    from ai_tutor import picker, projects
    from ai_tutor import skills as sk
    from ai_tutor.llm.client import LLMClient
    be = SmartBackend(session=review_script())
    with make_client(check_kwargs=READY, embedder=lambda: FakeEmbedder(), llm_client=lambda sid: LLMClient("t", be, model="m"), resume=False) as c:
        db = c.app.state.db
        db.execute("INSERT INTO source(id, title) VALUES (1, 'Book A')")
        db.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (1,1,'Ch. 3','t','Ch. 3',41,41,'Mai reaches',1)")
        cid = sk.add_concept(db, name="want", definition="what a character is after", example="e", chunk_ids=[1], questions=[("spot", "Which shows a want?\nA. x\nB. y", "B")])
        done = sk.add_skill(db, domain="d", name="Cut on action", description="d", practice_type="edit", source_id=1, unit_label=None, status="active",
                            principles=[("Cut during the move", "t", 1)], concepts=[(cid, "spot")])
        now = sk.add_skill(db, domain="d", name="Write a scene", description="d", practice_type="scene", source_id=1, unit_label=None, status="active",
                           principles=[("p1", "t1", 1)], concepts=[])
        p = projects.create(db, name="P", description="d", good_enough="g", minutes_per_session=25)
        sid = picker.start_skill(db, p, now)["session_id"]
        assert c.get("/api/home").json()["review_first"] is False
        assert c.post("/api/review/start", json={"mode": "continue", "session_id": sid}).json() == {"run": None}
        db.execute("INSERT INTO learner_skill(skill_id, status, last_session_at) VALUES (?, 'passed', '2026-10-01 10:00:00')", (done,))
        review.create_for_passed_skill(db, sk.skill_detail(db, done), review.parse("2026-10-01 10:00:00"), timedelta(days=1))
        h = c.get("/api/home").json()
        assert h["state"] == "reviews_due" and h["review_first"] is True and h["reviews_due"] == 2
        v = c.post("/api/review/start", json={"mode": "continue", "session_id": sid}).json()["run"]
        assert v["total"] == 2 and v["current"]["context"]
        again = c.post("/api/review/start", json={"mode": "continue", "session_id": sid}).json()["run"]
        assert again["id"] == v["id"]
        assert c.post(f"/api/review/{v['id']}/next").status_code == 409
        a = c.post(f"/api/review/{v['id']}/answer", json={"text": ""})
        assert a.status_code == 409 and a.json()["detail"]["message"] == "Write your answer first."
        r = c.post(f"/api/review/{v['id']}/answer", json={"text": "zzz"}).json()
        assert r["current"]["hint"] and not r["current"]["finished"]
        assert c.post(f"/api/review/{v['id']}/hint").status_code == 409
        assert c.post(f"/api/review/{v['id']}/show").json()["current"]["answer"]
        r = c.post(f"/api/review/{v['id']}/next").json()
        assert r["current"]["n"] == 2
        r = c.post(f"/api/review/{v['id']}/end").json()
        assert r["ended"] and r["summary"]["wrong"] == 1
        assert c.get("/api/home").json()["review_first"] is False
        assert c.get("/api/review/999").status_code == 404
        assert c.post("/api/review/start", json={"mode": "bogus"}).status_code == 409
        assert c.post("/api/review/start", json={"mode": "concept", "concept_id": 999}).status_code == 409
        be.fail_on = "concept_check"
        run = c.post("/api/review/start", json={"mode": "concept", "concept_id": cid}).json()["run"]
        assert run["current"]["level"] == "define"
        failed = c.post(f"/api/review/{run['id']}/answer", json={"text": "right"})
        assert failed.status_code == 503 and "Nothing was changed" in failed.json()["detail"]["message"]
        assert c.post(f"/api/review/{run['id']}/answer", json={"text": "right"}).json()["current"]["correct"]


def test_citations_in_the_models_remarks_are_dropped_and_the_apps_own_are_shown(env):
    assert review.plain("Close. Subtext is unsaid [Book A], ch. 5, p. 70. Look again [Book A, ch. 5, p. 70].") == "Close. Subtext is unsaid. Look again."
    s = svc_for(env, concept_check=lambda u, c: {"correct": False, "feedback": "Not it [Book Z, ch. 9, p. 999].", "hint": "Try [Book Z, p. 1] again", "confused_with": None})
    run = s.start("concept", concept_id=env.c1)["id"]
    v = s.answer(run, "zzz")
    assert "Book Z" not in v["current"]["feedback"] and "Book Z" not in v["current"]["hint"]
    v = s.answer(run, "zzz")
    assert v["current"]["citations"][0]["citation"] == "[Book A, ch. 3, p. 41]"
