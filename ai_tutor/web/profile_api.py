"""The learner profile ("How I learn") and the Progress screen."""
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import profile, progress

router = APIRouter(prefix="/api")


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def guard(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except profile.ProfileError as e:
        raise HTTPException(400, {"message": str(e)}) from e


class NoteIn(BaseModel):
    text: str
    section: str = "understand"


class NoteEdit(BaseModel):
    text: str


@router.get("/profile")
def get_profile(request: Request) -> dict:
    return {"sections": profile.sections(_db(request))}


@router.post("/profile/notes")
def add_note(body: NoteIn, request: Request) -> dict:
    db = _db(request)
    nid = guard(profile.add_user_note, db, body.text, body.section, request.app.state.clock())
    return next(n for n in profile.list_notes(db) if n["id"] == nid)


@router.patch("/profile/notes/{note_id}")
def edit_note(note_id: int, body: NoteEdit, request: Request) -> dict:
    db = _db(request)
    guard(profile.edit_note, db, note_id, body.text, request.app.state.clock())
    return next(n for n in profile.list_notes(db) if n["id"] == note_id)


@router.delete("/profile/notes/{note_id}")
def remove_note(note_id: int, request: Request) -> dict:
    guard(profile.remove_note, _db(request), note_id)
    return {"ok": True}


@router.get("/progress")
def get_progress(request: Request) -> dict:
    return progress.build(_db(request), request.app.state.clock())
