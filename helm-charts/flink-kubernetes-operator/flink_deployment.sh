#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Apache Flink Kubernetes Operator & Job Deployment Script (PRODUCTION)
#
# This script deploys:
# - Flink Kubernetes Operator into namespace: streaming-processing
# - FlinkApplication job: flink-c2c-telegram-job.yaml
#
# Order of execution:
# 1. Create namespace
# 2. Add Flink Operator Helm repo
# 3. Install/Upgrade Flink Kubernetes Operator
# 4. Apply cert-manager (if needed for webhook TLS)
# 5. Deploy Flink C2C Telegram job
# 6. Verify deployment
# ==========================================================

# --------------------------
# Config
# --------------------------
NAMESPACE="streaming-processing"
RELEASE_NAME="flink-kubernetes-operator"
HELM_REPO_NAME="flink-operator-repo"
HELM_REPO_URL="https://downloads.apache.org/flink/flink-kubernetes-operator-1.12.1/"
HELM_CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_MANAGER_FILE="${HELM_CHART_DIR}/cert-manager.yaml"
FLINK_JOB_FILE="${HELM_CHART_DIR}/flink-c2c-telegram-job.yaml"

echo "=========================================="
echo " Apache Flink Operator & Job Deployment"
echo "=========================================="
echo "▶ Namespace       : ${NAMESPACE}"
echo "▶ Release name    : ${RELEASE_NAME}"
echo "▶ Helm chart dir  : ${HELM_CHART_DIR}"
echo "▶ Job file        : ${FLINK_JOB_FILE}"

# --------------------------
# Prerequisites
# --------------------------
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v helm    >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }

# --------------------------
# 1. Create namespace if needed
# --------------------------
if kubectl get ns "${NAMESPACE}" >/dev/null 2>&1; then
  echo "ℹ️  Namespace ${NAMESPACE} already exists"
else
  echo "▶ Creating namespace: ${NAMESPACE}"
  kubectl create ns "${NAMESPACE}"
fi

# --------------------------
# 2. Add & update Flink Operator Helm repository
# --------------------------
echo "▶ Adding/updating Flink Kubernetes Operator Helm repository"
helm repo add "${HELM_REPO_NAME}" "${HELM_REPO_URL}" >/dev/null 2>&1 || true
helm repo update "${HELM_REPO_NAME}"

# --------------------------
# 3. Install / Upgrade Flink Kubernetes Operator
# --------------------------
echo "▶ Installing/Upgrading Flink Kubernetes Operator"
helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART_DIR}" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --wait \
  --timeout=600s

echo "▶ Waiting for Flink Operator to be ready"
kubectl rollout status deployment/flink-kubernetes-operator -n "${NAMESPACE}" --timeout=300s

# --------------------------
# 4. Apply cert-manager manifest (for webhook TLS, if required)
# --------------------------
if [[ -f "${CERT_MANAGER_FILE}" ]]; then
  echo "▶ Applying cert-manager manifest for webhook TLS"
  kubectl apply -f "${CERT_MANAGER_FILE}"
else
  echo "⚠️  cert-manager.yaml not found – skipping (webhook may use self-signed cert)"
fi

# --------------------------
# 5. Deploy Flink C2C Telegram Job
# --------------------------
if [[ ! -f "${FLINK_JOB_FILE}" ]]; then
  echo "❌ flink-c2c-telegram-job.yaml not found at ${FLINK_JOB_FILE}"
  exit 1
fi

echo "▶ Deploying Flink job: flink-c2c-telegram-job.yaml"
kubectl apply -f "${FLINK_JOB_FILE}" -n "${NAMESPACE}"

echo "▶ Waiting for FlinkApplication to be ready (this may take several minutes)..."
kubectl wait --for=condition=Ready flinkdeployment/c2c-telegram-job -n "${NAMESPACE}" --timeout=600s || {
  echo "⚠️  Flink job not fully ready yet. Check status with:"
  echo "   kubectl get flinkdeployment -n ${NAMESPACE}"
  echo "   kubectl describe flinkdeployment c2c-telegram-job -n ${NAMESPACE}"
}

# --------------------------
# 6. Final verification
# --------------------------
echo ""
echo "▶ Flink Operator pod:"
kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=flink-kubernetes-operator

echo ""
echo "▶ Flink job status:"
kubectl get flinkdeployment -n "${NAMESPACE}"

echo ""
echo "▶ Flink session/job clusters (if any):"
kubectl get flinksessionjob -n "${NAMESPACE}" || true

echo ""
echo "=========================================="
echo " Flink Deployment Complete!"
echo "=========================================="
echo ""
echo " Useful commands:"
echo "   • Watch pods:              kubectl get pods -n ${NAMESPACE} -w"
echo "   • Job details:             kubectl describe flinkdeployment c2c-telegram-job -n ${NAMESPACE}"
echo "   • Job logs (taskmanager):  kubectl logs -n ${NAMESPACE} -l app=c2c-telegram-job -c taskmanager"
echo "   • Port-forward dashboard:  kubectl port-forward svc/c2c-telegram-job-rest 8081:8081 -n ${NAMESPACE}"
echo ""
echo "✅ Your Flink C2C Telegram processing job is now running in namespace ${NAMESPACE}!"