#!/usr/bin/env bash
# deploy-aks.sh — Build images, push to ACR, and deploy Askloud to AKS.
#
# Usage:
#   ./deploy-aks.sh dev                        # deploy to dev environment
#   ./deploy-aks.sh prod                       # deploy to prod environment
#   IMAGE_TAG=v1.2.3 ./deploy-aks.sh dev       # pin a specific image tag
#   TF_APPLY=1 ./deploy-aks.sh dev             # also run terraform apply
set -euo pipefail

# ── Arguments & defaults ──────────────────────────────────────────────────────

ENV="${1:-}"
if [[ -z "$ENV" ]]; then
  echo "Usage: $0 <dev|prod>"
  exit 1
fi
if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "ERROR: environment must be 'dev' or 'prod'"
  exit 1
fi

IMAGE_TAG="${IMAGE_TAG:-latest}"
TF_APPLY="${TF_APPLY:-0}"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$REPO_ROOT/terraform/$ENV/azure"
NAMESPACE=askloud

# ── Colour helpers ────────────────────────────────────────────────────────────
green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }
step()   { echo; green "==> $*"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
for cmd in az terraform kubectl docker envsubst; do
  if ! command -v "$cmd" &>/dev/null; then
    red "ERROR: '$cmd' not found. Install it and re-run."
    exit 1
  fi
done

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  red "ERROR: ANTHROPIC_API_KEY is not set."
  exit 1
fi

# Verify az CLI is logged in
if ! az account show &>/dev/null; then
  red "ERROR: Not logged in to Azure CLI. Run: az login"
  exit 1
fi

# ── Optional: run terraform apply ─────────────────────────────────────────────
if [[ "$TF_APPLY" == "1" ]]; then
  step "Running terraform init + apply for $ENV/azure"
  terraform -chdir="$TF_DIR" init
  terraform -chdir="$TF_DIR" apply -auto-approve
fi

# ── Read terraform outputs ────────────────────────────────────────────────────
step "Reading Terraform outputs for $ENV/azure"
ACR_GUI_URL=$(terraform -chdir="$TF_DIR" output -raw acr_gui_url)
ACR_ENGINE_URL=$(terraform -chdir="$TF_DIR" output -raw acr_engine_url)
ACR_NAME=$(terraform -chdir="$TF_DIR" output -raw acr_name)
CLUSTER_NAME=$(terraform -chdir="$TF_DIR" output -raw cluster_name)
RESOURCE_GROUP=$(terraform -chdir="$TF_DIR" output -raw resource_group_name)

green "  Cluster        : $CLUSTER_NAME"
green "  Resource Group : $RESOURCE_GROUP"
green "  ACR GUI        : $ACR_GUI_URL"
green "  ACR Engine     : $ACR_ENGINE_URL"
green "  Image tag      : $IMAGE_TAG"

# ── Configure kubectl ─────────────────────────────────────────────────────────
step "Updating kubeconfig for $CLUSTER_NAME"
az aks get-credentials \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CLUSTER_NAME" \
  --overwrite-existing

# ── Authenticate Docker to ACR ────────────────────────────────────────────────
step "Authenticating Docker to ACR"
az acr login --name "$ACR_NAME"

# ── Build and push images ─────────────────────────────────────────────────────
step "Building askloud-engine image"
docker build -t "${ACR_ENGINE_URL}:${IMAGE_TAG}" "$REPO_ROOT"

step "Building askloud-gui image"
docker build -t "${ACR_GUI_URL}:${IMAGE_TAG}" \
  -f "$REPO_ROOT/askloud_gui/Dockerfile" "$REPO_ROOT"

step "Pushing images to ACR"
docker push "${ACR_ENGINE_URL}:${IMAGE_TAG}"
docker push "${ACR_GUI_URL}:${IMAGE_TAG}"

# ── Apply Kubernetes manifests ────────────────────────────────────────────────
step "Installing Metrics Server (enables kubectl top)"
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

step "Applying namespace and storage"
kubectl apply -f "$REPO_ROOT/k8s/namespace.yaml"
kubectl apply -f "$REPO_ROOT/k8s/storageclass-aks.yaml"
kubectl apply -f "$REPO_ROOT/k8s/pvc-aks.yaml"
kubectl apply -f "$REPO_ROOT/k8s/ingress.yaml"

# ── Create/update application secrets ────────────────────────────────────────
step "Creating askloud-secrets"
kubectl create secret generic askloud-secrets \
  --namespace="$NAMESPACE" \
  --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  --from-literal=DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')}" \
  --dry-run=client -o yaml | kubectl apply -f -

# ── Cloud credential secrets (optional) ──────────────────────────────────────
step "Creating cloud credential secrets (optional)"

if [[ -d "$HOME/.aws" ]]; then
  kubectl create secret generic cloud-creds-aws \
    --namespace="$NAMESPACE" \
    --from-file=credentials="$HOME/.aws/credentials" \
    --dry-run=client -o yaml | kubectl apply -f -
  green "AWS credentials secret created"
else
  kubectl apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: cloud-creds-aws
  namespace: askloud
type: Opaque
data: {}
EOF
  yellow "No ~/.aws found — created empty cloud-creds-aws secret"
fi

if [[ -d "$HOME/.azure" ]]; then
  kubectl create secret generic cloud-creds-azure \
    --namespace="$NAMESPACE" \
    $(find "$HOME/.azure" -maxdepth 1 -type f | sed 's/.*/--from-file=& /' | tr '\n' ' ') \
    --dry-run=client -o yaml | kubectl apply -f -
  green "Azure credentials secret created"
else
  kubectl apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: cloud-creds-azure
  namespace: askloud
type: Opaque
data: {}
EOF
  yellow "No ~/.azure found — created empty cloud-creds-azure secret"
fi

if [[ -d "$HOME/.config/gcloud" ]]; then
  GCLOUD_FILES=()
  for f in application_default_credentials.json credentials.db; do
    [[ -f "$HOME/.config/gcloud/$f" ]] && GCLOUD_FILES+=("--from-file=$f=$HOME/.config/gcloud/$f")
  done
  if [[ ${#GCLOUD_FILES[@]} -gt 0 ]]; then
    kubectl create secret generic cloud-creds-gcp \
      --namespace="$NAMESPACE" \
      "${GCLOUD_FILES[@]}" \
      --dry-run=client -o yaml | kubectl apply -f -
    green "GCP credentials secret created"
  else
    yellow "No GCP key files found"
  fi
else
  kubectl apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: cloud-creds-gcp
  namespace: askloud
type: Opaque
data: {}
EOF
  yellow "No ~/.config/gcloud found — created empty cloud-creds-gcp secret"
fi

# ── Deploy workloads (envsubst injects registry URLs) ─────────────────────────
step "Deploying askloud-gui"
export GUI_IMAGE="${ACR_GUI_URL}:${IMAGE_TAG}"
export ENGINE_IMAGE="${ACR_ENGINE_URL}:${IMAGE_TAG}"
envsubst < "$REPO_ROOT/k8s/gui-deployment.yaml" | kubectl apply -f -
kubectl apply -f "$REPO_ROOT/k8s/gui-service.yaml"

step "Deploying askloud-collector CronJob"
envsubst < "$REPO_ROOT/k8s/collector-cronjob.yaml" | kubectl apply -f -

# ── Wait for rollout ──────────────────────────────────────────────────────────
step "Waiting for askloud-gui rollout (up to 5 min)"
kubectl rollout status deployment/askloud-gui -n "$NAMESPACE" --timeout=300s

# ── Seed local data/ into the PVC ────────────────────────────────────────────
if [[ -d "$REPO_ROOT/data" && -n "$(ls -A "$REPO_ROOT/data" 2>/dev/null)" ]]; then
  step "Seeding local data/ into pod PVC"
  GUI_POD=$(kubectl get pod -l app=askloud-gui -n "$NAMESPACE" \
    -o jsonpath='{.items[0].metadata.name}')
  kubectl cp "$REPO_ROOT/data/." "$NAMESPACE/$GUI_POD:/app/data/"
  green "data/ seeded into $GUI_POD:/app/data/"
else
  yellow "data/ is empty — skipping seed (collector will populate it on first run)"
fi

# ── Print access URL ──────────────────────────────────────────────────────────
echo
green "============================================================"
green "  Askloud is running on AKS ($ENV)"
green "============================================================"
echo
LB_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "<pending>")
echo "  GUI URL    : http://$LB_IP/"
echo "  ArgoCD URL : http://$LB_IP/argocd"
echo "  (Azure LB may take 1-2 min to get a public IP)"
echo
echo "  Useful commands:"
echo "    kubectl get all -n $NAMESPACE"
echo "    kubectl logs -n $NAMESPACE deploy/askloud-gui -f"
echo "    kubectl create job --from=cronjob/askloud-collector collect-now -n $NAMESPACE"
