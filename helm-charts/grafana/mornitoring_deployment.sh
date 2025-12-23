#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Monitoring Stack Bootstrap Script
# Location: ./helm-charts/grafana/mornitoring_deployment.sh
# ==========================================================

# --------------------------
# Config
# --------------------------
PROJECT_ID="binance-c2c-deployment"
NAMESPACE="monitoring"

# 1. Get the directory where this script is located (.../helm-charts/grafana)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 2. Go UP one level to find the 'helm-charts' root (.../helm-charts)
CHARTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 3. Define the paths relative to that root
INGRESS_DIR="${CHARTS_DIR}/ingress"
CHART_CRDS="${CHARTS_DIR}/prometheus-operator-crds"
CHART_PROMETHEUS="${CHARTS_DIR}/prometheus"
CHART_GRAFANA="${CHARTS_DIR}/grafana"

echo "▶ Project        : ${PROJECT_ID}"
echo "▶ Namespace      : ${NAMESPACE}"
echo "▶ Charts Root    : ${CHARTS_DIR}"
echo "▶ Ingress Dir    : ${INGRESS_DIR}"

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
# 2. Install Prometheus CRDs
# --------------------------
echo "▶ Installing / Upgrading Prometheus CRDs"
if [[ ! -d "${CHART_CRDS}" ]]; then
    echo "❌ Chart directory not found: ${CHART_CRDS}"
    echo "   (Checked path: ${CHART_CRDS})"
    exit 1
fi

helm upgrade --install prometheus-crds "${CHART_CRDS}" -n "${NAMESPACE}"

# --------------------------
# 3. Install Prometheus
# --------------------------
echo "▶ Installing / Upgrading Prometheus"
if [[ ! -d "${CHART_PROMETHEUS}" ]]; then
    echo "❌ Chart directory not found: ${CHART_PROMETHEUS}"
    exit 1
fi

helm upgrade --install prometheus "${CHART_PROMETHEUS}" -n "${NAMESPACE}"

# --------------------------
# 4. Install Grafana
# --------------------------
echo "▶ Installing / Upgrading Grafana"
# Since the script is IN the grafana folder, SCRIPT_DIR is essentially CHART_GRAFANA, 
# but we stick to the CHARTS_DIR logic for consistency.
helm upgrade --install grafana "${CHART_GRAFANA}" -n "${NAMESPACE}"

# --------------------------
# 5. Apply Ingress resources
# --------------------------
if [[ -d "${INGRESS_DIR}" ]]; then
  echo "▶ Applying Ingress manifests from ${INGRESS_DIR}"
  kubectl apply -f "${INGRESS_DIR}" -n "${NAMESPACE}"
else
  echo "⚠️  Ingress directory not found: ${INGRESS_DIR} (skip)"
fi

# --------------------------
# 6. Show Status
# --------------------------
echo "▶ Current Services:"
kubectl get svc -n "${NAMESPACE}"

echo "✅ Monitoring stack deployment completed successfully"