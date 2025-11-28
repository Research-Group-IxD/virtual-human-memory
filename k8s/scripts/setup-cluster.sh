#!/bin/bash
# Setup script for local minikube cluster

set -e

echo "🚀 Setting up local Kubernetes cluster with minikube..."

# Check if minikube is installed
if ! command -v minikube &> /dev/null; then
    echo "❌ minikube is not installed. Please install it first:"
    echo "   brew install minikube  # macOS"
    echo "   or visit: https://minikube.sigs.k8s.io/docs/start/"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed. Please install it first:"
    echo "   brew install kubectl  # macOS"
    exit 1
fi

# Start minikube cluster
echo "📦 Starting minikube cluster..."
minikube start --driver=docker --memory=4096 --cpus=2

# Enable required addons
echo "🔧 Enabling minikube addons..."
minikube addons enable ingress
minikube addons enable metrics-server

# Create namespace
echo "📁 Creating vhm namespace..."
kubectl create namespace vhm --dry-run=client -o yaml | kubectl apply -f -

# Set context to vhm namespace
kubectl config set-context --current --namespace=vhm

echo "✅ Cluster setup complete!"
echo ""
echo "To verify the cluster is running:"
echo "  kubectl get nodes"
echo ""
echo "To view cluster status:"
echo "  minikube status"
echo ""
echo "To access the cluster dashboard:"
echo "  minikube dashboard"

