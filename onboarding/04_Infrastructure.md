# Project Onboarding: Infrastructure & Dependencies

> **Note on Production Environments**
> For production or staging environments on Kubernetes, you should replace containerized services with managed, cloud-native equivalents (e.g., Confluent Cloud for Kafka, Qdrant Cloud) as outlined in the Deployment Guide.

## 4. Infrastructure

The entire system is containerized and orchestrated using Kubernetes (Minikube for local development). This provides a reproducible, isolated environment for development and testing. The core infrastructure consists of two main third-party services: Apache Kafka and Qdrant.

### 4.1 Apache Kafka (Event Bus)

*   **Docker Image**: `confluentinc/cp-kafka:latest`
*   **Role**: Acts as the central nervous system for the entire architecture. All communication between the worker services is handled asynchronously through Kafka topics. This decouples the services and provides a resilient, auditable log of all memory operations.
*   **Configuration**:
    *   The Kubernetes manifests configure a modern, single-node Kafka cluster running in KRaft mode, which eliminates the need for a separate Zookeeper instance.
    *   The Kafka broker is available to other services within the Kubernetes cluster at `kafka-service:9092`.
    *   For local development and testing, use `kubectl port-forward` to access Kafka from your local machine at `localhost:9092`.
*   **Key Topics**:
    *   `anchors-write`: For creating new memories.
    *   `anchors-indexed`: For confirming that memories have been stored.
    *   `recall-request`: For querying for memories.
    *   `recall-response`: For returning the raw results ("beats") of a query.
    *   `retell-response`: For returning the final, LLM-generated narrative.

### 4.2 Qdrant (Vector Database)

*   **Docker Image**: `qdrant/qdrant:latest`
*   **Role**: Serves as the long-term memory store. Qdrant is a high-performance vector database specifically designed for storing and searching high-dimensional data, like the embeddings generated from memory text.
*   **Configuration**:
    *   The service is available within the Kubernetes cluster at `http://qdrant-service:6333`.
    *   For local development and testing, use `kubectl port-forward` to access Qdrant from your local machine at `http://localhost:6333`.
    *   Data is persisted using Kubernetes PersistentVolumes. This means your memories will survive even if you stop and restart the pods.
*   **Usage**:
    *   The **Indexer** service writes to Qdrant, storing each memory's vector embedding and its metadata payload.
    *   The **Resonance** service reads from Qdrant, performing a nearest-neighbor search to find memories that are semantically similar to a given query.
    *   The collection name used by the services is configured via the `QDRANT_COLLECTION` environment variable (defaults to `anchors`).

### 4.3 Ollama (Local LLM/Embedding Provider)

While not deployed as part of the Kubernetes infrastructure, the system is designed to integrate with a local Ollama instance for generating embeddings and performing narrative retelling without relying on cloud APIs.

*   **Role**: Provides local, privacy-preserving access to a wide range of open-source embedding and language models.
*   **Configuration**:
    *   The workers are configured to reach Ollama via `OLLAMA_BASE_URL`.
    *   For local development with Minikube, you can access Ollama running on your host machine by using the host's IP address or by setting up port-forwarding.
    *   This setup is crucial for local development, testing, and use cases where data privacy is paramount.
*   **Usage**:
    *   Set `EMBEDDING_MODEL=ollama:bge-m3` or similar to use Ollama for embeddings.
    *   The system also supports a `deterministic` embedding model for testing without external dependencies.
