#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# MinIO Deployment Script
# Location: ./helm-charts/minio-operator/minio-deployment.sh
# ==========================================================

# --------------------------
# Config
# --------------------------
NAMESPACE="storage"

# 1. Get the directory where this script is located (.../helm-charts/minio-operator)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 2. Go UP one level to find the 'helm-charts' root (.../helm-charts)
CHARTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 3. Define Chart Paths
# Since this script is INSIDE the minio-operator folder, the chart path is SCRIPT_DIR
CHART_OPERATOR="${SCRIPT_DIR}"
CHART_TENANT="${CHARTS_DIR}/minio-tenant"
TENANT_VALUES="${CHART_TENANT}/override-values.yaml"
INGRESS_DIR="${CHARTS_DIR}/ingress"

echo "======================================"
echo "🚀 Setup MinIO Operator, Tenant & Ingress"
echo "======================================"
echo "▶ Namespace      : ${NAMESPACE}"
echo "▶ Charts Root    : ${CHARTS_DIR}"
echo "▶ Operator Path  : ${CHART_OPERATOR}"

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
# 2. Deploy MinIO Operator
# --------------------------
echo "▶ Installing / Upgrading MinIO Operator..."
# We check if Chart.yaml exists to ensure we are in the right place
if [[ -f "${CHART_OPERATOR}/Chart.yaml" ]]; then
    helm upgrade --install minio-operator "${CHART_OPERATOR}" \
        -n "${NAMESPACE}"
else
    echo "❌ Chart.yaml not found in ${CHART_OPERATOR}"
    echo "   Ensure this script is located inside the minio-operator chart folder."
    exit 1
fi

# --------------------------
# 3. Deploy MinIO Tenant
# --------------------------
echo "▶ Installing / Upgrading MinIO Tenant..."
if [[ -d "${CHART_TENANT}" ]] && [[ -f "${TENANT_VALUES}" ]]; then
    helm upgrade --install minio-tenant "${CHART_TENANT}" \
        -f "${TENANT_VALUES}" \
        -n "${NAMESPACE}"
else
    echo "❌ Chart or Values file not found for Tenant."
    echo "   Checked Chart:  ${CHART_TENANT}"
    echo "   Checked Values: ${TENANT_VALUES}"
    exit 1
fi

# --------------------------
# 4. Wait for Tenant Pods
# --------------------------
echo "▶ Waiting for MinIO Tenant pods to be READY..."
kubectl wait --for=condition=Ready pod \
  -l v1.min.io/tenant=minio-tenant \
  -n "${NAMESPACE}" \
  --timeout=300s || echo "⚠️  Wait timed out, but continuing..."

# --------------------------
# 5. Apply Ingress
# --------------------------
echo "▶ Applying Ingress..."
INGRESS_FILE="${INGRESS_DIR}/minio-ingress.yaml"

if [[ -f "${INGRESS_FILE}" ]]; then
    kubectl apply -f "${INGRESS_FILE}"
else
    echo "⚠️  Ingress file not found: ${INGRESS_FILE}"
fi

# --------------------------
# 6. Status
# --------------------------
echo "======================================"
echo "✅ MinIO setup completed"
echo "======================================"
kubectl get pods -n "${NAMESPACE}"