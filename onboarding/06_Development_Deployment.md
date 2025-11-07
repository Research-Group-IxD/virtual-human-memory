# Project Onboarding: Development & Deployment

## 6. Local Development Guide

This guide covers how to get the full system running locally for development and testing.

### 6.1 Prerequisites

1.  **Docker & Docker Compose**: For running the containerized services.
2.  **Python & `uv`**: For managing Python dependencies and running local scripts. Install `uv` with `pip install uv`.
3.  **Ollama**: (Recommended) For local access to embedding and language models. Download from [ollama.com](https://ollama.com).
    *   After installing, pull the recommended models:
        ```sh
        ollama pull bge-m3
        ollama pull phi4
        ```

### 6.2 Full System Quick Start (Docker)

This is the recommended way to run the entire system, including Kafka and Qdrant.

1.  **Configure your environment**:
    *   Create a `.env` file in the project root.
    *   Add your desired configuration (see `05_Configuration.md`). For a quick start with local models, your `.env` can be simple:
        ```sh
        EMBEDDING_MODEL=ollama:bge-m3
        OLLAMA_MODEL=phi4
        ```

2.  **Initialize Kafka Topics**:
    *   Run the provided script to ensure the necessary Kafka topics are created. This script also clears out any old Qdrant data.
        ```sh
        bash convai_narrative_memory_poc/scripts/create_topics.sh
        ```

3.  **Launch Services**:
    *   Start all the services in detached mode using Docker Compose.
        ```sh
        docker compose -f convai_narrative_memory_poc/docker-compose.yml up -d
        ```

4.  **Interact with the System**:
    *   **Streamlit UI (Recommended)**: Open your browser to [http://localhost:8501](http://localhost:8501). This UI provides a chat interface and real-time visibility into the memory system's internal state (recalled beats, final retelling, etc.).
    *   **CLI Chatbot**: For a simpler, command-line interface:
        ```sh
        docker compose -f convai_narrative_memory_poc/docker-compose.yml run --rm chatbot
        ```

5.  **Shut Down**:
    *   When you're finished, bring down all the containers:
        ```sh
        docker compose -f convai_narrative_memory_poc/docker-compose.yml down
        ```

### 6.3 Lightweight Testing (Python only)

For quickly testing changes to the core logic without the overhead of Kafka and Docker, you can run the validation script directly.

1.  **Install dependencies**:
    ```sh
    uv sync
    ```
2.  **Run the script**:
    ```sh
    python -m convai_narrative_memory_poc.tools.validation_experiments
    ```
This script bypasses Kafka, directly calling the resonance and retelling logic and printing diagnostic output to the console.

## 7. Deployment Guide (Migrating to Kubernetes)

This section outlines the conceptual steps for migrating this PoC from Docker Compose to a production-ready Kubernetes environment. The key is to move from local, containerized infrastructure (Kafka, Qdrant) to robust, managed cloud services.

### 7.1 Key Principles for Production

*   **Managed Services over Self-Hosting**: For stateful components like Kafka and Qdrant, strongly prefer managed cloud services (e.g., Confluent Cloud, Aiven for Kafka, Qdrant Cloud, or a managed PostgreSQL with `pgvector`). This offloads the immense operational burden of managing, scaling, and backing up stateful infrastructure, allowing you to focus on the stateless worker applications.
*   **Infrastructure as Code (IaC)**: Define your managed services and Kubernetes resources using a tool like Terraform or OpenTofu. This makes your production infrastructure reproducible, version-controlled, and easier to manage.
*   **Helm for Application Packaging**: Package each worker service (`indexer`, `resonance`, `reteller`) as a separate Helm chart. This standardizes deployments, simplifies configuration, and makes versioning and rollbacks much more manageable.
*   **CI/CD Automation**: Set up a CI/CD pipeline (e.g., GitHub Actions) with the following stages:
    1.  **CI**: On every push to `main`, run tests, build Docker images for each worker, tag them with the Git SHA, and push them to a container registry (e.g., Docker Hub, AWS ECR, Google Artifact Registry).
    2.  **CD**: On a new tag or merge to a `production` branch, automatically deploy the corresponding Helm charts to the Kubernetes cluster.
*   **Centralized Configuration & Secrets**: Use Kubernetes Secrets for sensitive information (API keys, database credentials) and ConfigMaps for non-sensitive configuration. These should be populated from a secure, central secret store (e.g., HashiCorp Vault, AWS Secrets Manager, Doppler). **Do not** commit secrets to your Git repository.

### 7.2 Conceptual Migration Steps

1.  **Containerize and Registry**:
    *   The existing `Dockerfile` for each worker is production-ready.
    *   Set up your CI pipeline to build these images and push them to your chosen container registry.

2.  **Provision Managed Infrastructure (IaC)**:
    *   Using Terraform/OpenTofu, write scripts to provision:
        *   A managed Kafka cluster.
        *   A managed Qdrant Cloud instance or equivalent vector DB.
        *   A Kubernetes cluster (e.g., GKE, EKS, AKS).
    *   Capture the output credentials and endpoints from your IaC apply.

3.  **Create Kubernetes Resources (Helm)**:
    *   For each worker, create a Helm chart containing:
        *   A `Deployment` to manage the worker's pods. Define resource requests and limits (`cpu`, `memory`) to ensure stable performance.
        *   A `HorizontalPodAutoscaler` (HPA) to automatically scale the number of pods. For Kafka consumers, it's best to scale based on a custom metric like consumer group lag, which can be exposed via a tool like KEDA.
        *   Templates for `ConfigMap` and `Secret` resources that will hold the configuration.
    *   The Helm chart's `values.yaml` file will allow you to easily override settings for different environments (staging, production).

4.  **Deploy to the Cluster (CD)**:
    *   Configure your CD pipeline to:
        1.  Fetch the credentials for your managed services from your secret store.
        2.  Create the Kubernetes `Secret` and `ConfigMap` objects in your cluster.
        3.  Deploy the Helm charts for each worker, passing the correct image tag and configuration values.
    *   Monitor the pod logs (`kubectl logs -f <pod-name>`) to ensure they start up correctly and connect to Kafka and Qdrant.

5.  **Expose the System**:
    *   To allow external applications to write memories or receive recalled narratives, you need an entry point into the cluster.
    *   Deploy an **API Gateway** or **Ingress Controller** (like NGINX Ingress or Traefik).
    *   Create a new, simple service (e.g., an `api-writer` service) that exposes an HTTP endpoint. This service's only job is to receive an API call, validate the payload, and publish the corresponding message to the `anchors-write` or `recall-request` Kafka topic. This keeps your core workers decoupled from the public internet.
