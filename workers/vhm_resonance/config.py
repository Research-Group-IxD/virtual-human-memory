"""
Typed configuration for the resonance worker.

The worker relies on a combination of shared defaults from
`vhm_common_utils.config` and worker-specific tunables.  This module exposes a
validated settings object so tests and production code share the exact same
contract.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from vhm_common_utils.config import (
    KAFKA_BOOTSTRAP,
    QDRANT_COLLECTION,
    QDRANT_URL,
    RESONANCE_DIVERSITY_THRESHOLD,
    RESONANCE_MAX_BEATS,
)


class ResonanceSettings(BaseModel):
    """Validated runtime settings for the resonance worker."""

    kafka_bootstrap_servers: str = Field(default=KAFKA_BOOTSTRAP, min_length=1)
    kafka_topic_in: str = Field(default="recall-request", min_length=1)
    kafka_topic_out: str = Field(default="recall-response", min_length=1)
    qdrant_url: str = Field(default=QDRANT_URL, min_length=1)
    qdrant_collection: str = Field(default=QDRANT_COLLECTION, min_length=1)
    max_beats: int = Field(default=RESONANCE_MAX_BEATS, gt=0)
    diversity_threshold: float = Field(
        default=RESONANCE_DIVERSITY_THRESHOLD, ge=0.0, le=1.0
    )
    decay_lambda_per_day: float = Field(default=0.002, ge=0.0)
    cross_time_mu: float = Field(default=0.001, ge=0.0)
    kafka_poll_timeout_seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    producer_flush_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    qdrant_search_retries: int = Field(default=3, ge=0, le=10)
    qdrant_retry_backoff_seconds: float = Field(default=0.25, ge=0.0, le=5.0)
    kafka_publish_retries: int = Field(default=3, ge=0, le=10)
    kafka_publish_retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=5.0)

    @computed_field(return_type=dict[str, str])
    @property
    def consumer_config(self) -> dict[str, str]:
        return {
            "bootstrap.servers": self.kafka_bootstrap_servers,
            "group.id": "resonance",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }

    @computed_field(return_type=dict[str, str])
    @property
    def producer_config(self) -> dict[str, str]:
        return {"bootstrap.servers": self.kafka_bootstrap_servers}

    @classmethod
    def from_env(cls, **overrides: object) -> "ResonanceSettings":
        """
        Build a settings object using the shared environment defaults.

        Keyword arguments override specific fields which is handy for tests.
        """
        candidate = cls()  # type: ignore[call-arg]
        if overrides:
            data = candidate.model_dump()
            data.update(overrides)
            return cls.model_validate(data)
        return candidate

