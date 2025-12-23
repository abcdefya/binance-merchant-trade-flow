#!/usr/bin/env bash

set -e  # dừng script nếu có lỗi

NAMESPACE="nginx-system"
RELEASE_NAME="nginx-ingress"
CHART_PATH="./helm-charts/nginx-ingress"

echo "▶ Creating namespace (if not exists): $NAMESPACE"
kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE"

echo "▶ Deploying nginx-ingress via Helm"
helm upgrade --install "$RELEASE_NAME" "$CHART_PATH" \
  -n "$NAMESPACE" \
  --create-namespace

echo "▶ Listing services in namespace: $NAMESPACE"
kubectl get svc -n "$NAMESPACE"

echo "✅ nginx-ingress deployment completed successfully"
