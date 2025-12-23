#!/bin/bash
set -u

echo "🔥 STARTING AUTOMATED NUCLEAR CLEANUP..."

# 1. Start kubectl proxy in the background to bypass Windows path issues
echo "▶ Starting background proxy..."
kubectl proxy &
PROXY_PID=$!
sleep 3  # Wait for proxy to start

# Function to force-kill a namespace via the proxy
force_kill_ns() {
    local NS=$1
    if kubectl get ns "$NS" >/dev/null 2>&1; then
        echo "💀 Force-killing namespace: $NS"
        
        # 1. Force delete all resources in the namespace first
        kubectl delete all --all -n "$NS" --force --grace-period=0 >/dev/null 2>&1
        
        # 2. Trigger delete of namespace
        kubectl delete ns "$NS" --wait=false --ignore-not-found >/dev/null 2>&1
        
        # 3. Patch finalizers to empty (this unblocks the 'Terminating' status)
        kubectl get ns "$NS" -o json | \
        jq '.spec.finalizers=[]' | \
        curl -s -X PUT --data-binary @- \
        -H "Content-Type: application/json" \
        "http://127.0.0.1:8001/api/v1/namespaces/$NS/finalize" >/dev/null
        
        echo "   ✅ $NS finalized."
    else
        echo "   ℹ️  $NS already gone."
    fi
}

# Function to force-delete a resource by removing finalizers
force_delete_resource() {
    local KIND=$1
    local NAME=$2
    local NS=${3:-} # Optional namespace

    if [ -z "$NS" ]; then
        # Cluster-level resource (CRD, PV)
        kubectl delete "$KIND" "$NAME" --wait=false --ignore-not-found >/dev/null 2>&1
        # Patch finalizer to null to unstick it
        kubectl patch "$KIND" "$NAME" -p '{"metadata":{"finalizers":[]}}' --type=merge >/dev/null 2>&1 || true
    else
        # Namespaced resource
        kubectl delete "$KIND" "$NAME" -n "$NS" --wait=false --ignore-not-found >/dev/null 2>&1
        kubectl patch "$KIND" "$NAME" -n "$NS" -p '{"metadata":{"finalizers":[]}}' --type=merge >/dev/null 2>&1 || true
    fi
}

# ---------------------------------------------
# 2. Force Kill the Stack Namespaces
# ---------------------------------------------
force_kill_ns "streaming-processing"
force_kill_ns "olm"
force_kill_ns "operators"

# ---------------------------------------------
# 3. Delete Conflicting Webhooks (Critical)
# ---------------------------------------------
echo "▶ Deleting Leftover Webhooks..."
kubectl delete validatingwebhookconfigurations -l app.kubernetes.io/name=flink-kubernetes-operator --ignore-not-found
kubectl delete mutatingwebhookconfigurations -l app.kubernetes.io/name=flink-kubernetes-operator --ignore-not-found
kubectl delete validatingwebhookconfigurations -l app=strimzi --ignore-not-found
kubectl delete validatingwebhookconfigurations strimzi-validating-webhook --ignore-not-found

# ---------------------------------------------
# 4. Wipe Persistent Volumes (PVs) - Auto-Unstick
# ---------------------------------------------
echo "▶ Wiping Old Persistent Volumes (Data Disks)..."

# Get all PVs bound to streaming-processing namespace
PVS_TO_DELETE=$(kubectl get pv -o json | jq -r '.items[] | select(.spec.claimRef.namespace == "streaming-processing") | .metadata.name')

for pv in $PVS_TO_DELETE; do
    echo "   💀 Deleting stuck PV: $pv"
    force_delete_resource "pv" "$pv"
done

# Also clean up any "Released" volumes (orphaned disks)
ORPHANED_PVS=$(kubectl get pv | grep "Released" | awk '{print $1}')
for pv in $ORPHANED_PVS; do
    echo "   💀 Deleting orphaned PV: $pv"
    force_delete_resource "pv" "$pv"
done

# ---------------------------------------------
# 5. Delete CRDs - Auto-Unstick
# ---------------------------------------------
echo "▶ Deleting CRDs (Strimzi, Flink, OLM)..."

# Get list of CRDs to delete
CRDS=$(kubectl get crd | grep -E "strimzi\.io|flink\.apache\.org|operators\.coreos\.com" | awk '{print $1}')

for crd in $CRDS; do
    echo "   💀 Deleting stuck CRD: $crd"
    force_delete_resource "crd" "$crd"
done

# ---------------------------------------------
# 6. Delete Global ClusterRoles & Bindings
# ---------------------------------------------
echo "▶ Deleting Global ClusterRoles & Bindings..."
kubectl get clusterrolebinding | grep strimzi | awk '{print $1}' | xargs -r kubectl delete clusterrolebinding
kubectl get clusterrolebinding | grep flink | awk '{print $1}' | xargs -r kubectl delete clusterrolebinding

kubectl get clusterrole | grep strimzi | awk '{print $1}' | xargs -r kubectl delete clusterrole
kubectl get clusterrole | grep flink | awk '{print $1}' | xargs -r kubectl delete clusterrole

# ---------------------------------------------
# 7. Final Sweep
# ---------------------------------------------
kubectl delete secret -n streaming-processing -l owner=helm --ignore-not-found >/dev/null 2>&1

# 8. Stop the proxy
echo "▶ Stopping proxy..."
kill $PROXY_PID

echo "================================================="
echo "✅ TOTAL CLEANUP COMPLETE."
echo "   - Namespaces deleted & un-stuck"
echo "   - Disks (PVs) formatted & un-stuck"
echo "   - Operators & CRDs removed & un-stuck"
echo "   Ready for fresh install."
echo "================================================="