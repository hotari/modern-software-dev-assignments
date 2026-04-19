from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NoteCreatePayload(BaseModel):
    """POST /notes body."""

    content: str = Field(..., min_length=1, description="Non-empty note body")

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    model_config = ConfigDict(json_schema_extra={"examples": [{"content": "Meeting notes"}]})


class NoteOut(BaseModel):
    """Single note returned by the API."""

    id: int
    content: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)
