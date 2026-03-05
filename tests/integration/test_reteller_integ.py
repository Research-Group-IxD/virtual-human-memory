"""Integration tests for the reteller worker.

Uses real Kafka (Redpanda) for message flow but mocks LLM backends.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from confluent_kafka import Producer

from _helpers import (
    KAFKA_BOOTSTRAP,
    consume_one_msg,
    consume_until_match,
    consume_until_match_raw,
)
from vhm_common_utils.data_models import RecallResponse, ResonanceBeat
from workers.vhm_reteller.main import _process_message

pytestmark = pytest.mark.integration


def _make_recall_response(request_id: str | None = None) -> RecallResponse:
    rid = uuid.UUID(request_id) if request_id else uuid.uuid4()
    return RecallResponse(
        request_id=rid,
        beats=[
            ResonanceBeat(
                anchor_id=str(uuid.uuid4()),
                text="We built the prototype for the demo",
                perceived_age="yesterday",
                activation=0.9,
            ),
            ResonanceBeat(
                anchor_id=str(uuid.uuid4()),
                text="We deployed to production last week",
                perceived_age="1 weeks ago",
                activation=0.6,
            ),
        ],
    )


class TestProcessMessagePublishesNarrative:
    @patch("workers.vhm_reteller.main.call_openai", return_value=None)
    @patch("workers.vhm_reteller.main.call_portkey", return_value=None)
    @patch("workers.vhm_reteller.main.call_ollama", return_value=None)
    def test_stub_narrative_on_kafka(
        self, _ollama, _portkey, _openai, kafka_producer, kafka_consumer_factory
    ):
        """Produce a RecallResponse, process it, verify retell-response on Kafka."""
        response = _make_recall_response()
        payload = json.dumps(response.model_dump(mode="json")).encode()

        input_consumer = kafka_consumer_factory("recall-response")
        kafka_producer.produce("recall-response", payload)
        kafka_producer.flush()

        msg = consume_until_match_raw(
            input_consumer, "request_id", str(response.request_id)
        )
        assert msg is not None, "Timed out waiting on our recall-response"

        output_consumer = kafka_consumer_factory("retell-response")
        output_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

        _process_message(input_consumer, output_producer, msg)

        data = consume_until_match(
            output_consumer, "request_id", str(response.request_id)
        )
        assert data is not None, "No retell-response received"
        assert "retelling" in data
        assert len(data["retelling"]) > 0


class TestProcessMessageCommitsOnLLMFailure:
    @patch("workers.vhm_reteller.main.call_openai", side_effect=Exception("LLM down"))
    @patch("workers.vhm_reteller.main.call_portkey", return_value=None)
    @patch("workers.vhm_reteller.main.call_ollama", return_value=None)
    def test_llm_failure_still_produces_output(
        self, _ollama, _portkey, _openai, kafka_producer, kafka_consumer_factory
    ):
        """Even when the primary LLM throws, the stub fallback should produce output."""
        response = _make_recall_response()
        payload = json.dumps(response.model_dump(mode="json")).encode()

        input_consumer = kafka_consumer_factory("recall-response")
        kafka_producer.produce("recall-response", payload)
        kafka_producer.flush()

        msg = consume_until_match_raw(
            input_consumer, "request_id", str(response.request_id)
        )
        assert msg is not None

        output_consumer = kafka_consumer_factory("retell-response")
        output_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

        _process_message(input_consumer, output_producer, msg)

        data = consume_until_match(
            output_consumer, "request_id", str(response.request_id)
        )
        assert data is not None, "No retell-response after LLM failure"
        assert len(data["retelling"]) > 0


class TestValidationErrorCommitted:
    def test_invalid_json_commits_without_crash(
        self, kafka_producer, kafka_consumer_factory
    ):
        """Invalid payload should be committed (no poison pill) without crashing."""
        test_marker = uuid.uuid4().hex
        bad_payload = json.dumps({"bad": "payload", "marker": test_marker}).encode()
        kafka_producer.produce("recall-response", bad_payload)
        kafka_producer.flush()

        input_consumer = kafka_consumer_factory("recall-response")
        msg = consume_until_match_raw(input_consumer, "marker", test_marker)
        assert msg is not None

        output_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

        # Should not raise.
        _process_message(input_consumer, output_producer, msg)
