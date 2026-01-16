"""Root conftest.py - configures Python path before pytest collects tests."""

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient
from confluent_kafka import Consumer, Producer

from vhm_common_utils.data_models import Anchor


def pytest_configure(config):
    """Set up import paths for the test suite.
    
    This runs before test collection, ensuring modules are importable
    when pytest tries to import test files.
    """
    root = Path(__file__).resolve().parent
    
    # Add project root for `workers.vhm_*` imports
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    
    # Add common/utils for `vhm_common_utils` imports
    utils_path = root / "common" / "utils"
    if utils_path.exists():
        utils_str = str(utils_path)
        if utils_str not in sys.path:
            sys.path.insert(0, utils_str)


# ============================================================================
# Shared pytest fixtures for all tests
# ============================================================================

@pytest.fixture
def mock_qdrant_client():
    """Mock QdrantClient for testing."""
    client = MagicMock(spec=QdrantClient)

    # Default: collection doesn't exist
    client.get_collections.return_value.collections = []

    # Default: retrieve returns empty (anchor doesn't exist)
    client.retrieve.return_value = []

    return client


@pytest.fixture
def mock_kafka_consumer():
    """Mock Kafka Consumer for testing."""
    consumer = MagicMock(spec=Consumer)
    consumer.poll.return_value = None  # No message by default
    return consumer


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka Producer for testing."""
    producer = MagicMock(spec=Producer)
    return producer


@pytest.fixture
def mock_get_embedding():
    """Mock get_embedding function that returns deterministic embeddings."""

    def _mock(text: str) -> list[float]:
        # Return deterministic embedding for testing (384-dim)
        return [0.1] * 384

    return _mock


@pytest.fixture
def sample_anchor_payload():
    """Sample anchor payload as a dictionary for testing."""
    return {
        "anchor_id": str(uuid.uuid4()),
        "text": "We demoed the Virtual Human system to colleagues",
        "stored_at": "2025-11-21T10:00:00+00:00",
        "salience": 1.0,
        "meta": {"tags": ["demo"], "session": "session-123"},
    }


@pytest.fixture
def sample_anchor(sample_anchor_payload):
    """Sample anchor as a Pydantic model instance."""
    return Anchor.model_validate(sample_anchor_payload)

