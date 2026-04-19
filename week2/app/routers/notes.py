from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import NoteCreatePayload, NoteOut

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteOut)
def create_note(payload: NoteCreatePayload) -> NoteOut:
    note_id = db.insert_note(payload.content)
    note = db.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=500, detail="failed to load created note")
    return NoteOut.model_validate(note)


@router.get("", response_model=list[NoteOut])
def list_all_notes() -> list[NoteOut]:
    rows = db.list_notes()
    return [NoteOut.model_validate(row) for row in rows]


@router.get("/{note_id}", response_model=NoteOut)
def get_single_note(note_id: int) -> NoteOut:
    row = db.get_note(note_id)
    if row is None:
        raise HTTPException(status_code=404, detail="note not found")
    return NoteOut.model_validate(row)
