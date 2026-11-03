"""Open the SQLite database: WAL, foreign keys, sqlite-vec, and run migrations.

Copied from book-to-skills `book_to_skills/store/conn.py` (unchanged).
"""
import sqlite3
from pathlib import Path

import sqlite_vec

MIGRATIONS = Path(__file__).with_name("migrations")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 30000")
    return db


def migrate(db: sqlite3.Connection) -> list[str]:
    """Apply migrations/NNNN_name.sql in order. Returns the names applied now."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    done = {r[0] for r in db.execute("SELECT name FROM schema_version")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        db.executescript(f.read_text(encoding="utf-8"))
        db.execute("INSERT INTO schema_version(name) VALUES (?)", (f.name,))
        db.commit()
        applied.append(f.name)
    return applied


def open_db(path: Path | str) -> sqlite3.Connection:
    db = connect(path)
    migrate(db)
    return db
