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

log "Rebuilding gateway and readability"
docker compose up -d --build gateway readability

log "Ensuring obsidian-remote is running"
docker compose up -d obsidian-remote

log "Waiting for services to be healthy (up to 60s)"
for i in $(seq 1 12); do
    gw_ok=$(docker compose ps gateway    | grep -c '(healthy)' || true)
    rd_ok=$(docker compose ps readability | grep -c '(healthy)' || true)
    if [ "$gw_ok" -ge 1 ] && [ "$rd_ok" -ge 1 ]; then
        log "Both gateway and readability healthy"
        sleep 3   # brief stabilisation — let FastAPI finish startup tasks
        break
    fi
    if [ "$i" -eq 12 ]; then
        log "ERROR: Services did not become healthy in time"
        docker compose logs gateway --tail=20 >> "$LOG"
        docker compose logs readability --tail=20 >> "$LOG"
        exit 1
    fi
    log "Waiting... gateway=${gw_ok}/1 readability=${rd_ok}/1 (${i}/12)"
    sleep 5
done

log "Running self-test"
if python3 "$REPO/tests/agentic_self_test.py" >> "$LOG" 2>&1; then
    log "Self-test passed — deploy complete"
    # Sync service file and reload webhook last — this restarts our parent process
    cp "$REPO/webhook/senji-webhook.service" /etc/systemd/system/senji-webhook.service
    systemctl daemon-reload
    systemctl restart senji-webhook
    log "Webhook service synced and restarted"
else
    log "ERROR: Self-test failed — rolling back"
    git stash 2>/dev/null || true
    docker compose up -d --build gateway readability
    exit 1
fi
