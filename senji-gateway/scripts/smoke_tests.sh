#!/usr/bin/env bash
# Post-deploy smoke tests for senji-gateway.
# Usage: ./scripts/smoke_tests.sh [BASE_URL]
# Exit 0 = all pass, Exit 1 = any failure
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
VAULT_PATH="${VAULT_PATH:-/opt/vault}"
PASS=0
FAIL=0

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
ok()  { log "  PASS: $*"; PASS=$((PASS + 1)); }
err() { log "  FAIL: $*"; FAIL=$((FAIL + 1)); }

log "Smoke tests — target: $BASE_URL"
echo "---"

# 1. GET /health → 200
HTTP=$(curl -sf -o /tmp/senji_health.json -w "%{http_code}" "${BASE_URL}/health" 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
    ok "GET /health → 200"
    STATUS=$(python3 -c "import json,sys; d=json.load(open('/tmp/senji_health.json')); print(d.get('status','?'))" 2>/dev/null || echo "?")
    log "     status=$STATUS"
    if [ "$STATUS" = "healthy" ]; then
        ok "  health.status = healthy"
    else
        err "  health.status = $STATUS (expected healthy)"
    fi
else
    err "GET /health → $HTTP (expected 200)"
fi

# 2. GET /api/jobs requires auth — expect 401 without token
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE_URL}/api/jobs" 2>/dev/null || echo "000")
if [ "$HTTP" = "401" ]; then
    ok "GET /api/jobs (no token) → 401 (auth working)"
else
    err "GET /api/jobs (no token) → $HTTP (expected 401)"
fi

# 3. Vault directory exists and is writable
if [ -d "$VAULT_PATH" ] && [ -w "$VAULT_PATH" ]; then
    ok "Vault dir $VAULT_PATH exists and writable"
else
    err "Vault dir $VAULT_PATH missing or not writable"
fi

# 4. index.md exists
if [ -f "$VAULT_PATH/index.md" ]; then
    ok "index.md exists at $VAULT_PATH/index.md"
else
    err "index.md missing at $VAULT_PATH/index.md"
fi

echo "---"
log "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
