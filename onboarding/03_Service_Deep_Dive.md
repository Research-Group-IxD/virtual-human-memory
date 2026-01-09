# Project Onboarding: Service Deep Dive

## 3. Worker Services

The system's logic is distributed across three independent, containerized Python services called "workers". Each worker subscribes to a specific Kafka topic, performs a single well-defined task, and publishes its result to another topic.

### 3.1 Indexer

*   **Source Code**: `workers/vhm_indexer/main.py`
*   **Purpose**: To process new memories, convert them into a searchable format, and store them in the long-term vector database.
*   **Kafka Input Topic**: `anchors-write`
*   **Kafka Output Topic**: `anchors-indexed`

#### Logic & Key Features:

1.  **Consumes Raw Memories**: Listens for incoming JSON messages on the `anchors-write` topic.
2.  **Enforces Immutability**: Before processing, it checks Qdrant to see if a memory with the same `anchor_id` already exists. If it does, it skips the write operation and publishes a warning. This enforces the "immutable anchor" principle.
3.  **Generates Embeddings**: It uses a configured sentence-transformer model (e.g., BGE-M3) via a helper utility to convert the memory's text into a high-dimensional vector.
4.  **Stores in Qdrant**: It "upserts" the memory into the Qdrant collection. This includes:
    *   The unique `anchor_id` as the point ID.
    *   The generated vector.
    *   The full original JSON message as the payload (containing the text, timestamp, salience, etc.).
5.  **Handles Model Changes**: A key feature is the `ensure_collection` function. On startup, the Indexer checks if the Qdrant collection's vector dimensions match the dimensions of the currently configured embedding model. If they don't (e.g., switching from a 768-dim model to a 1024-dim model), it automatically deletes and recreates the collection. This allows for seamless model upgrades without manual intervention.
6.  **Publishes Confirmation**: Once the memory is successfully stored, it publishes a confirmation message to the `anchors-indexed` topic.
7.  **Production Readiness**: The Indexer includes retry logic with exponential backoff for both Qdrant and Kafka operations, ensuring memories aren't lost on temporary network issues. It also implements graceful shutdown handling (SIGTERM/SIGINT) to prevent data loss during deployments, and uses manual Kafka commits to ensure messages are only acknowledged after successful processing.

#### Kubernetes Considerations:

*   **Stateless**: The Indexer is a stateless service. All its state is managed externally in Kafka and Qdrant.
*   **Scalability**: You can run multiple replicas of the Indexer. Kubernetes, in conjunction with Kafka's consumer group protocol, will automatically balance the message load across the available pods. Scaling is typically limited by the write throughput of your Qdrant database.

---

### 3.2 Resonance

*   **Source Code**: `workers/vhm_resonance/main.py`
*   **Purpose**: To simulate the act of human recall. It searches for relevant memories and applies a psychological model to determine which ones are the most "active" or top-of-mind.
*   **Kafka Input Topic**: `recall-request`
*   **Kafka Output Topic**: `recall-response`

#### Logic & Key Features:

1.  **Consumes Recall Requests**: Listens for requests on the `recall-request` topic, which contain a `query` text and a `now` timestamp.
2.  **Semantic Search**: It first embeds the `query` text and performs a semantic search in Qdrant to find the most similar memory anchors based on cosine similarity.
3.  **Calculates Activation Score**: For each potential memory, it calculates a final activation score using the **Multi-Factor Activation** formula:
    `activation = similarity × decay × salience`
    *   `similarity`: The raw cosine similarity score from Qdrant.
    *   `decay`: An exponential decay weight calculated based on the memory's age. The formula is `exp(-λ * age_in_days)`, which directly models the Ebbinghaus forgetting curve.
    *   `salience`: The importance weight that was stored with the memory.
4.  **Selects for Diversity**: Instead of just picking the top memories by activation score, the `select_diverse_scored` function introduces a crucial step. It actively tries to build a set of results that are not too similar to each other. This prevents the final narrative from being repetitive and surfaces a wider range of relevant information.
5.  **Formats "Beats"**: It formats the final, selected memories into a list of "beats". Each beat is a dictionary containing the memory's text, its final activation score, and a human-readable `perceived_age` (e.g., "yesterday", "about 3 months ago").
6.  **Publishes Beats**: It publishes the list of beats to the `recall-response` topic.

#### Kubernetes Considerations:

*   **Stateless**: The Resonance worker is also stateless.
*   **Scalability**: You can scale the number of Resonance pods horizontally to handle a high volume of concurrent recall requests. Scaling is typically limited by the read throughput and query performance of your Qdrant database.

---

### 3.3 Reteller

*   **Source Code**: `workers/vhm_reteller/main.py`
*   **Purpose**: To act as the final narrative-generation layer. It takes the raw, disconnected memory "beats" from the Resonance worker and weaves them into a single, coherent, human-like story.
*   **Kafka Input Topic**: `recall-response`
*   **Kafka Output Topic**: `retell-response`

#### Logic & Key Features:

1.  **Consumes Memory Beats**: Listens for the list of beats on the `recall-response` topic.
2.  **Robust LLM Fallback Chain**: The Reteller is designed to be highly resilient. It attempts to generate a narrative using LLMs in a specific order, falling back to the next option if one fails:
    1.  OpenAI (if `OPENAI_API_KEY` is set)
    2.  Portkey (if `PORTKEY_API_KEY` is set)
    3.  A local Ollama instance (if `OLLAMA_BASE_URL` is set)
    4.  A deterministic `retell_stub` function (if all LLMs fail).
3.  **Advanced Prompt Engineering**: The core of the service is the `build_narrative_guidance` function. It doesn't just dump the memory text into a prompt. Instead, it:
    *   Orders beats chronologically.
    *   Extracts recurring keywords ("motifs") and guesses an overall "theme".
    *   Applies "forgetting" to the text of older memories by removing specific details (e.g., changing "at 14:30 in room R10" to "sometime in a room").
    *   Constructs a detailed prompt with instructions for the LLM to write a first-person, integrated recap, using the motifs and theme as guidance.
4.  **Stub Mode (No LLM)**: The `retell_stub` provides a non-LLM alternative that generates a decent, structured narrative. It uses hedging language ("I think...", "I remember...") for older memories and combines the beats into a summary. This ensures the system remains functional even without LLM connectivity.
5.  **Publishes Final Narrative**: It publishes the final generated string to the `retell-response` topic for the client application to use.

#### Kubernetes Considerations:

*   **Stateless**: The Reteller is stateless.
*   **Scalability**: This service can also be scaled horizontally. Its performance is primarily bound by the latency and rate limits of the external LLM APIs it calls (or the inference speed of a local model).
