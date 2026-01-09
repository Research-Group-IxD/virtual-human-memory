import os
from typing import Callable, TypeVar

_T = TypeVar("_T")


def _read_env(
    *names: str, transform: Callable[[str], _T] | None = None, default: _T | None = None
) -> _T | None:
    """
    Read the first available environment variable from `names`, optionally applying
    `transform` to coerce the value. If none are found or coercion fails, return
    `default`.
    """
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        if not transform:
            return raw  # type: ignore[return-value]
        try:
            return transform(raw)
        except Exception:
            # Fall through to try other names or the default.
            continue
    return default


# Qdrant Configuration
QDRANT_URL = _read_env("QDRANT_URL", default="http://qdrant:6333")
QDRANT_COLLECTION = _read_env("QDRANT_COLLECTION", default="anchors")

# Kafka Configuration
KAFKA_BOOTSTRAP = _read_env(
    "KAFKA_BOOTSTRAP", "KAFKA_BOOTSTRAP_SERVERS", default="kafka:9092"
)

# Embedding Model Configuration
EMBEDDING_MODEL = _read_env("EMBEDDING_MODEL", default="deterministic")
OLLAMA_BASE_URL = _read_env("OLLAMA_BASE_URL", default="http://host.docker.internal:11434")
OLLAMA_MODEL = _read_env("OLLAMA_MODEL", default="llama3")

# OpenAI Configuration
OPENAI_API_KEY = _read_env("OPENAI_API_KEY")
OPENAI_MODEL = _read_env("OPENAI_MODEL", default="gpt-4o-mini")

# Portkey.ai Configuration
PORTKEY_API_KEY = _read_env("PORTKEY_API_KEY")
PORTKEY_BASE_URL = _read_env("PORTKEY_BASE_URL", default="https://api.portkey.ai/v1")
PORTKEY_CONFIG_ID = _read_env("PORTKEY_CONFIG_ID")
PORTKEY_MODEL = _read_env("PORTKEY_MODEL")

# Resonance Worker Configuration
RESONANCE_MAX_BEATS = _read_env("RESONANCE_MAX_BEATS", transform=int, default=3)
RESONANCE_DIVERSITY_THRESHOLD = _read_env(
    "RESONANCE_DIVERSITY_THRESHOLD", transform=float, default=0.85
)

# Indexer Worker Configuration
INDEXER_QDRANT_RETRIES = _read_env("INDEXER_QDRANT_RETRIES", transform=int, default=3)
INDEXER_QDRANT_RETRY_BACKOFF_SECONDS = _read_env(
    "INDEXER_QDRANT_RETRY_BACKOFF_SECONDS", transform=float, default=0.25
)
INDEXER_KAFKA_RETRIES = _read_env("INDEXER_KAFKA_RETRIES", transform=int, default=3)
INDEXER_KAFKA_RETRY_BACKOFF_SECONDS = _read_env(
    "INDEXER_KAFKA_RETRY_BACKOFF_SECONDS", transform=float, default=0.5
)
INDEXER_SHUTDOWN_TIMEOUT_SECONDS = _read_env(
    "INDEXER_SHUTDOWN_TIMEOUT_SECONDS", transform=float, default=10.0
)

# Embedding dimensions by model
EMBEDDING_DIMS = {
    "deterministic": 384,
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "bge-m3": 1024,
    "cohere-embed-v3": 1024,
}
