import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def ensure_repository_on_path() -> None:
    """Make sure the project root is importable during CI runs."""
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "pyproject.toml").exists():
            root_str = str(candidate)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return
    # Fallback for unusual layouts: add the grandparent directory.
    fallback = str(current.parents[2])
    if fallback not in sys.path:
        sys.path.insert(0, fallback)


ensure_repository_on_path()


def register_dependency_stubs() -> SimpleNamespace:
    """
    Ensure optional dependencies used by the worker are available.

    Pytest environments without Kafka/Qdrant bindings would otherwise fail at
    import time. These lightweight stubs satisfy type hints without changing
    behaviour under test.
    """

    def _ensure_module(name: str, namespace: SimpleNamespace) -> None:
        if name not in sys.modules:
            sys.modules[name] = namespace

    kafka_namespace = SimpleNamespace(
        Consumer=type("StubConsumer", (), {}),
        Producer=type("StubProducer", (), {}),
    )
    kafka_message_namespace = SimpleNamespace(Message=type("StubMessage", (), {}))
    qdrant_namespace = SimpleNamespace(QdrantClient=type("StubQdrantClient", (), {}))
    qdrant_models_namespace = SimpleNamespace(ScoredPoint=type("StubScoredPoint", (), {}))

    _ensure_module("confluent_kafka", kafka_namespace)
    _ensure_module("confluent_kafka.message", kafka_message_namespace)
    _ensure_module("qdrant_client", qdrant_namespace)
    _ensure_module("qdrant_client.http", SimpleNamespace(models=qdrant_models_namespace))
    _ensure_module("qdrant_client.http.models", qdrant_models_namespace)

    return SimpleNamespace(
        kafka=kafka_namespace,
        kafka_message=kafka_message_namespace,
        qdrant=qdrant_namespace,
        qdrant_models=qdrant_models_namespace,
    )


register_dependency_stubs()

from vhm_common_utils.data_models import RecallRequest
from workers.vhm_resonance.config import ResonanceSettings
from workers.vhm_resonance.main import (
    ResonanceWorker,
    decay_weight,
    select_diverse_scored,
)


def make_hit(
    *,
    hit_id: str,
    text: str,
    stored_at: str,
    score: float,
    salience: float = 1.0,
    meta: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=hit_id,
        score=score,
        payload={
            "text": text,
            "stored_at": stored_at,
            "salience": salience,
            "meta": meta or {},
        },
    )


def test_decay_weight_monotonic():
    now = dt.datetime(2025, 1, 10, 12, 0, 0)
    recent = (now - dt.timedelta(days=1)).isoformat()
    older = (now - dt.timedelta(days=30)).isoformat()
    lam = 0.002

    recent_weight = decay_weight(recent, now, lam)
    older_weight = decay_weight(older, now, lam)

    assert recent_weight > older_weight
    assert 0 < older_weight < 1


def test_select_diverse_scored_prefers_unique_texts():
    base_time = "2025-01-01T00:00:00"
    first = make_hit(hit_id="a", text="Alpha memory", stored_at=base_time, score=0.9)
    duplicate = make_hit(hit_id="b", text="Alpha memory", stored_at=base_time, score=0.8)
    different = make_hit(hit_id="c", text="Beta memory", stored_at=base_time, score=0.7)

    scored = [(0.9, first), (0.8, duplicate), (0.7, different)]
    selected = select_diverse_scored(
        scored,
        desired=2,
        embedding_cache={},
        diversity_threshold=0.85,
    )

    selected_ids = [hit.id for _, hit in selected]
    assert "a" in selected_ids
    assert "c" in selected_ids
    assert "b" not in selected_ids


def test_process_request_returns_ranked_beats():
    now = dt.datetime(2025, 1, 5, 12, 0, 0)
    recent_time = (now - dt.timedelta(hours=12)).isoformat()
    older_time = (now - dt.timedelta(days=30)).isoformat()

    hits = [
        make_hit(
            hit_id="anchor-alpha",
            text="Alpha memory about friendship",
            stored_at=recent_time,
            score=0.9,
            salience=2.0,
        ),
        make_hit(
            hit_id="anchor-beta",
            text="Beta memory about courage",
            stored_at=older_time,
            score=0.8,
        ),
    ]

    class StubWorker(ResonanceWorker):
        def __init__(self, *, search_results):
            settings = ResonanceSettings()
            super().__init__(
                settings=settings,
                client=MagicMock(),
                consumer=MagicMock(),
                producer=MagicMock(),
            )
            self._search_results = search_results

        def _search_with_retry(self, query_vector, top_k):
            return list(self._search_results)

    worker = StubWorker(search_results=hits)
    request = RecallRequest(query="friendship", now=now, top_k=3)

    response = worker._process_request(request)

    assert len(response.beats) == 2
    assert response.beats[0].anchor_id == "anchor-alpha"
    assert response.beats[1].anchor_id == "anchor-beta"
    assert response.beats[0].activation > response.beats[1].activation
    assert response.beats[0].perceived_age == "yesterday"
    assert response.beats[1].perceived_age in {"1 months ago", "1 month ago"}
