import json
import logging
import signal
import sys
import time
from confluent_kafka import Consumer, Producer
from pydantic import ValidationError
from qdrant_client import QdrantClient
from qdrant_client.http import models

from vhm_common_utils.config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    KAFKA_BOOTSTRAP,
    EMBEDDING_MODEL,
    INDEXER_QDRANT_RETRIES,
    INDEXER_QDRANT_RETRY_BACKOFF_SECONDS,
    INDEXER_KAFKA_RETRIES,
    INDEXER_KAFKA_RETRY_BACKOFF_SECONDS,
    INDEXER_SHUTDOWN_TIMEOUT_SECONDS,
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

# Global flag for graceful shutdown
shutdown_requested = False


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


def _qdrant_operation_with_retry(operation_name: str, operation_func, *args, **kwargs):
    """Execute a Qdrant operation with retry logic and exponential backoff."""
    attempts = (INDEXER_QDRANT_RETRIES or 3) + 1
    for attempt in range(1, attempts + 1):
        try:
            return operation_func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - want to log and retry
            backoff = (INDEXER_QDRANT_RETRY_BACKOFF_SECONDS or 0.25) * attempt
            logger.warning(
                f"Qdrant {operation_name} failed, retrying",
                extra={
                    "attempt": attempt,
                    "max_attempts": attempts,
                    "backoff_seconds": backoff,
                    "error": str(exc),
                },
            )
            if attempt >= attempts:
                raise
            if backoff > 0:
                time.sleep(backoff)
    return None


def anchor_exists(client: QdrantClient, anchor_id: str) -> bool:
    """Check if an anchor already exists in Qdrant with retry logic."""
    if not anchor_id:
        return False
    try:
        existing = _qdrant_operation_with_retry(
            "retrieve",
            client.retrieve,
            collection_name=QDRANT_COLLECTION,
            ids=[anchor_id],
            with_payload=False,
            with_vectors=False,
        )
        return bool(existing)
    except Exception as e:
        logger.error(f"Failed to check existing anchor {anchor_id} after retries: {e}")
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
    
    # Generate embedding with retry logic
    try:
        embedding = get_embedding_fn(anchor.text)
    except Exception as e:
        logger.error(f"Failed to generate embedding for anchor {anchor_id_str}: {e}")
        return {
            "anchor_id": anchor_id_str,
            "ok": False,
            "reason": "embedding_generation_failed",
            "detail": str(e),
        }
    
    # Store in Qdrant with retry logic
    try:
        _qdrant_operation_with_retry(
            "upsert",
            client.upsert,
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
    except Exception as e:
        logger.error(f"Failed to store anchor {anchor_id_str} in Qdrant after retries: {e}")
        return {
            "anchor_id": anchor_id_str,
            "ok": False,
            "reason": "qdrant_storage_failed",
            "detail": str(e),
        }
    
    return {"anchor_id": anchor_id_str, "ok": True}


def _publish_to_kafka_with_retry(producer: Producer, topic: str, message: bytes) -> bool:
    """Publish a message to Kafka with retry logic."""
    attempts = (INDEXER_KAFKA_RETRIES or 3) + 1
    for attempt in range(1, attempts + 1):
        try:
            producer.produce(topic, message)
            producer.flush()
            return True
        except Exception as exc:  # noqa: BLE001 - want to log and retry
            backoff = (INDEXER_KAFKA_RETRY_BACKOFF_SECONDS or 0.5) * attempt
            logger.warning(
                f"Kafka publish failed, retrying",
                extra={
                    "attempt": attempt,
                    "max_attempts": attempts,
                    "backoff_seconds": backoff,
                    "error": str(exc),
                },
            )
            if attempt >= attempts:
                logger.error(f"Failed to publish to Kafka after {attempts} attempts: {exc}")
                return False
            if backoff > 0:
                time.sleep(backoff)
    return False


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def main():
    """Main entry point for the indexer worker."""
    global shutdown_requested
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    
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
            "enable.auto.commit": False,  # Manual commit for better control
        }
    )
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    consumer.subscribe([TOP_IN])
    
    logger.info("Listening for anchor messages...")
    
    current_message = None
    try:
        while not shutdown_requested:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue
            
            current_message = msg
            payload_str = msg.value().decode("utf-8")
            try:
                # Parse JSON first
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON message: {e}")
                # Commit even on parse errors to avoid reprocessing bad messages
                consumer.commit(message=msg)
                continue
            
            try:
                # Validate with Pydantic
                anchor = Anchor.model_validate(payload)
                
                # Process the anchor
                result = process_anchor(anchor, client, get_embedding)
                
                # Publish result to Kafka with retry
                result_json = json.dumps(result).encode("utf-8")
                if _publish_to_kafka_with_retry(producer, TOP_OUT, result_json):
                    # Only commit if we successfully published the result
                    consumer.commit(message=msg)
                    
                    if result["ok"]:
                        logger.info(f"Indexed anchor {result['anchor_id']}")
                    else:
                        logger.warning(
                            f"{result['reason']} for anchor {result['anchor_id']}: {result.get('detail', '')}"
                        )
                else:
                    logger.error(f"Failed to publish result for anchor {result.get('anchor_id', 'unknown')}, not committing")
                    # Don't commit if publish failed - message will be reprocessed
                    
            except ValidationError as e:
                # Handle Pydantic validation errors
                error_msg = {
                    "anchor_id": payload.get("anchor_id", "unknown"),
                    "ok": False,
                    "reason": "validation_failed",
                    "errors": e.errors(),
                }
                error_json = json.dumps(error_msg).encode("utf-8")
                if _publish_to_kafka_with_retry(producer, TOP_OUT, error_json):
                    consumer.commit(message=msg)
                logger.error(
                    f"Validation failed for anchor {payload.get('anchor_id', 'unknown')}: {e.errors()}"
                )
                continue
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON message: {e}")
                consumer.commit(message=msg)
                continue
            except Exception as e:
                logger.exception(f"Unexpected error processing message: {e}")
                # Don't commit on unexpected errors - allow reprocessing
                
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        # Graceful shutdown: finish processing current message if any
        shutdown_timeout = INDEXER_SHUTDOWN_TIMEOUT_SECONDS or 10.0
        logger.info(f"Shutting down gracefully (timeout: {shutdown_timeout}s)...")
        
        # Flush any pending producer messages
        try:
            producer.flush(timeout=5.0)
        except Exception as e:
            logger.warning(f"Error flushing producer: {e}")
        
        # Close consumer (this will commit offsets)
        try:
            consumer.close()
        except Exception as e:
            logger.warning(f"Error closing consumer: {e}")
        
        logger.info("Indexer worker shutdown complete")


if __name__ == "__main__":
    main()
