"""The teaching session: read it, act on it, save a draft, ask what comes next, and flag a message that felt wrong."""
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import picker
from ..session import SessionService, TransitionError
from ..teaching import TutorError
from ..worker import Worker

router = APIRouter(prefix="/api")


def service(request: Request) -> SessionService:
    st = request.app.state
    llm = st.llm_factory(0)
    if llm is not None:
        llm.call_log = Worker._call_logger(st.db)
    return SessionService(st.db, llm=llm, embedder=st.embedder(), clock=st.clock, log_path=st.paths.feedback_log)


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


class NoteIn(BaseModel):
    note: str = ""


@router.get("/sessions/{session_id}")
def get_session(session_id: int, request: Request) -> dict:
    _exists(request.app.state.db, session_id)
    return run(service(request).view, session_id)


@router.post("/sessions/{session_id}/act")
def act(session_id: int, body: ActIn, request: Request) -> dict:
    _exists(request.app.state.db, session_id)
    return run(service(request).act, session_id, body.action, body.text)


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
