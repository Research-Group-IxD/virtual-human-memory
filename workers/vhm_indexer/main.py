import json, sys
from confluent_kafka import Consumer, Producer
from qdrant_client import QdrantClient
from qdrant_client.http import models

from vhm_common_utils.config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    KAFKA_BOOTSTRAP,
    EMBEDDING_MODEL,
)
from vhm_common_utils.embedding import get_embedding, get_embedding_dim
from vhm_common_utils.health import run_health_check_server


TOP_IN = "anchors-write"
TOP_OUT = "anchors-indexed"


def ensure_collection(client: QdrantClient):
    dim = get_embedding_dim()
    cols = client.get_collections().collections
    names = [c.name for c in cols]

    # Check if collection exists and has correct dimensions
    if QDRANT_COLLECTION in names:
        collection_info = client.get_collection(QDRANT_COLLECTION)
        config = getattr(collection_info, "config", None)
        params = getattr(config, "params", None) if config else None
        vectors = getattr(params, "vectors", None) if params else None
        size = getattr(vectors, "size", None) if vectors else None
        if size != dim:
            print(
                f"[indexer] Collection has wrong dimensions ({size} vs {dim}), recreating..."
            )
            client.delete_collection(QDRANT_COLLECTION)
            names.remove(QDRANT_COLLECTION)

    if QDRANT_COLLECTION not in names:
        print(
            f"[indexer] Creating collection with {dim} dimensions for {EMBEDDING_MODEL} embeddings"
        )
        client.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=models.VectorParams(
                size=dim, distance=models.Distance.COSINE
            ),
        )


def anchor_exists(client: QdrantClient, anchor_id: str) -> bool:
    if not anchor_id:
        return False
    try:
        existing = client.retrieve(
            collection_name=QDRANT_COLLECTION,
            ids=[anchor_id],
            with_payload=False,
            with_vectors=False,
        )
        return bool(existing)
    except Exception as e:
        print(
            f"[indexer] failed to check existing anchor {anchor_id}: {e}",
            file=sys.stderr,
        )
        return False


def main():
    # Start the health check server in a background thread
    run_health_check_server()

    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client)
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "indexer",
            "auto.offset.reset": "earliest",
        }
    )
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    consumer.subscribe([TOP_IN])
    print("[indexer] listening...")
    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            print(f"[indexer] error: {msg.error()}", file=sys.stderr)
            continue
        try:
            payload = json.loads(msg.value().decode("utf-8"))
            anchor_id = payload.get("anchor_id")
            text = payload["text"]
            stored_at = payload["stored_at"]
            meta = payload.get("meta", {})
            salience = float(payload.get("salience", 1.0))
            if anchor_exists(client, anchor_id):
                warn_msg = {
                    "anchor_id": anchor_id,
                    "ok": False,
                    "reason": "anchor_immutable_violation",
                    "detail": "Anchor already exists; skipping write",
                }
                producer.produce(TOP_OUT, json.dumps(warn_msg).encode("utf-8"))
                producer.flush()
                print(
                    f"[indexer] WARNING: anchor {anchor_id} already exists, skipping",
                    file=sys.stderr,
                )
                continue
            embedding = get_embedding(text)
            client.upsert(
                collection_name=QDRANT_COLLECTION,
                wait=True,
                points=[
                    models.PointStruct(
                        id=anchor_id,
                        vector=embedding,
                        payload={
                            "text": text,
                            "stored_at": stored_at,
                            "salience": salience,
                            "meta": meta,
                        },
                    )
                ],
            )
            out = {"anchor_id": anchor_id, "ok": True}
            producer.produce(TOP_OUT, json.dumps(out).encode("utf-8"))
            producer.flush()
            print(f"[indexer] indexed {anchor_id}")
        except Exception as e:
            print(f"[indexer] exception: {e}", file=sys.stderr)
    consumer.close()


if __name__ == "__main__":
    main()
