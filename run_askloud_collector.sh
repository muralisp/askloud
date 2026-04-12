#!/usr/bin/env bash
# Wrapper for the Askloud data collector.
# All arguments are passed through to askloud_collector.py inside the container.
#
# Usage:
#   ./run_askloud_collector.sh                        # interactive mode
#   ./run_askloud_collector.sh --schedule             # run all due collections
#   ./run_askloud_collector.sh --schedule --dry-run   # preview without running
#   ./run_askloud_collector.sh "get ec2 for prod us-east-1"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${ASKLOUD_IMAGE:-askloud:latest}"

: "${ANTHROPIC_API_KEY:?Error: ANTHROPIC_API_KEY environment variable is not set}"

docker run -it --rm \
  --name askloud-collector \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  -v "${SCRIPT_DIR}/data:/app/data" \
  -v "${SCRIPT_DIR}/config:/app/config" \
  -v "${HOME}/.aws:/root/.aws:ro" \
  -v "${HOME}/.azure:/root/.azure:ro" \
  -v "${HOME}/.config/gcloud:/root/.config/gcloud:ro" \
  --entrypoint python3 \
  "${IMAGE}" askloud_collector.py "$@"
