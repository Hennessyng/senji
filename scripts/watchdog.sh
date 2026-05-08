#!/usr/bin/env bash
# Recovers compose containers stuck in `Created` state.
# Docker does not retry failed volume mounts (NFS timeout, missing bind path,
# etc.), so a container can sit in `Created` forever while `restart` policies
# never trigger. This script is invoked by senji-watchdog.timer.
set -euo pipefail

PROJECT_DIR="${SENJI_PROJECT_DIR:-/opt/stacks/homelab/senji}"
LOG_TAG="senji-watchdog"
cd "$PROJECT_DIR"

stuck=$(docker compose ps -a --status=created --format '{{.Service}}' || true)

if [ -z "$stuck" ]; then
  logger -t "$LOG_TAG" "ok: no stuck containers"
  exit 0
fi

logger -t "$LOG_TAG" "stuck services: $(echo "$stuck" | tr '\n' ' ')"

recover() {
  local svc="$1"
  local cname="senji-${svc}-1"
  # Policy: hard reset. Force-remove the stuck container, then recreate.
  # Necessary because `compose up --force-recreate` can itself block on the
  # bad mount that left the container in Created state.
  docker rm -f "$cname" >/dev/null 2>&1 || true
  docker compose up -d "$svc"
}

rc=0
while IFS= read -r svc; do
  if recover "$svc"; then
    logger -t "$LOG_TAG" "recovered: $svc"
  else
    logger -t "$LOG_TAG" -p user.err "recover failed: $svc"
    rc=1
  fi
done <<< "$stuck"
exit "$rc"
