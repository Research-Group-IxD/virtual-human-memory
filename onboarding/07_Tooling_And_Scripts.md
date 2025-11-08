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

Legacy Docker Compose tooling has been retired in favour of Kubernetes-native workflows. The most up-to-date operational guide is the [Minikube Worker Recovery Guide](../minikube-worker-recovery.md), which documents the diagnostic steps and commands we use today. Future visualization or demo tools will live directly inside this monorepo (for example under a `tools/` directory or in dedicated Notebooks), but the old `convai_narrative_memory_poc` helpers are no longer part of this codebase.
