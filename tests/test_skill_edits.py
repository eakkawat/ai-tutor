import pytest

from ai_tutor import skills as sk
from ai_tutor.store.conn import open_db


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path / "a.db")
    d.execute("INSERT INTO source(id, title) VALUES (1, '[Book A]')")
    for i in range(1, 7):
        d.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (?,1,'Ch. 1','Want','Ch. 1',?,?,?,?)",
                  (i, i, i, f"[Passage {i}]", i))
    d.commit()
    return d


def make(db, name="Skill one", n=4, status="active", concepts=("subtext",), start=1):
    cids = []
    for c in concepts:
        row = db.execute("SELECT id FROM concept WHERE name = ?", (c,)).fetchone()
        cids.append(row[0] if row else sk.add_concept(db, name=c, definition=f"{c} means", example="Made-up example: x", chunk_ids=[1], questions=[]))
    return sk.add_skill(db, domain="screenwriting", name=name, description=f"You can {name}", practice_type="scene", source_id=1, unit_label="Ch. 1",
                        status=status, principles=[(f"{name} p{i}", f"test {i}", start + i % 6) for i in range(n)], concepts=[(c, "spot") for c in cids])


def test_rename_and_edit_fields(db):
    s = make(db)
    sk.update_skill(db, s, name="  Write a better scene ", practice_type="beat sheet")
    d = sk.skill_detail(db, s)
    assert d["name"] == "Write a better scene" and d["practice_type"] == "beat sheet"
    with pytest.raises(sk.SkillError, match="needs a name"):
        sk.update_skill(db, s, name="  ")


def test_edit_principles_validates_text_test_source_and_count(db):
    s = make(db)
    ok = [{"principle": "New one", "test": "Does X?", "chunk_id": 2}, {"principle": "New two", "test": "Does Y?", "chunk_id": 3}]
    sk.set_principles(db, s, ok)
    d = sk.skill_detail(db, s)
    assert [p["principle"] for p in d["principles"]] == ["New one", "New two"] and d["principles"][0]["citation"].startswith("[[Book A], ch. 1")
    assert {x["pages"][0] for x in d["sources"]} == {2}
    for bad, msg in [([], "between 1 and 6"), ([{"principle": "x", "test": "y", "chunk_id": 1}] * 7, "between 1 and 6"),
                     ([{"principle": " ", "test": "y", "chunk_id": 1}], "statement"), ([{"principle": "x", "test": "", "chunk_id": 1}], "statement"),
                     ([{"principle": "x", "test": "y", "chunk_id": 999}], "cite a passage")]:
        with pytest.raises(sk.SkillError, match=msg):
            sk.set_principles(db, s, bad)
    assert len(sk.skill_detail(db, s)["principles"]) == 2          # a rejected edit changes nothing


def test_split_moves_chosen_principles_and_shares_concepts(db):
    s = make(db, n=4)
    ids = [p["id"] for p in sk.skill_detail(db, s)["principles"]]
    new = sk.split_skill(db, s, name="Second half", description="", principle_ids=ids[2:])
    a, b = sk.skill_detail(db, s), sk.skill_detail(db, new)
    assert len(a["principles"]) == 2 and len(b["principles"]) == 2
    assert [c["name"] for c in b["concepts"]] == ["subtext"] and b["domain"] == a["domain"] and b["status"] == "active"
    for d in (a, b):
        assert d["sources"], "each skill keeps at least one source"
    with pytest.raises(sk.SkillError, match="not all"):
        sk.split_skill(db, s, name="x", description="", principle_ids=[p["id"] for p in a["principles"]])
    with pytest.raises(sk.SkillError, match="Name"):
        sk.split_skill(db, s, name=" ", description="", principle_ids=[a["principles"][0]["id"]])


def test_manual_merge_combines_without_duplicating(db):
    a = make(db, "Skill A", n=3, concepts=("subtext",))
    b = make(db, "Skill B", n=2, concepts=("subtext", "objective"), start=3)
    prereq = make(db, "Prereq", n=2)
    db.execute("INSERT INTO skill_prereq(skill_id, prereq_skill_id) VALUES (?,?)", (b, prereq))
    db.commit()
    assert sk.merge_skills(db, b, a) == "deleted"
    d = sk.skill_detail(db, a)
    assert len(d["principles"]) == 5 and {c["name"] for c in d["concepts"]} == {"subtext", "objective"}
    assert [p["name"] for p in d["prerequisites"]] == ["Prereq"]
    assert db.execute("SELECT COUNT(*) FROM skill WHERE id = ?", (b,)).fetchone()[0] == 0
    with pytest.raises(sk.SkillError):
        sk.merge_skills(db, a, a)


def test_deleting_a_skill_keeps_its_concepts(db):
    s = make(db)
    assert sk.retire(db, s) == "deleted"
    assert db.execute("SELECT COUNT(*) FROM concept WHERE name = 'subtext'").fetchone()[0] == 1
    c = sk.concept_list(db)[0]
    assert c["skills"] == 0                                        # still in the library, used by nothing


def test_deleting_a_practised_skill_archives_it(db):
    s = make(db)
    db.execute("INSERT INTO learner_skill(skill_id, status, hours_total) VALUES (?, 'paused', 2.5)", (s,))
    db.commit()
    assert sk.retire(db, s) == "archived"
    assert db.execute("SELECT status FROM skill WHERE id = ?", (s,)).fetchone()[0] == "archived"
    assert sk.skill_map(db) == []                                  # off the map, hours kept
    assert db.execute("SELECT hours_total FROM learner_skill").fetchone()[0] == 2.5


def test_discarding_a_proposal_removes_only_the_concepts_it_brought(db):
    keep = make(db, "Kept", concepts=("subtext",))
    prop = make(db, "Proposed", status="pending", concepts=("subtext", "only mine"))
    sk.discard(db, prop)
    names = {r[0] for r in db.execute("SELECT name FROM concept")}
    assert names == {"subtext"} and sk.skill_detail(db, keep)["concepts"][0]["name"] == "subtext"
    with pytest.raises(sk.SkillError):
        sk.discard(db, keep)                                       # only proposals can be discarded


def test_accept_activates_and_flags_foundations(db):
    ids = [make(db, f"S{i}", status="pending") for i in range(3)]
    for i in ids[:2]:
        sk.accept(db, i)
    assert sk.concept_list(db)[0]["is_foundation"] is False
    sk.accept(db, ids[2])
    assert sk.concept_list(db)[0]["is_foundation"] is True
    with pytest.raises(sk.SkillError):
        sk.accept(db, ids[2])


def test_accept_as_new_turns_a_merge_proposal_into_its_own_skill(db):
    target = make(db, "Target")
    prop = sk.add_skill(db, domain="screenwriting", name="Cousin", description="d", practice_type=None, source_id=1, unit_label=None, status="pending",
                        principles=[("p", "t", 1)], concepts=[], merge_into=target)
    sk.accept_as_new(db, prop)
    d = sk.skill_detail(db, prop)
    assert d["status"] == "active" and d["merge_into"] is None


def test_concept_detail_shows_everything_the_screen_needs(db):
    s = make(db)
    cid = db.execute("SELECT id FROM concept").fetchone()[0]
    db.execute("UPDATE concept_mastery SET level = 'define', confusions_json = '[\"exposition\"]' WHERE concept_id = ?", (cid,))
    db.commit()
    d = sk.concept_detail(db, cid)
    assert d["level"] == "define" and d["confusions"] == ["exposition"] and d["skills"][0]["id"] == s
    assert d["sources"][0]["citation"] == "[[Book A], ch. 1, p. 1]" and d["definition"] and d["example"]


# ---------- the same through the API

def test_api_edit_flow(make_client, tmp_path):
    with make_client() as c:
        d = c.app.state.db
        d.execute("INSERT INTO source(id, title) VALUES (1, '[Book A]')")
        for i in range(1, 5):
            d.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (?,1,'Ch. 1','Want','Ch. 1',?,?,'t',?)", (i, i, i, i))
        d.commit()
        a, b = make(d, "Alpha", n=4), make(d, "Beta", n=2)
        assert [s["name"] for s in c.get("/api/skills").json()["domains"][0]["skills"]] == ["Alpha", "Beta"]
        assert c.patch(f"/api/skills/{a}", json={"name": "Alpha 2"}).json()["name"] == "Alpha 2"
        assert c.patch(f"/api/skills/{a}", json={"name": ""}).status_code == 400
        ps = c.get(f"/api/skills/{a}").json()["principles"]
        r = c.post(f"/api/skills/{a}/split", json={"name": "Alpha part two", "principle_ids": [p["id"] for p in ps[:2]]})
        assert r.status_code == 200 and len(r.json()["new_skill"]["principles"]) == 2
        assert c.post(f"/api/skills/{a}/split", json={"name": "x", "principle_ids": []}).json()["detail"]["message"].startswith("Choose some")
        r = c.put(f"/api/skills/{b}/principles", json=[{"principle": "P", "test": "T", "chunk_id": 1}])
        assert r.status_code == 200 and len(r.json()["principles"]) == 1
        assert c.put(f"/api/skills/{b}/principles", json=[{"principle": "P", "test": "T", "chunk_id": 500}]).status_code == 400
        assert c.post(f"/api/skills/{b}/merge", json={"into": a}).json()["outcome"] == "deleted"
        assert c.get(f"/api/skills/{b}").status_code == 400
        assert c.delete(f"/api/skills/{a}").json()["outcome"] == "deleted"
        assert c.get("/api/concepts").json()["concepts"][0]["skills"] == 1          # "Alpha part two" still uses it
        assert c.get("/api/concepts/9999").status_code == 400
