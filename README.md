# Virtual Human Memory (VHM)

[![CI](https://github.com/Research-Group-IxD/virtual-human-memory/actions/workflows/ci.yaml/badge.svg)](https://github.com/Research-Group-IxD/virtual-human-memory/actions/workflows/ci.yaml)

This repository is the central monorepo for the Virtual Human Memory (VHM) project, a multi-agent, psychologically-grounded, long-term memory system for virtual humans. Our goal is to enable emergent identity through the stories virtual humans tell over time.

**[➡️ View the full Project Page here](https://research-group-ixd.github.io/virtual-human-memory/)**

## Architecture

The VHM system is built on a distributed, microservices architecture orchestrated by Kubernetes. This monorepo contains all the code for the following services:

- `workers/indexer`: Ingests and indexes new memories.
- `workers/resonance`: Calculates the emotional and contextual significance of memories.
- `workers/reteller`: Weaves memories into coherent, dynamic narratives.
- `common/utils`: Shared utilities and data models for all services.
- `k8s/`: All Kubernetes manifests for deploying the system.

### Resonance Worker (Production-Ready Highlights)
- Typed configuration surface backed by Pydantic ensures consistent defaults across dev, staging, and prod.
- Structured logging + retry-aware Qdrant calls keep recall behaviour transparent under load.
- Deterministic request/response models now power richer unit tests (`uv run pytest -k resonance`) for CI confidence.

## Local Development & Deployment

This project uses `uv` for Python environment management and Minikube for local Kubernetes deployment.

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Minikube](https://minikube.sigs.k8s.io/docs/start/)
- [uv](https://github.com/astral-sh/uv) (Python package manager)

### 2. Running Locally with Minikube

The entire deployment process has been streamlined. For a complete guide on the fixes that led to our stable system, please see the **[Minikube Worker Recovery Guide](./minikube-worker-recovery.md)**.

The quick-start steps are:

```bash
# 1. Start minikube and configure the local environment
./k8s/scripts/setup-cluster.sh

# 2. Point your Docker client to Minikube's Docker daemon
eval "$(minikube docker-env)"

# 3. Build the worker images
# (See the recovery guide for the full docker build commands)
docker build -t vhm-indexer:0.1.3 ...
docker build -t vhm-resonance:0.1.3 ...
docker build -t vhm-reteller:0.1.3 ...

# 4. Deploy the full application to Minikube
kubectl apply -f k8s/infrastructure/
kubectl apply -f k8s/config/
kubectl apply -f k8s/workers/

# 5. When you are finished, unset the Docker environment variable
eval "$(minikube docker-env -u)"
```

## Production Deployment Workflow (with GitHub Container Registry)

Our Kubernetes manifests are configured to pull images from the GitHub Container Registry (`ghcr.io`).

### 1. Login to the Registry

```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME
```

### 2. Build, Tag, and Push a Worker Image

To build and push an image (e.g., the indexer), follow this pattern:

```bash
# Define variables
export ORG="Research-Group-IxD"
export IMAGE_NAME="vhm-indexer"
export TAG="0.1.3"

# 1. Build the image using the shared Dockerfile
docker build -t "${IMAGE_NAME}:${TAG}" \
  -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_indexer.main .

# 2. Tag the image for the registry
docker tag "${IMAGE_NAME}:${TAG}" "ghcr.io/${ORG}/${IMAGE_NAME}:${TAG}"

# 3. Push the image to the registry
docker push "ghcr.io/${ORG}/${IMAGE_NAME}:${TAG}"
```

### 3. Deploy to Kubernetes

Once your images are pushed, you can deploy them to any Kubernetes cluster.

```bash
# This will pull the newly pushed images from ghcr.io
kubectl apply -k k8s/
```

## CI/CD Workflows

We use GitHub Actions to keep the dojo disciplined:

- **CI (`ci.yaml`)** runs on every push and pull request. It installs dependencies with `uv`, runs the placeholder Pytest suite, and builds each worker image using `docker/worker.Dockerfile`. These smoke tests will fail once you replace the placeholders with real assertions.
- **Publish (`publish.yaml`)** can be triggered manually from the Actions tab. Choose the worker and tag, and the workflow will build the image and push it to `ghcr.io/research-group-ixd` using the `GITHUB_TOKEN`.

To run the same checks locally:

```bash
# Install dependencies and run the placeholder tests
uv sync
uv run pytest

# Build a worker image the same way CI does
docker build -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_indexer.main \
  -t vhm-indexer:test .
```

## Testing

This project includes a comprehensive test suite for the indexer worker, with unit and integration tests. Tests can be run using pytest:

```bash
# Run all tests
uv run pytest

# Run indexer tests specifically
uv run pytest workers/indexer/tests/ -v
```

For detailed information about the test structure, how to navigate tests, and best practices, see the [Test Guide](./TEST_GUIDE.md).

## Tools & Demos

This repository includes several tools and demo applications for testing and demonstrating the system:

### Interactive Demo (Streamlit)

The **Indexer Service Demo** provides a visual interface to test and explore the memory system:

```bash
uv run streamlit run tools/demo/indexer_demo.py
```

Features:
- Create and send memory anchors
- Visualize the complete processing flow (Kafka → Indexer → Qdrant)
- Inspect stored anchors and their embeddings
- Simulate time passing and test recall with temporal decay

See [tools/demo/README.md](./tools/demo/README.md) for detailed usage instructions.

### End-to-End Demo Script

The **Three Retells Demo** tests the complete pipeline from anchor creation to narrative generation:

```bash
uv run python tools/demo_three_retells.py
```

This script:
1. Seeds three memory anchors with different timestamps
2. Sends a recall request
3. Waits for resonance beats
4. Waits for retelling
5. Logs everything to a JSON file

See [tools/README.md](./tools/README.md) for more information about available tools.

For detailed information about the project's architecture, research goals, and results, please see our [full project page](https://research-group-ixd.github.io/virtual-human-memory/).
