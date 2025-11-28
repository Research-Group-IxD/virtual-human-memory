# vhm-k8s-manifests

VHM Kubernetes: Contains all Kubernetes manifests and Helm charts for deploying the Virtual Human Memory system.

## Overview

This directory contains Kubernetes manifests for deploying the VHM microservices architecture locally using minikube. The setup includes:

- **Workers**: indexer, resonance, reteller
- **Infrastructure**: Kafka (message broker), Qdrant (vector database)
- **Configuration**: ConfigMaps and Secrets for environment variables

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                    │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Indexer    │  │  Resonance   │  │   Reteller   │    │
│  │   Worker     │  │   Worker     │  │   Worker     │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │            │
│         └─────────────────┼─────────────────┘            │
│                           │                              │
│         ┌─────────────────┴─────────────────┐            │
│         │            Kafka Service          │            │
│         └─────────────────┬─────────────────┘            │
│                           │                              │
│         ┌─────────────────┴─────────────────┐            │
│         │          Qdrant Service           │            │
│         └───────────────────────────────────┘            │
└─────────────────────────────────────────────────────── ──┘
```

## Prerequisites

Before you begin, ensure you have the following installed:

- **minikube**: Local Kubernetes cluster
  ```bash
  brew install minikube  # macOS
  # or visit: https://minikube.sigs.k8s.io/docs/start/
  ```

- **kubectl**: Kubernetes command-line tool
  ```bash
  brew install kubectl  # macOS
  # or visit: https://kubernetes.io/docs/tasks/tools/
  ```

- **Docker**: Required by minikube (Docker driver)
  ```bash
  # Install Docker Desktop or Docker Engine
  ```

## Quick Start

### 1. Setup Local Cluster

Run the setup script to create and configure your local minikube cluster:

```bash
./scripts/setup-cluster.sh
```

This will:
- Start a minikube cluster with 4GB RAM and 2 CPUs
- Enable ingress and metrics-server addons
- Create the `vhm` namespace
- Set the current context to the `vhm` namespace

### 2. Deploy Everything (Quick Method)

Use the deployment script to deploy everything at once:

```bash
# First, configure secrets if needed
kubectl create secret generic vhm-secrets \
  --from-literal=PORTKEY_API_KEY=your-api-key-here \
  --namespace=vhm \
  --dry-run=client -o yaml | kubectl apply -f -

# Then deploy everything
./scripts/deploy.sh
```

### 3. Deploy Manually (Step by Step)

Alternatively, deploy components manually:

#### Deploy Infrastructure

Deploy Kafka and Qdrant first (they are dependencies for the workers):

```bash
# Apply infrastructure manifests
kubectl apply -f infrastructure/kafka-deployment.yaml
kubectl apply -f infrastructure/kafka-service.yaml
kubectl apply -f infrastructure/qdrant-deployment.yaml
kubectl apply -f infrastructure/qdrant-service.yaml

# Wait for infrastructure to be ready
kubectl wait --for=condition=available --timeout=300s deployment/kafka -n vhm
kubectl wait --for=condition=available --timeout=300s deployment/qdrant -n vhm
```

#### Configure Secrets

Create the secrets (update with your actual values):

```bash
# Create secret for Portkey API key (if using Portkey embeddings)
kubectl create secret generic vhm-secrets \
  --from-literal=PORTKEY_API_KEY=your-api-key-here \
  --namespace=vhm \
  --dry-run=client -o yaml | kubectl apply -f -

# Or apply the template and edit manually
kubectl apply -f config/secrets.yaml
```

#### Deploy Configuration

Apply the ConfigMap:

```bash
kubectl apply -f config/configmap.yaml
```

#### Deploy Workers

Deploy all three workers:

```bash
# Deploy indexer
kubectl apply -f workers/indexer-deployment.yaml
kubectl apply -f workers/indexer-service.yaml

# Deploy resonance
kubectl apply -f workers/resonance-deployment.yaml
kubectl apply -f workers/resonance-service.yaml

# Deploy reteller
kubectl apply -f workers/reteller-deployment.yaml
kubectl apply -f workers/reteller-service.yaml
```

Or deploy everything at once:

```bash
kubectl apply -f .
```

### 4. Verify Deployment

Check that all pods are running:

```bash
kubectl get pods -n vhm
kubectl get services -n vhm
kubectl get deployments -n vhm
```

## Directory Structure

```
k8s/
├── config/
│   ├── configmap.yaml      # Shared configuration
│   └── secrets.yaml         # Secrets template
├── infrastructure/
│   ├── kafka-deployment.yaml
│   ├── kafka-service.yaml
│   ├── qdrant-deployment.yaml
│   └── qdrant-service.yaml
├── workers/
│   ├── indexer-deployment.yaml
│   ├── indexer-service.yaml
│   ├── resonance-deployment.yaml
│   ├── resonance-service.yaml
│   ├── reteller-deployment.yaml
│   └── reteller-service.yaml
├── scripts/
│   ├── setup-cluster.sh    # Setup local cluster
│   ├── deploy.sh           # Deploy all manifests
│   └── teardown-cluster.sh # Teardown cluster
└── README.md
```

## Configuration

### Environment Variables

All workers use the same configuration from the ConfigMap (`vhm-config`):

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker address (default: `kafka-service:9092`)
- `QDRANT_URL`: Qdrant server URL (default: `http://qdrant-service:6333`)
- `QDRANT_COLLECTION`: Qdrant collection name (default: `anchors`)
- `EMBEDDING_MODEL`: Embedding model to use (default: `deterministic`)
- `OLLAMA_BASE_URL`: Ollama server URL (if using Ollama)
- `PORTKEY_BASE_URL`: Portkey API base URL
- `PORTKEY_API_KEY`: Portkey API key (from Secrets)

### Updating Configuration

To update configuration:

```bash
# Edit the ConfigMap
kubectl edit configmap vhm-config -n vhm

# Or update the YAML and reapply
kubectl apply -f config/configmap.yaml

# Restart pods to pick up new configuration
kubectl rollout restart deployment/indexer -n vhm
kubectl rollout restart deployment/resonance -n vhm
kubectl rollout restart deployment/reteller -n vhm
```

## Troubleshooting

### Pods Not Starting

Check pod status and logs:

```bash
# Check pod status
kubectl get pods -n vhm

# View logs for a specific pod
kubectl logs -n vhm <pod-name>

# Describe pod for events
kubectl describe pod -n vhm <pod-name>
```

### Services Not Accessible

Verify services are running:

```bash
# Check services
kubectl get svc -n vhm

# Test service connectivity from within cluster
kubectl run -it --rm debug --image=busybox --restart=Never -n vhm -- wget -O- http://qdrant-service:6333/health
```

### Kafka Connection Issues

Ensure Kafka is ready before deploying workers:

```bash
# Check Kafka pod logs
kubectl logs -n vhm deployment/kafka

# Test Kafka connectivity
kubectl run -it --rm kafka-test --image=apache/kafka:3.7.0 --restart=Never -n vhm -- \
  bin/kafka-topics.sh --bootstrap-server kafka-service:9092 --list
```

### Qdrant Connection Issues

Check Qdrant health:

```bash
# Check Qdrant pod logs
kubectl logs -n vhm deployment/qdrant

# Test Qdrant health endpoint
kubectl run -it --rm qdrant-test --image=curlimages/curl --restart=Never -n vhm -- \
  curl http://qdrant-service:6333/health
```

### Resource Issues

If pods are being evicted or not starting due to resource constraints:

```bash
# Check node resources
kubectl top nodes

# Check pod resources
kubectl top pods -n vhm

# Increase minikube resources
minikube stop
minikube start --memory=8192 --cpus=4
```

### Accessing Services from Host

To access services from your local machine:

```bash
# Port forward to access a service
kubectl port-forward -n vhm service/qdrant-service 6333:6333

# Then access at http://localhost:6333
```

## Teardown

To stop and remove the cluster:

```bash
./scripts/teardown-cluster.sh
```

To delete all resources but keep the cluster:

```bash
kubectl delete all --all -n vhm
kubectl delete configmap,secret --all -n vhm
```

## Next Steps

1. **Update Worker Images**: Replace the placeholder images in worker deployments with your actual container images
2. **Add Health Checks**: Uncomment and configure health check probes in worker deployments
3. **Configure Resource Limits**: Adjust resource requests/limits based on your workload
4. **Add Monitoring**: Set up Prometheus and Grafana for monitoring
5. **Add Ingress**: Configure ingress for external access to services
6. **Add Persistent Storage**: Configure persistent volumes for Kafka and Qdrant data

## Additional Resources

- [minikube Documentation](https://minikube.sigs.k8s.io/docs/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
