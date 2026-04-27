#!/usr/bin/env bash
# setup-minikube.sh — Build Askloud images inside minikube and deploy as microservices
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE=askloud

# ── Colour helpers ────────────────────────────────────────────────────────────
green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }
step()   { echo; green "==> $*"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
for cmd in minikube kubectl docker; do
  if ! command -v "$cmd" &>/dev/null; then
    red "ERROR: '$cmd' not found. Install it and re-run."
    exit 1
  fi
done

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  red "ERROR: ANTHROPIC_API_KEY is not set."
  echo "  export ANTHROPIC_API_KEY=sk-ant-..."
  exit 1
fi

# ── Start minikube (plain, no --mount flag) ───────────────────────────────────
step "Ensuring minikube is running"
DATA_DIR="$REPO_ROOT/data"
MINIKUBE_MOUNT_TARGET="/data/askloud"
MOUNT_STRING="$DATA_DIR:$MINIKUBE_MOUNT_TARGET"

if ! minikube status --format '{{.Host}}' 2>/dev/null | grep -q Running; then
  minikube start --memory=4096 --cpus=2
else
  yellow "minikube already running — skipping start"
fi


# ── Build images inside minikube's docker daemon ──────────────────────────────
step "Pointing docker to minikube's daemon"
eval "$(minikube docker-env)"

step "Building askloud-engine image"
docker build -t askloud-engine:latest "$REPO_ROOT"

step "Building askloud-gui image"
docker build -t askloud-gui:latest -f "$REPO_ROOT/askloud_gui/Dockerfile" "$REPO_ROOT"


# ── Seed snapshot data into minikube node BEFORE pods start ──────────────────
# docker cp writes directly into the minikube container's hostPath so data is
# present when the engine initializes at Django startup (AppConfig.ready()).
step "Seeding data/ into minikube node hostPath"
docker exec minikube mkdir -p /data/askloud
docker cp "$REPO_ROOT/data/." minikube:/data/askloud/
green "data/ seeded at /data/askloud inside minikube node"

# ── Apply Kubernetes manifests ────────────────────────────────────────────────
step "Applying namespace and storage"
kubectl apply -f "$REPO_ROOT/k8s/namespace.yaml"
kubectl apply -f "$REPO_ROOT/k8s/pv.yaml"
kubectl apply -f "$REPO_ROOT/k8s/pvc.yaml"

# ── Create/update secrets ─────────────────────────────────────────────────────
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
  # Azure dir can have many files; create from the whole directory
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
  # Mount key files only to keep the secret small
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
    yellow "~/.config/gcloud exists but no key files found — skipping GCP secret"
    kubectl apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: cloud-creds-gcp
  namespace: askloud
type: Opaque
data: {}
EOF
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

# ── Deploy services ───────────────────────────────────────────────────────────
step "Deploying askloud-gui"
kubectl apply -f "$REPO_ROOT/k8s/gui-deployment.yaml"
kubectl apply -f "$REPO_ROOT/k8s/gui-service.yaml"

step "Deploying askloud-collector CronJob"
kubectl apply -f "$REPO_ROOT/k8s/collector-cronjob.yaml"

# ── Wait for GUI to be ready ──────────────────────────────────────────────────
step "Waiting for askloud-gui pod to be ready (up to 3 min)"
kubectl rollout status deployment/askloud-gui -n "$NAMESPACE" --timeout=180s


# ── Print access URL ──────────────────────────────────────────────────────────
echo
green "================================================================"
green "  Askloud is running on Kubernetes (minikube)"
green "================================================================"
echo
echo "  GUI URL:  $(minikube service askloud-gui -n "$NAMESPACE" --url)"
echo
echo "  Other useful commands:"
echo "    kubectl get all -n $NAMESPACE"
echo "    kubectl logs -n $NAMESPACE deploy/askloud-gui -f"
echo "    kubectl create job --from=cronjob/askloud-collector collect-now -n $NAMESPACE"
echo "    minikube dashboard"
echo
