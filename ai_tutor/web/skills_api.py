"""Skill map, review of proposed skills, concepts library, and the review mode setting."""
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import app_settings
from .. import skills as sk

router = APIRouter(prefix="/api")


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def guard(fn, *args, **kw):
    """Turn a rule violation into a plain 400 with the message the user should read."""
    try:
        return fn(*args, **kw)
    except sk.SkillError as e:
        raise HTTPException(400, {"message": str(e)}) from e


class SkillPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    practice_type: str | None = None
    domain: str | None = None


class PrincipleIn(BaseModel):
    principle: str
    test: str
    chunk_id: int


class SplitIn(BaseModel):
    name: str
    description: str = ""
    principle_ids: list[int]


class MergeIn(BaseModel):
    into: int


class ModeIn(BaseModel):
    mode: str


@router.get("/skills")
def skill_map(request: Request) -> dict:
    db = _db(request)
    return {"domains": sk.skill_map(db), "pending": db.execute("SELECT COUNT(*) FROM skill WHERE status = 'pending'").fetchone()[0]}


@router.get("/skills/pending")
def pending(request: Request) -> dict:
    db = _db(request)
    ids = [r["id"] for r in db.execute("SELECT id FROM skill WHERE status = 'pending' ORDER BY merge_into IS NOT NULL DESC, id")]
    return {"skills": [sk.pending_view(db, i) for i in ids]}


@router.get("/skills/{skill_id}")
def one(skill_id: int, request: Request) -> dict:
    return guard(sk.skill_detail, _db(request), skill_id)


@router.patch("/skills/{skill_id}")
def patch(skill_id: int, body: SkillPatch, request: Request) -> dict:
    db = _db(request)
    guard(sk.update_skill, db, skill_id, **body.model_dump())
    return sk.skill_detail(db, skill_id)


@router.put("/skills/{skill_id}/principles")
def principles(skill_id: int, items: list[PrincipleIn], request: Request) -> dict:
    db = _db(request)
    guard(sk.set_principles, db, skill_id, [i.model_dump() for i in items])
    return sk.skill_detail(db, skill_id)


@router.delete("/skills/{skill_id}")
def delete(skill_id: int, request: Request) -> dict:
    db = _db(request)
    status = db.execute("SELECT status FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if status and status["status"] == "pending":
        guard(sk.discard, db, skill_id)
        return {"outcome": "discarded"}
    return {"outcome": guard(sk.retire, db, skill_id)}


@router.post("/skills/{skill_id}/split")
def split(skill_id: int, body: SplitIn, request: Request) -> dict:
    db = _db(request)
    new_id = guard(sk.split_skill, db, skill_id, name=body.name, description=body.description, principle_ids=body.principle_ids)
    return {"new_skill": sk.skill_detail(db, new_id), "skill": sk.skill_detail(db, skill_id)}


@router.post("/skills/{skill_id}/merge")
def merge(skill_id: int, body: MergeIn, request: Request) -> dict:
    db = _db(request)
    outcome = guard(sk.merge_skills, db, skill_id, body.into)
    return {"outcome": outcome, "skill": sk.skill_detail(db, body.into)}


@router.post("/skills/{skill_id}/accept")
def accept(skill_id: int, request: Request) -> dict:
    return guard(sk.accept, _db(request), skill_id)


@router.post("/skills/{skill_id}/accept-as-new")
def accept_as_new(skill_id: int, request: Request) -> dict:
    return guard(sk.accept_as_new, _db(request), skill_id)


@router.get("/concepts")
def concepts(request: Request) -> dict:
    return {"concepts": sk.concept_list(_db(request))}


@router.get("/concepts/{concept_id}")
def concept(concept_id: int, request: Request) -> dict:
    return guard(sk.concept_detail, _db(request), concept_id)


@router.get("/settings/skill-mode")
def get_mode() -> dict:
    return {"mode": app_settings.skill_mode()}


@router.put("/settings/skill-mode")
def put_mode(body: ModeIn) -> dict:
    if body.mode not in ("auto", "manual"):
        raise HTTPException(400, {"message": "Choose “Add automatically” or “Ask me first”."})
    s = app_settings.load()
    s.skill_mode = body.mode
    app_settings.save(s)
    return {"mode": body.mode}
