#!/usr/bin/env bash
# Wrapper for the Askloud query engine.
# All arguments are passed through to askloud.py inside the container.
#
# Usage:
#   ./run_askloud.sh                        # interactive snapshot mode
#   ./run_askloud.sh --live                 # interactive live mode
#   ./run_askloud.sh "list running ec2"     # one-shot query
#   ./run_askloud.sh web-01                 # direct search
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${ASKLOUD_IMAGE:-askloud:latest}"

: "${ANTHROPIC_API_KEY:?Error: ANTHROPIC_API_KEY environment variable is not set}"

sudo docker run -it --rm \
  --name askloud \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  -v "${SCRIPT_DIR}/data:/app/data" \
  -v "${SCRIPT_DIR}/config:/app/config" \
  -v "${HOME}/.aws:/root/.aws:ro" \
  -v "${HOME}/.azure:/root/.azure:ro" \
  -v "${HOME}/.config/gcloud:/root/.config/gcloud:ro" \
  "${IMAGE}" "$@"
