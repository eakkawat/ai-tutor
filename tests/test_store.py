from ai_tutor.store.conn import open_db

TABLES = {
    "source", "chunk", "skill", "skill_principle", "skill_source", "skill_prereq", "concept", "concept_source", "skill_concept",
    "concept_mastery", "concept_question", "project", "learner_skill", "session", "message", "submission", "submission_asset",
    "video_frame", "feedback", "principle_check", "flow_rating", "mistake", "profile_note", "review_item",
}


def test_initial_migration_creates_spec_tables_and_is_idempotent(tmp_path):
    p = tmp_path / "app.db"
    db = open_db(p)
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert TABLES <= names
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    db.close()
    from ai_tutor.store.conn import MIGRATIONS
    assert open_db(p).execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == len(list(MIGRATIONS.glob("*.sql")))


def test_sqlite_vec_loads(tmp_path):
    assert open_db(tmp_path / "a.db").execute("SELECT vec_version()").fetchone()[0]
