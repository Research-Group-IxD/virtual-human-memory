import collections
import json
import re
import sys
import time
from typing import Any, Dict, List

from confluent_kafka import Consumer, Producer
from confluent_kafka.message import Message
import requests
from pydantic import ValidationError

from vhm_common_utils.embedding import perceived_age_to_days
from vhm_common_utils.config import (
    KAFKA_BOOTSTRAP,
    OPENAI_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_MODEL,
    PORTKEY_API_KEY,
    PORTKEY_BASE_URL,
    PORTKEY_CONFIG_ID,
    PORTKEY_MODEL,
    RETELLER_KAFKA_RETRIES,
    RETELLER_KAFKA_RETRY_BACKOFF_SECONDS,
    RETELLER_POLL_TIMEOUT_SECONDS,
    RETELLER_PRODUCER_FLUSH_TIMEOUT_SECONDS,
)
from vhm_common_utils.data_models import RecallResponse
from vhm_common_utils.health import run_health_check_server
from vhm_common_utils.version import get_version


TOP_IN = "recall-response"
TOP_OUT = "retell-response"


STOPWORDS = set(
    """
    a an the and or but if while of for to in on at from with by as about into over after before up down out off again
    further then once here there when where why how all any both each few more most other some such no nor not only own
    same so than too very s t can will just don dont should now
    """.split()
)


def _tokenize(text: str) -> List[str]:
    return [
        t.lower().strip(".,;:!?()[]{}\"'")
        for t in re.findall(r"[A-Za-z0-9\-]+", text or "")
    ]


def extract_motifs(beats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive lightweight motifs and a guessed theme across beats."""

    per_beat_keywords: List[List[str]] = []
    global_counts: "collections.Counter[str]" = collections.Counter()

    for beat in beats:
        tokens = [
            t
            for t in _tokenize(beat.get("text", ""))
            if t not in STOPWORDS and len(t) > 2
        ]
        nouns = [
            t
            for t in tokens
            if not re.match(r"^(i|you|we|they|he|she|it|me|us|them)$", t)
        ]
        unique_terms = sorted(set(nouns))
        per_beat_keywords.append(unique_terms)
        global_counts.update(unique_terms)

    flat_terms = [term for keywords in per_beat_keywords for term in set(keywords)]
    beat_presence = collections.Counter(flat_terms)
    recurrent = {term for term, count in beat_presence.items() if count >= 2}

    ignore_terms = {
        "yesterday",
        "today",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
    }
    top_terms = [
        term for term, _ in global_counts.most_common(6) if term not in ignore_terms
    ]
    theme_guess = (
        ", ".join(top_terms[:3]) if top_terms else "continuity of work across time"
    )

    return {
        "per_beat_keywords": per_beat_keywords,
        "recurrent": recurrent,
        "theme_guess": theme_guess,
    }


def order_beats_temporally(beats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(beats, key=lambda b: perceived_age_to_days(b.get("perceived_age")))


def apply_forgetting_to_text(text: str, activation: float) -> str:
    if activation >= 0.85:
        return text
    if activation >= 0.6:
        text = re.sub(r"\b\d{1,2}:\d{2}\b", "earlier", text)
        text = re.sub(r"\b\d{4}\b", "some time", text)
        return text
    text = text.strip()
    if not text:
        return text
    text = re.sub(r"\b\d{1,2}:\d{2}\b", "sometime", text)
    text = re.sub(r"\b\d{4}\b", "a while back", text)
    text = re.sub(r"\b(R\d+|room\s*\w+)\b", "a room", text, flags=re.I)
    clauses = re.split(r"[.;]", text)
    primary_clause = clauses[0].strip() if clauses else text
    return primary_clause


def narrativize_for_stub(beats: List[Dict[str, Any]]) -> str:
    ordered = order_beats_temporally(beats)
    if not ordered:
        return "I couldn’t piece together a clear thread."

    motifs = extract_motifs(ordered)
    theme = motifs["theme_guess"]

    def decapitalize(text: str) -> str:
        if not text:
            return text
        return text[0].lower() + text[1:]

    def summarise(beat: Dict[str, Any]) -> str:
        text = apply_forgetting_to_text(
            beat.get("text", ""), beat.get("activation", 1.0)
        )
        confidence = beat.get("activation", 1.0)
        if confidence >= 0.85:
            hedge = ""
        elif confidence >= 0.6:
            hedge = "I remember "
            text = decapitalize(text.strip())
        else:
            hedge = "I think "
            text = decapitalize(text.strip())
        return (hedge + text.strip()).strip()

    recent = summarise(ordered[0])
    if len(ordered) == 1:
        motif_phrase = ", ".join(sorted(motifs["recurrent"]))
        motif_clause = f" Motif: {motif_phrase}." if motif_phrase else ""
        return f"{recent}. Theme: {theme}.{motif_clause}"

    mid = summarise(ordered[1]) if len(ordered) > 1 else ""
    old = summarise(ordered[-1]) if len(ordered) > 2 else ""

    first_sentence = recent
    if mid:
        first_sentence = f"{first_sentence}, which echoed {mid}".strip()
    first_sentence = first_sentence.rstrip(".") + "."

    motif_phrase = ", ".join(sorted(motifs["recurrent"]))
    if old:
        second_sentence = f"Looking back, {old}, shaping a thread around {theme}."
    else:
        second_sentence = f"Together these moments formed a thread around {theme}."
    if motif_phrase:
        second_sentence = second_sentence.rstrip(".") + f" Motif: {motif_phrase}."
    else:
        second_sentence = second_sentence.rstrip(".") + "."

    narrative = f"{first_sentence} {second_sentence}".strip()
    narrative = re.sub(r"\s+", " ", narrative)
    return narrative[:400]


def retell_stub(beats):
    return narrativize_for_stub(beats)


def call_ollama(prompt):
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        response = data.get("response", "")

        # Qwen3 includes <think> tags for reasoning - extract just the final answer
        if "<think>" in response and "</think>" in response:
            # Get everything after the closing </think> tag
            response = response.split("</think>", 1)[-1].strip()

        return response
    except Exception as e:
        print(f"[reteller] Ollama error: {e}", file=sys.stderr)
        return None


def call_openai(messages):
    try:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.35,
            max_tokens=180,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[reteller] OpenAI error: {e}", file=sys.stderr)
        return None


def call_portkey(messages):
    if not PORTKEY_API_KEY:
        return None

    try:
        payload = {
            "model": PORTKEY_MODEL,
            "messages": messages,
            "max_tokens": 200,
            "temperature": 0.35,
        }

        headers = {
            "content-type": "application/json",
            "x-portkey-api-key": PORTKEY_API_KEY,
        }
        if PORTKEY_CONFIG_ID:
            headers["x-portkey-config"] = PORTKEY_CONFIG_ID

        r = requests.post(
            f"{PORTKEY_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message", {})
        content = message.get("content")
        return content
    except Exception as e:
        print(f"[reteller] Portkey error: {e}", file=sys.stderr)
        return None


def build_narrative_guidance(beats: List[Dict[str, Any]]) -> Dict[str, Any]:
    ordered = order_beats_temporally(beats)
    motifs = extract_motifs(ordered)
    lines = []
    for idx, beat in enumerate(ordered):
        activation = beat.get("activation", 1.0)
        text = apply_forgetting_to_text(beat.get("text", ""), activation)
        age = beat.get("perceived_age", "some time ago")
        confidence = (
            "high" if activation >= 0.85 else "medium" if activation >= 0.6 else "low"
        )
        keywords = motifs["per_beat_keywords"][idx][:4]
        keyword_text = ", ".join(keywords)
        scaffold = f"- {age} | conf:{confidence} | {text}"
        if keyword_text:
            scaffold += f" | motifs:{keyword_text}"
        lines.append(scaffold)

    system_prompt = (
        "You are a Virtual Human producing an INTEGRATED memory recap for yourself."
        "\nVoice: first-person, past tense, practical, emotionally neutral."
        "\nGoal: weave one coherent arc across memories instead of listing them."
    )

    user_prompt = (
        "Write a single integrated recap (2–3 sentences, ≤85 words) flowing recent→older."
        "\nDo:\n• Fuse events into one storyline using subtle connectors."
        "\n• Highlight recurring motifs once and propose a short through-line theme."
        "\n• Hedge older items with uncertainty phrases."
        "\n• No bullet points, lists, or meta commentary."
        f"\n\nGuessed theme: {motifs['theme_guess']}"
        f"\nRecurring motifs: {', '.join(sorted(motifs['recurrent'])) or '—'}"
        "\n\nMemory scaffold (recent→older):\n"
        + "\n".join(lines)
        + "\n\nIntegrated recap:"
    )

    return {"system": system_prompt, "user": user_prompt}


def _publish_to_kafka_with_retry(
    producer: Producer,
    topic: str,
    message: bytes,
    *,
    retries: int,
    backoff_seconds: float,
    flush_timeout_seconds: float,
) -> bool:
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            producer.produce(topic, message)
            producer.flush(timeout=flush_timeout_seconds)
            return True
        except Exception as exc:  # noqa: BLE001 - want to log and retry
            backoff = backoff_seconds * attempt
            print(
                f"[reteller] publish failed (attempt {attempt}/{attempts}): {exc}",
                file=sys.stderr,
            )
            if attempt >= attempts:
                return False
            if backoff > 0:
                time.sleep(backoff)
    return False


def _commit_message(consumer: Consumer, msg: Message, reason: str) -> None:
    try:
        consumer.commit(message=msg)
        print(
            f"[reteller] committed message ({reason}) partition={msg.partition()} offset={msg.offset()}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"[reteller] failed to commit message ({reason}): {exc}",
            file=sys.stderr,
        )


def _process_message(consumer: Consumer, producer: Producer, msg: Message) -> None:
    try:
        response = RecallResponse.model_validate_json(msg.value())
    except ValidationError as e:
        print(
            f"[reteller] invalid payload: {e}",
            file=sys.stderr,
        )
        _commit_message(consumer, msg, reason="validation_failed")
        return

    try:
        request_id = str(response.request_id)
        beats = [beat.model_dump(mode="json") for beat in response.beats]
        guidance = build_narrative_guidance(beats)
        text = None
        messages = [
            {"role": "system", "content": guidance["system"]},
            {"role": "user", "content": guidance["user"]},
        ]
        if OPENAI_API_KEY:
            text = call_openai(messages)
        if text is None:
            text = call_portkey(messages)
        if text is None and OLLAMA_BASE_URL:
            prompt = "\n\n".join([guidance["system"], guidance["user"]])
            text = call_ollama(prompt)
        if text is None:
            text = retell_stub(beats)
        out = {"request_id": request_id, "retelling": text}
        payload = json.dumps(out).encode("utf-8")
        published = _publish_to_kafka_with_retry(
            producer,
            TOP_OUT,
            payload,
            retries=RETELLER_KAFKA_RETRIES or 3,
            backoff_seconds=RETELLER_KAFKA_RETRY_BACKOFF_SECONDS or 0.5,
            flush_timeout_seconds=RETELLER_PRODUCER_FLUSH_TIMEOUT_SECONDS or 5.0,
        )
        if published:
            _commit_message(consumer, msg, reason="published")
            print(f"[reteller] retold {request_id}")
        else:
            print(
                f"[reteller] publish failed after retries for {request_id}",
                file=sys.stderr,
            )
            _commit_message(consumer, msg, reason="publish_failed")
    except Exception as e:
        print(f"[reteller] exception: {e}", file=sys.stderr)
        _commit_message(consumer, msg, reason="exception")


def main():
    __version__ = get_version("reteller")
    print(f"[reteller] Starting reteller worker version {__version__}")
    # Start the health check server in a background thread
    run_health_check_server()

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "reteller",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    consumer.subscribe([TOP_IN])
    print("[reteller] listening...")
    try:
        while True:
            msg = consumer.poll(RETELLER_POLL_TIMEOUT_SECONDS or 1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"[reteller] error: {msg.error()}", file=sys.stderr)
                continue
            _process_message(consumer, producer, msg)
    finally:
        consumer.close()
if __name__ == "__main__":
    main()
