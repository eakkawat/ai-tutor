"""Skills, principles, concepts and their edits. All database changes for the skill map live here; the API and the pipeline call these.

Rules (SPEC §6.1.1, §6.1.2): a skill has principles (each cites a chunk), at least one source chunk, and links to concepts. A concept
is shared across skills. Deleting a skill keeps its concepts; discarding a *proposed* skill removes the concepts only it brought.
"""
import json
import re
import sqlite3

MAX_PRINCIPLES = 6
FOUNDATION_MIN_SKILLS = 3       # a concept used by this many skills is flagged a foundation


class SkillError(ValueError):
    """A change the user asked for that cannot be made. The message is shown as is."""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def has_history(db: sqlite3.Connection, skill_id: int) -> bool:
    if db.execute("SELECT 1 FROM session WHERE skill_id = ? LIMIT 1", (skill_id,)).fetchone():
        return True
    row = db.execute("SELECT status, hours_total FROM learner_skill WHERE skill_id = ?", (skill_id,)).fetchone()
    return bool(row and (row["status"] != "not_started" or row["hours_total"] > 0))


def add_skill(db: sqlite3.Connection, *, domain: str, name: str, description: str, practice_type: str | None, source_id: int | None,
              unit_label: str | None, status: str, principles: list[tuple[str, str, int]], concepts: list[tuple[int, str]],
              merge_into: int | None = None, merge_note: str | None = None) -> int:
    """`principles` = [(principle, test, chunk_id)], `concepts` = [(concept_id, required_level)]. The skill's sources are its principles' chunks."""
    cur = db.execute(
        "INSERT INTO skill(domain, name, description, practice_type, status, source_id, unit_label, merge_into, merge_note) VALUES (?,?,?,?,?,?,?,?,?)",
        (domain, name, description, practice_type, status, source_id, unit_label, merge_into, merge_note))
    sid = cur.lastrowid
    for i, (p, t, cid) in enumerate(principles):
        db.execute('INSERT INTO skill_principle(skill_id, principle, test, chunk_id, "order") VALUES (?,?,?,?,?)', (sid, p, t, cid, i))
        db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) VALUES (?,?)", (sid, cid))
    for cid, level in concepts:
        db.execute("INSERT OR IGNORE INTO skill_concept(skill_id, concept_id, required_level) VALUES (?,?,?)", (sid, cid, level))
    db.commit()
    return sid


def add_concept(db: sqlite3.Connection, *, name: str, definition: str, example: str, chunk_ids: list[int],
                questions: list[tuple[str, str, str]]) -> int:
    """`questions` = [(level, prompt, answer_key)]."""
    cur = db.execute("INSERT INTO concept(name, definition, example) VALUES (?,?,?)", (name, definition, example))
    cid = cur.lastrowid
    for ch in chunk_ids:
        db.execute("INSERT OR IGNORE INTO concept_source(concept_id, chunk_id) VALUES (?,?)", (cid, ch))
    db.execute("INSERT INTO concept_mastery(concept_id, level) VALUES (?, 'none')", (cid,))
    for level, prompt, key in questions:
        db.execute("INSERT INTO concept_question(concept_id, level, prompt, answer_key) VALUES (?,?,?,?)", (cid, level, prompt, key))
    db.commit()
    return cid


def recompute_foundations(db: sqlite3.Connection) -> None:
    db.execute(
        "UPDATE concept SET is_foundation = (SELECT COUNT(DISTINCT sc.skill_id) FROM skill_concept sc JOIN skill s ON s.id = sc.skill_id "
        "WHERE sc.concept_id = concept.id AND s.status = 'active') >= ?", (FOUNDATION_MIN_SKILLS,))
    db.commit()


def delete_orphan_concepts(db: sqlite3.Connection) -> None:
    """Concepts that only a discarded proposal brought, and that nobody has practised."""
    db.execute("DELETE FROM concept WHERE id NOT IN (SELECT concept_id FROM skill_concept) "
               "AND id IN (SELECT concept_id FROM concept_mastery WHERE level = 'none')")
    db.commit()


# ---------- views

def citation_row(db: sqlite3.Connection, chunk_id: int) -> dict | None:
    from .citations import cite
    r = db.execute("SELECT c.*, s.title AS source_title FROM chunk c JOIN source s ON s.id = c.source_id WHERE c.id = ?", (chunk_id,)).fetchone()
    return {"chunk_id": chunk_id, "citation": cite(r)} if r else None


def principles_of(db: sqlite3.Connection, skill_id: int) -> list[dict]:
    rows = db.execute('SELECT * FROM skill_principle WHERE skill_id = ? ORDER BY "order", id', (skill_id,)).fetchall()
    return [{"id": r["id"], "principle": r["principle"], "test": r["test"], **(citation_row(db, r["chunk_id"]) or {"chunk_id": r["chunk_id"], "citation": None})}
            for r in rows]


def skill_detail(db: sqlite3.Connection, skill_id: int) -> dict:
    s = db.execute("SELECT * FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if s is None:
        raise SkillError("This skill no longer exists.")
    ls = db.execute("SELECT status, hours_total FROM learner_skill WHERE skill_id = ?", (skill_id,)).fetchone()
    pages = [r for r in db.execute(
        "SELECT c.source_id, so.title, MIN(c.page_start) AS a, MAX(c.page_end) AS b FROM skill_source ss JOIN chunk c ON c.id = ss.chunk_id "
        "JOIN source so ON so.id = c.source_id WHERE ss.skill_id = ? GROUP BY c.source_id", (skill_id,))]
    return {
        "id": s["id"], "domain": s["domain"], "name": s["name"], "description": s["description"], "practice_type": s["practice_type"],
        "status": s["status"], "merge_into": s["merge_into"], "merge_note": s["merge_note"], "source_id": s["source_id"],
        "learning_status": ls["status"] if ls else "not_started", "hours": round(ls["hours_total"], 1) if ls else 0.0,
        "principles": principles_of(db, skill_id),
        "sources": [{"source_id": r["source_id"], "title": r["title"], "pages": [r["a"], r["b"]]} for r in pages],
        "concepts": [{"id": r["id"], "name": r["name"], "required_level": r["required_level"], "is_foundation": bool(r["is_foundation"])}
                     for r in db.execute("SELECT c.id, c.name, c.is_foundation, sc.required_level FROM skill_concept sc JOIN concept c ON c.id = sc.concept_id "
                                         "WHERE sc.skill_id = ? ORDER BY c.name", (skill_id,))],
        "prerequisites": [{"id": r["id"], "name": r["name"]} for r in db.execute(
            "SELECT s.id, s.name FROM skill_prereq p JOIN skill s ON s.id = p.prereq_skill_id WHERE p.skill_id = ? AND s.status = 'active'", (skill_id,))],
    }


def skill_map(db: sqlite3.Connection) -> list[dict]:
    """Active skills grouped by domain. No ordering that looks like a plan: alphabetical."""
    out: dict[str, list[dict]] = {}
    for r in db.execute("SELECT id FROM skill WHERE status = 'active' ORDER BY domain, name"):
        d = skill_detail(db, r["id"])
        out.setdefault(d["domain"], []).append(d)
    return [{"domain": k, "skills": v} for k, v in out.items()]


def pending_view(db: sqlite3.Connection, skill_id: int) -> dict:
    """A proposed skill for review. A proposed merge shows what it would add to the skill it matches (B5)."""
    d = skill_detail(db, skill_id)
    if d["merge_into"]:
        target = skill_detail(db, d["merge_into"])
        d["merge"] = {"target": {"id": target["id"], "name": target["name"], "principles": len(target["principles"])},
                      "adds": [p["principle"] for p in d["principles"]],
                      "text": f"adds {len(d['principles'])} principle{'s' if len(d['principles']) != 1 else ''} to {target['name']}"}
    return d


# ---------- merging

def add_principles(db: sqlite3.Connection, target_id: int, principles: list[tuple[str, str, int]]) -> int:
    have = {norm(r["principle"]) for r in db.execute("SELECT principle FROM skill_principle WHERE skill_id = ?", (target_id,))}
    n = db.execute("SELECT COUNT(*) FROM skill_principle WHERE skill_id = ?", (target_id,)).fetchone()[0]
    added = 0
    for p, t, cid in principles:
        if norm(p) in have or n >= MAX_PRINCIPLES:
            db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) VALUES (?,?)", (target_id, cid))
            continue
        db.execute('INSERT INTO skill_principle(skill_id, principle, test, chunk_id, "order") VALUES (?,?,?,?,?)', (target_id, p, t, cid, n))
        db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) VALUES (?,?)", (target_id, cid))
        have.add(norm(p))
        n += 1
        added += 1
    return added


def move_into(db: sqlite3.Connection, from_id: int, into_id: int) -> int:
    """Add everything from one skill to another: new principles, sources, concept links, prerequisites. Returns principles added."""
    rows = db.execute('SELECT principle, test, chunk_id FROM skill_principle WHERE skill_id = ? ORDER BY "order", id', (from_id,)).fetchall()
    added = add_principles(db, into_id, [(r["principle"], r["test"], r["chunk_id"]) for r in rows])
    for r in db.execute("SELECT chunk_id FROM skill_source WHERE skill_id = ?", (from_id,)).fetchall():
        db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) VALUES (?,?)", (into_id, r["chunk_id"]))
    for r in db.execute("SELECT concept_id, required_level FROM skill_concept WHERE skill_id = ?", (from_id,)).fetchall():
        db.execute("INSERT OR IGNORE INTO skill_concept(skill_id, concept_id, required_level) VALUES (?,?,?)", (into_id, r["concept_id"], r["required_level"]))
    for r in db.execute("SELECT prereq_skill_id FROM skill_prereq WHERE skill_id = ?", (from_id,)).fetchall():
        if r["prereq_skill_id"] != into_id:
            db.execute("INSERT OR IGNORE INTO skill_prereq(skill_id, prereq_skill_id) VALUES (?,?)", (into_id, r["prereq_skill_id"]))
    for r in db.execute("SELECT skill_id FROM skill_prereq WHERE prereq_skill_id = ?", (from_id,)).fetchall():     # skills that needed the old one now need this one
        if r["skill_id"] != into_id:
            db.execute("INSERT OR IGNORE INTO skill_prereq(skill_id, prereq_skill_id) VALUES (?,?)", (r["skill_id"], into_id))
    db.commit()
    return added


def accept(db: sqlite3.Connection, skill_id: int) -> dict:
    """Keep a proposed skill. A proposed merge is applied to the skill it matches and the proposal goes away."""
    s = db.execute("SELECT status, merge_into FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if s is None or s["status"] != "pending":
        raise SkillError("This skill is not waiting for review.")
    if s["merge_into"]:
        target = s["merge_into"]
        added = move_into(db, skill_id, target)
        db.execute("DELETE FROM skill WHERE id = ?", (skill_id,))
        db.commit()
        recompute_foundations(db)
        return {"merged_into": target, "principles_added": added}
    db.execute("UPDATE skill SET status = 'active' WHERE id = ?", (skill_id,))
    db.commit()
    recompute_foundations(db)
    return {"skill": skill_id}


def accept_as_new(db: sqlite3.Connection, skill_id: int) -> dict:
    s = db.execute("SELECT status FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if s is None or s["status"] != "pending":
        raise SkillError("This skill is not waiting for review.")
    db.execute("UPDATE skill SET status = 'active', merge_into = NULL, merge_note = NULL WHERE id = ?", (skill_id,))
    db.commit()
    recompute_foundations(db)
    return {"skill": skill_id}


def discard(db: sqlite3.Connection, skill_id: int) -> None:
    """Throw away a proposal. Concepts that only it brought go too."""
    s = db.execute("SELECT status FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if s is None or s["status"] != "pending":
        raise SkillError("This skill is not waiting for review.")
    db.execute("DELETE FROM skill WHERE id = ?", (skill_id,))
    db.commit()
    delete_orphan_concepts(db)


# ---------- edits to the map

def retire(db: sqlite3.Connection, skill_id: int) -> str:
    """Delete a skill. If it has practice history it is archived instead, so hours and sessions are not lost. Its concepts stay."""
    if db.execute("SELECT 1 FROM skill WHERE id = ?", (skill_id,)).fetchone() is None:
        raise SkillError("This skill no longer exists.")
    if has_history(db, skill_id):
        db.execute("UPDATE skill SET status = 'archived' WHERE id = ?", (skill_id,))
        outcome = "archived"
    else:
        db.execute("DELETE FROM skill WHERE id = ?", (skill_id,))
        outcome = "deleted"
    db.commit()
    recompute_foundations(db)
    return outcome


def update_skill(db: sqlite3.Connection, skill_id: int, **fields) -> None:
    allowed = {k: (v or "").strip() for k, v in fields.items() if k in ("name", "description", "practice_type", "domain") and v is not None}
    if "name" in allowed and not allowed["name"]:
        raise SkillError("A skill needs a name.")
    if not allowed:
        return
    cur = db.execute(f"UPDATE skill SET {', '.join(f'{k} = ?' for k in allowed)} WHERE id = ?", (*allowed.values(), skill_id))
    if cur.rowcount == 0:
        raise SkillError("This skill no longer exists.")
    db.commit()


def set_principles(db: sqlite3.Connection, skill_id: int, items: list[dict]) -> None:
    """Replace the checklist. Each principle needs text, a test and a real source chunk (SPEC §6.1.1)."""
    if not 1 <= len(items) <= MAX_PRINCIPLES:
        raise SkillError(f"A skill needs between 1 and {MAX_PRINCIPLES} principles.")
    for it in items:
        if not (it.get("principle") or "").strip() or not (it.get("test") or "").strip():
            raise SkillError("Each principle needs a statement and a one-line test.")
        if db.execute("SELECT 1 FROM chunk WHERE id = ?", (it.get("chunk_id"),)).fetchone() is None:
            raise SkillError("Each principle must cite a passage from your library.")
    db.execute("DELETE FROM skill_principle WHERE skill_id = ?", (skill_id,))
    for i, it in enumerate(items):
        db.execute('INSERT INTO skill_principle(skill_id, principle, test, chunk_id, "order") VALUES (?,?,?,?,?)',
                   (skill_id, it["principle"].strip(), it["test"].strip(), it["chunk_id"], i))
    db.execute("DELETE FROM skill_source WHERE skill_id = ?", (skill_id,))
    db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) SELECT skill_id, chunk_id FROM skill_principle WHERE skill_id = ?", (skill_id,))
    db.commit()


def split_skill(db: sqlite3.Connection, skill_id: int, *, name: str, description: str, principle_ids: list[int]) -> int:
    """Move the chosen principles to a new skill. Both skills keep the concepts, the practice type and the prerequisites."""
    s = db.execute("SELECT * FROM skill WHERE id = ? AND status = 'active'", (skill_id,)).fetchone()
    if s is None:
        raise SkillError("This skill no longer exists.")
    all_ids = [r["id"] for r in db.execute("SELECT id FROM skill_principle WHERE skill_id = ?", (skill_id,))]
    moving = [i for i in principle_ids if i in all_ids]
    if not name.strip():
        raise SkillError("Name the new skill.")
    if not moving or len(moving) == len(all_ids):
        raise SkillError("Choose some of the principles, but not all of them, for the new skill.")
    new_id = db.execute("INSERT INTO skill(domain, name, description, practice_type, status, source_id, unit_label) VALUES (?,?,?,?, 'active', ?, ?)",
                        (s["domain"], name.strip(), description.strip() or s["description"], s["practice_type"], s["source_id"], s["unit_label"])).lastrowid
    for i, pid in enumerate(moving):
        db.execute('UPDATE skill_principle SET skill_id = ?, "order" = ? WHERE id = ?', (new_id, i, pid))
    for sk in (skill_id, new_id):
        db.execute("DELETE FROM skill_source WHERE skill_id = ?", (sk,))
        db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) SELECT skill_id, chunk_id FROM skill_principle WHERE skill_id = ?", (sk,))
    db.execute("INSERT INTO skill_concept(skill_id, concept_id, required_level) SELECT ?, concept_id, required_level FROM skill_concept WHERE skill_id = ?", (new_id, skill_id))
    db.execute("INSERT INTO skill_prereq(skill_id, prereq_skill_id) SELECT ?, prereq_skill_id FROM skill_prereq WHERE skill_id = ?", (new_id, skill_id))
    db.commit()
    recompute_foundations(db)
    return new_id


def merge_skills(db: sqlite3.Connection, from_id: int, into_id: int) -> str:
    """Manual merge: everything from `from_id` goes into `into_id`, then `from_id` is deleted (or archived if it has practice history)."""
    if from_id == into_id:
        raise SkillError("Choose two different skills.")
    for sid in (from_id, into_id):
        if db.execute("SELECT 1 FROM skill WHERE id = ? AND status = 'active'", (sid,)).fetchone() is None:
            raise SkillError("One of these skills no longer exists.")
    move_into(db, from_id, into_id)
    return retire(db, from_id)


def purge_source_citations(db: sqlite3.Connection, source_id: int) -> None:
    """A book is being removed: drop every citation of its passages so nothing points at a deleted chunk.

    Skills left without any principle are removed (archived if practised). Concepts left without a source are removed."""
    ids = "(SELECT id FROM chunk WHERE source_id = ?)"
    db.execute(f"DELETE FROM skill_principle WHERE chunk_id IN {ids}", (source_id,))
    db.execute(f"DELETE FROM skill_source WHERE chunk_id IN {ids}", (source_id,))
    db.execute(f"DELETE FROM concept_source WHERE chunk_id IN {ids}", (source_id,))
    db.execute("DELETE FROM concept WHERE id NOT IN (SELECT concept_id FROM concept_source)")
    db.commit()
    for r in db.execute("SELECT id FROM skill WHERE status != 'archived' AND id NOT IN (SELECT skill_id FROM skill_principle)").fetchall():
        retire(db, r["id"])
    recompute_foundations(db)


# ---------- concepts (library views)

LEVEL_ORDER = {"none": 0, "define": 1, "spot": 2, "use": 3}


def concept_list(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        "SELECT c.id, c.name, c.is_foundation, COALESCE(m.level, 'none') AS level, "
        "(SELECT COUNT(DISTINCT sc.skill_id) FROM skill_concept sc JOIN skill s ON s.id = sc.skill_id WHERE sc.concept_id = c.id AND s.status = 'active') AS skills "
        "FROM concept c LEFT JOIN concept_mastery m ON m.concept_id = c.id ORDER BY c.is_foundation DESC, skills DESC, c.name").fetchall()
    return [dict(r, is_foundation=bool(r["is_foundation"])) for r in rows]


def concept_detail(db: sqlite3.Connection, concept_id: int) -> dict:
    c = db.execute("SELECT * FROM concept WHERE id = ?", (concept_id,)).fetchone()
    if c is None:
        raise SkillError("This concept no longer exists.")
    m = db.execute("SELECT level, confusions_json FROM concept_mastery WHERE concept_id = ?", (concept_id,)).fetchone()
    return {
        "id": c["id"], "name": c["name"], "definition": c["definition"], "example": c["example"], "is_foundation": bool(c["is_foundation"]),
        "level": m["level"] if m else "none", "confusions": json.loads(m["confusions_json"]) if m and m["confusions_json"] else [],
        "sources": [x for x in (citation_row(db, r["chunk_id"]) for r in db.execute("SELECT chunk_id FROM concept_source WHERE concept_id = ?", (concept_id,))) if x],
        "skills": [{"id": r["id"], "name": r["name"], "required_level": r["required_level"]} for r in db.execute(
            "SELECT s.id, s.name, sc.required_level FROM skill_concept sc JOIN skill s ON s.id = sc.skill_id WHERE sc.concept_id = ? AND s.status = 'active' ORDER BY s.name", (concept_id,))],
        "questions": {lv: db.execute("SELECT COUNT(*) FROM concept_question WHERE concept_id = ? AND level = ?", (concept_id, lv)).fetchone()[0]
                      for lv in ("define", "spot", "use")},
    }
