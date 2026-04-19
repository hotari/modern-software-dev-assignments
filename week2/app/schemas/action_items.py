from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtractPayload(BaseModel):
    """POST /action-items/extract body (matches frontend: text + save_note)."""

    text: str = Field(..., min_length=1, description="Raw notes to extract tasks from")
    save_note: bool = False

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class ExtractedItemOut(BaseModel):
    id: int
    text: str


class ExtractResponse(BaseModel):
    note_id: int | None
    items: list[ExtractedItemOut]


class ActionItemOut(BaseModel):
    """GET /action-items — persisted checklist row."""

    id: int
    note_id: int | None
    text: str
    done: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class ActionItemDonePayload(BaseModel):
    """POST /action-items/{id}/done body."""

    done: bool = True


class ActionItemMarkedOut(BaseModel):
    """Response after toggling done state."""

    id: int
    done: bool
