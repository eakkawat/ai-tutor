import pytest
from helpers import TRIAGE_REF, FakeEmbedder, SmartBackend, concept_json, make_pdf, skill_json

from ai_tutor import app_settings
from ai_tutor import skills as sk
from ai_tutor.llm.client import LLMClient

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}
CHAPTERS = [("Chapter 1: Want", 3), ("Chapter 2: Obstacle", 3), ("Chapter 3: Stakes", 2)]


@pytest.fixture
def app_for(make_client, tmp_path):
    def make(backend, *, mode="manual", embedder=None):
        app_settings.save(app_settings.AppSettings(skill_mode=mode))
        emb = embedder or FakeEmbedder()
        c = make_client(check_kwargs=READY, embedder=lambda: emb, llm_client=lambda sid: LLMClient("triage", backend, model="m"), resume=False)
        c.backend = backend
        return c
    return make


def add_book(c, tmp_path, name="[Book A].pdf", chapters=CHAPTERS, title="[Book A]"):
    p = make_pdf(tmp_path / name, chapters, title=title)
    r = c.post("/api/library/upload", files=[("files", (p.name, p.read_bytes(), "application/pdf"))])
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    c.app.state.worker.wait(sid, 30)
    return sid, next(s for s in c.get("/api/library").json()["sources"] if s["id"] == sid)


def two_skills(label, ids, existing):
    return {"Ch. 1": [skill_json("Write a want and obstacle scene", ids, concepts=("subtext", "objective"), prereqs=["Write a logline"])],
            "Ch. 2": [skill_json("Raise the stakes in a scene", ids, concepts=("subtext",))]}.get(label, [])


def test_manual_mode_proposes_skills_with_cited_principles_and_concepts(app_for, tmp_path):
    with app_for(SmartBackend(skills=two_skills)) as c:
        _sid, s = add_book(c, tmp_path)
        assert s["status"] == "ready" and s["pending_skills"] == 2 and s["skills"] == 0
        assert s["message"] == "2 new skills waiting for your review."
        db = c.app.state.db
        assert db.execute("SELECT COUNT(*) FROM skill WHERE status = 'pending'").fetchone()[0] == 2
        pend = c.get("/api/skills/pending").json()["skills"]
        want = next(p for p in pend if p["name"].startswith("Write a want"))
        assert len(want["principles"]) == 2 and all(p["citation"].startswith("[[Book A], ch. 1") for p in want["principles"])
        assert want["sources"][0]["title"] == "[Book A]" and want["practice_type"] == "scene"
        assert {c_["name"] for c_ in want["concepts"]} == {"subtext", "objective"}
        # every concept has a cited definition and an example, and questions at all three levels
        for cid, in db.execute("SELECT id FROM concept"):
            d = c.get(f"/api/concepts/{cid}").json()
            assert d["definition"] and d["example"] and d["sources"] and d["questions"] == {"define": 1, "spot": 1, "use": 1}
        assert c.get("/api/skills").json()["domains"] == []         # nothing on the map until accepted


def test_auto_mode_adds_skills_straight_to_the_map(app_for, tmp_path):
    with app_for(SmartBackend(skills=two_skills), mode="auto") as c:
        _, s = add_book(c, tmp_path)
        assert s["skills"] == 2 and s["pending_skills"] == 0 and s["message"] is None
        doms = c.get("/api/skills").json()["domains"]
        assert [d["domain"] for d in doms] == ["general"] and len(doms[0]["skills"]) == 2


def test_bad_model_output_is_dropped_not_stored(app_for, tmp_path):
    def skills(label, ids, existing):
        if label != "Ch. 1":
            return []
        good = skill_json("Good skill", ids)
        bad_ids = skill_json("Skill with invented sources", ids)
        for p in bad_ids["principles"]:
            p["chunk_id"] = 99999
        one = skill_json("Skill with one principle", ids, principles=1)
        none = skill_json("Skill with no concepts", ids, concepts=())
        return [good, bad_ids, one, none]
    with app_for(SmartBackend(skills=skills), mode="auto") as c:
        add_book(c, tmp_path)
        names = [r["name"] for r in c.app.state.db.execute("SELECT name FROM skill")]
        assert names == ["Good skill"]


def test_zero_valid_skills_says_why_and_offers_another_look(app_for, tmp_path):
    with app_for(SmartBackend(skills=lambda *a: [])) as c:
        sid, s = add_book(c, tmp_path)
        assert s["status"] == "ready" and "No valid skills" in s["message"] and s["skills"] == 0
        c.app.state.worker.backend = None
        assert c.post(f"/api/library/{sid}/find-skills").status_code == 200
        c.app.state.worker.wait(sid, 30)


def test_a_concept_is_defined_once_and_reused_across_skills(app_for, tmp_path):
    backend = SmartBackend(skills=two_skills)
    with app_for(backend, mode="auto") as c:
        add_book(c, tmp_path)
        db = c.app.state.db
        assert db.execute("SELECT COUNT(*) FROM concept WHERE name = 'subtext'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM skill_concept WHERE concept_id = (SELECT id FROM concept WHERE name='subtext')").fetchone()[0] == 2
        assert backend.calls["concept_extraction"] == 1          # chapter 2 only needed 'subtext', which already existed


def test_a_concept_found_again_under_another_name_is_linked_not_duplicated(app_for, tmp_path):
    same = "a scene shows what a character will not say aloud and the reader feels it"
    def skills(label, ids, existing):
        return {"Ch. 1": [skill_json("Skill one", ids, concepts=("subtext",))], "Ch. 2": [skill_json("Skill two", ids, concepts=("unspoken meaning",))]}.get(label, [])
    def concepts(names, ids):
        return [concept_json(n, ids[0], definition=same) for n in names]
    with app_for(SmartBackend(skills=skills, concepts=concepts), mode="auto") as c:
        add_book(c, tmp_path)
        db = c.app.state.db
        assert db.execute("SELECT COUNT(*) FROM concept").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM concept_source").fetchone()[0] == 2           # both passages now back the one concept
        assert db.execute("SELECT COUNT(DISTINCT skill_id) FROM skill_concept").fetchone()[0] == 2


def test_a_concept_used_by_many_skills_is_a_foundation(app_for, tmp_path):
    def skills(label, ids, existing):
        return [skill_json(f"Skill for {label}", ids, concepts=("subtext", f"only {label}"))]
    with app_for(SmartBackend(skills=skills), mode="auto") as c:
        add_book(c, tmp_path)
        lst = {x["name"]: x for x in c.get("/api/concepts").json()["concepts"]}
        assert lst["subtext"]["is_foundation"] is True and lst["subtext"]["skills"] == 3
        assert lst["only Ch. 1"]["is_foundation"] is False
        assert c.get("/api/concepts").json()["concepts"][0]["name"] == "subtext"            # foundations first


def test_prerequisites_are_linked_by_name(app_for, tmp_path):
    def skills(label, ids, existing):
        return {"Ch. 1": [skill_json("Write a logline", ids)],
                "Ch. 2": [skill_json("Write a scene", ids, prereqs=["write a LOGLINE", "A skill that does not exist"])]}.get(label, [])
    with app_for(SmartBackend(skills=skills), mode="auto") as c:
        add_book(c, tmp_path)
        scene = next(s for d in c.get("/api/skills").json()["domains"] for s in d["skills"] if s["name"] == "Write a scene")
        assert [p["name"] for p in scene["prerequisites"]] == ["Write a logline"]


def test_same_skill_found_twice_in_one_book_is_merged_quietly(app_for, tmp_path):
    def skills(label, ids, existing):
        return {"Ch. 1": [skill_json("Write a scene", ids, principles=2)], "Ch. 2": [skill_json("Write a scene", ids, principles=3)]}.get(label, [])
    def merge(e, c):
        return {"same_skill": True, "reason": "same", "add_principles": [3]}
    with app_for(SmartBackend(skills=skills, merge=merge), mode="auto") as c:
        _, s = add_book(c, tmp_path)
        rows = c.app.state.db.execute("SELECT id FROM skill").fetchall()
        assert len(rows) == 1 and s["pending_skills"] == 0
        assert len(c.get(f"/api/skills/{rows[0]['id']}").json()["principles"]) == 3


def test_a_match_with_another_book_waits_as_a_merge_diff(app_for, tmp_path):
    def skills(label, ids, existing):
        name = "Write a want and obstacle scene" + (" in two beats" if "obstacle scene" in existing else "")      # book B words it differently
        return [skill_json(name, ids, principles=3)] if label == "Ch. 1" else []
    def merge(e, c):
        return {"same_skill": True, "reason": "Both teach the same scene craft.", "add_principles": [3]}
    with app_for(SmartBackend(skills=skills, merge=merge), mode="auto") as c:
        add_book(c, tmp_path)                                                                # book A: skill goes live (auto)
        _sid_b, sb = add_book(c, tmp_path, name="b.pdf", title="[Book B]", chapters=[("Chapter 1: Want and obstacle", 3), ("Chapter 2: Other", 2)])
        assert sb["pending_skills"] == 1
        pend = c.get("/api/skills/pending").json()["skills"]
        assert len(pend) == 1 and pend[0]["merge"]["text"] == "adds 1 principle to Write a want and obstacle scene"
        target = pend[0]["merge"]["target"]["id"]
        assert len(c.get(f"/api/skills/{target}").json()["principles"]) == 3
        # accept: principles join the target, the proposal disappears
        r = c.post(f"/api/skills/{pend[0]['id']}/accept").json()
        assert r["merged_into"] == target and r["principles_added"] == 1
        t = c.get(f"/api/skills/{target}").json()
        assert len(t["principles"]) == 4 and {x["title"] for x in t["sources"]} == {"[Book A]", "[Book B]"}
        assert c.get("/api/skills/pending").json()["skills"] == []


def test_rejecting_a_merge_keeps_the_map_unchanged(app_for, tmp_path):
    def skills(label, ids, existing):
        name = "Write a want and obstacle scene" + (" in two beats" if "obstacle scene" in existing else "")      # book B words it differently
        return [skill_json(name, ids, principles=3)] if label == "Ch. 1" else []
    with app_for(SmartBackend(skills=skills, merge=lambda e, c: {"same_skill": True, "add_principles": [3]}), mode="auto") as c:
        add_book(c, tmp_path)
        add_book(c, tmp_path, name="b.pdf", title="[Book B]", chapters=[("Chapter 1: Want and obstacle", 3), ("Chapter 2: Other", 2)])
        pend = c.get("/api/skills/pending").json()["skills"][0]
        assert c.delete(f"/api/skills/{pend['id']}").json()["outcome"] == "discarded"
        assert len(c.get("/api/skills").json()["domains"][0]["skills"]) == 1


def test_a_retry_continues_with_the_chapters_not_yet_done(app_for, tmp_path):
    backend = SmartBackend(skills=two_skills, fail_on=None)
    with app_for(backend, mode="auto") as c:
        # fail the skill call when it reaches chapter 2
        orig = backend.skills
        def flaky(label, ids, existing):
            if label == "Ch. 2" and not getattr(flaky, "tripped", False):
                flaky.tripped = True
                from ai_tutor.llm.errors import LLMPausedError
                raise LLMPausedError("down")
            return orig(label, ids, existing)
        backend.skills = flaky
        sid, s = add_book(c, tmp_path)
        assert s["status"] == "error" and "Retry" in s["message"] and s["skills"] == 1
        c.post(f"/api/library/{sid}/retry")
        c.app.state.worker.wait(sid, 30)
        s = next(x for x in c.get("/api/library").json()["sources"] if x["id"] == sid)
        assert s["status"] == "ready" and s["skills"] == 2
        assert backend.labels.count("Ch. 1") == 1               # chapter 1 was not asked again


def test_reference_only_book_can_be_searched_for_skills_on_request(app_for, tmp_path):
    with app_for(SmartBackend(triage=TRIAGE_REF, skills=two_skills), mode="auto") as c:
        sid, s = add_book(c, tmp_path)
        assert s["status"] == "reference_only" and s["skills"] == 0 and c.backend.calls["skill_extraction"] == 0
        assert c.post(f"/api/library/{sid}/find-skills").status_code == 200
        c.app.state.worker.wait(sid, 30)
        s = next(x for x in c.get("/api/library").json()["sources"] if x["id"] == sid)
        assert s["status"] == "ready" and s["skills"] == 2


def test_domain_comes_from_triage(app_for, tmp_path):
    triage = '{"book_type": "practical", "practicable": true, "domain": "screenwriting", "likely_skills": [], "reason": "r"}'
    with app_for(SmartBackend(triage=triage, skills=two_skills), mode="auto") as c:
        add_book(c, tmp_path)
        assert [d["domain"] for d in c.get("/api/skills").json()["domains"]] == ["screenwriting"]


def test_removing_a_book_removes_the_citations_that_pointed_into_it(app_for, tmp_path):
    with app_for(SmartBackend(skills=two_skills), mode="auto") as c:
        sid, _ = add_book(c, tmp_path)
        assert c.delete(f"/api/library/{sid}").status_code == 200
        db = c.app.state.db
        assert db.execute("SELECT COUNT(*) FROM skill").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM skill_principle").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM concept").fetchone()[0] == 0


def test_mode_setting(app_for):
    with app_for(SmartBackend()) as c:
        assert c.get("/api/settings/skill-mode").json()["mode"] == "manual"
        assert c.put("/api/settings/skill-mode", json={"mode": "auto"}).json()["mode"] == "auto"
        assert c.put("/api/settings/skill-mode", json={"mode": "x"}).status_code == 400
        assert sk.MAX_PRINCIPLES == 6
