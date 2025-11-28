#!/bin/bash
# Deployment script for VHM Kubernetes manifests

set -e

echo "🚀 Deploying VHM to Kubernetes..."

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed. Please install it first."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace vhm &> /dev/null; then
    echo "📁 Creating vhm namespace..."
    kubectl create namespace vhm
fi

# Set context to vhm namespace
kubectl config set-context --current --namespace=vhm

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
K8S_DIR="$(dirname "$SCRIPT_DIR")"

echo "📦 Deploying infrastructure..."
kubectl apply -f "$K8S_DIR/infrastructure/"

echo "⏳ Waiting for infrastructure to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/kafka -n vhm || true
kubectl wait --for=condition=available --timeout=300s deployment/qdrant -n vhm || true

echo "🔧 Deploying configuration..."
kubectl apply -f "$K8S_DIR/config/"

echo "👷 Deploying workers..."
kubectl apply -f "$K8S_DIR/workers/"

echo "✅ Deployment complete!"
echo ""
echo "To check status:"
echo "  kubectl get pods -n vhm"
echo "  kubectl get services -n vhm"
echo ""
echo "To view logs:"
echo "  kubectl logs -n vhm deployment/indexer"
echo "  kubectl logs -n vhm deployment/resonance"
echo "  kubectl logs -n vhm deployment/reteller"

