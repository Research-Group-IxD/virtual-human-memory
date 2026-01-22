from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import datetime as dt
from typing import Dict, Iterable, List, Sequence, Tuple

from confluent_kafka import Consumer, Producer
from confluent_kafka.message import Message
from pydantic import ValidationError
from qdrant_client import QdrantClient
from qdrant_client.http.models import ScoredPoint

from vhm_common_utils.data_models import RecallRequest, RecallResponse, ResonanceBeat
from vhm_common_utils.embedding import get_embedding, human_age
from vhm_common_utils.health import run_health_check_server
from vhm_common_utils.version import get_version
from workers.vhm_resonance.config import ResonanceSettings


logger = logging.getLogger("vhm.resonance")


def configure_logging() -> None:
    """Configure structured logging once per process."""
    if logging.getLogger().handlers:
        return
    level_name = os.getenv("RESONANCE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def search_anchors(
    client: QdrantClient, collection: str, query_vec: Sequence[float], top_k: int
) -> Sequence[ScoredPoint]:
    return client.search(
        collection_name=collection, query_vector=query_vec, limit=top_k, with_payload=True
    )


def deterministic_query_vec(text: str) -> List[float]:
    return get_embedding(text)


def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def dedupe_hits_by_text(hits: Sequence[ScoredPoint]) -> List[ScoredPoint]:
    seen_texts: set[str] = set()
    unique: List[ScoredPoint] = []
    for hit in hits:
        payload = getattr(hit, "payload", {}) or {}
        text = payload.get("text")
        key = text.strip().lower() if isinstance(text, str) else None
        if key and key in seen_texts:
            continue
        if key:
            seen_texts.add(key)
        unique.append(hit)
    return unique


def select_diverse_scored(
    scored: Sequence[Tuple[float, ScoredPoint]],
    desired: int,
    embedding_cache: Dict[str, List[float]],
    diversity_threshold: float,
) -> List[Tuple[float, ScoredPoint]]:
    if desired <= 0:
        return []

    selected: List[Tuple[float, ScoredPoint]] = []
    taken_ids: set[str] = set()

    for act, hit in scored:
        payload = getattr(hit, "payload", {}) or {}
        text = payload.get("text")
        if text and text not in embedding_cache:
            embedding_cache[text] = get_embedding(text)

        is_diverse = True
        if text and text in embedding_cache:
            cand_vec = embedding_cache[text]
            for _, existing in selected:
                ex_payload = getattr(existing, "payload", {}) or {}
                ex_text = ex_payload.get("text")
                if not ex_text or ex_text not in embedding_cache:
                    continue
                sim = cosine_similarity(cand_vec, embedding_cache[ex_text])
                if sim >= diversity_threshold:
                    is_diverse = False
                    break

        if is_diverse:
            selected.append((act, hit))
            taken_ids.add(str(hit.id))
        if len(selected) >= desired:
            break

    if len(selected) < desired:
        for act, hit in scored:
            if str(hit.id) in taken_ids:
                continue
            selected.append((act, hit))
            taken_ids.add(str(hit.id))
            if len(selected) >= desired:
                break

    return selected


def decay_weight(stored_at_iso: str, now: dt.datetime, decay_lambda: float) -> float:
    stored = dt.datetime.fromisoformat(stored_at_iso.replace("Z", "+00:00")).replace(
        tzinfo=None
    )
    age_days = (now - stored).days
    return math.exp(-decay_lambda * max(age_days, 0))


def normalize_datetime(value: dt.datetime) -> dt.datetime:
    if value.tzinfo:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


class ResonanceWorker:
    """Coordinates Kafka consumption, Qdrant recall, and response publication."""

    def __init__(
        self,
        settings: ResonanceSettings,
        client: QdrantClient,
        consumer: Consumer,
        producer: Producer,
    ) -> None:
        self.settings = settings
        self.client = client
        self.consumer = consumer
        self.producer = producer

    def run(self) -> None:
        """Start consuming recall requests and publishing responses."""
        self.consumer.subscribe([self.settings.kafka_topic_in])
        logger.info(
            "Listening for recall requests",
            extra={"topic": self.settings.kafka_topic_in},
        )
        try:
            while True:
                msg = self.consumer.poll(self.settings.kafka_poll_timeout_seconds)
                if msg is None:
                    continue
                if msg.error():
                    logger.error(
                        "Kafka consumer error",
                        extra={
                            "topic": msg.topic(),
                            "partition": msg.partition(),
                            "offset": msg.offset(),
                            "error": str(msg.error()),
                        },
                    )
                    continue
                self._handle_message(msg)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal, closing consumer")
        finally:
            self.consumer.close()

    def _handle_message(self, msg: Message) -> None:
        try:
            request = RecallRequest.model_validate_json(msg.value())
        except ValidationError as err:
            logger.error(
                "Invalid recall request payload",
                extra={"payload": msg.value().decode("utf-8", errors="ignore")},
            )
            logger.debug("Validation details: %s", err)
            self._commit_message(msg, reason="validation_failed")
            return

        try:
            response = self._process_request(request)
        except Exception:
            logger.exception(
                "Failed to process recall request",
                extra={
                    "request_id": str(request.request_id),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )
            return

        payload_bytes = json.dumps(response.model_dump(mode="json")).encode("utf-8")
        if not self._publish_response_with_retry(payload_bytes, response.request_id):
            return

        self._commit_message(msg, reason="published")
        logger.info(
            "Published recall response",
            extra={
                "request_id": str(response.request_id),
                "beats": len(response.beats),
            },
        )

    def _process_request(self, request: RecallRequest) -> RecallResponse:
        request_now = normalize_datetime(request.now)
        ignore_ids = {str(anchor_id) for anchor_id in request.ignore_anchor_ids}
        query_vector = deterministic_query_vec(request.query)
        hits = self._search_with_retry(query_vector, request.top_k)
        filtered = self._filter_hits(hits, ignore_ids, request.session_id, request_now)
        deduped = dedupe_hits_by_text(filtered)
        scored = self._score_hits(deduped, request_now, request.session_id)
        scored.sort(key=lambda pair: pair[0], reverse=True)

        desired = min(self.settings.max_beats, request.top_k, len(scored))
        embedding_cache: Dict[str, List[float]] = {}
        selected = select_diverse_scored(
            scored,
            desired,
            embedding_cache,
            self.settings.diversity_threshold,
        )

        beats = [self._build_beat(act, hit, request_now) for act, hit in selected]
        return RecallResponse(request_id=request.request_id, beats=beats)

    def _publish_response_with_retry(self, payload: bytes, request_id) -> bool:
        attempts = self.settings.kafka_publish_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                self.producer.produce(self.settings.kafka_topic_out, payload)
                self.producer.flush(self.settings.producer_flush_timeout_seconds)
                return True
            except Exception as exc:  # noqa: BLE001 - want to log and retry
                backoff = self.settings.kafka_publish_retry_backoff_seconds * attempt
                logger.warning(
                    "Kafka publish failed, retrying",
                    extra={
                        "request_id": str(request_id),
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "backoff_seconds": backoff,
                        "error": str(exc),
                    },
                )
                if attempt >= attempts:
                    logger.exception(
                        "Failed to publish recall response after retries",
                        extra={"request_id": str(request_id)},
                    )
                    return False
                if backoff > 0:
                    time.sleep(backoff)
        return False

    def _commit_message(self, msg: Message, reason: str) -> None:
        try:
            self.consumer.commit(message=msg)
            logger.debug(
                "Committed message",
                extra={
                    "reason": reason,
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )
        except Exception:
            logger.exception(
                "Failed to commit message",
                extra={
                    "reason": reason,
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )

    def _search_with_retry(
        self, query_vector: Sequence[float], top_k: int
    ) -> Sequence[ScoredPoint]:
        attempts = self.settings.qdrant_search_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return search_anchors(
                    self.client, self.settings.qdrant_collection, query_vector, top_k
                )
            except Exception as exc:  # noqa: BLE001 - want to log and retry
                backoff = self.settings.qdrant_retry_backoff_seconds * attempt
                logger.warning(
                    "Qdrant search failed, retrying",
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
        return []

    def _filter_hits(
        self,
        hits: Sequence[ScoredPoint],
        ignore_ids: Iterable[str],
        session_id: str | None,
        now: dt.datetime,
    ) -> List[ScoredPoint]:
        ignore_set = set(ignore_ids)
        filtered: List[ScoredPoint] = []
        for hit in hits:
            if str(hit.id) in ignore_set:
                continue
            payload = getattr(hit, "payload", {}) or {}
            if not isinstance(payload, dict):
                continue
            meta = payload.get("meta") or {}
            if session_id and isinstance(meta, dict) and meta.get("session") == session_id:
                continue
            stored_iso = payload.get("stored_at")
            if stored_iso:
                stored = dt.datetime.fromisoformat(stored_iso.replace("Z", "+00:00")).replace(
                    tzinfo=None
                )
                if (now - stored).total_seconds() < 5:
                    continue
            filtered.append(hit)
        return filtered

    def _score_hits(
        self,
        hits: Sequence[ScoredPoint],
        now: dt.datetime,
        session_id: str | None,
    ) -> List[Tuple[float, ScoredPoint]]:
        scored: List[Tuple[float, ScoredPoint]] = []
        for hit in hits:
            payload = getattr(hit, "payload", {}) or {}
            if not isinstance(payload, dict):
                continue
            meta = payload.get("meta") or {}
            if session_id and isinstance(meta, dict) and meta.get("session") == session_id:
                continue
            stored_at = payload.get("stored_at")
            text = payload.get("text")
            if not stored_at or not text:
                continue
            decay = decay_weight(stored_at, now, self.settings.decay_lambda_per_day)
            salience = float(payload.get("salience", 1.0))
            stored = dt.datetime.fromisoformat(stored_at.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            if (now - stored).total_seconds() < 5:
                continue
            similarity = float(getattr(hit, "score", 0.0))
            activation = similarity * decay * salience
            scored.append((activation, hit))
        return scored

    def _build_beat(
        self, activation: float, hit: ScoredPoint, now: dt.datetime
    ) -> ResonanceBeat:
        payload = getattr(hit, "payload", {}) or {}
        stored_iso = payload.get("stored_at")
        stored = dt.datetime.fromisoformat(stored_iso.replace("Z", "+00:00")).replace(
            tzinfo=None
        ) if stored_iso else now
        return ResonanceBeat(
            anchor_id=str(hit.id),
            text=payload.get("text", ""),
            perceived_age=human_age(now - stored),
            activation=activation,
        )


def main() -> None:
    configure_logging()
    __version__ = get_version("resonance")
    logging.info(f"Starting resonance worker version {__version__}")
    run_health_check_server()
    settings = ResonanceSettings.from_env()
    worker = ResonanceWorker(
        settings=settings,
        client=QdrantClient(url=settings.qdrant_url),
        consumer=Consumer(settings.consumer_config),
        producer=Producer(settings.producer_config),
    )
    worker.run()


if __name__ == "__main__":
    main()
