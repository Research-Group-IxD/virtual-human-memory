"""Shared constants and utilities for integration tests."""

from __future__ import annotations

import json
import os
import time

from confluent_kafka import Consumer

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:19092")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:16333")


def consume_one_msg(consumer: Consumer, timeout: float = 15.0):
    """Poll a consumer until one valid message arrives or *timeout* elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        return msg
    return None


def consume_until_match(
    consumer: Consumer,
    match_key: str,
    match_value: str,
    timeout: float = 15.0,
) -> dict | None:
    """Consume JSON messages until one contains *match_key* == *match_value*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            data = json.loads(msg.value())
        except Exception:
            continue
        if str(data.get(match_key)) == str(match_value):
            return data
    return None


def consume_until_match_raw(
    consumer: Consumer,
    match_key: str,
    match_value: str,
    timeout: float = 15.0,
):
    """Like consume_until_match but returns the raw Kafka Message object."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            data = json.loads(msg.value())
        except Exception:
            continue
        if str(data.get(match_key)) == str(match_value):
            return msg
    return None
