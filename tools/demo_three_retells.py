"""Demo script that tests the complete flow: anchors → recall → resonance → retelling.

This script:
1. Seeds three memory anchors with different timestamps
2. Sends a recall request
3. Waits for resonance beats (recall-response)
4. Waits for retelling (retell-response)
5. Logs the complete flow to a JSON file
"""

import os
import json
import uuid
import time
import datetime as dt
from pathlib import Path

from confluent_kafka import Producer, Consumer
from qdrant_client import QdrantClient
from qdrant_client.http import models

from vhm_common_utils.config import (
    KAFKA_BOOTSTRAP,
    QDRANT_URL,
    QDRANT_COLLECTION,
)
from vhm_common_utils.embedding import (
    human_age,
    get_embedding_dim,
)


TOP_ANCHORS = "anchors-write"
TOP_RECALL_REQUEST = "recall-request"
TOP_RECALL_RESPONSE = "recall-response"
TOP_RETELL_RESPONSE = "retell-response"
LOG_DIR = Path(os.getenv("DEMO_LOG_DIR", "./results"))
RESET_COLLECTION_FLAG = os.getenv("DEMO_RESET_COLLECTION", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Always reset the collection before demos so we start from a clean slate.


def produce_anchor(
    producer: Producer, text: str, stored_at: str, salience: float
) -> dict:
    """Produce an anchor to Kafka."""
    anchor = {
        "anchor_id": str(uuid.uuid4()),
        "text": text,
        "stored_at": stored_at,
        "salience": salience,
        "meta": {},
    }
    producer.produce(TOP_ANCHORS, json.dumps(anchor).encode("utf-8"))
    producer.flush()
    return anchor


def request_recall(
    producer: Producer, query: str, now_iso: str, top_k: int = 5
) -> dict:
    """Send a recall request to Kafka."""
    request = {
        "request_id": str(uuid.uuid4()),
        "query": query,
        "now": now_iso,
        "top_k": top_k,
    }
    producer.produce(TOP_RECALL_REQUEST, json.dumps(request).encode("utf-8"))
    producer.flush()
    return request


def wait_for_message(topic: str, request_id: str, timeout: float = 30.0) -> dict:
    """Wait for a message on a Kafka topic matching the request_id."""
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"demo-three-{uuid.uuid4()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"[demo] {topic} error: {msg.error()}")
                continue
            payload = json.loads(msg.value().decode("utf-8"))
            if payload.get("request_id") == request_id:
                return payload
    finally:
        consumer.close()
    raise TimeoutError(f"No message on {topic} for request {request_id}")


def describe_anchor(anchor: dict, now: dt.datetime) -> str:
    """Format an anchor for display."""
    stored = dt.datetime.fromisoformat(anchor["stored_at"].replace("Z", "+00:00"))
    stored = stored.astimezone(dt.timezone.utc)
    delta = now - stored
    return (
        f"{anchor['anchor_id']} • stored {human_age(delta)} • salience {anchor['salience']:.1f}\n"
        f"    {anchor['text']}"
    )


def persist_log(entries: dict) -> Path:
    """Save the demo results to a JSON file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = LOG_DIR / f"demo-three-retells-{timestamp}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
    return path


def reset_collection_if_requested():
    """Reset the Qdrant collection if DEMO_RESET_COLLECTION is enabled."""
    if not RESET_COLLECTION_FLAG:
        return
    try:
        client = QdrantClient(url=QDRANT_URL)
        dim = get_embedding_dim()
        print(
            f"[demo] Resetting Qdrant collection '{QDRANT_COLLECTION}' to {dim} dimensions"
        )
        client.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=models.VectorParams(
                size=dim, distance=models.Distance.COSINE
            ),
        )
        # Give Qdrant a moment to finish the recreation before indexer writes
        time.sleep(0.5)
    except Exception as exc:
        print(
            f"[demo] WARNING: failed to reset collection '{QDRANT_COLLECTION}': {exc}"
        )


def main():
    """Main demo function."""
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

    now = dt.datetime.now(dt.timezone.utc)
    reset_collection_if_requested()
    
    # Seed three anchors with different timestamps
    anchors = [
        (
            "While calibrating the narrative memory today, we watched BB-8 mimic the reteller's cadence.",
            (now - dt.timedelta(hours=12)).isoformat(),
            1.0,
        ),
        (
            "A couple of weeks back, we demoed the prototype at Fontys; questions spiraled about forgetting curves.",
            (now - dt.timedelta(days=14)).isoformat(),
            0.95,
        ),
        (
            "Last autumn, in Rotterdam, the Reflective City pilot sparked debates over long-term narrative drift.",
            (now - dt.timedelta(days=210)).isoformat(),
            0.9,
        ),
    ]

    stored = []
    print("[demo] Seeding three anchors...")
    for text, stored_at, sal in anchors:
        anchor = produce_anchor(producer, text, stored_at, sal)
        stored.append(anchor)
        print(describe_anchor(anchor, now))
        
    # Give indexer time to process anchors
    print("\n[demo] Waiting for anchors to be indexed...")
    time.sleep(2.0)

    recall = request_recall(
        producer,
        query="Retell the highlights from our narrative memory experiments.",
        now_iso=now.isoformat(),
        top_k=5,
    )
    print(f"\n[demo] Recall request id: {recall['request_id']}")

    print("[demo] Waiting for resonance beats...")
    beats_msg = wait_for_message(TOP_RECALL_RESPONSE, recall["request_id"])
    beats = beats_msg.get("beats", [])
    if not beats:
        print("[demo] No beats returned—check that indexer and resonance are running.")
    else:
        for idx, beat in enumerate(beats, 1):
            print(
                f"  Beat {idx}: anchor {beat['anchor_id']} • perceived {beat['perceived_age']} • activation {beat['activation']:.3f}\n"
                f"    {beat['text']}"
            )

    print("\n[demo] Waiting for retelling...")
    retell_msg = wait_for_message(TOP_RETELL_RESPONSE, recall["request_id"])
    retelling = retell_msg.get("retelling", "<no retelling>")
    print("\n[demo] Reteller response:\n")
    print(retelling)

    log_path = persist_log(
        {
            "timestamp": now.isoformat(),
            "request_id": recall["request_id"],
            "anchors": stored,
            "beats": beats,
            "retelling": retelling,
        }
    )
    print(f"\n[demo] Saved transcript to {log_path}")


if __name__ == "__main__":
    main()

