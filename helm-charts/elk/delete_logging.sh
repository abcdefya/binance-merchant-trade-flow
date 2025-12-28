#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Force Cleanup Script for Logging Namespace
# ==========================================================

NAMESPACE="logging"

echo "🚨 STARTING FORCE CLEANUP OF '${NAMESPACE}'..."

# 1. Uninstall Helm releases (Skip hooks to avoid hanging on dead jobs)
echo "▶ Uninstalling Helm releases..."
helm uninstall elasticsearch -n "${NAMESPACE}" --no-hooks 2>/dev/null || true
helm uninstall logstash      -n "${NAMESPACE}" --no-hooks 2>/dev/null || true
helm uninstall filebeat      -n "${NAMESPACE}" --no-hooks 2>/dev/null || true
helm uninstall kibana        -n "${NAMESPACE}" --no-hooks 2>/dev/null || true

# 2. Delete all PVCs (Crucial to release storage locks)
echo "▶ Deleting Persistent Volume Claims..."
kubectl delete pvc --all -n "${NAMESPACE}" --ignore-not-found=true --wait=false

# 3. Delete any hanging Jobs
echo "▶ Deleting hanging Jobs..."
kubectl delete jobs --all -n "${NAMESPACE}" --ignore-not-found=true --wait=false

# 4. Attempt standard namespace deletion (background)
echo "▶ triggering namespace deletion..."
kubectl delete ns "${NAMESPACE}" --wait=false --ignore-not-found=true

# 5. Monitor and Force Kill if Stuck
echo "⏳ Waiting 10 seconds to see if it deletes gracefully..."
sleep 10

if kubectl get ns "${NAMESPACE}" >/dev/null 2>&1; then
    echo "⚠️  Namespace '${NAMESPACE}' is stuck in Terminating status."
    echo "🔨 FORCE REMOVING finalizers..."
    
    # This patch command removes the "kubernetes" finalizer which locks the namespace
    # It tells K8s: "Stop waiting for resources to clean up, just delete the record."
    kubectl patch ns "${NAMESPACE}" -p '{"metadata":{"finalizers":null}}'
    
    echo "✅ Force delete signal sent."
else
    echo "✅ Namespace deleted gracefully."
fi

echo "🎉 Cleanup Complete."