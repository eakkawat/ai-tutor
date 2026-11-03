"""Projects (C1): something real the learner wants to make. Skills are chosen and practised in service of one."""
import sqlite3

MINUTES = (25, 45, 60, 90)


class ProjectError(ValueError):
    """A project change that cannot be made. The message is shown as is."""


def _clean(name, description, good_enough, minutes) -> tuple[str, str, str, int]:
    name, description, good_enough = (name or "").strip(), (description or "").strip(), (good_enough or "").strip()
    if not name:
        raise ProjectError("Name your project.")
    if not description:
        raise ProjectError("Say what you are making.")
    if not good_enough:
        raise ProjectError("Say what “good enough” looks like, so skills can be judged against it.")
    if not isinstance(minutes, int) or not 10 <= minutes <= 180:
        raise ProjectError("Choose a session length between 10 and 180 minutes.")
    return name, description, good_enough, minutes


def view(db: sqlite3.Connection, r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "name": r["name"], "description": r["description"], "good_enough": r["good_enough"],
        "minutes_per_session": r["minutes_per_session"], "active": bool(r["active"]),
        "skills_practised": db.execute("SELECT COUNT(DISTINCT skill_id) FROM session WHERE project_id = ?", (r["id"],)).fetchone()[0],
    }


def list_projects(db: sqlite3.Connection) -> list[dict]:
    return [view(db, r) for r in db.execute("SELECT * FROM project ORDER BY active DESC, id DESC")]


def get(db: sqlite3.Connection, project_id: int) -> sqlite3.Row:
    r = db.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if r is None:
        raise ProjectError("This project no longer exists.")
    return r


def create(db: sqlite3.Connection, *, name, description, good_enough, minutes_per_session) -> int:
    """The new project becomes the active one."""
    n, d, g, m = _clean(name, description, good_enough, minutes_per_session)
    db.execute("UPDATE project SET active = 0 WHERE active = 1")
    pid = db.execute("INSERT INTO project(name, description, good_enough, minutes_per_session, active) VALUES (?,?,?,?,1)", (n, d, g, m)).lastrowid
    db.commit()
    return pid


def update(db: sqlite3.Connection, project_id: int, *, name, description, good_enough, minutes_per_session) -> None:
    """Sessions keep pointing at the project by id, so editing never detaches them."""
    get(db, project_id)
    n, d, g, m = _clean(name, description, good_enough, minutes_per_session)
    db.execute("UPDATE project SET name = ?, description = ?, good_enough = ?, minutes_per_session = ? WHERE id = ?", (n, d, g, m, project_id))
    db.commit()


def activate(db: sqlite3.Connection, project_id: int) -> None:
    get(db, project_id)
    db.execute("UPDATE project SET active = 0 WHERE active = 1 AND id != ?", (project_id,))
    db.execute("UPDATE project SET active = 1 WHERE id = ?", (project_id,))
    db.commit()


def active(db: sqlite3.Connection) -> dict | None:
    r = db.execute("SELECT * FROM project WHERE active = 1").fetchone()
    return view(db, r) if r else None
