"""Shared fixtures for integration tests.

These tests require running Redpanda and Qdrant instances.
Start them with: docker compose -f docker-compose.test.yaml up -d

Run integration tests:  uv run pytest tests/integration/ -v -m integration
Run unit tests only:    uv run pytest -m "not integration"
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import uuid
from types import SimpleNamespace

import pytest
import requests
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from qdrant_client import QdrantClient

# ---------------------------------------------------------------------------
# Register stubs for submodules that exist only in certain build variants
# of confluent-kafka. Must happen before any worker module is imported.
# ---------------------------------------------------------------------------

if importlib.util.find_spec("confluent_kafka.message") is None:
    sys.modules["confluent_kafka.message"] = SimpleNamespace(
        Message=type("StubMessage", (), {})
    )

# ---------------------------------------------------------------------------
# Ensure the _helpers module is importable from test files.
# ---------------------------------------------------------------------------

_INTEG_DIR = os.path.dirname(os.path.abspath(__file__))
if _INTEG_DIR not in sys.path:
    sys.path.insert(0, _INTEG_DIR)

from _helpers import KAFKA_BOOTSTRAP, QDRANT_URL  # noqa: E402

# ---------------------------------------------------------------------------
# Environment overrides — set BEFORE any worker/config module is imported.
# ---------------------------------------------------------------------------

os.environ["KAFKA_BOOTSTRAP"] = KAFKA_BOOTSTRAP
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = KAFKA_BOOTSTRAP
os.environ["QDRANT_URL"] = QDRANT_URL
os.environ["EMBEDDING_MODEL"] = "deterministic"
os.environ["OLLAMA_BASE_URL"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["PORTKEY_API_KEY"] = ""

# Reload config so cached module-level values reflect the env overrides.
import vhm_common_utils.config as _cfg  # noqa: E402

importlib.reload(_cfg)

TOPICS = [
    "anchors-write",
    "anchors-indexed",
    "recall-request",
    "recall-response",
    "retell-response",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_redpanda(bootstrap: str, timeout: float = 30.0) -> AdminClient:
    """Block until Redpanda is reachable or skip the session."""
    admin = AdminClient({"bootstrap.servers": bootstrap})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            meta = admin.list_topics(timeout=5)
            if meta.topics is not None:
                return admin
        except Exception:
            pass
        time.sleep(1)
    pytest.skip(f"Redpanda not available at {bootstrap} after {timeout}s")


def _wait_for_qdrant(url: str, timeout: float = 30.0) -> None:
    """Block until Qdrant is reachable or skip the session."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{url}/readyz", timeout=3)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    pytest.skip(f"Qdrant not available at {url} after {timeout}s")


# ---------------------------------------------------------------------------
# Session-scoped fixtures (infrastructure)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def kafka_admin():
    """Wait for Redpanda, create all required topics, return the admin client."""
    admin = _wait_for_redpanda(KAFKA_BOOTSTRAP)
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=1, replication_factor=1) for t in TOPICS]
    )
    for topic, future in futures.items():
        try:
            future.result(timeout=10)
        except Exception:
            pass  # topic may already exist
    return admin


@pytest.fixture(scope="session")
def qdrant_session(kafka_admin):
    """Wait for Qdrant, return a session-scoped client."""
    _wait_for_qdrant(QDRANT_URL)
    return QdrantClient(url=QDRANT_URL)


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def qdrant(qdrant_session):
    """Per-test Qdrant client — deletes the ``anchors`` collection after each test."""
    yield qdrant_session
    try:
        qdrant_session.delete_collection("anchors")
    except Exception:
        pass


@pytest.fixture()
def kafka_producer(kafka_admin):
    p = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    yield p
    p.flush(timeout=5)


@pytest.fixture()
def kafka_consumer_factory(kafka_admin):
    """Factory that creates consumers with unique group IDs per test."""
    consumers: list[Consumer] = []

    def _make(topic: str) -> Consumer:
        c = Consumer(
            {
                "bootstrap.servers": KAFKA_BOOTSTRAP,
                "group.id": f"test-{uuid.uuid4().hex[:12]}",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        c.subscribe([topic])
        consumers.append(c)
        return c

    yield _make

    for c in consumers:
        try:
            c.close()
        except Exception:
            pass
