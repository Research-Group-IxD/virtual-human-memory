"""Integration tests for the resonance worker.

Layer 1: seed anchors in real Qdrant, run _process_request, verify ranked results.
Layer 2: push a real Kafka message through _handle_message, verify output topic.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from confluent_kafka import Consumer, Producer

from _helpers import (
    KAFKA_BOOTSTRAP,
    QDRANT_URL,
    consume_one_msg,
    consume_until_match,
    consume_until_match_raw,
)
from vhm_common_utils.data_models import Anchor, RecallRequest, RecallResponse
from vhm_common_utils.embedding import get_embedding
from workers.vhm_indexer.main import ensure_collection, process_anchor
from workers.vhm_resonance.config import ResonanceSettings
from workers.vhm_resonance.main import ResonanceWorker

pytestmark = pytest.mark.integration


def _seed_anchor(client, *, text: str, stored_at: dt.datetime, salience: float = 1.0):
    """Store an anchor in Qdrant via the indexer's process_anchor."""
    anchor = Anchor(
        anchor_id=uuid.uuid4(),
        text=text,
        stored_at=stored_at,
        salience=salience,
        meta={"tags": ["integ-seed"]},
    )
    result = process_anchor(anchor, client, get_embedding)
    assert result["ok"] is True, f"Seeding failed: {result}"
    return anchor


def _make_settings(**overrides) -> ResonanceSettings:
    defaults = dict(
        kafka_bootstrap_servers=KAFKA_BOOTSTRAP,
        qdrant_url=QDRANT_URL,
        qdrant_collection="anchors",
        qdrant_search_retries=1,
        qdrant_retry_backoff_seconds=0.1,
        kafka_publish_retries=1,
        kafka_publish_retry_backoff_seconds=0.1,
    )
    defaults.update(overrides)
    return ResonanceSettings(**defaults)


# ---- Layer 1: component integration ----------------------------------------


class TestSearchReturnsSeededAnchors:
    def test_seeded_anchors_appear_in_results(self, qdrant):
        ensure_collection(qdrant)

        now = dt.datetime(2026, 2, 27, 12, 0, 0)
        one_day_ago = now - dt.timedelta(days=1)

        a1 = _seed_anchor(
            qdrant, text="We built the prototype for the demo", stored_at=one_day_ago
        )
        a2 = _seed_anchor(
            qdrant, text="We deployed the demo to the server", stored_at=one_day_ago
        )
        a3 = _seed_anchor(
            qdrant, text="Lunch was great today", stored_at=one_day_ago
        )

        settings = _make_settings()
        worker = ResonanceWorker(
            settings=settings,
            client=qdrant,
            consumer=None,  # not needed for _process_request
            producer=None,
        )

        request = RecallRequest(query="prototype demo", now=now, top_k=5)
        response = worker._process_request(request)

        ids = [b.anchor_id for b in response.beats]
        assert str(a1.anchor_id) in ids or str(a2.anchor_id) in ids
        assert len(response.beats) >= 1


class TestTemporalDecayOrdering:
    def test_recent_anchors_rank_higher(self, qdrant):
        ensure_collection(qdrant)

        now = dt.datetime(2026, 2, 27, 12, 0, 0)
        recent = now - dt.timedelta(days=1)
        old = now - dt.timedelta(days=90)

        _seed_anchor(qdrant, text="recent memory about the project meeting", stored_at=recent)
        _seed_anchor(qdrant, text="old memory about the project meeting", stored_at=old)

        settings = _make_settings(decay_lambda_per_day=0.01)
        worker = ResonanceWorker(
            settings=settings, client=qdrant, consumer=None, producer=None
        )

        request = RecallRequest(query="project meeting", now=now, top_k=5)
        response = worker._process_request(request)

        assert len(response.beats) == 2
        assert response.beats[0].activation > response.beats[1].activation


class TestDiversitySelection:
    def test_duplicate_texts_are_deduped(self, qdrant):
        ensure_collection(qdrant)

        now = dt.datetime(2026, 2, 27, 12, 0, 0)
        one_week_ago = now - dt.timedelta(days=7)

        _seed_anchor(qdrant, text="We finished the prototype sprint", stored_at=one_week_ago)
        _seed_anchor(qdrant, text="We finished the prototype sprint", stored_at=one_week_ago)
        _seed_anchor(qdrant, text="We planned the next phase of development", stored_at=one_week_ago)

        settings = _make_settings(diversity_threshold=0.85, max_beats=3)
        worker = ResonanceWorker(
            settings=settings, client=qdrant, consumer=None, producer=None
        )

        request = RecallRequest(query="prototype sprint", now=now, top_k=5)
        response = worker._process_request(request)

        texts = [b.text for b in response.beats]
        assert texts.count("We finished the prototype sprint") <= 1


# ---- Layer 2: message-level integration ------------------------------------


class TestHandleMessagePublishesResponse:
    def test_real_kafka_round_trip(self, qdrant, kafka_producer, kafka_consumer_factory):
        ensure_collection(qdrant)

        now = dt.datetime(2026, 2, 27, 12, 0, 0)
        one_day_ago = now - dt.timedelta(days=1)
        _seed_anchor(qdrant, text="We tested the recall pipeline", stored_at=one_day_ago)

        request = RecallRequest(query="recall pipeline", now=now, top_k=3)
        request_json = json.dumps(request.model_dump(mode="json")).encode()

        input_consumer = kafka_consumer_factory("recall-request")
        kafka_producer.produce("recall-request", request_json)
        kafka_producer.flush()

        msg = consume_until_match_raw(
            input_consumer, "request_id", str(request.request_id)
        )
        assert msg is not None, "Timed out waiting on recall-request"

        output_consumer = kafka_consumer_factory("recall-response")

        settings = _make_settings()
        worker = ResonanceWorker(
            settings=settings,
            client=qdrant,
            consumer=input_consumer,
            producer=Producer({"bootstrap.servers": KAFKA_BOOTSTRAP}),
        )

        worker._handle_message(msg)

        data = consume_until_match(
            output_consumer, "request_id", str(request.request_id)
        )
        assert data is not None, "No recall-response received"
        response = RecallResponse.model_validate(data)
        assert response.request_id == request.request_id
        assert len(response.beats) >= 1
