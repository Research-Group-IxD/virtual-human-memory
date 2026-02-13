# Pure Showcase: Virtual Human Memory (VHM)

This document provides ready-to-use text for uploading the Virtual Human Memory project and its contributions to **Pure** (research information system). Copy the sections below into the relevant Pure fields.

---

## 1. Suggested title (short)

**Virtual Human Memory: A Psychologically-Grounded Memory System for Virtual Humans**

*Alternative shorter:* **Virtual Human Memory (VHM)**

---

## 2. Abstract (for Pure "Abstract" or "Description" field)

**Recommended length: 150–250 words.**

Virtual Human Memory (VHM) is a multi-agent, psychologically-grounded long-term memory system for virtual humans and conversational AI. A central research aim was to implement a simulation of the **Ebbinghaus forgetting curve** within a virtual human: memories lose strength over time in a psychologically plausible way, so that recall and storytelling feel natural rather than database-like. A further aim was to deliver a **real, deployable prototype**—Docker images and Kubernetes-ready deployment—using practices from real IT projects (CI/CD, retry logic, graceful shutdown, tests), so the system is both research-valid and operationally usable.

The system simulates how humans form, recall, and retell memories using three specialised workers: an **Indexer** that ingests and stores memories as vector embeddings, a **Resonance** worker that recalls and ranks memories using a psychologically-inspired activation model (similarity × temporal decay × salience), and a **Reteller** that weaves recalled fragments into coherent narratives via large language models. The architecture is event-driven (Apache Kafka), uses a vector database (Qdrant) for semantic search, and is designed for Kubernetes deployment.

Contributions include production-ready behaviour in the Indexer worker: retry logic with exponential backoff for transient failures, graceful shutdown to avoid data loss, manual Kafka commits for at-least-once processing guarantees, and structured logging with context and timing. The codebase is supported by conceptual documentation (worker overview, retry logic explanation) suitable for teaching and presentations, and by a comprehensive test suite for the Indexer. The project is developed as an open monorepo with CI/CD, container images, and deployment manifests, and can serve as a reference implementation for narrative memory in virtual human systems.

---

## 3. Extended description (for "Full description" or "Project narrative")

**Use if Pure allows a longer text field (e.g. 300–500 words).**

### Context and aim

Virtual humans and conversational agents need long-term memory that is not only technically robust but also psychologically plausible: memories should be stored, forgotten over time, and recalled in a way that supports natural, story-like responses. Virtual Human Memory (VHM) had two main goals. First, **psychological plausibility**: we set out to simulate the **Ebbinghaus forgetting curve** inside a virtual human—so that older memories decay in strength over time and recall reflects this decay, making the system’s behaviour interpretable and grounded in memory research. Second, **deliverable prototype**: we wanted a real, runnable system, not only a design. That meant producing **Docker images**, deployment manifests, and production-style behaviour (retries, graceful shutdown, logging, tests), applying knowledge from real IT projects so the prototype can be deployed, demonstrated, and extended by others.

### Architecture

VHM is built as a distributed system with three main workers:

- **Indexer**: Consumes memory "anchors" from a message broker (Kafka), validates them, generates embeddings, and stores them in a vector database (Qdrant). It enforces immutability (no overwriting of existing memories) and supports configurable embedding models.
- **Resonance**: Responds to recall requests by performing semantic search in Qdrant and ranking results using an activation score that combines similarity to the query, **temporal decay following the Ebbinghaus forgetting curve**, and salience. Results are returned as "beats" for narrative generation.
- **Reteller**: Consumes recall results and uses LLMs to produce coherent, first-person narratives, with fallbacks across multiple providers and a deterministic stub for robustness.

Communication is asynchronous via Kafka; workers are stateless and horizontally scalable.

### Research and engineering contributions

- **Production-ready Indexer**: Retry logic (with exponential backoff) for Qdrant and Kafka operations; graceful shutdown on SIGTERM/SIGINT; manual Kafka commits so that only successfully processed messages are acknowledged; structured logging (including JSON) with context and processing time for observability.
- **Documentation for dissemination**: Presentation-oriented documents (e.g. workers overview, retry logic explanation) with diagrams and analogies, suitable for teaching and conference or project presentations.
- **Testability**: Focused test suite for the Indexer (unit, integration, retry, and shutdown scenarios) to support continuous integration and safe refactoring.
- **Open and reusable design**: Monorepo with shared utilities, Kubernetes manifests, and CI/CD (GitHub Actions), intended as a reference for narrative memory in virtual human systems.

### Relevance

VHM demonstrates how to combine vector search, psychological models of memory, and narrative generation in a single, deployable system. It is relevant to researchers and practitioners in human–computer interaction, conversational AI, and virtual human design who need a concrete, open implementation of long-term narrative memory.

---

## 4. Key outcomes / contributions (bullet list for Pure "Results" or "Outputs")

- **Ebbinghaus forgetting curve simulation** integrated into a virtual human’s memory recall (temporal decay in activation).
- Psychologically-grounded memory pipeline: store → recall (with activation) → narrate.
- **Deployable prototype**: Docker images and Kubernetes manifests; practices from IT projects (CI/CD, retries, graceful shutdown) applied so the system is runnable and maintainable.
- Production-ready Indexer worker: retry logic, graceful shutdown, manual Kafka commits, structured logging.
- Conceptual and presentation-ready documentation (worker overview, retry logic) for teaching and dissemination.
- Comprehensive Indexer test suite (unit, integration, retry, shutdown).
- Open-source monorepo with Kubernetes deployment and CI/CD (GitHub Actions).
- Reference implementation for narrative memory in virtual human and conversational AI systems.

---

## 5. Keywords (for Pure "Keywords" or "Topics")

Suggested terms (adjust to your institution's vocabulary):

- Virtual humans  
- Conversational AI  
- Long-term memory  
- Narrative memory  
- Vector databases  
- Semantic search  
- Psychological models of memory  
- Ebbinghaus forgetting curve  
- Human–computer interaction  
- Kubernetes  
- Event-driven architecture  

---

## 6. Links to add in Pure

- **Project / repository**: `https://github.com/Research-Group-IxD/virtual-human-memory`
- **Project page (if used)**: `https://research-group-ixd.github.io/virtual-human-memory/`
- **Documentation (concepts)**: link to `docs/concepts/` in the repo (e.g. workers-overview, retry-logic-explanation)

---

## 7. Type of research output in Pure

Depending on your Pure setup, this can be registered as:

- **Project** (with the abstract and description above), and/or  
- **Software** (if your organisation uses a "Software" or "Digital product" type), with the same abstract and a link to the repository.

---

## 8. Short elevator pitch (1–2 sentences)

*For profiles, tweets, or very short descriptions.*

Virtual Human Memory (VHM) is an open, psychologically-grounded long-term memory system for virtual humans: it simulates the Ebbinghaus forgetting curve in recall, stores memories as vectors, and turns them into coherent stories—delivered as a deployable prototype (Docker, Kubernetes) with production-ready behaviour and documentation for teaching and dissemination.

---

*Last updated: January 2025. Adjust authors, affiliations, and links to match your Pure entry.*
