"""
Tests for retry logic with exponential backoff and configuration.

These tests verify that retry mechanisms work correctly with
exponential backoff and that configuration is respected.
"""
import pytest
from unittest.mock import MagicMock, Mock, patch

from workers.vhm_indexer.main import (
    _qdrant_operation_with_retry,
    _publish_to_kafka_with_retry,
)


@patch("workers.vhm_indexer.main.time.sleep")
@patch("workers.vhm_indexer.main.INDEXER_QDRANT_RETRY_BACKOFF_SECONDS", 0.25)
def test_qdrant_retry_with_backoff(mock_sleep):
    """Test exponential backoff timing for Qdrant operations."""
    mock_operation = MagicMock()
    # First two attempts fail, third succeeds
    mock_operation.side_effect = [
        Exception("Error 1"),
        Exception("Error 2"),
        "success",
    ]

    result = _qdrant_operation_with_retry("test_operation", mock_operation, "arg1", kwarg1="value1")

    assert result == "success"
    assert mock_operation.call_count == 3
    # Verify backoff was called with correct values (0.25 * attempt)
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0][0][0] == 0.25  # First backoff: 0.25 * 1
    assert mock_sleep.call_args_list[1][0][0] == 0.5   # Second backoff: 0.25 * 2


@patch("workers.vhm_indexer.main.time.sleep")
@patch("workers.vhm_indexer.main.INDEXER_KAFKA_RETRY_BACKOFF_SECONDS", 0.5)
def test_kafka_retry_with_backoff(mock_sleep):
    """Test exponential backoff timing for Kafka operations."""
    from confluent_kafka import Producer
    
    mock_producer = MagicMock(spec=Producer)
    # First two attempts fail, third succeeds
    mock_producer.flush.side_effect = [
        Exception("Error 1"),
        Exception("Error 2"),
        None,  # Success
    ]

    result = _publish_to_kafka_with_retry(mock_producer, "test-topic", b"test message")

    assert result is True
    assert mock_producer.flush.call_count == 3
    # Verify backoff was called with correct values (0.5 * attempt)
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0][0][0] == 0.5  # First backoff: 0.5 * 1
    assert mock_sleep.call_args_list[1][0][0] == 1.0  # Second backoff: 0.5 * 2


@patch("workers.vhm_indexer.main.time.sleep")
@patch("workers.vhm_indexer.main.INDEXER_QDRANT_RETRIES", 1)
def test_retry_configurable_attempts_qdrant(mock_sleep):
    """Test that Qdrant retry attempts are configurable."""
    mock_operation = MagicMock()
    # All attempts fail
    mock_operation.side_effect = Exception("Persistent error")

    with pytest.raises(Exception, match="Persistent error"):
        _qdrant_operation_with_retry("test_operation", mock_operation)

    # With INDEXER_QDRANT_RETRIES=1, should try 2 times total (1 initial + 1 retry)
    assert mock_operation.call_count == 2
    assert mock_sleep.call_count == 1  # Backoff called once


@patch("workers.vhm_indexer.main.time.sleep")
@patch("workers.vhm_indexer.main.INDEXER_KAFKA_RETRIES", 1)
def test_retry_configurable_attempts_kafka(mock_sleep):
    """Test that Kafka retry attempts are configurable."""
    from confluent_kafka import Producer
    
    mock_producer = MagicMock(spec=Producer)
    mock_producer.flush.side_effect = Exception("Persistent error")

    result = _publish_to_kafka_with_retry(mock_producer, "test-topic", b"test message")

    assert result is False
    # With INDEXER_KAFKA_RETRIES=1, should try 2 times total (1 initial + 1 retry)
    assert mock_producer.flush.call_count == 2
    assert mock_sleep.call_count == 1  # Backoff called once


@patch("workers.vhm_indexer.main.time.sleep")
def test_retry_zero_retries_qdrant(mock_sleep):
    """Test retry behavior when INDEXER_QDRANT_RETRIES is 0 (falsy, uses default)."""
    # When INDEXER_QDRANT_RETRIES is 0, the code uses "or 3" which means 0 is falsy
    # So it falls back to default of 3 retries, making total attempts = 4
    with patch("workers.vhm_indexer.main.INDEXER_QDRANT_RETRIES", 0):
        mock_operation = MagicMock()
        mock_operation.side_effect = Exception("Error")

        with pytest.raises(Exception):
            _qdrant_operation_with_retry("test_operation", mock_operation)

        # With INDEXER_QDRANT_RETRIES=0 (falsy), attempts = (0 or 3) + 1 = 4
        # This is the actual behavior: 0 is falsy, so it uses default 3
        assert mock_operation.call_count == 4
        assert mock_sleep.call_count == 3  # Backoff called 3 times


@patch("workers.vhm_indexer.main.time.sleep")
def test_retry_zero_backoff(mock_sleep):
    """Test retry behavior when INDEXER_QDRANT_RETRY_BACKOFF_SECONDS is 0.0 (falsy, uses default)."""
    # When INDEXER_QDRANT_RETRY_BACKOFF_SECONDS is 0.0, the code uses "or 0.25" which means 0.0 is falsy
    # So it falls back to default of 0.25, making backoff = 0.25 * attempt
    with patch("workers.vhm_indexer.main.INDEXER_QDRANT_RETRY_BACKOFF_SECONDS", 0.0):
        mock_operation = MagicMock()
        # First attempt fails, second succeeds
        mock_operation.side_effect = [
            Exception("Error"),
            "success",
        ]

        result = _qdrant_operation_with_retry("test_operation", mock_operation)

        assert result == "success"
        assert mock_operation.call_count == 2
        # With 0.0 backoff (falsy), (0.0 or 0.25) = 0.25, so backoff = 0.25 * 1 = 0.25
        # This is the actual behavior: 0.0 is falsy, so it uses default 0.25
        # So sleep will be called with 0.25
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 0.25
