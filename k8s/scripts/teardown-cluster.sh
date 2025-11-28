#!/bin/bash
# Teardown script for local minikube cluster

set -e

echo "🗑️  Tearing down local Kubernetes cluster..."

# Check if minikube is installed
if ! command -v minikube &> /dev/null; then
    echo "❌ minikube is not installed."
    exit 1
fi

# Stop minikube cluster
echo "🛑 Stopping minikube cluster..."
minikube stop

# Delete minikube cluster (optional - uncomment if you want to completely remove it)
# echo "🗑️  Deleting minikube cluster..."
# minikube delete

echo "✅ Cluster teardown complete!"

