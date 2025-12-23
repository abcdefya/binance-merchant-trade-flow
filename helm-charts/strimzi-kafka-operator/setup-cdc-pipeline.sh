#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Full CDC & Streaming Pipeline Bootstrap Script (PRODUCTION)
# ==========================================================

# ==========================================================
# 🔧 USER CONFIGURATION (EDIT THIS SECTION)
# ==========================================================
# 👇 INSERT YOUR REAL TELEGRAM DATA HERE 👇
TELEGRAM_BOT_TOKEN=.   # <--- Replace "token" with your real Bot Token
TELEGRAM_CHAT_ID=.       # <--- Replace "chat_id" with your real Chat ID

# --------------------------
# System Config
# --------------------------
STREAMING_NAMESPACE="streaming-processing"
BATCH_NAMESPACE="batch-processing"
STORAGE_NAMESPACE="storage"

RELEASE_NAME_STRIMZI="strimzi-kafka-operator"
HELM_REPO_NAME_STRIMZI="strimzi"
HELM_REPO_URL_STRIMZI="https://strimzi.io/charts/"
HELM_CHART_STRIMZI="strimzi/strimzi-kafka-operator"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HELM_CHARTS_DIR="${PROJECT_ROOT}/helm-charts"
KAFKA_HELM_DIR="${HELM_CHARTS_DIR}/strimzi-kafka-operator"

# Connector Files
CONNECTOR_FILE="${HELM_CHARTS_DIR}/strimzi-kafka-operator/c2c-connector.yaml"
POSTGRES_CONNECTOR_FILE="${HELM_CHARTS_DIR}/strimzi-kafka-operator/postgres-connector.yaml"

INGRESS_DIR="${PROJECT_ROOT}/ingress"

echo "=========================================="
echo " Full CDC Pipeline Bootstrap"
echo "=========================================="

# --------------------------
# Prerequisites
# --------------------------
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }

# --------------------------
# 1. Create namespaces
# --------------------------
for ns in "${STREAMING_NAMESPACE}" "${BATCH_NAMESPACE}" "${STORAGE_NAMESPACE}"; do
  if kubectl get ns "${ns}" >/dev/null 2>&1; then
    echo "ℹ️  Namespace ${ns} already exists"
  else
    echo "▶ Creating namespace: ${ns}"
    kubectl create ns "${ns}"
  fi
done

# --------------------------
# 2. Install Strimzi Operator (Helm)
# --------------------------
echo "▶ Adding/updating Strimzi Helm repository"
helm repo add "${HELM_REPO_NAME_STRIMZI}" "${HELM_REPO_URL_STRIMZI}" >/dev/null 2>&1 || true
helm repo update "${HELM_REPO_NAME_STRIMZI}"

echo "▶ Installing/Upgrading Strimzi Kafka Operator"
helm upgrade --install "${RELEASE_NAME_STRIMZI}" "${HELM_CHART_STRIMZI}" \
  --namespace "${STREAMING_NAMESPACE}" \
  --create-namespace \
  --wait \
  --timeout=600s

echo "▶ Waiting for Strimzi Operator deployment"
kubectl rollout status deployment/strimzi-cluster-operator -n "${STREAMING_NAMESPACE}" --timeout=300s

# --------------------------
# 3. Create Secrets (CRITICAL: Must be before Connect deployment)
# --------------------------
echo "▶ Creating secrets in ${STREAMING_NAMESPACE}"

# 3a. Postgres Credentials
if kubectl get secret -n "${BATCH_NAMESPACE}" airflow-postgresql >/dev/null 2>&1; then
    PGPASSWORD=$(kubectl get secret -n "${BATCH_NAMESPACE}" airflow-postgresql -o jsonpath='{.data.postgres-password}' | base64 -d)
    
    kubectl create secret generic postgres-credentials -n "${STREAMING_NAMESPACE}" \
      --from-literal=hostname=airflow-postgresql.${BATCH_NAMESPACE}.svc.cluster.local \
      --from-literal=port=5432 \
      --from-literal=user=postgres \
      --from-literal=password="$PGPASSWORD" \
      --from-literal=dbname=c2c_trade \
      --dry-run=client -o yaml | kubectl apply -f -
    echo "   ✅ postgres-credentials created"
else
    echo "   ⚠️  Skipping postgres-credentials (airflow-postgresql secret not found in batch namespace)"
fi

# 3b. MinIO Credentials
MINIO_ACCESS_KEY=$(kubectl get secret -n "${STORAGE_NAMESPACE}" minio-tenant-user-1 -o jsonpath='{.data.CONSOLE_ACCESS_KEY}' 2>/dev/null | base64 -d || echo "minio")
MINIO_SECRET_KEY=$(kubectl get secret -n "${STORAGE_NAMESPACE}" minio-tenant-user-1 -o jsonpath='{.data.CONSOLE_SECRET_KEY}' 2>/dev/null | base64 -d || echo "minio123")

kubectl create secret generic minio-credentials -n "${STREAMING_NAMESPACE}" \
  --from-literal=access-key="$MINIO_ACCESS_KEY" \
  --from-literal=secret-key="$MINIO_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "   ✅ minio-credentials created"

# 3c. Telegram Secrets (Added as requested)
kubectl create secret generic telegram-secrets -n "${STREAMING_NAMESPACE}" \
  --from-literal=bot-token="${TELEGRAM_BOT_TOKEN}" \
  --from-literal=chat-id="${TELEGRAM_CHAT_ID}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "   ✅ telegram-secrets created"

# --------------------------
# 4. Deploy Kafka cluster + Debezium Connect
# --------------------------
echo "▶ Deploying Kafka cluster and Debezium Connect cluster"

cd "${KAFKA_HELM_DIR}"
if [[ ! -f "Chart.yaml" ]]; then
  echo "❌ Chart.yaml not found in ${KAFKA_HELM_DIR}."
  exit 1
fi

helm upgrade --install kafka-cdc . \
  -n "${STREAMING_NAMESPACE}" \
  --create-namespace

echo "▶ Waiting for Kafka cluster to be ready (may take 3-5 mins)..."
sleep 10
kubectl wait --for=condition=Ready pod -l strimzi.io/cluster=kafka -n "${STREAMING_NAMESPACE}" --timeout=600s || true

echo "▶ Waiting for Kafka Connect (Debezium) to be ready..."
# This should now succeed because secrets exist
kubectl wait --for=condition=Ready pod -l strimzi.io/cluster=debezium-connect-cluster -n "${STREAMING_NAMESPACE}" --timeout=400s || true

# --------------------------
# 5. Enable PostgreSQL logical replication
# --------------------------
echo "▶ Enabling logical replication on PostgreSQL"

if kubectl get pods -n "${BATCH_NAMESPACE}" | grep -q airflow-postgresql; then
  PGPASSWORD=$(kubectl get secret -n "${BATCH_NAMESPACE}" airflow-postgresql -o jsonpath='{.data.postgres-password}' | base64 -d)
  WAL_LEVEL=$(kubectl exec -n "${BATCH_NAMESPACE}" airflow-postgresql-0 -- bash -c "PGPASSWORD='$PGPASSWORD' psql -U postgres -t -c 'SHOW wal_level;' " | tr -d ' \n')

  if [ "$WAL_LEVEL" != "logical" ]; then
    echo "   ⚠️  Changing wal_level to 'logical'"
    kubectl exec -n "${BATCH_NAMESPACE}" airflow-postgresql-0 -- bash -c "
      PGPASSWORD='$PGPASSWORD' psql -U postgres -c \"ALTER SYSTEM SET wal_level = 'logical';\"
      PGPASSWORD='$PGPASSWORD' psql -U postgres -c \"ALTER SYSTEM SET max_replication_slots = 10;\"
      PGPASSWORD='$PGPASSWORD' psql -U postgres -c \"ALTER SYSTEM SET max_wal_senders = 10;\"
    "
    kubectl rollout restart statefulset/airflow-postgresql -n "${BATCH_NAMESPACE}"
    kubectl rollout status statefulset/airflow-postgresql -n "${BATCH_NAMESPACE}" --timeout=300s
  else
    echo "   ℹ️  wal_level is already logical"
  fi
fi

# --------------------------
# 6. Create DB resources
# --------------------------
if kubectl get pods -n "${BATCH_NAMESPACE}" | grep -q airflow-postgresql; then
    echo "▶ Configuring c2c_trade database"
    PGPASSWORD=$(kubectl get secret -n "${BATCH_NAMESPACE}" airflow-postgresql -o jsonpath='{.data.postgres-password}' | base64 -d)
    
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
          amount NUMERIC(38, 8),
          total_price NUMERIC(38, 8),
          unit_price NUMERIC(38, 8),
          order_status TEXT,
          create_time BIGINT,
          commission NUMERIC(38, 8),
          counter_part_nick_name TEXT,
          advertisement_role TEXT
      );
      DROP PUBLICATION IF EXISTS c2c_publication;
      CREATE PUBLICATION c2c_publication FOR TABLE c2c.trades;
EOF
"
    echo "   ✅ Database configured"
fi

# --------------------------
# 7. Deploy Connectors
# --------------------------
echo "▶ Deploying CDC connectors"

# 7a. C2C Connector
if [[ -f "${CONNECTOR_FILE}" ]]; then
  echo "▶ Applying C2C Connector..."
  kubectl apply -f "${CONNECTOR_FILE}" -n "${STREAMING_NAMESPACE}"
else
  echo "❌ C2C Connector file not found at ${CONNECTOR_FILE}"
fi

# 7b. Postgres Connector (Added as requested)
if [[ -f "${POSTGRES_CONNECTOR_FILE}" ]]; then
  echo "▶ Applying Postgres Connector..."
  kubectl apply -f "${POSTGRES_CONNECTOR_FILE}" -n "${STREAMING_NAMESPACE}"
else
  echo "⚠️  Postgres Connector file not found at ${POSTGRES_CONNECTOR_FILE} (Skipping)"
fi

# --------------------------
# 8. Ingress
# --------------------------
echo "▶ Applying Ingress manifests"
if [[ -d "${INGRESS_DIR}" && -n "$(ls -A "${INGRESS_DIR}"/*.yaml 2>/dev/null)" ]]; then
  kubectl apply -f "${INGRESS_DIR}" -n "${STREAMING_NAMESPACE}"
fi

# --------------------------
# Final Status
# --------------------------
echo ""
echo "=========================================="
echo " Setup Complete!"
echo "=========================================="
kubectl get pods -n "${STREAMING_NAMESPACE}"
