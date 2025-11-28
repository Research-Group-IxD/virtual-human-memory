from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4


class Anchor(BaseModel):
    anchor_id: UUID = Field(default_factory=uuid4)
    text: str
    stored_at: datetime = Field(default_factory=datetime.utcnow)
    salience: float = 1.0


class RecallRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    query: str = Field(min_length=1)
    now: datetime = Field(default_factory=datetime.utcnow)
    top_k: int = Field(default=3, gt=0, le=50)
    session_id: str | None = None
    ignore_anchor_ids: list[UUID] = Field(default_factory=list)


class ResonanceBeat(BaseModel):
    anchor_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    perceived_age: str = Field(min_length=1)
    activation: float


class RecallResponse(BaseModel):
    request_id: UUID
    beats: list[ResonanceBeat] = Field(default_factory=list)
