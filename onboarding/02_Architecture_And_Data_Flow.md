# Project Onboarding: Architecture & Data Flow

## 2. System Architecture

The system is built on a **microservices architecture** using **event-driven communication**. Components communicate by sending messages through Apache Kafka. This design provides decoupling, resilience, and scalability.

### 2.1 Why this architecture for Kubernetes?

The event-driven, microservices-based design is an ideal foundation for a Kubernetes deployment.

*   **Independent Scaling**: Because the `Indexer`, `Resonance`, and `Reteller` services are completely decoupled, each can be scaled independently. If you have a high volume of incoming memories, you can scale up the `Indexer` pods without touching the others. If recall is slow, you can scale up `Resonance`. This is a core benefit of Kubernetes.
*   **Resilience**: Kafka acts as a durable buffer. If a worker pod crashes and restarts, it can resume processing messages from the last known offset in the Kafka topic, ensuring no data is lost.
*   **Observability**: Each microservice can have its own focused monitoring and alerting, making it easier to pinpoint performance bottlenecks in a complex, distributed system.

### 2.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Apache Kafka (Message Broker)               │
│  Topics: anchors-write → anchors-indexed → recall-request →         │
│          recall.response → retell.response                          │
└─────────────────────────────────────────────────────────────────────┘
                                   ↕
       ┌──────────────┬────────────┼────────────┬──────────────┐
       ↓              ↓            ↓            ↓              ↓
  ┌─────────┐   ┌─────────┐  ┌─────────┐  ┌─────────┐   ┌─────────┐
  │ Indexer │   │Resonance│  │Reteller │  │ Qdrant  │   │  Tools  │
  │ Worker  │   │ Worker  │  │ Worker  │  │Vector DB│   │(Client) │
  └─────────┘   └─────────┘  └─────────┘  └─────────┘   └─────────┘
```

### 2.2 Core Components

*   **Apache Kafka**: The central nervous system. All communication flows through Kafka topics, providing a durable and auditable log of every memory operation.
*   **Qdrant (Vector DB)**: The long-term memory store. It holds the vector embeddings of memory "anchors" and allows for high-speed similarity searches.
*   **Workers**: These are the stateless, containerized Python services that do the actual work.
    *   **Indexer**: Listens for new memories, generates vector embeddings using a model like BGE-M3, and stores them in Qdrant.
    *   **Resonance**: The psychological core. It takes a search query, finds similar memories in Qdrant, and applies the temporal decay and salience formulas to calculate a final "activation" score.
    *   **Reteller**: Takes the raw memory "beats" from Resonance and uses an LLM (like Phi-3 or GPT-4o) to weave them into a natural, human-like story.
*   **Tools**: A client application (or any external system) that writes new memories and submits recall requests.

## 3. Data Flow: The Lifecycle of a Memory

Here is the step-by-step journey of a memory, from its creation to its recall and retelling.

### Phase 1: Memory Formation (Indexing)

1.  **A memory is created**: An external application (e.g., a chatbot) creates a JSON object representing an event.
    ```json
    {
      "anchor_id": "uuid-goes-here",
      "text": "We demoed our Virtual Human at Fontys; lively Q&A about ethics",
      "stored_at": "2025-10-01T14:30:00Z",
      "salience": 1.5
    }
    ```
2.  **Publish to Kafka**: This JSON object is published as a message to the `anchors-write` Kafka topic.
3.  **Indexer Consumes**: The `Indexer` worker picks up the message.
4.  **Embed & Store**: The Indexer uses an embedding model to turn the `.text` field into a high-dimensional vector (e.g., `[0.12, -0.45, ...]`). It then stores this vector along with the original JSON payload in the Qdrant database.
5.  **Confirmation**: The Indexer publishes a confirmation message to the `anchors.indexed` topic. The memory is now permanently stored and searchable.

### Phase 2: Memory Recall & Retelling

1.  **A query is made**: The application wants to recall a memory. It creates a recall request.
    ```json
    {
      "request_id": "uuid-goes-here",
      "query": "What happened at the demo?",
      "now": "2025-10-02T10:00:00Z",
      "top_k": 3
    }
    ```
2.  **Publish to Kafka**: This request is published to the `recall.request` topic.
3.  **Resonance Consumes**: The `Resonance` worker picks up the request.
4.  **Search & Score**:
    *   Resonance embeds the `query` text into a vector.
    *   It searches Qdrant for the `