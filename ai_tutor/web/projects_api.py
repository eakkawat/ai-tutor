"""Projects, the short list of skills for a project, and starting one skill."""
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import picker, projects
from ..worker import Worker

router = APIRouter(prefix="/api")


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def guard(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except (projects.ProjectError, picker.PickerError) as e:
        raise HTTPException(400, {"message": str(e)}) from e


class ProjectIn(BaseModel):
    name: str = ""
    description: str = ""
    good_enough: str = ""
    minutes_per_session: int = 25


class StartIn(BaseModel):
    project_id: int
    pause_current: bool = False


@router.get("/projects")
def list_all(request: Request) -> dict:
    db = _db(request)
    return {"projects": projects.list_projects(db), "active": projects.active(db)}


@router.post("/projects")
def create(body: ProjectIn, request: Request) -> dict:
    db = _db(request)
    pid = guard(projects.create, db, **body.model_dump())
    return projects.view(db, projects.get(db, pid))


@router.patch("/projects/{project_id}")
def edit(project_id: int, body: ProjectIn, request: Request) -> dict:
    db = _db(request)
    guard(projects.update, db, project_id, **body.model_dump())
    return projects.view(db, projects.get(db, project_id))


@router.post("/projects/{project_id}/activate")
def activate(project_id: int, request: Request) -> dict:
    db = _db(request)
    guard(projects.activate, db, project_id)
    return projects.view(db, projects.get(db, project_id))


@router.post("/projects/{project_id}/shortlist")
def shortlist(project_id: int, request: Request) -> dict:
    """5 to 10 skills for this project, one recommended. The only place skills are offered as choices (C2)."""
    db = _db(request)
    llm = request.app.state.llm_factory(0)
    if llm is not None:
        llm.call_log = Worker._call_logger(db)
    guard(projects.get, db, project_id)
    return picker.shortlist(db, project_id, embedder=request.app.state.embedder(), llm=llm)


@router.get("/active-skill")
def active_skill(request: Request) -> dict:
    return {"active": picker.active_skill(_db(request))}


@router.post("/skills/{skill_id}/start")
def start(skill_id: int, body: StartIn, request: Request) -> dict:
    db = _db(request)
    try:
        return guard(picker.start_skill, db, body.project_id, skill_id, pause_current=body.pause_current)
    except picker.ActiveSkillError as e:
        raise HTTPException(409, {"message": f"You are working on “{e.active['name']}”. Pause it to start another.", "code": "active_skill",
                                  "active": e.active}) from e
