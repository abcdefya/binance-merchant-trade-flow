#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Full CDC & Streaming Pipeline Bootstrap Script (PRODUCTION)
#
# This script sets up the COMPLETE CDC pipeline with updated namespaces:
# - Strimzi Kafka Operator → namespace: streaming-processing
# - Kafka cluster + Kafka Connect + Connectors → namespace: streaming-processing
# - PostgreSQL (Airflow's DB) → namespace: batch-processing
#
# Order of execution:
# 1. Install Strimzi Kafka Operator (in streaming-processing)
# 2. Deploy Kafka cluster + Debezium Connect cluster
# 3. Enable PostgreSQL logical replication
# 4. Create c2c_trade database, table and publication
# 5. Create required secrets
# 6. Deploy C2C CDC connector
# 7. Apply Ingress resources (tương tự Airflow)
# ==========================================================

# --------------------------
# Config
# --------------------------
STREAMING_NAMESPACE="streaming-processing"
BATCH_NAMESPACE="batch-processing"
STORAGE_NAMESPACE="storage"

RELEASE_NAME_STRIMZI="strimzi-kafka-operator"
HELM_REPO_NAME_STRIMZI="strimzi"
HELM_REPO_URL_STRIMZI="https://strimzi.io/charts/"
HELM_CHART_STRIMZI="strimzi/strimzi-kafka-operator"
OLM_VERSION="v0.20.0"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HELM_CHARTS_DIR="${PROJECT_ROOT}/helm-charts"
STRIMZI_MANIFEST_DIR="${HELM_CHARTS_DIR}/strimzi-kafka-operator"
KAFKA_HELM_DIR="${HELM_CHARTS_DIR}/strimzi-kafka-operator"
CONNECTOR_FILE="${HELM_CHARTS_DIR}/strimzi-kafka-operator/c2c-connector.yaml"
INGRESS_DIR="${PROJECT_ROOT}/ingress"   # Thư mục chứa các Ingress manifests

echo "=========================================="
echo " Full CDC Pipeline Bootstrap (with Ingress)"
echo "=========================================="
echo "▶ Streaming namespace : ${STREAMING_NAMESPACE}"
echo "▶ Batch namespace     : ${BATCH_NAMESPACE}"
echo "▶ Helm charts dir     : ${HELM_CHARTS_DIR}"
echo "▶ Connector file      : ${CONNECTOR_FILE}"
echo "▶ Ingress dir         : ${INGRESS_DIR}"

# --------------------------
# Prerequisites
# --------------------------
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "❌ curl not found"; exit 1; }

# --------------------------
# 1. Create namespaces
# --------------------------
for ns in "${STREAMING_NAMESPACE}" "${BATCH_NAMESPACE}" "${STORAGE_NAMESPACE}"; do
  if kubectl get ns "${ns}" >/dev/null 2>&1; then
    echo "ℹ️ Namespace ${ns} already exists"
  else
    echo "▶ Creating namespace: ${ns}"
    kubectl create ns "${ns}"
  fi
done

# --------------------------
# 2. Install OLM (if not present)
# --------------------------
echo "▶ Checking Operator Lifecycle Manager (OLM)..."

# 1. Corrected Check: Look for the specific OLM CRD
if kubectl get crd clusterserviceversions.operators.coreos.com >/dev/null 2>&1; then
  echo "ℹ️ OLM already installed"
else
  echo "▶ Installing OLM ${OLM_VERSION}..."
  # 2. Safety: Added '|| true' so if the installer exits early, your script keeps going
  curl -sL https://github.com/operator-framework/operator-lifecycle-manager/releases/download/${OLM_VERSION}/install.sh | bash -s ${OLM_VERSION} || true
  
  echo "ℹ️ Waiting for OLM to initialize..."
  sleep 40
fi
# --------------------------
# 3. Apply Strimzi CRDs & base manifests
# --------------------------
if [[ -f "${STRIMZI_MANIFEST_DIR}/strimzi-kafka-operator.yaml" ]]; then
  echo "▶ Applying Strimzi operator manifests"
  kubectl apply -f "${STRIMZI_MANIFEST_DIR}/strimzi-kafka-operator.yaml"
else
  echo "❌ strimzi-kafka-operator.yaml not found in ${STRIMZI_MANIFEST_DIR}"
  exit 1
fi

# --------------------------
# 4. Add Strimzi Helm repo & Install/Upgrade Operator
# --------------------------
echo "▶ Adding/updating Strimzi Helm repository"
helm repo add "${HELM_REPO_NAME_STRIMZI}" "${HELM_REPO_URL_STRIMZI}" >/dev/null 2>&1 || true
helm repo update "${HELM_REPO_NAME_STRIMZI}"

echo "▶ Installing/Upgrading Strimzi Kafka Operator in ${STREAMING_NAMESPACE}"
helm upgrade --install "${RELEASE_NAME_STRIMZI}" "${HELM_CHART_STRIMZI}" \
  --namespace "${STREAMING_NAMESPACE}" \
  --create-namespace \
  --wait \
  --timeout=600s

echo "▶ Waiting for Strimzi Operator deployment"
kubectl rollout status deployment/strimzi-cluster-operator -n "${STREAMING_NAMESPACE}" --timeout=300s

# --------------------------
# 5. Deploy Kafka cluster + Debezium Connect
# --------------------------
echo "▶ Deploying Kafka cluster and Debezium Connect cluster"
cd "${KAFKA_HELM_DIR}"

if [[ ! -f "Chart.yaml" || ! -d "templates" ]]; then
  echo "❌ Invalid Helm chart structure in ${KAFKA_HELM_DIR}"
  exit 1
fi

helm upgrade --install kafka-cdc . \
  -n "${STREAMING_NAMESPACE}" \
  --create-namespace

echo "▶ Waiting for Kafka cluster to be ready (3-5 minutes)..."
sleep 30
kubectl wait --for=condition=Ready pod -l strimzi.io/cluster=kafka -n "${STREAMING_NAMESPACE}" --timeout=600s || true

echo "▶ Waiting for Kafka Connect (Debezium) to be ready..."
kubectl wait --for=condition=Ready pod -l strimzi.io/cluster=debezium-connect-cluster -n "${STREAMING_NAMESPACE}" --timeout=400s || true

# --------------------------
# 6. Enable PostgreSQL logical replication
# --------------------------
echo "▶ Enabling logical replication on PostgreSQL (${BATCH_NAMESPACE} namespace)"

if ! kubectl get pods -n "${BATCH_NAMESPACE}" | grep -q airflow-postgresql; then
  echo "❌ PostgreSQL pod not found in namespace ${BATCH_NAMESPACE}"
  exit 1
fi

PGPASSWORD=$(kubectl get secret -n "${BATCH_NAMESPACE}" airflow-postgresql -o jsonpath='{.data.postgres-password}' | base64 -d)

WAL_LEVEL=$(kubectl exec -n "${BATCH_NAMESPACE}" airflow-postgresql-0 -- bash -c "PGPASSWORD='$PGPASSWORD' psql -U postgres -t -c 'SHOW wal_level;' " | tr -d ' \n')

if [ "$WAL_LEVEL" = "logical" ]; then
  echo "ℹ️ wal_level already set to logical"
else
  echo "⚠️ Changing wal_level from '$WAL_LEVEL' to 'logical'"
  kubectl exec -n "${BATCH_NAMESPACE}" airflow-postgresql-0 -- bash -c "
    PGPASSWORD='$PGPASSWORD' psql -U postgres -c \"ALTER SYSTEM SET wal_level = 'logical';\"
    PGPASSWORD='$PGPASSWORD' psql -U postgres -c \"ALTER SYSTEM SET max_replication_slots = 10;\"
    PGPASSWORD='$PGPASSWORD' psql -U postgres -c \"ALTER SYSTEM SET max_wal_senders = 10;\"
  "
  echo "▶ Restarting PostgreSQL to apply changes..."
  kubectl rollout restart statefulset/airflow-postgresql -n "${BATCH_NAMESPACE}"
  kubectl rollout status statefulset/airflow-postgresql -n "${BATCH_NAMESPACE}" --timeout=300s
  sleep 15
fi

WAL_LEVEL=$(kubectl exec -n "${BATCH_NAMESPACE}" airflow-postgresql-0 -- bash -c "PGPASSWORD='$PGPASSWORD' psql -U postgres -t -c 'SHOW wal_level;' " | tr -d ' \n')
echo "✅ wal_level is now: $WAL_LEVEL"

# --------------------------
# 7. Create c2c_trade database, table and publication
# --------------------------
echo "▶ Creating c2c_trade database, table and publication"

kubectl exec -n "${BATCH_NAMESPACE}" airflow-postgresql-0 -- bash -c "
  PGPASSWORD='$PGPASSWORD' psql -U postgres <<'EOF'
  SELECT 'CREATE DATABASE c2c_trade' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'c2c_trade')\\gexec

  \\c c2c_trade

  CREATE SCHEMA IF NOT EXISTS c2c;

  CREATE TABLE IF NOT EXISTS c2c.trades (
      order_number TEXT PRIMARY KEY,
      adv_no TEXT,
      trade_type TEXT CHECK (trade_type IN ('BUY','SELL')),
      asset VARCHAR(16),
      fiat VARCHAR(16),
      fiat_symbol VARCHAR(16),
      amount NUMERIC(38, 8) CHECK (amount >= 0),
      total_price NUMERIC(38, 8) CHECK (total_price >= 0),
      unit_price NUMERIC(38, 8) CHECK (unit_price >= 0),
      order_status TEXT,
      create_time BIGINT,
      commission NUMERIC(38, 8) CHECK (commission >= 0),
      counter_part_nick_name TEXT,
      advertisement_role TEXT
  );

  DROP PUBLICATION IF EXISTS c2c_publication;
  CREATE PUBLICATION c2c_publication FOR TABLE c2c.trades;
EOF
"

echo "✅ Database and publication ready"

# --------------------------
# 8. Create secrets for Debezium
# --------------------------
echo "▶ Creating secrets in ${STREAMING_NAMESPACE}"

kubectl create secret generic postgres-credentials -n "${STREAMING_NAMESPACE}" \
  --from-literal=hostname=airflow-postgresql.${BATCH_NAMESPACE}.svc.cluster.local \
  --from-literal=port=5432 \
  --from-literal=user=postgres \
  --from-literal=password="$PGPASSWORD" \
  --from-literal=dbname=c2c_trade \
  --dry-run=client -o yaml | kubectl apply -f -

MINIO_ACCESS_KEY=$(kubectl get secret -n "${STORAGE_NAMESPACE}" minio-tenant-user-1 -o jsonpath='{.data.CONSOLE_ACCESS_KEY}' 2>/dev/null | base64 -d || echo "minio")
MINIO_SECRET_KEY=$(kubectl get secret -n "${STORAGE_NAMESPACE}" minio-tenant-user-1 -o jsonpath='{.data.CONSOLE_SECRET_KEY}' 2>/dev/null | base64 -d || echo "minio123")

kubectl create secret generic minio-credentials -n "${STREAMING_NAMESPACE}" \
  --from-literal=access-key="$MINIO_ACCESS_KEY" \
  --from-literal=secret-key="$MINIO_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Secrets created"

# --------------------------
# 9. Deploy C2C CDC Connector
# --------------------------
echo "▶ Deploying C2C CDC connector"

if [[ ! -f "${CONNECTOR_FILE}" ]]; then
  echo "❌ c2c-connector.yaml not found at ${CONNECTOR_FILE}"
  exit 1
fi

kubectl apply -f "${CONNECTOR_FILE}" -n "${STREAMING_NAMESPACE}"

echo "✅ Connector deployed"

# --------------------------
# 10. Apply Ingress resources
# --------------------------
echo "▶ Applying Ingress manifests"

if [[ -d "${INGRESS_DIR}" && -n "$(ls -A "${INGRESS_DIR}"/*.yaml "${INGRESS_DIR}"/*.yml 2>/dev/null || true)" ]]; then
  echo "▶ Found Ingress manifests in ${INGRESS_DIR}"
  kubectl apply -f "${INGRESS_DIR}" -n "${STREAMING_NAMESPACE}"
else
  echo "⚠️ No Ingress directory or YAML files found at ${INGRESS_DIR} (skipping)"
  echo "   Create folder ingress/ in project root and put your Ingress YAML files there."
fi

# --------------------------
# 11. Show current Ingress & Services
# --------------------------
echo "▶ Current Ingress resources in ${STREAMING_NAMESPACE}:"
kubectl get ingress -n "${STREAMING_NAMESPACE}" || true

echo ""
echo "▶ Current Services in ${STREAMING_NAMESPACE}:"
kubectl get svc -n "${STREAMING_NAMESPACE}"

# --------------------------
# 12. Final verification
# --------------------------
echo ""
echo "▶ Strimzi Operator:"
kubectl get pods -n "${STREAMING_NAMESPACE}" -l name=strimzi-cluster-operator

echo ""
echo "▶ Kafka cluster:"
kubectl get pods -n "${STREAMING_NAMESPACE}" -l strimzi.io/cluster=kafka

echo ""
echo "▶ Kafka Connect (Debezium):"
kubectl get pods -n "${STREAMING_NAMESPACE}" -l strimzi.io/cluster=debezium-connect-cluster

echo ""
echo "▶ Active connectors:"
kubectl get kafkaconnector -n "${STREAMING_NAMESPACE}"

echo ""
echo "=========================================="
echo " CDC Pipeline Setup Complete (with Ingress)!"
echo "=========================================="
echo ""
echo " PostgreSQL (${BATCH_NAMESPACE}) --> Debezium --> Kafka (${STREAMING_NAMESPACE})"
echo "                                           ↓"
echo "                                 Topic: c2c_cdc.c2c.trades (or as configured)"
echo ""
echo " Useful commands:"
echo "   • Watch all pods:          kubectl get pods -n ${STREAMING_NAMESPACE} -w"
echo "   • Check Ingress:           kubectl get ingress -n ${STREAMING_NAMESPACE}"
echo "   • Connector details:       kubectl describe kafkaconnector c2c-trades-connector -n ${STREAMING_NAMESPACE}"
echo "   • Connector logs:          kubectl logs -f -n ${STREAMING_NAMESPACE} \$(kubectl get pod -n ${STREAMING_NAMESPACE} -l strimzi.io/name=debezium-connect-cluster-connect -o jsonpath='{.items[0].metadata.name}')"
echo ""
echo "✅ All done! Your real-time C2C CDC pipeline with Ingress is now fully operational."