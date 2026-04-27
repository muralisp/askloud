#!/usr/bin/env bash
# install-argocd.sh — Install ArgoCD into the EKS cluster and apply the
# Askloud Application manifest.
#
# Run once after the cluster is provisioned:
#   ./k8s/argocd/install-argocd.sh
set -euo pipefail

green() { echo -e "\033[32m$*\033[0m"; }
step()  { echo; green "==> $*"; }

# ── Install ArgoCD ────────────────────────────────────────────────────────────
step "Installing ArgoCD"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

step "Waiting for ArgoCD server to be ready (up to 5 min)"
kubectl wait --for=condition=available deployment/argocd-server \
  -n argocd --timeout=300s

# ── Apply Askloud Application ─────────────────────────────────────────────────
step "Registering Askloud Application with ArgoCD"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
kubectl apply -f "$SCRIPT_DIR/application.yaml"

# ── Print access info ─────────────────────────────────────────────────────────
echo
green "================================================================"
green "  ArgoCD installed"
green "================================================================"
echo
echo "  Admin password:"
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
echo
echo
echo "  Access the UI (port-forward):"
echo "    kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "    Then open: https://localhost:8080  (user: admin)"
echo
echo "  Or expose via LoadBalancer:"
echo "    kubectl patch svc argocd-server -n argocd -p '{\"spec\":{\"type\":\"LoadBalancer\"}}'"
