# Project Onboarding: Development & Deployment

## 6. Local Development Guide

This guide covers how to get the full system running locally for development and testing using the new monorepo structure.

### 6.1 Prerequisites

1.  **Docker Desktop**: Required for building container images.
2.  **Minikube & kubectl**: To run the Kubernetes cluster locally.
3.  **`uv`**: Python dependency manager. Install with `pip install uv`.
4.  **Optional – Ollama**: For local embedding/LLM experimentation. Download from [ollama.com](https://ollama.com).

### 6.2 Full System Quick Start (Minikube)

This is the recommended path for running Kafka, Qdrant, and all workers locally.

```bash
# 1. Start and configure the Minikube cluster
./k8s/scripts/setup-cluster.sh

# 2. Build worker images inside Minikube's Docker daemon
eval "$(minikube docker-env)"
docker build -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_indexer.main \
  -t vhm-indexer:dev .

docker build -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_resonance.main \
  -t vhm-resonance:dev .

docker build -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_reteller.main \
  -t vhm-reteller:dev .

eval "$(minikube docker-env -u)"

# 3. Deploy infrastructure + workers
kubectl apply -f k8s/infrastructure/
kubectl apply -f k8s/config/
kubectl apply -f k8s/workers/

# 4. Verify everything is running
kubectl get pods -n vhm
```

For a deeper walkthrough of the Minikube setup, see the updated [Minikube Worker Recovery Guide](../minikube-worker-recovery.md).

### 6.3 Lightweight Testing (Python only)

If you want to quickly check code without spinning up the entire cluster:

```bash
uv sync
uv run pytest  # placeholder smoke tests live in common/utils/tests and each worker package
```

You can also run individual modules directly, for example:

```bash
uv run python -m workers.vhm_indexer.main --help
```

This bypasses Kafka/Qdrant orchestration but lets you smoke-test imports and CLI behaviour.

## 7. Deployment Guide (Migrating to Kubernetes)

The rest of this section still applies conceptually, but replace references to separate repositories with the new monorepo layout. The key ideas remain the same: managed services for stateful components, IaC for reproducibility, Helm for packaging, and CI/CD automation now backed by our GitHub Actions workflows.
