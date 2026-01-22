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
    INDEXER_LOG_LEVEL,
    INDEXER_LOG_JSON,
)
from vhm_common_utils.data_models import Anchor
from vhm_common_utils.embedding import get_embedding, get_embedding_dim
from vhm_common_utils.health import run_health_check_server
from vhm_common_utils.version import get_version

logger = logging.getLogger("indexer")


def configure_logging() -> None:
    """Configure structured logging once per process."""
    if logging.getLogger().handlers:
        return
    
    level_name = (INDEXER_LOG_LEVEL or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    
    if INDEXER_LOG_JSON:
        # JSON logging format for structured logs
        import json as json_module
        from datetime import datetime
        
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                # Add extra fields from record
                if hasattr(record, "anchor_id"):
                    log_data["anchor_id"] = record.anchor_id
                if hasattr(record, "processing_time_ms"):
                    log_data["processing_time_ms"] = record.processing_time_ms
                if hasattr(record, "embedding_model"):
                    log_data["embedding_model"] = record.embedding_model
                if hasattr(record, "kafka_partition"):
                    log_data["kafka_partition"] = record.kafka_partition
                if hasattr(record, "kafka_offset"):
                    log_data["kafka_offset"] = record.kafka_offset
                if hasattr(record, "attempt"):
                    log_data["attempt"] = record.attempt
                if hasattr(record, "max_attempts"):
                    log_data["max_attempts"] = record.max_attempts
                if hasattr(record, "backoff_seconds"):
                    log_data["backoff_seconds"] = record.backoff_seconds
                if hasattr(record, "error"):
                    log_data["error"] = record.error
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                return json_module.dumps(log_data)
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logging.basicConfig(level=level, handlers=[handler])
    else:
        # Human-readable format with timestamps
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )

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
                "Collection has wrong dimensions, recreating",
                extra={
                    "current_dimensions": size,
                    "required_dimensions": dim,
                    "collection": QDRANT_COLLECTION,
                    "embedding_model": EMBEDDING_MODEL,
                },
            )
            client.delete_collection(QDRANT_COLLECTION)
            names.remove(QDRANT_COLLECTION)

    if QDRANT_COLLECTION not in names:
        logger.info(
            "Creating collection",
            extra={
                "collection": QDRANT_COLLECTION,
                "dimensions": dim,
                "embedding_model": EMBEDDING_MODEL,
            },
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
        logger.error(
            "Failed to check existing anchor after retries",
            extra={"anchor_id": anchor_id, "error": str(e)},
        )
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
        logger.error(
            "Failed to generate embedding for anchor",
            extra={
                "anchor_id": anchor_id_str,
                "error": str(e),
                "embedding_model": EMBEDDING_MODEL,
            },
        )
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
        logger.error(
            "Failed to store anchor in Qdrant after retries",
            extra={
                "anchor_id": anchor_id_str,
                "error": str(e),
                "collection": QDRANT_COLLECTION,
            },
        )
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
                logger.error(
                    "Failed to publish to Kafka after all attempts",
                    extra={
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "topic": topic,
                        "error": str(exc),
                    },
                )
                return False
            if backoff > 0:
                time.sleep(backoff)
    return False


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(
        "Received shutdown signal, initiating graceful shutdown",
        extra={"signal": signal_name, "signal_number": signum},
    )
    shutdown_requested = True


def _get_kafka_context(msg):
    """Extract Kafka message context for logging."""
    return {
        "kafka_partition": msg.partition() if hasattr(msg, "partition") else None,
        "kafka_offset": msg.offset() if hasattr(msg, "offset") else None,
    }


def _process_kafka_message(msg, client, producer, consumer):
    """Process a single Kafka message.
    
    Returns:
        bool: True if message was committed (successfully processed or bad message),
              False if message should be reprocessed (transient error).
    """
    # Parse JSON - early return on parse errors
    try:
        payload = json.loads(msg.value().decode("utf-8"))
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to parse JSON message",
            extra={
                "error": str(e),
                **_get_kafka_context(msg),
            },
        )
        # Commit bad messages to avoid infinite reprocessing
        consumer.commit(message=msg)
        return True
    
    # Validate with Pydantic - early return on validation errors
    try:
        anchor = Anchor.model_validate(payload)
    except ValidationError as e:
        anchor_id = payload.get("anchor_id", "unknown")
        error_msg = {
            "anchor_id": anchor_id,
            "ok": False,
            "reason": "validation_failed",
            "errors": e.errors(),
        }
        error_json = json.dumps(error_msg).encode("utf-8")
        
        # Try to publish error response
        if _publish_to_kafka_with_retry(producer, TOP_OUT, error_json):
            consumer.commit(message=msg)
            logger.error(
                "Validation failed for anchor",
                extra={
                    "anchor_id": anchor_id,
                    "errors": str(e.errors()),
                    **_get_kafka_context(msg),
                },
            )
            return True
        else:
            # Failed to publish error - don't commit, allow reprocessing
            logger.error(
                "Validation failed and failed to publish error response",
                extra={
                    "anchor_id": anchor_id,
                    "errors": str(e.errors()),
                    **_get_kafka_context(msg),
                },
            )
            return False
    
    # Process the anchor
    anchor_id = str(anchor.anchor_id)
    start_time = time.time()
    
    try:
        result = process_anchor(anchor, client, get_embedding)
    except Exception as e:
        # Unexpected error during processing
        logger.exception(
            "Unexpected error processing anchor",
            extra={
                "anchor_id": anchor_id,
                "error": str(e),
                **_get_kafka_context(msg),
            },
        )
        # Don't commit - allow reprocessing
        return False
    
    # Calculate processing time
    processing_time_ms = int((time.time() - start_time) * 1000)
    kafka_context = _get_kafka_context(msg)
    
    # Publish result to Kafka with retry
    result_json = json.dumps(result).encode("utf-8")
    if not _publish_to_kafka_with_retry(producer, TOP_OUT, result_json):
        logger.error(
            "Failed to publish result, not committing",
            extra={
                "anchor_id": result.get("anchor_id", "unknown"),
                "processing_time_ms": processing_time_ms,
                **kafka_context,
            },
        )
        # Don't commit if publish failed - message will be reprocessed
        return False
    
    # Successfully published - commit the message
    consumer.commit(message=msg)
    
    if result["ok"]:
        logger.info(
            "Indexed anchor successfully",
            extra={
                "anchor_id": anchor_id,
                "processing_time_ms": processing_time_ms,
                "embedding_model": EMBEDDING_MODEL,
                **kafka_context,
            },
        )
    else:
        logger.warning(
            f"{result['reason']} for anchor {anchor_id}: {result.get('detail', '')}",
            extra={
                "anchor_id": anchor_id,
                "processing_time_ms": processing_time_ms,
                "reason": result["reason"],
                "detail": result.get("detail", ""),
                **kafka_context,
            },
        )
    
    return True


def main():
    """Main entry point for the indexer worker."""
    global shutdown_requested
    
    # Configure logging first
    configure_logging()
    
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
    
    try:
        while not shutdown_requested:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            
            if msg.error():
                logger.error(
                    "Kafka consumer error",
                    extra={
                        "error": str(msg.error()),
                        **_get_kafka_context(msg),
                    },
                )
                continue
            
            # Process the message (all error handling is inside this function)
            _process_kafka_message(msg, client, producer, consumer)
                
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
