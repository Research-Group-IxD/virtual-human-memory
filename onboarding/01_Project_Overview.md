# Project Onboarding: Narrative Memory System

## 1. Project Overview & Core Concepts

Welcome to the Narrative Memory System, a psychologically-grounded memory architecture for conversational AI. This document provides a high-level overview of the system's purpose, core concepts, and architecture.

### 1.1 What is the Goal?

The primary goal is to create a more human-like memory system for AI agents (Virtual Humans). Instead of a perfect, database-like memory, this system mimics human cognition by incorporating:

*   **Temporal Decay**: Memories fade over time, following the Ebbinghaus forgetting curve.
*   **Recency & Salience**: Recent and emotionally important events are easier to recall.
*   **Narrative Retelling**: Memories are not just raw data; they are retold as stories, with details becoming "fuzzy" as they age.

The core paradigm is the **Anchor-and-Flux Model**:
*   **Anchors**: Durable, factual memories of events (the "what, where, when"). These are immutable.
*   **Flux**: The adaptive, ever-changing stories woven from those anchors.

This allows an AI's identity to emerge from its history, rather than being defined by static personality traits.

### 1.2 Core Terminology

*   **Activation**: The final score determining a memory's recall strength. It's a combination of:
    *   **Semantic Similarity**: How closely a memory matches a query.
    *   **Temporal Decay**: How much the memory has faded over time (a weight from 1.0 down to ~0.0).
    *   **Salience**: A manually assigned weight (e.g., 0.3 for a trivial chat, 2.5 for a critical system failure) that reflects the memory's importance.
*   **Beats**: The raw memory fragments retrieved from the database *before* they are woven into a narrative. Each beat includes the original text, its perceived age ("yesterday"), and its activation score.
*   **Workers**: The independent microservices that perform specific tasks:
    *   **Indexer**: Creates and stores memory anchors.
    *   **Resonance**: Simulates the act of remembering by calculating activation scores.
    *   **Reteller**: Weaves the recalled beats into a natural-language story.

### 1.3 High-Level Architecture

The system uses an **event-driven microservices architecture** built on Apache Kafka and Qdrant. This design is inherently scalable and well-suited for cloud-native deployment on platforms like Kubernetes.

```
┌──────────┐     ┌───────────┐     ┌──────────┐
│          │     │           │     │          │
│ Indexer  ├─────► Resonance ├─────► Reteller │
│          │     │           │     │          │
└────┬─────┘     └─────┬─────┘     └──────────┘
     │                 │
     │ Stores/Searches │
     ▼                 ▼
┌───────────┐     ┌────────────────┐
│  Qdrant   │     │  Apache Kafka  │
│(Vector DB)│     │(Event Streams) │
└───────────┘     └────────────────┘
```

1.  **Communication**: Services do not call each other directly. They produce and consume events from **Kafka topics** (e.g., `anchors-write`, `recall-request`). This makes the system decoupled, scalable, and resilient.
2.  **Long-Term Storage**: The **Indexer** converts memories into vector embeddings and stores them in **Qdrant**, a specialized vector database.
3.  **Recall Process**:
    *   A query hits the **Resonance** worker.
    *   Resonance searches Qdrant for semantically similar memories.
    *   It then applies the **Multi-Factor Activation** formula to score and rank the results.
    *   The top-ranked memories (beats) are passed to the **Reteller**.
4.  **Narrative Generation**: The **Reteller** uses a Large Language Model (LLM) to transform the raw beats into a coherent, age-aware narrative.

This architecture ensures that the process of remembering is transparent, tunable, and scalable, moving beyond simple information retrieval to a more dynamic and psychologically plausible model of memory.
