import json
import logging
import sys
from confluent_kafka import Consumer, Producer
from pydantic import ValidationError
from qdrant_client import QdrantClient
from qdrant_client.http import models

from vhm_common_utils.config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    KAFKA_BOOTSTRAP,
    EMBEDDING_MODEL,
)
from vhm_common_utils.data_models import Anchor
from vhm_common_utils.embedding import get_embedding, get_embedding_dim
from vhm_common_utils.health import run_health_check_server
from vhm_common_utils.version import get_version

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("indexer")


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
            logger.warning(
                f"Collection has wrong dimensions ({size} vs {dim}), recreating..."
            )
            client.delete_collection(QDRANT_COLLECTION)
            names.remove(QDRANT_COLLECTION)

    if QDRANT_COLLECTION not in names:
        logger.info(
            f"Creating collection with {dim} dimensions for {EMBEDDING_MODEL} embeddings"
        )
        client.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=models.VectorParams(
                size=dim, distance=models.Distance.COSINE
            ),
        )


def anchor_exists(client: QdrantClient, anchor_id: str) -> bool:
    """Check if an anchor already exists in Qdrant."""
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
        logger.error(f"Failed to check existing anchor {anchor_id}: {e}")
        return False


def process_anchor(
    anchor: Anchor,
    client: QdrantClient,
    get_embedding_fn=get_embedding,
) -> dict:
    """Process a single anchor payload. Returns result dict.
    
    Args:
        anchor: Validated Anchor model instance
        client: QdrantClient instance
        get_embedding_fn: Function to generate embeddings (default: get_embedding)
    
    Returns:
        dict with keys: anchor_id (str), ok (bool), reason (str, optional), detail (str, optional)
    """
    anchor_id_str = str(anchor.anchor_id)
    
    # Check for immutability violation
    if anchor_exists(client, anchor_id_str):
        return {
            "anchor_id": anchor_id_str,
            "ok": False,
            "reason": "anchor_immutable_violation",
            "detail": "Anchor already exists; skipping write",
        }
    
    # Generate embedding and store in Qdrant
    embedding = get_embedding_fn(anchor.text)
    client.upsert(
        collection_name=QDRANT_COLLECTION,
        wait=True,
        points=[
            models.PointStruct(
                id=anchor_id_str,
                vector=embedding,
                payload={
                    "text": anchor.text,
                    "stored_at": anchor.stored_at.isoformat(),
                    "salience": anchor.salience,
                    "meta": anchor.meta,
                },
            )
        ],
    )
    
    return {"anchor_id": anchor_id_str, "ok": True}


def main():
    """Main entry point for the indexer worker."""
    __version__ = get_version("indexer")
    logger.info(f"Starting indexer worker version {__version__}")
    
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
    
    logger.info("Listening for anchor messages...")
    
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue
            
            payload_str = msg.value().decode("utf-8")
            try:
                # Parse JSON first
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON message: {e}")
                continue
            
            try:
                # Validate with Pydantic
                anchor = Anchor.model_validate(payload)
                
                # Process the anchor
                result = process_anchor(anchor, client, get_embedding)
                
                # Publish result to Kafka
                producer.produce(TOP_OUT, json.dumps(result).encode("utf-8"))
                producer.flush()
                
                if result["ok"]:
                    logger.info(f"Indexed anchor {result['anchor_id']}")
                else:
                    logger.warning(
                        f"{result['reason']} for anchor {result['anchor_id']}: {result.get('detail', '')}"
                    )
                    
            except ValidationError as e:
                # Handle Pydantic validation errors
                # payload is already parsed from json.loads() above, so we can safely use it
                error_msg = {
                    "anchor_id": payload.get("anchor_id", "unknown"),
                    "ok": False,
                    "reason": "validation_failed",
                    "errors": e.errors(),
                }
                producer.produce(TOP_OUT, json.dumps(error_msg).encode("utf-8"))
                producer.flush()
                logger.error(
                    f"Validation failed for anchor {payload.get('anchor_id', 'unknown')}: {e.errors()}"
                )
                continue
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON message: {e}")
                continue
            except Exception as e:
                logger.exception(f"Unexpected error processing message: {e}")
    finally:
        consumer.close()
        logger.info("Shutting down indexer worker")


if __name__ == "__main__":
    main()
