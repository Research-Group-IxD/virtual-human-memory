# Project Onboarding: Configuration

## 5. Configuration (Environment Variables)

The entire system is highly configurable using environment variables. This allows you to switch models, connect to different services, and tune performance without changing any code.

### 5.1 How to Configure

The recommended way to manage configuration is to create a `.env` file in the root of the project directory. The `docker-compose.yml` file is set up to automatically load variables from this file.

**Example `.env` file:**

```sh
# Use a specific multilingual embedding model
EMBEDDING_MODEL=ollama:bge-m3

# Use a local Ollama model for retelling
OLLAMA_MODEL=phi4

# Optionally, use OpenAI's most powerful model (will be preferred over Ollama)
# OPENAI_API_KEY=sk-your-key-here
# OPENAI_MODEL=gpt-4o
```

You can also set these variables directly in your shell before running `docker-compose`.

### 5.2 Global Configuration

These variables are used by multiple services.

- `EMBEDDING_MODEL`
  - **Description**: Specifies the model to use for generating text embeddings. The system is designed to handle different models and their corresponding vector dimensions automatically.
  - **Default**: `ollama:bge-m3`
  - **Options**:
    - `ollama:bge-m3`: (Recommended) State-of-the-art multilingual model.
    - `ollama:nomic-embed-text`: Excellent English-only model.
    - `ollama:mxbai-embed-large`: High-quality retrieval.
    - `deterministic`: A simple, built-in model for testing that requires no external dependencies.
- `OLLAMA_BASE_URL`
  - **Description**: The base URL for the Ollama server, which provides local access to open-source LLMs and embedding models.
  - **Default**: `http://host.docker.internal:11434` (This special DNS name allows the Docker containers to access services running on the host machine).

### 5.3 Service-Specific Configuration

#### Reteller Service

These variables control the narrative generation behavior of the `reteller` worker.

- `OLLAMA_MODEL`
  - **Description**: The name of the model to use from the local Ollama instance for retelling.
  - **Default**: `llama3`
- `OPENAI_API_KEY`
  - **Description**: Your API key for OpenAI. If this is set, the Reteller will prioritize using OpenAI over Ollama.
  - **Default**: Not set.
- `OPENAI_MODEL`
  - **Description**: The specific OpenAI model to use (e.g., `gpt-4o-mini`, `gpt-4o`).
  - **Default**: `gpt-4o-mini`
- `PORTKEY_API_KEY`, `PORTKEY_BASE_URL`, `PORTKEY_CONFIG_ID`, `PORTKEY_MODEL`
  - **Description**: Configuration for using Portkey.ai as an alternative LLM provider. Portkey is tried after OpenAI but before Ollama.
  - **Default**: Not set.

#### Resonance Service

These variables tune the memory recall algorithm.

- `RESONANCE_MAX_BEATS`
  - **Description**: The maximum number of memory "beats" to return for a given query.
  - **Default**: `3`
- `RESONANCE_DIVERSITY_THRESHOLD`
  - **Description**: Controls how different memories must be to be included in the results. A higher value (e.g., `0.9`) means results must be very dissimilar; a lower value (e.g., `0.7`) allows for more closely related memories.
  - **Default**: `0.85`

### 5.4 Infrastructure Configuration

These variables tell the services how to connect to Kafka and Qdrant. You generally won't need to change these unless you have a custom network setup.

- `KAFKA_BOOTSTRAP`
  - **Description**: The address of the Kafka broker.
  - **Default**: `kafka:9092` (within the Docker network)
- `QDRANT_URL`
  - **Description**: The URL of the Qdrant database.
  - **Default**: `http://qdrant:6333` (within the Docker network)
- `QDRANT_COLLECTION`
  - **Description**: The name of the collection within Qdrant to use for storing memories.
  - **Default**: `anchors`

### 5.5 Kubernetes Configuration

When deploying to Kubernetes, the `.env` file approach is replaced by native Kubernetes objects for managing configuration:

- **ConfigMaps**: Non-sensitive configuration, such as `EMBEDDING_MODEL`, `OLLAMA_MODEL`, `KAFKA_BOOTSTRAP`, `QDRANT_URL`, etc., should be stored in a ConfigMap. The values from the ConfigMap can then be injected into the worker pods as environment variables.

- **Secrets**: All sensitive information, especially `OPENAI_API_KEY` and any credentials for managed Kafka or Qdrant services, must be stored in a Kubernetes Secret. Like ConfigMaps, these are mounted into the pods as environment variables, but they are stored more securely within the cluster.

Using these objects allows you to separate your configuration from your application code, which is a core principle of cloud-native development.
