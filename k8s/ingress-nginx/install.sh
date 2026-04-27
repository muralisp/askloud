#!/usr/bin/env bash
# install.sh — Install Nginx Ingress Controller on EKS.
# Creates one NLB that routes traffic to all services via Ingress rules.
# Run once after the cluster is provisioned.
set -euo pipefail

green() { echo -e "\033[32m$*\033[0m"; }
step()  { echo; green "==> $*"; }

INGRESS_NGINX_VERSION="v1.11.2"

step "Installing ingress-nginx ${INGRESS_NGINX_VERSION}"
kubectl apply --server-side -f \
  "https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-${INGRESS_NGINX_VERSION}/deploy/static/provider/aws/deploy.yaml"

step "Waiting for ingress-nginx controller to be ready (up to 3 min)"
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=180s

echo
green "================================================================"
green "  Nginx Ingress Controller installed"
green "================================================================"
echo
echo "  NLB hostname (may take 1-2 min to provision):"
kubectl get svc ingress-nginx-controller -n ingress-nginx \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
echo
echo
echo "  Routes (after applying k8s/ingress.yaml and k8s/argocd/ingress.yaml):"
echo "    http://<NLB>/           → Askloud GUI"
echo "    http://<NLB>/argocd     → ArgoCD UI"
