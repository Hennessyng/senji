#!/usr/bin/env bash
# Deploy senji-gateway container on Proxmox (standalone docker run).
# Usage: ./scripts/deploy.sh [IMAGE_TAG]
# Requires: docker, curl
# Env: REGISTRY, IMAGE_NAME, SENJI_TOKEN, OLLAMA_BASE_URL set in environment or .env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG=/var/log/senji-deploy.log
CONTAINER_NAME=senji-gateway
PORT=8000
VAULT_PATH=/opt/vault
IMAGE_TAG="${1:-latest}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

# Load .env if present
if [ -f "$REPO_ROOT/../.env" ]; then
    set -o allexport
    source "$REPO_ROOT/../.env"
    set +o allexport
fi

REGISTRY="${REGISTRY:-ghcr.io/hennessyng}"
IMAGE="${REGISTRY}/senji-gateway:${IMAGE_TAG}"

log "Deploy started — image: $IMAGE"

# Pull latest image
log "Pulling image"
docker pull "$IMAGE"

# Capture old container ID for rollback
OLD_IMAGE=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME" 2>/dev/null || echo "")

# Stop and remove old container (graceful 10s)
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Stopping old container"
    docker stop --time 10 "$CONTAINER_NAME" || true
    docker rm "$CONTAINER_NAME" || true
fi

# Ensure vault directory exists
mkdir -p "$VAULT_PATH"

# Run new container
log "Starting new container"
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "${PORT}:8000" \
    -v "${VAULT_PATH}:/opt/vault" \
    -e "OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://10.1.1.222:11434}" \
    -e "VAULT_PATH=/opt/vault" \
    -e "LOG_LEVEL=${LOG_LEVEL:-INFO}" \
    -e "SENJI_TOKEN=${SENJI_TOKEN}" \
    --add-host "host.docker.internal:host-gateway" \
    "$IMAGE"

# Health check loop (30s timeout)
log "Waiting for health check (up to 30s)"
for i in $(seq 1 6); do
    sleep 5
    HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/health" 2>/dev/null || echo "000")
    if [ "$HTTP" = "200" ]; then
        log "Health check passed"
        break
    fi
    if [ "$i" -eq 6 ]; then
        log "ERROR: Health check failed (HTTP $HTTP) — rolling back"
        docker stop "$CONTAINER_NAME" || true
        docker rm "$CONTAINER_NAME" || true
        if [ -n "$OLD_IMAGE" ]; then
            log "Rolling back to $OLD_IMAGE"
            docker run -d \
                --name "$CONTAINER_NAME" \
                --restart unless-stopped \
                -p "${PORT}:8000" \
                -v "${VAULT_PATH}:/opt/vault" \
                -e "OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://10.1.1.222:11434}" \
                -e "VAULT_PATH=/opt/vault" \
                -e "LOG_LEVEL=${LOG_LEVEL:-INFO}" \
                -e "SENJI_TOKEN=${SENJI_TOKEN}" \
                "$OLD_IMAGE"
            log "Rollback complete"
        fi
        exit 1
    fi
    log "Not ready yet ($i/6), retrying..."
done

# Post-deploy smoke tests
log "Running smoke tests"
if bash "$SCRIPT_DIR/smoke_tests.sh" >> "$LOG" 2>&1; then
    log "Smoke tests passed — deploy complete"
else
    log "ERROR: Smoke tests failed"
    exit 1
fi
