"""End-to-end pipeline test.

Starts all three workers as subprocesses, pushes an anchor through
anchors-write, triggers a recall request, and verifies a retell-response
arrives on the output topic.

Requirements:
  - Redpanda and Qdrant running (docker compose -f docker-compose.test.yaml up -d)
  - No real LLM needed — workers fall back to the stub narrative.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid

import pytest

from _helpers import KAFKA_BOOTSTRAP, QDRANT_URL, consume_until_match
from confluent_kafka import Consumer, Producer

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


_WORKER_ENV = {
    **os.environ,
    "KAFKA_BOOTSTRAP": KAFKA_BOOTSTRAP,
    "KAFKA_BOOTSTRAP_SERVERS": KAFKA_BOOTSTRAP,
    "QDRANT_URL": QDRANT_URL,
    "EMBEDDING_MODEL": "deterministic",
    "OPENAI_API_KEY": "",
    "PORTKEY_API_KEY": "",
    "OLLAMA_BASE_URL": "",
    "PYTHONPATH": f"{os.getcwd()}:{os.getcwd()}/common/utils",
}


def _start_worker(module: str, port_offset: int = 0) -> subprocess.Popen:
    """Launch a worker as a subprocess."""
    env = {**_WORKER_ENV}
    return subprocess.Popen(
        [sys.executable, "-m", module],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _stop_worker(proc: subprocess.Popen, timeout: float = 10.0) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _make_consumer(topic: str) -> Consumer:
    c = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"e2e-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    c.subscribe([topic])
    return c


class TestFullPipeline:
    """Start workers, push an anchor, trigger recall, assert retell-response."""

    @pytest.fixture(autouse=True)
    def _workers(self):
        procs = [
            _start_worker("workers.vhm_indexer.main"),
            _start_worker("workers.vhm_resonance.main"),
            _start_worker("workers.vhm_reteller.main"),
        ]
        time.sleep(5)

        yield procs

        names = ["indexer", "resonance", "reteller"]
        for i, p in enumerate(procs):
            _stop_worker(p)
            stdout = p.stdout.read().decode(errors="replace") if p.stdout else ""
            stderr = p.stderr.read().decode(errors="replace") if p.stderr else ""
            print(f"\n=== {names[i]} stdout ===\n{stdout[-2000:]}")
            print(f"\n=== {names[i]} stderr ===\n{stderr[-2000:]}")

    def test_anchor_to_retelling(self, _workers, kafka_admin):
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        anchor_id = str(uuid.uuid4())

        anchor_payload = {
            "anchor_id": anchor_id,
            "text": "We finished the end-to-end integration test suite",
            "stored_at": "2026-02-26T12:00:00+00:00",
            "salience": 1.0,
            "meta": {"tags": ["e2e"]},
        }
        producer.produce("anchors-write", json.dumps(anchor_payload).encode())
        producer.flush()

        indexed_consumer = _make_consumer("anchors-indexed")
        try:
            indexed = consume_until_match(
                indexed_consumer, "anchor_id", anchor_id, timeout=30
            )
            assert indexed is not None, "Indexer did not produce to anchors-indexed"
            assert indexed["ok"] is True
        finally:
            indexed_consumer.close()

        # Now issue a recall request for the anchor we just stored.
        request_id = str(uuid.uuid4())
        recall_payload = {
            "request_id": request_id,
            "query": "end-to-end integration test",
            "now": "2026-02-27T12:00:00",
            "top_k": 3,
        }
        producer.produce("recall-request", json.dumps(recall_payload).encode())
        producer.flush()

        retell_consumer = _make_consumer("retell-response")
        try:
            retell = consume_until_match(
                retell_consumer, "request_id", request_id, timeout=45
            )
            assert retell is not None, "Reteller did not produce retell-response"
            assert "retelling" in retell
            assert len(retell["retelling"]) > 0
        finally:
            retell_consumer.close()
