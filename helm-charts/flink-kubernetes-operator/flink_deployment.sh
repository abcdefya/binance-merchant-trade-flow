#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Apache Flink Kubernetes Operator & Job Deployment Script
# Location: helm-charts/flink-kubernetes-operator/flink_deployment.sh
# ==========================================================

# --------------------------
# Config
# --------------------------
NAMESPACE="streaming-processing"
RELEASE_NAME="flink-kubernetes-operator"
FLINK_CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLINK_JOB_FILE="${FLINK_CHART_DIR}/flink-c2c-telegram-job.yaml"

# Cert Manager Config
CM_REPO_NAME="jetstack"
CM_REPO_URL="https://charts.jetstack.io"
CM_VERSION="v1.12.0" # Standard stable version

echo "=========================================="
echo " Apache Flink Operator & Job Deployment"
echo "=========================================="
echo "▶ Namespace       : ${NAMESPACE}"
echo "▶ Flink Chart Dir : ${FLINK_CHART_DIR}"

# --------------------------
# Prerequisites
# --------------------------
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v helm    >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }

# --------------------------
# 1. Create namespace
# --------------------------
if kubectl get ns "${NAMESPACE}" >/dev/null 2>&1; then
  echo "ℹ️  Namespace ${NAMESPACE} already exists"
else
  echo "▶ Creating namespace: ${NAMESPACE}"
  kubectl create ns "${NAMESPACE}"
fi

# --------------------------
# 2. Install Cert-Manager (REQUIRED DEPENDENCY)
# --------------------------
# Flink Operator requires cert-manager for webhook TLS unless explicitly disabled.
echo "▶ Checking for cert-manager..."

if ! kubectl get crd certificates.cert-manager.io >/dev/null 2>&1; then
  echo "▶ cert-manager CRDs not found. Installing cert-manager..."
  
  # Add Jetstack repo
  helm repo add "${CM_REPO_NAME}" "${CM_REPO_URL}" >/dev/null 2>&1 || true
  helm repo update "${CM_REPO_NAME}"

  # Install cert-manager
  helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager \
    --create-namespace \
    --version "${CM_VERSION}" \
    --set installCRDs=true \
    --wait

  echo "✅ cert-manager installed successfully."
else
  echo "ℹ️  cert-manager is already installed."
fi

# --------------------------
# 3. Install / Upgrade Flink Kubernetes Operator
# --------------------------
echo "▶ Installing/Upgrading Flink Kubernetes Operator..."

# We use the local chart directory you have
helm upgrade --install "${RELEASE_NAME}" "${FLINK_CHART_DIR}" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --set webhook.create=true \
  --wait \
  --timeout=600s

echo "▶ Waiting for Flink Operator to be ready..."
kubectl rollout status deployment/flink-kubernetes-operator -n "${NAMESPACE}" --timeout=300s

# --------------------------
# 4. Deploy Flink Job
# --------------------------
if [[ ! -f "${FLINK_JOB_FILE}" ]]; then
  echo "❌ flink-c2c-telegram-job.yaml not found at ${FLINK_JOB_FILE}"
  # We don't exit here to allow the operator installation to remain valid, 
  # but we warn the user.
else
  echo "▶ Deploying Flink job: flink-c2c-telegram-job.yaml"
  # We apply the job definition. The Operator will pick this up and create the cluster.
  kubectl apply -f "${FLINK_JOB_FILE}" -n "${NAMESPACE}"
  
  echo "▶ Job submitted. The Operator is now launching the cluster."
  echo "  Use the commands below to check progress."
fi

# --------------------------
# 5. Final Status
# --------------------------
echo ""
echo "=========================================="
echo "✅ Deployment Finished"
echo "=========================================="
echo "Check Status:"
echo "  kubectl get flinkdeployment -n ${NAMESPACE}"
echo "  kubectl describe flinkdeployment c2c-telegram-job -n ${NAMESPACE}"
echo "  kubectl logs -f deployment/flink-kubernetes-operator -n ${NAMESPACE}"