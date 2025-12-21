#!/bin/bash
set -e

# ==========================
# CONFIG
# ==========================
NAMESPACE="storage"
INGRESS_DIR="./helm-charts/ingress"

echo "======================================"
echo "🚀 Setup MinIO Operator, Tenant & Ingress"
echo "======================================"

# ==========================
# 1. Create namespace (if not exists)
# ==========================
echo "▶ Creating namespace: ${NAMESPACE}"
kubectl get namespace ${NAMESPACE} >/dev/null 2>&1 || \
kubectl create namespace ${NAMESPACE}

# ==========================
# 2. Check MinIO Operator Pods
# ==========================
echo "▶ Checking MinIO Operator pods..."
kubectl get pods -n ${NAMESPACE}

# ==========================
# 3. Wait for MinIO Tenant Pods
# ==========================
echo "▶ Waiting for MinIO Tenant pods to be READY..."

kubectl wait \
  --for=condition=Ready \
  pod \
  -l v1.min.io/tenant=minio-tenant \
  -n ${NAMESPACE} \
  --timeout=300s || true

kubectl get pods -n ${NAMESPACE}

# ==========================
# 4. Apply Ingress
# ==========================
echo "▶ Applying Ingress manifests from ${INGRESS_DIR}"
kubectl apply -f ${INGRESS_DIR}

echo "======================================"
echo "✅ MinIO + Ingress setup completed"
echo "======================================"
