#!/usr/bin/env bash
set -euo pipefail

REPO=/opt/stacks/homelab/senji
LOG=/var/log/senji-deploy.log

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

log "Deploy started"

cd "$REPO"

log "Pulling latest code"
git pull --ff-only

# Generate live hooks.json with real secret from .env
set -o allexport; source "$REPO/.env"; set +o allexport
sed "s/REPLACE_WITH_YOUR_WEBHOOK_SECRET/$WEBHOOK_SECRET/" \
  "$REPO/webhook/hooks.json" > /etc/senji-hooks-live.json
log "Generated live hooks.json"
systemctl restart senji-webhook
log "Restarted webhook service"

log "Rebuilding gateway and readability"
docker compose up -d --build gateway readability

log "Ensuring obsidian-remote is running"
docker compose up -d obsidian-remote

log "Waiting for services to be healthy (up to 60s)"
for i in $(seq 1 12); do
    if docker compose ps | grep -E '(gateway|readability)' | grep -q '(healthy)'; then
        log "Services healthy"
        break
    fi
    if [ "$i" -eq 12 ]; then
        log "ERROR: Services did not become healthy in time"
        docker compose logs gateway --tail=20 >> "$LOG"
        docker compose logs readability --tail=20 >> "$LOG"
        exit 1
    fi
    sleep 5
done

log "Running self-test"
if python3 "$REPO/tests/agentic_self_test.py" >> "$LOG" 2>&1; then
    log "Self-test passed — deploy complete"
else
    log "ERROR: Self-test failed — rolling back"
    git stash 2>/dev/null || true
    docker compose up -d --build gateway readability
    exit 1
fi
