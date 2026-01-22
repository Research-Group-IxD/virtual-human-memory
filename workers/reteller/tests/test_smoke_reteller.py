from unittest.mock import MagicMock, patch

from workers.vhm_reteller.main import (
    _commit_message,
    _process_message,
    _publish_to_kafka_with_retry,
    build_narrative_guidance,
)


def test_publish_retry_success():
    producer = MagicMock()
    producer.flush.side_effect = [Exception("temp"), None]

    ok = _publish_to_kafka_with_retry(
        producer,
        "topic",
        b"payload",
        retries=1,
        backoff_seconds=0,
        flush_timeout_seconds=1.0,
    )

    assert ok is True
    assert producer.produce.call_count == 2
    assert producer.flush.call_count == 2


def test_publish_retry_failure():
    producer = MagicMock()
    producer.flush.side_effect = Exception("fail")

    ok = _publish_to_kafka_with_retry(
        producer,
        "topic",
        b"payload",
        retries=2,
        backoff_seconds=0,
        flush_timeout_seconds=1.0,
    )

    assert ok is False
    assert producer.produce.call_count == 3
    assert producer.flush.call_count == 3


def test_publish_retry_backoff_uses_delay():
    producer = MagicMock()
    producer.flush.side_effect = [Exception("fail"), None]

    with patch("workers.vhm_reteller.main.time.sleep") as sleep_mock:
        ok = _publish_to_kafka_with_retry(
            producer,
            "topic",
            b"payload",
            retries=1,
            backoff_seconds=0.5,
            flush_timeout_seconds=1.0,
        )

    assert ok is True
    sleep_mock.assert_called_once_with(0.5)


def test_commit_message_calls_consumer():
    consumer = MagicMock()

    class StubMessage:
        def partition(self):
            return 1

        def offset(self):
            return 10

    _commit_message(consumer, StubMessage(), reason="test")
    consumer.commit.assert_called_once()


def test_build_narrative_guidance_returns_prompts():
    beats = [
        {"text": "We built the prototype", "activation": 0.9, "perceived_age": "today"},
        {"text": "We deployed the demo", "activation": 0.7, "perceived_age": "1 week ago"},
    ]

    guidance = build_narrative_guidance(beats)

    assert "system" in guidance
    assert "user" in guidance
    assert "Integrated recap" in guidance["user"]


def test_process_message_commits_on_validation_error():
    consumer = MagicMock()
    producer = MagicMock()

    class StubMessage:
        def value(self):
            return b'{"invalid": true}'

        def partition(self):
            return 3

        def offset(self):
            return 12

    _process_message(consumer, producer, StubMessage())

    consumer.commit.assert_called_once()
