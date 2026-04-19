from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..schemas import (
    ActionItemDonePayload,
    ActionItemMarkedOut,
    ActionItemOut,
    ExtractedItemOut,
    ExtractPayload,
    ExtractResponse,
)
from ..services.extract import extract_action_items, extract_action_items_llm

router = APIRouter(prefix="/action-items", tags=["action-items"])


@router.post("/extract", response_model=ExtractResponse)
def extract(payload: ExtractPayload) -> ExtractResponse:
    note_id: int | None = None
    if payload.save_note:
        note_id = db.insert_note(payload.text)

    items = extract_action_items(payload.text)
    ids = db.insert_action_items(items, note_id=note_id)
    return ExtractResponse(
        note_id=note_id,
        items=[ExtractedItemOut(id=i, text=t) for i, t in zip(ids, items)],
    )


@router.post("/extract-llm", response_model=ExtractResponse)
def extract_llm(payload: ExtractPayload) -> ExtractResponse:
    note_id: int | None = None
    if payload.save_note:
        note_id = db.insert_note(payload.text)

    items = extract_action_items_llm(payload.text)
    ids = db.insert_action_items(items, note_id=note_id)
    return ExtractResponse(
        note_id=note_id,
        items=[ExtractedItemOut(id=i, text=t) for i, t in zip(ids, items)],
    )


@router.get("", response_model=list[ActionItemOut])
def list_all(note_id: int | None = Query(default=None)) -> list[ActionItemOut]:
    rows = db.list_action_items(note_id=note_id)
    return [ActionItemOut.model_validate(row) for row in rows]


@router.post("/{action_item_id}/done", response_model=ActionItemMarkedOut)
def mark_done(action_item_id: int, payload: ActionItemDonePayload) -> ActionItemMarkedOut:
    updated = db.mark_action_item_done(action_item_id, payload.done)
    if not updated:
        raise HTTPException(status_code=404, detail="action item not found")
    return ActionItemMarkedOut(id=action_item_id, done=payload.done)
