"""The teaching session: read it, act on it, save a draft, ask what comes next, and flag a message that felt wrong."""
import logging
import sqlite3

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from .. import app_settings, picker, profile, setup_check
from ..session import SessionService, TransitionError
from ..store.conn import open_db
from ..teaching import TutorError
from ..worker import Worker

router = APIRouter(prefix="/api")


def service(request: Request) -> SessionService:
    st = request.app.state
    llm = st.llm_factory(0)
    if llm is not None:
        llm.call_log = Worker._call_logger(st.db)
    return SessionService(st.db, llm=llm, embedder=st.embedder(), clock=st.clock, log_path=st.paths.feedback_log,
                          vision=lambda: setup_check.model_supports_images(app_settings.llm_config()))


def run(fn, *args, **kw):
    """A rule violation is a 409 with the message to show. A model failure is a 503 that says the state did not change."""
    try:
        return fn(*args, **kw)
    except TransitionError as e:
        raise HTTPException(409, {"message": str(e)}) from e
    except TutorError as e:
        raise HTTPException(503, {"message": str(e), "retryable": e.retryable}) from e


def _exists(db: sqlite3.Connection, session_id: int) -> None:
    if db.execute("SELECT 1 FROM session WHERE id = ?", (session_id,)).fetchone() is None:
        raise HTTPException(404, {"message": "This session no longer exists."})


class ActIn(BaseModel):
    action: str
    text: str = ""


class DraftIn(BaseModel):
    text: str = ""


class RatingIn(BaseModel):
    rating: str
    cant_start: bool = False


class NoteIn(BaseModel):
    note: str = ""


@router.get("/sessions/{session_id}")
def get_session(session_id: int, request: Request) -> dict:
    _exists(request.app.state.db, session_id)
    return run(service(request).view, session_id)


def _learn_from(db_path, llm, session_id: int, now) -> None:
    """After a skill is finished: add what the session showed to the learner profile. Runs after the reply is sent; never raises."""
    db = open_db(db_path)
    try:
        profile.update_after_session(db, llm, session_id, now)
    except Exception:
        logging.getLogger(__name__).exception("could not update the profile for session %s", session_id)
    finally:
        db.close()


@router.post("/sessions/{session_id}/act")
def act(session_id: int, body: ActIn, request: Request, background: BackgroundTasks) -> dict:
    _exists(request.app.state.db, session_id)
    before = request.app.state.db.execute("SELECT ended_at FROM session WHERE id = ?", (session_id,)).fetchone()["ended_at"]
    view = run(service(request).act, session_id, body.action, body.text)
    if view["ended"] and not before:
        st = request.app.state
        background.add_task(_learn_from, st.paths.db, st.llm_factory(0), session_id, st.clock())
    return view


@router.post("/sessions/{session_id}/rating")
def rate(session_id: int, body: RatingIn, request: Request) -> dict:
    """One tap after a task: Too easy, Just right or Too hard. Returns the session with what changed for the next attempt."""
    _exists(request.app.state.db, session_id)
    return run(service(request).rate, session_id, body.rating, body.cant_start)


@router.get("/sessions/{session_id}/compare")
def compare(session_id: int, a: int, b: int, request: Request) -> dict:
    _exists(request.app.state.db, session_id)
    return run(service(request).compare, session_id, a, b)


@router.put("/sessions/{session_id}/draft")
def draft(session_id: int, body: DraftIn, request: Request) -> dict:
    _exists(request.app.state.db, session_id)
    run(service(request).save_draft, session_id, body.text)
    return {"ok": True}


@router.get("/sessions/{session_id}/next")
def next_skill(session_id: int, request: Request) -> dict:
    """After a pass: the skill to start next. One recommendation, not a plan."""
    db = request.app.state.db
    _exists(db, session_id)
    r = db.execute("SELECT project_id FROM session WHERE id = ?", (session_id,)).fetchone()
    st = request.app.state
    llm = st.llm_factory(0)
    if llm is not None:
        llm.call_log = Worker._call_logger(db)
    out = picker.shortlist(db, r["project_id"], embedder=st.embedder(), llm=llm)
    first = out["skills"][0] if out["skills"] else None
    return {"next": first, "note": out["note"], "all_passed": out["all_passed"]}


@router.post("/messages/{message_id}/felt-wrong")
def felt_wrong(message_id: int, body: NoteIn, request: Request) -> dict:
    return run(service(request).felt_wrong, message_id, body.note)
