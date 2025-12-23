#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Airflow environment bootstrap script (PRODUCTION)
# - Create GCP SA key (key.json)
# - Create Kubernetes Secrets
# - Install / Upgrade Apache Airflow via Helm
# - Apply Ingress manifests
# - DOES NOT manage GCP IAM permissions
# ==========================================================

# --------------------------
# Config
# --------------------------
PROJECT_ID="binance-c2c-deployment"
NAMESPACE="batch-processing"
RELEASE_NAME="airflow"
HELM_REPO_NAME="apache-airflow"
HELM_REPO_URL="https://airflow.apache.org"
HELM_CHART="apache-airflow/airflow"
GCP_SA_EMAIL="airflow-gcs-logger@binance-c2c-deployment.iam.gserviceaccount.com"

AIRFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
HELM_CHARTS_DIR="$(cd "${AIRFLOW_DIR}/.." && pwd)"

KEY_FILE="${AIRFLOW_DIR}/key.json"
OVERRIDE_FILE="${AIRFLOW_DIR}/override.yaml"
INGRESS_DIR="${HELM_CHARTS_DIR}/ingress"

echo "▶ Project        : ${PROJECT_ID}"
echo "▶ Namespace      : ${NAMESPACE}"
echo "▶ Release        : ${RELEASE_NAME}"
echo "▶ ServiceAccount : ${GCP_SA_EMAIL}"
echo "▶ Airflow dir    : ${AIRFLOW_DIR}"
echo "▶ Override file  : ${OVERRIDE_FILE}"
echo "▶ Ingress dir    : ${INGRESS_DIR}"

# --------------------------
# Prerequisites
# --------------------------
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v gcloud  >/dev/null 2>&1 || { echo "❌ gcloud not found"; exit 1; }
command -v helm    >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }

gcloud config set project "${PROJECT_ID}" >/dev/null

# --------------------------
# 1. Create SA key (ONLY if not exists)
# --------------------------
if [[ -f "${KEY_FILE}" ]]; then
  echo "ℹ️  key.json already exists, skip creating new key"
else
  echo "▶ Creating GCP service account key: key.json"
  gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account "${GCP_SA_EMAIL}"
fi

# --------------------------
# 2. Create namespace if needed
# --------------------------
if kubectl get ns "${NAMESPACE}" >/dev/null 2>&1; then
  echo "ℹ️  Namespace ${NAMESPACE} already exists"
else
  echo "▶ Creating namespace: ${NAMESPACE}"
  kubectl create ns "${NAMESPACE}"
fi

# --------------------------
# 3. Airflow external API secret (example)
# --------------------------
echo "▶ Creating airflow-producer-secret"

kubectl create secret generic airflow-producer-secret \
  --from-literal=API_KEY=your_api_key \
  --from-literal=API_SECRET=your_api_secret \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

# --------------------------
# 4. MinIO / S3 credentials
# --------------------------
echo "▶ Creating minio-secret"

kubectl create secret generic minio-secret \
  --from-literal=access_key=minio \
  --from-literal=secret_key=minio123 \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

# --------------------------
# 5. GCS logger key secret
# --------------------------
echo "▶ Creating gcs-logger-key from key.json"

kubectl create secret generic gcs-logger-key \
  --from-file=key.json="${KEY_FILE}" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

# --------------------------
# 6. Add & update Helm repo
# --------------------------
echo "▶ Adding Helm repo: ${HELM_REPO_NAME}"

helm repo add "${HELM_REPO_NAME}" "${HELM_REPO_URL}" >/dev/null 2>&1 || true
helm repo update

# --------------------------
# 7. Install / Upgrade Airflow
# --------------------------
echo "▶ Installing / Upgrading Apache Airflow via Helm"

if [[ ! -f "${OVERRIDE_FILE}" ]]; then
  echo "❌ override.yaml not found at ${OVERRIDE_FILE}"
  exit 1
fi

helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART}" \
  -n "${NAMESPACE}" \
  -f "${OVERRIDE_FILE}" \
  --create-namespace

# --------------------------
# 8. Wait for core Airflow components
# --------------------------
echo "▶ Waiting for Airflow core components to be Ready"

kubectl rollout status deployment/airflow-webserver -n "${NAMESPACE}"
kubectl rollout status deployment/airflow-scheduler -n "${NAMESPACE}"
kubectl rollout status deployment/airflow-statsd -n "${NAMESPACE}" || true
kubectl rollout status statefulset/airflow-triggerer -n "${NAMESPACE}"

# --------------------------
# 9. Apply Ingress resources
# --------------------------
if [[ -d "${INGRESS_DIR}" ]]; then
  echo "▶ Applying Ingress manifests from ${INGRESS_DIR}"
  kubectl apply -f "${INGRESS_DIR}"
else
  echo "⚠️  Ingress directory not found: ${INGRESS_DIR} (skip)"
fi

# --------------------------
# 10. Show ingress & services
# --------------------------
echo "▶ Current Ingress resources:"
kubectl get ingress -n "${NAMESPACE}" || true

echo "▶ Current Services:"
kubectl get svc -n "${NAMESPACE}"

echo "✅ Airflow environment setup completed successfully"

# ==========================================================
# IMPORTANT: IAM PERMISSIONS (MANUAL / TERRAFORM)
# ==========================================================
#
# This script DOES NOT grant IAM permissions.
#
# If Airflow cannot write logs to GCS (403 PermissionDenied),
# verify that the following Service Account has permissions:
#
#   airflow-gcs-logger@binance-c2c-deployment.iam.gserviceaccount.com
#
# Required role (minimum):
#   roles/storage.objectAdmin
#
# Manual check:
#
#   gcloud projects get-iam-policy binance-c2c-deployment \
#     --flatten="bindings[].members" \
#     --filter="bindings.members:airflow-gcs-logger@binance-c2c-deployment.iam.gserviceaccount.com" \
#     --format="table(bindings.role)"
#
# Manual grant (ONLY if missing):
#
#   gcloud projects add-iam-policy-binding binance-c2c-deployment \
#     --member="serviceAccount:airflow-gcs-logger@binance-c2c-deployment.iam.gserviceaccount.com" \
#     --role="roles/storage.objectAdmin"
#
# Prefer Terraform-managed IAM whenever possible.
# ==========================================================
