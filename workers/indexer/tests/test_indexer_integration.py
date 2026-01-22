"""
Integration tests for indexer worker.

These tests test the interaction between components,
with mocked external dependencies (Qdrant, Kafka).
"""
import pytest
from unittest.mock import MagicMock, Mock, patch

from workers.vhm_indexer.main import process_anchor, _publish_to_kafka_with_retry


def test_indexer_full_flow_success(
    mock_qdrant_client, mock_get_embedding, sample_anchor
):
    """
    Test the full, successful processing flow for a new anchor.
    Verifies interaction between Qdrant and embedding generation.
    """
    # Setup: Anchor does not exist
    mock_qdrant_client.retrieve.return_value = []

    # Execute
    result = process_anchor(sample_anchor, mock_qdrant_client, mock_get_embedding)

    # Assert: Anchor was stored in Qdrant with correct data
    mock_qdrant_client.upsert.assert_called_once()
    call_args = mock_qdrant_client.upsert.call_args
    # Check that collection_name was provided (actual value comes from config)
    assert "collection_name" in call_args[1]
    point = call_args[1]["points"][0]
    assert point.id == str(sample_anchor.anchor_id)
    assert point.payload["text"] == sample_anchor.text
    assert point.vector == mock_get_embedding(sample_anchor.text)

    # Assert: A success confirmation was returned
    assert result["ok"] is True
    assert result["anchor_id"] == str(sample_anchor.anchor_id)


def test_indexer_immutability_enforcement_flow(
    mock_qdrant_client, sample_anchor
):
    """
    Test the full flow for an existing anchor, ensuring immutability is enforced.
    Verifies that Qdrant is not updated and a warning is returned.
    """
    # Setup: Anchor already exists
    mock_qdrant_client.retrieve.return_value = [Mock()]

    # Execute
    result = process_anchor(
        sample_anchor,
        mock_qdrant_client,
        lambda x: [0.1] * 384,  # Mock embedding
    )

    # Assert: Anchor was NOT stored in Qdrant again
    mock_qdrant_client.upsert.assert_not_called()

    # Assert: A warning was returned
    assert result["ok"] is False
    assert result["reason"] == "anchor_immutable_violation"
    assert "detail" in result


# Test Kafka producer retry logic
@patch("workers.vhm_indexer.main.time.sleep")
def test_kafka_producer_retry_success(mock_sleep, mock_qdrant_client, mock_get_embedding, sample_anchor):
    """Test Kafka producer retry logic in full flow."""
    from confluent_kafka import Producer
    
    # Setup: anchor doesn't exist
    mock_qdrant_client.retrieve.return_value = []
    
    # Create a mock producer
    mock_producer = MagicMock(spec=Producer)
    # First flush fails, second succeeds
    mock_producer.flush.side_effect = [
        Exception("Kafka temporary error"),
        None,  # Success on retry
    ]
    
    # Process anchor successfully
    result = process_anchor(sample_anchor, mock_qdrant_client, mock_get_embedding)
    assert result["ok"] is True
    
    # Test publishing with retry
    message = b'{"ok": true, "anchor_id": "test-id"}'
    success = _publish_to_kafka_with_retry(mock_producer, "test-topic", message)
    
    assert success is True
    assert mock_producer.produce.call_count == 2  # Called twice (retry)
    assert mock_producer.flush.call_count == 2
    assert mock_sleep.called  # Verify backoff was used


@patch("workers.vhm_indexer.main.time.sleep")
@patch("workers.vhm_indexer.main.INDEXER_KAFKA_RETRIES", 2)
def test_kafka_producer_retry_failure(mock_sleep, mock_qdrant_client, mock_get_embedding, sample_anchor, caplog):
    """Test that message is not committed if Kafka publish fails after retries."""
    from confluent_kafka import Producer
    
    # Setup: anchor doesn't exist
    mock_qdrant_client.retrieve.return_value = []
    
    # Create a mock producer that always fails
    mock_producer = MagicMock(spec=Producer)
    mock_producer.flush.side_effect = Exception("Persistent Kafka error")
    
    # Process anchor successfully
    result = process_anchor(sample_anchor, mock_qdrant_client, mock_get_embedding)
    assert result["ok"] is True
    
    # Test publishing with retry - should fail after all retries
    message = b'{"ok": true, "anchor_id": "test-id"}'
    success = _publish_to_kafka_with_retry(mock_producer, "test-topic", message)
    
    assert success is False
    # Should have tried 3 times (1 initial + 2 retries)
    assert mock_producer.flush.call_count == 3
    assert mock_sleep.call_count == 2  # Backoff called twice
    assert "Failed to publish to Kafka after" in caplog.text

