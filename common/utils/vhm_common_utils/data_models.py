from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4


class Anchor(BaseModel):
    """Anchor model for memory anchors stored in Qdrant.
    
    Used by the indexer worker to validate incoming anchor data from Kafka.
    All fields are required when receiving from Kafka (no defaults).
    """
    anchor_id: UUID
    text: str = Field(..., min_length=1, max_length=10000)
    stored_at: datetime
    salience: float = Field(default=1.0, ge=0.3, le=2.5)
    meta: dict = Field(default_factory=dict)


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
