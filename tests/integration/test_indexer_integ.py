"""Integration tests for the indexer worker.

Layer 1: call processing functions with real Qdrant + deterministic embeddings.
Layer 2: feed real Kafka messages through the message handler.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from qdrant_client.http import models as qmodels

from _helpers import consume_one_msg, consume_until_match, consume_until_match_raw
from vhm_common_utils.data_models import Anchor
from vhm_common_utils.embedding import get_embedding
from workers.vhm_indexer.main import (
    _process_kafka_message,
    _publish_to_kafka_with_retry,
    ensure_collection,
    process_anchor,
)

pytestmark = pytest.mark.integration


def _make_anchor(**overrides) -> Anchor:
    defaults = {
        "anchor_id": str(uuid.uuid4()),
        "text": "We demoed the Virtual Human system to colleagues",
        "stored_at": datetime.now(tz=timezone.utc),
        "salience": 1.0,
        "meta": {"tags": ["integration-test"]},
    }
    defaults.update(overrides)
    return Anchor.model_validate(defaults)


# ---- Layer 1: component integration ----------------------------------------


class TestEnsureCollection:
    def test_creates_real_collection(self, qdrant):
        ensure_collection(qdrant)

        names = [c.name for c in qdrant.get_collections().collections]
        assert "anchors" in names

        info = qdrant.get_collection("anchors")
        assert info.config.params.vectors.size == 384


class TestProcessAnchor:
    def test_stores_in_qdrant(self, qdrant):
        ensure_collection(qdrant)
        anchor = _make_anchor()

        result = process_anchor(anchor, qdrant, get_embedding)

        assert result["ok"] is True
        assert result["anchor_id"] == str(anchor.anchor_id)

        points = qdrant.retrieve(
            collection_name="anchors",
            ids=[str(anchor.anchor_id)],
            with_payload=True,
            with_vectors=True,
        )
        assert len(points) == 1
        assert points[0].payload["text"] == anchor.text
        assert len(points[0].vector) == 384

    def test_immutability(self, qdrant):
        ensure_collection(qdrant)
        anchor = _make_anchor()

        first = process_anchor(anchor, qdrant, get_embedding)
        assert first["ok"] is True

        second = process_anchor(anchor, qdrant, get_embedding)
        assert second["ok"] is False
        assert second["reason"] == "anchor_immutable_violation"


class TestPublishToKafka:
    def test_message_lands_on_topic(self, kafka_producer, kafka_consumer_factory):
        tag = uuid.uuid4().hex
        payload = json.dumps({"test_tag": tag, "ok": True}).encode()

        _publish_to_kafka_with_retry(kafka_producer, "anchors-indexed", payload)

        consumer = kafka_consumer_factory("anchors-indexed")
        data = consume_until_match(consumer, "test_tag", tag)
        assert data is not None
        assert data["ok"] is True


# ---- Layer 2: message-level integration -------------------------------------


class TestFullMessageFlow:
    def test_process_kafka_message(
        self, qdrant, kafka_producer, kafka_consumer_factory
    ):
        """Construct a real Kafka message, process it, verify Qdrant + output topic."""
        ensure_collection(qdrant)
        anchor = _make_anchor(text="Full message flow integration test")

        anchor_json = json.dumps(
            {
                "anchor_id": str(anchor.anchor_id),
                "text": anchor.text,
                "stored_at": anchor.stored_at.isoformat(),
                "salience": anchor.salience,
                "meta": anchor.meta,
            }
        ).encode()

        # Produce to input topic, consume until we get OUR message (skip stale
        # messages from prior runs).
        input_consumer = kafka_consumer_factory("anchors-write")
        kafka_producer.produce("anchors-write", anchor_json)
        kafka_producer.flush()

        msg = consume_until_match_raw(
            input_consumer, "anchor_id", str(anchor.anchor_id)
        )
        assert msg is not None, "Timed out waiting for our message on anchors-write"

        # The indexer's message handler needs a producer for the output topic
        # and the consumer it received the message from (for commit).
        output_consumer = kafka_consumer_factory("anchors-indexed")

        committed = _process_kafka_message(
            msg, qdrant, kafka_producer, input_consumer
        )
        assert committed is True

        # Verify anchor in Qdrant.
        points = qdrant.retrieve(
            collection_name="anchors",
            ids=[str(anchor.anchor_id)],
            with_payload=True,
        )
        assert len(points) == 1
        assert points[0].payload["text"] == anchor.text

        # Verify result message on output topic.
        data = consume_until_match(
            output_consumer, "anchor_id", str(anchor.anchor_id)
        )
        assert data is not None
        assert data["ok"] is True
