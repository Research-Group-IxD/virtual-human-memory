"""
Unit tests for indexer worker individual functions.

These tests focus on testing individual functions in isolation,
with all dependencies mocked.
"""
import pytest
from unittest.mock import MagicMock, Mock, patch

from workers.vhm_indexer.main import (
    ensure_collection,
    anchor_exists,
    process_anchor,
)


# Test process_anchor
def test_process_anchor_success(
    mock_qdrant_client, mock_get_embedding, sample_anchor
):
    """Test successful anchor processing when anchor does not exist."""
    # Setup: anchor doesn't exist
    mock_qdrant_client.retrieve.return_value = []

    result = process_anchor(sample_anchor, mock_qdrant_client, mock_get_embedding)

    assert result["ok"] is True
    assert result["anchor_id"] == str(sample_anchor.anchor_id)
    mock_qdrant_client.upsert.assert_called_once()


def test_process_anchor_immutability_violation(
    mock_qdrant_client, sample_anchor
):
    """Test that existing anchors are not overwritten."""
    # Setup: anchor already exists
    mock_qdrant_client.retrieve.return_value = [Mock()]

    result = process_anchor(
        sample_anchor,
        mock_qdrant_client,
        lambda x: [0.1] * 384,  # Mock embedding function
    )

    assert result["ok"] is False
    assert result["reason"] == "anchor_immutable_violation"
    mock_qdrant_client.upsert.assert_not_called()


# Test ensure_collection
def test_ensure_collection_creates_new(mock_qdrant_client):
    """Test collection creation when it doesn't exist."""
    mock_qdrant_client.get_collections.return_value.collections = []

    ensure_collection(mock_qdrant_client)

    mock_qdrant_client.recreate_collection.assert_called_once()


@patch("workers.vhm_indexer.main.get_embedding_dim", return_value=384)
def test_ensure_collection_recreates_on_dimension_mismatch(
    mock_get_dim, mock_qdrant_client
):
    """Test collection recreation when vector dimensions don't match."""
    # Setup: collection exists with wrong dimensions (e.g., 768)
    mock_collection = Mock()
    mock_collection.name = "anchors"
    mock_qdrant_client.get_collections.return_value.collections = [mock_collection]

    mock_collection_info = Mock()
    mock_collection_info.config = Mock()
    mock_collection_info.config.params = Mock()
    mock_collection_info.config.params.vectors = Mock()
    mock_collection_info.config.params.vectors.size = 768  # Wrong dimension
    mock_qdrant_client.get_collection.return_value = mock_collection_info

    ensure_collection(mock_qdrant_client)

    mock_qdrant_client.delete_collection.assert_called_once_with("anchors")
    mock_qdrant_client.recreate_collection.assert_called_once()


@patch("workers.vhm_indexer.main.get_embedding_dim", return_value=384)
def test_ensure_collection_no_change_when_correct(mock_get_dim, mock_qdrant_client):
    """Test no action is taken when collection exists with correct dimensions."""
    mock_collection = Mock()
    mock_collection.name = "anchors"
    mock_qdrant_client.get_collections.return_value.collections = [mock_collection]

    mock_collection_info = Mock()
    mock_collection_info.config = Mock()
    mock_collection_info.config.params = Mock()
    mock_collection_info.config.params.vectors = Mock()
    mock_collection_info.config.params.vectors.size = 384  # Correct dimension
    mock_qdrant_client.get_collection.return_value = mock_collection_info

    ensure_collection(mock_qdrant_client)

    mock_qdrant_client.delete_collection.assert_not_called()
    mock_qdrant_client.recreate_collection.assert_not_called()


# Test anchor_exists
def test_anchor_exists_true(mock_qdrant_client):
    """Test anchor_exists returns True when the anchor exists."""
    mock_qdrant_client.retrieve.return_value = [Mock()]  # Simulate anchor found

    result = anchor_exists(mock_qdrant_client, "test-id")

    assert result is True
    mock_qdrant_client.retrieve.assert_called_once()


def test_anchor_exists_false(mock_qdrant_client):
    """Test anchor_exists returns False when the anchor does not exist."""
    mock_qdrant_client.retrieve.return_value = []  # Simulate anchor not found

    result = anchor_exists(mock_qdrant_client, "test-id")

    assert result is False


def test_anchor_exists_empty_id(mock_qdrant_client):
    """Test anchor_exists returns False for an empty anchor_id without querying."""
    result = anchor_exists(mock_qdrant_client, "")
    assert result is False
    mock_qdrant_client.retrieve.assert_not_called()


def test_anchor_exists_qdrant_error(mock_qdrant_client, caplog):
    """Test anchor_exists handles Qdrant errors gracefully and returns False."""
    mock_qdrant_client.retrieve.side_effect = Exception("Qdrant connection error")

    result = anchor_exists(mock_qdrant_client, "test-id")

    assert result is False
    assert "failed to check existing anchor" in caplog.text.lower()

