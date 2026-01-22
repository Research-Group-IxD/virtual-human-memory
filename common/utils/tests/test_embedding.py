from __future__ import annotations

import importlib

from vhm_common_utils import config as config_module
from vhm_common_utils import embedding as embedding_module


def test_deterministic_embedding_length():
    vec = embedding_module.deterministic_embed("hello world", dim=64)
    assert len(vec) == 64
    assert all(isinstance(v, float) for v in vec)


def test_get_embedding_defaults_to_deterministic():
    vec = embedding_module.get_embedding("testing deterministic")
    assert len(vec) == embedding_module.get_embedding_dim()


def test_get_embedding_dim_respects_model_name(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    importlib.reload(config_module)
    importlib.reload(embedding_module)

    assert embedding_module.get_embedding_dim() == 768


def test_get_embedding_dim_handles_prefixed_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "ollama:nomic-embed-text")
    importlib.reload(config_module)
    importlib.reload(embedding_module)

    assert embedding_module.get_embedding_dim() == 768
