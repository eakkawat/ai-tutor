"""Spaced review: the two-question review before Continue, Review mode, and the 3-minute check on one concept."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..review import ReviewError, ReviewService
from ..teaching import TutorError
from ..worker import Worker

router = APIRouter(prefix="/api")


def service(request: Request) -> ReviewService:
    st = request.app.state
    llm = st.llm_factory(0)
    if llm is not None:
        llm.call_log = Worker._call_logger(st.db)
    return ReviewService(st.db, llm=llm, embedder=st.embedder(), clock=st.clock)


def run(fn, *args, **kw):
    """A rule violation is a 409 with the message to show. A model failure is a 503 that says nothing changed."""
    try:
        return fn(*args, **kw)
    except ReviewError as e:
        raise HTTPException(409, {"message": str(e)}) from e
    except TutorError as e:
        raise HTTPException(503, {"message": str(e), "retryable": e.retryable}) from e


class StartIn(BaseModel):
    mode: str
    session_id: int | None = None
    concept_id: int | None = None


class AnswerIn(BaseModel):
    text: str = ""


@router.post("/review/start")
def start(body: StartIn, request: Request) -> dict:
    """Open or resume a sitting. `run` is null when nothing is due, so the screen can go straight on."""
    return {"run": run(service(request).start, body.mode, session_id=body.session_id, concept_id=body.concept_id)}


def _exists(request: Request, run_id: int) -> None:
    if request.app.state.db.execute("SELECT 1 FROM review_run WHERE id = ?", (run_id,)).fetchone() is None:
        raise HTTPException(404, {"message": "This review no longer exists."})


@router.get("/review/{run_id}")
def get_run(run_id: int, request: Request) -> dict:
    _exists(request, run_id)
    return run(service(request).view, run_id)


@router.post("/review/{run_id}/answer")
def answer(run_id: int, body: AnswerIn, request: Request) -> dict:
    _exists(request, run_id)
    return run(service(request).answer, run_id, body.text)


@router.post("/review/{run_id}/hint")
def hint(run_id: int, request: Request) -> dict:
    _exists(request, run_id)
    return run(service(request).hint, run_id)


@router.post("/review/{run_id}/show")
def show(run_id: int, request: Request) -> dict:
    _exists(request, run_id)
    return run(service(request).show, run_id)


@router.post("/review/{run_id}/next")
def next_question(run_id: int, request: Request) -> dict:
    _exists(request, run_id)
    return run(service(request).next, run_id)


@router.post("/review/{run_id}/end")
def end(run_id: int, request: Request) -> dict:
    _exists(request, run_id)
    return run(service(request).end, run_id)
