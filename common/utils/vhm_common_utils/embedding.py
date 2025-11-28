import hashlib
import numpy as np
import datetime as dt
import re
from typing import List

from .config import (
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
    PORTKEY_API_KEY,
    PORTKEY_BASE_URL,
    PORTKEY_CONFIG_ID,
    EMBEDDING_DIMS,
)


def get_embedding_dim() -> int:
    """Resolve embedding dimension for the current model (provider agnostic)."""
    key = EMBEDDING_MODEL
    if ":" in key:
        key = key.split(":", 1)[1]
    return EMBEDDING_DIMS.get(key, 384)


def deterministic_embed(text: str, dim: int | None = None) -> List[float]:
    # Fast, deterministic pseudo-embedding based on hashing tokens.
    # Useful for POC/testing without external dependencies
    if dim is None:
        dim = get_embedding_dim()
    vec = np.zeros(dim, dtype=np.float32)
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        vec[idx] += (h % 1000) / 1000.0
    # L2 normalize
    norm = np.linalg.norm(vec) + 1e-9
    return (vec / norm).tolist()


def _normalize_model_name(model: str) -> str:
    return model.split(":", 1)[1] if ":" in model else model


def _resolve_embedding_backend(model: str) -> tuple[str, str]:
    """Return (backend, normalized_model)."""
    if model.startswith("portkey:"):
        return ("portkey", _normalize_model_name(model))
    if model.startswith("ollama:"):
        return ("ollama", _normalize_model_name(model))
    if model in {"nomic-embed-text", "mxbai-embed-large", "bge-m3"}:
        return ("ollama", model)
    return ("deterministic", model)


def portkey_embed(text: str, model: str) -> List[float]:
    """Generate embeddings using Portkey gateway."""
    if not PORTKEY_API_KEY:
        raise RuntimeError("PORTKEY_API_KEY is not configured")

    backend, normalized = _resolve_embedding_backend(model)
    if backend != "portkey":
        raise ValueError(f"portkey_embed called for non-Portkey model: {model}")

    try:
        import requests

        headers = {
            "content-type": "application/json",
            "x-portkey-api-key": PORTKEY_API_KEY,
        }
        if PORTKEY_CONFIG_ID:
            headers["x-portkey-config"] = PORTKEY_CONFIG_ID

        response = requests.post(
            f"{PORTKEY_BASE_URL}/embeddings",
            headers=headers,
            json={"model": normalized, "input": [text]},
            timeout=60,
        )
        try:
            response.raise_for_status()
        except Exception as exc:
            print(
                "[embedding] Portkey embedding response error",
                {
                    "status_code": response.status_code,
                    "text": response.text[:200],
                    "model": normalized,
                },
            )
            raise
        data = response.json()
        embeddings = data.get("data", [])
        if not embeddings:
            raise ValueError("Empty embeddings response from Portkey")
        return embeddings[0].get("embedding", [])
    except Exception as e:
        print(
            f"[embedding] Portkey embedding failed: {e}, falling back to deterministic"
        )
        return deterministic_embed(text, dim=get_embedding_dim())


def ollama_embed(text: str, model: str = "nomic-embed-text") -> List[float]:
    """
    Generate embeddings using Ollama.
    Supported models: nomic-embed-text, mxbai-embed-large, bge-m3
    """
    backend, normalized = _resolve_embedding_backend(model)
    if backend != "ollama":
        raise ValueError(f"ollama_embed called for non-Ollama model: {model}")

    try:
        import requests

        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": normalized, "prompt": text},
            timeout=30,  # Larger models like BGE-M3 need more time
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        print(
            f"[embedding] Ollama embedding failed: {e}, falling back to deterministic"
        )
        return deterministic_embed(text, dim=get_embedding_dim())


def get_embedding(text: str) -> List[float]:
    """
    Main embedding function that respects EMBEDDING_MODEL env var.
    """
    backend, resolved = _resolve_embedding_backend(EMBEDDING_MODEL)
    if backend == "deterministic":
        return deterministic_embed(text, dim=get_embedding_dim())
    if backend == "portkey":
        return portkey_embed(text, model=EMBEDDING_MODEL)
    if backend == "ollama":
        return ollama_embed(text, model=EMBEDDING_MODEL)
    return deterministic_embed(text, dim=get_embedding_dim())


def human_age(delta: dt.timedelta) -> str:
    days = delta.days
    if days < 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        return f"{days//7} weeks ago"
    return f"{days // 30} months ago" if days < 365 else f"{days // 365} years ago"


def perceived_age_to_days(perceived_age: str | None) -> float:
    """Rudimentary parser that maps perceived age phrases to an approximate day count."""

    if not perceived_age:
        return float("inf")

    text = perceived_age.strip().lower()
    if not text:
        return float("inf")

    if any(term in text for term in ("just now", "this moment")):
        return 0.0
    if "today" in text:
        return 0.25
    if "yesterday" in text:
        return 1.0

    units = {
        "minute": 1 / 1440,
        "minutes": 1 / 1440,
        "hour": 1 / 24,
        "hours": 1 / 24,
        "day": 1.0,
        "days": 1.0,
        "week": 7.0,
        "weeks": 7.0,
        "month": 30.0,
        "months": 30.0,
        "year": 365.0,
        "years": 365.0,
    }

    number_match = re.search(r"(\d+(?:\.\d+)?)", text)
    value = float(number_match.group(1)) if number_match else 1.0

    for unit, multiplier in units.items():
        if unit in text:
            return value * multiplier

    if any(term in text for term in ("last week", "a week")):
        return 7.0
    if any(term in text for term in ("last month", "a month")):
        return 30.0
    if "last year" in text or "a year" in text:
        return 365.0

    # Fallback for phrases like "last autumn" or unrecognised metaphors
    if any(term in text for term in ("autumn", "fall")):
        return 270.0
    if "spring" in text:
        return 150.0
    if "summer" in text:
        return 90.0
    if "winter" in text:
        return 330.0

    return float("inf")
