# Project Onboarding: Tooling & Scripts

## 8. Scripts

The `k8s/scripts/` directory contains helper shell scripts for managing the local Minikube environment.

*   `setup-cluster.sh`
    *   **Purpose**: Boots Minikube with the correct resources, enables addons, creates the `vhm` namespace, and configures your kubectl context.
*   `deploy.sh`
    *   **Purpose**: Applies the infrastructure, config, and worker manifests in one go.
*   `teardown-cluster.sh`
    *   **Purpose**: Deletes the `vhm` namespace and stops the Minikube cluster.

For Kafka topic initialization we now rely on the declarative `k8s/infrastructure/kafka-topic-job.yaml`, so no manual shell script is required.

## 9. Tools

The `tools/` directory contains utility scripts and demo applications for testing and demonstrating the VHM system.

### Available Tools

*   **`tools/demo/indexer_demo.py`** (Streamlit)
    *   **Purpose**: Interactive visual interface for testing and exploring the Indexer service. Provides real-time visualization of the complete memory processing flow, from anchor creation through indexing to Qdrant storage.
    *   **Usage**: `uv run streamlit run tools/demo/indexer_demo.py`
    *   **See**: [tools/demo/README.md](../tools/demo/README.md) for detailed documentation

*   **`tools/demo_three_retells.py`**
    *   **Purpose**: End-to-end demonstration script that tests the complete pipeline: seeds three memory anchors with different timestamps, sends a recall request, waits for resonance beats, and waits for retelling. Logs the complete flow to JSON.
    *   **Usage**: `uv run python tools/demo_three_retells.py`
    *   **See**: [tools/README.md](../tools/README.md) for more information

### Operational Tools

For operational diagnostics and troubleshooting, see the [Minikube Worker Recovery Guide](../minikube-worker-recovery.md), which documents the diagnostic steps and commands we use today.

Legacy Docker Compose tooling has been retired in favour of Kubernetes-native workflows. The old `convai_narrative_memory_poc` helpers are no longer part of this codebase.
