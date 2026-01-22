"""Tests for common utility modules."""
from __future__ import annotations

import importlib
from datetime import datetime, timezone

from vhm_common_utils import config as config_module
from vhm_common_utils.data_models import Anchor, RecallRequest
from vhm_common_utils.health import health_check
from vhm_common_utils.version import get_version


def test_health_check_returns_ok():
    assert health_check() == {"status": "ok"}


def test_anchor_validation_accepts_valid_payload():
    anchor = Anchor(
        anchor_id="00000000-0000-0000-0000-000000000000",
        text="test memory",
        stored_at=datetime.now(tz=timezone.utc),
        salience=1.0,
        meta={"session": "s1"},
    )

    assert anchor.text == "test memory"
    assert anchor.meta["session"] == "s1"


def test_recall_request_defaults_are_valid():
    request = RecallRequest(query="hello")

    assert request.top_k == 3
    assert request.ignore_anchor_ids == []


def test_config_reads_env_overrides(monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setenv("QDRANT_URL", "http://qdrant-test:6333")
        scoped.setenv("INDEXER_KAFKA_RETRIES", "5")

        reloaded = importlib.reload(config_module)

        assert reloaded.QDRANT_URL == "http://qdrant-test:6333"
        assert reloaded.INDEXER_KAFKA_RETRIES == 5

    importlib.reload(config_module)


def test_get_version_returns_project_version():
    version = get_version()

    assert isinstance(version, str)
    assert version != "0.0.0-unknown"

