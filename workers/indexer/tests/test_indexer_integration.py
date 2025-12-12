"""
Integration tests for indexer worker.

These tests test the interaction between components,
with mocked external dependencies (Qdrant, Kafka).
"""
import pytest
from unittest.mock import MagicMock, Mock

from workers.vhm_indexer.main import process_anchor


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

