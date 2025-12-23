#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# ELK Stack Deployment Script
# Location: ./helm-charts/elk/elk_deployment.sh
# ==========================================================

# --------------------------
# Config
# --------------------------
NAMESPACE="logging"
ELASTIC_VERSION="8.5.1"

# 1. Get the directory where this script is located (.../helm-charts/elk)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 2. Go UP one level to find the 'helm-charts' root (.../helm-charts)
CHARTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INGRESS_DIR="${CHARTS_DIR}/ingress"

echo "▶ Namespace      : ${NAMESPACE}"
echo "▶ Elastic Ver    : ${ELASTIC_VERSION}"
echo "▶ Config Dir     : ${SCRIPT_DIR}"

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
# 2. Add/Update Helm Repo
# --------------------------
echo "▶ Updating Elastic Helm repo..."
helm repo add elastic https://helm.elastic.co >/dev/null 2>&1 || true
helm repo update

# --------------------------
# 3. Deploy Components
# --------------------------

# Function to deploy a chart to avoid repeating code
deploy_chart() {
    local APP_NAME=$1
    local CHART_NAME=$2
    local VALUES_FILE="${SCRIPT_DIR}/values-${APP_NAME}.yaml"

    if [[ -f "${VALUES_FILE}" ]]; then
        echo "▶ Installing ${APP_NAME}..."
        helm upgrade --install "${APP_NAME}" "${CHART_NAME}" \
            -f "${VALUES_FILE}" \
            --version "${ELASTIC_VERSION}" \
            -n "${NAMESPACE}"
    else
        echo "⚠️  ${VALUES_FILE} not found. Skipping ${APP_NAME}."
    fi
}

deploy_chart "elasticsearch" "elastic/elasticsearch"
deploy_chart "logstash"      "elastic/logstash"
deploy_chart "filebeat"      "elastic/filebeat"
deploy_chart "kibana"        "elastic/kibana"

# --------------------------
# 4. Apply Ingress (Specific files only)
# --------------------------
echo "▶ Applying Logging Ingress..."

# We look for specific files to avoid applying the whole folder and getting errors for missing namespaces
INGRESS_FILES=("elasticsearch-ingress.yaml" "kibana-ingress.yaml")

for FILE in "${INGRESS_FILES[@]}"; do
    FULL_PATH="${INGRESS_DIR}/${FILE}"
    if [[ -f "${FULL_PATH}" ]]; then
        echo "  - Applying ${FILE}"
        kubectl apply -f "${FULL_PATH}"
    else
        echo "  ⚠️  File not found: ${FILE} (checked in ${INGRESS_DIR})"
    fi
done

# --------------------------
# 5. Success Message
# --------------------------
echo ""
echo "✅ ELK deployment finished."
echo "ℹ️  Get Elastic Password: kubectl get secrets -n ${NAMESPACE} elasticsearch-master-credentials -ojsonpath='{.data.password}' | base64 -d"
echo "ℹ️  Get Kibana Token:     kubectl get secrets -n ${NAMESPACE} kibana-kibana-es-token -ojsonpath='{.data.token}' | base64 -d"