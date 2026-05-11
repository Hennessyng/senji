# Senji CI/CD Pipeline

## Overview

Every push to `main` triggers a fully automated deploy with self-test and auto-rollback. No SSH is exposed to the internet — the webhook endpoint is secured behind a Cloudflare Tunnel.

```
git push origin main
        │
        ▼
GitHub Actions (.github/workflows/deploy.yml)
  └─ POST https://deploy.myloft.cloud/hooks/deploy-senji
          │  X-Webhook-Secret: <secret>
          │
        [ Cloudflare Tunnel ]
          │  routes deploy.myloft.cloud → localhost:9000 on VM
          │
        ▼
adnanh/webhook  (systemd: senji-webhook.service, :9000)
  └─ validates X-Webhook-Secret header against hooks.json
  └─ exec: /bin/bash /opt/stacks/homelab/senji/scripts/deploy.sh
          │
          ▼
        deploy.sh
          ├─ git fetch + reset --hard origin/main
          ├─ self-refresh (re-exec itself so the newly-pulled version runs)
          ├─ source .env → generate /etc/senji-hooks-live.json
          ├─ docker compose up -d --build --force-recreate gateway readability
          ├─ docker compose up -d obsidian-remote
          ├─ health-check loop (up to 120s)
          ├─ python3 tests/agentic_self_test.py
          │       ├─ PASS → sync + restart senji-webhook.service
          │       └─ FAIL → git stash + rebuild previous + exit 1
          │
          ▼
        /var/log/senji-deploy.log  (all steps timestamped)
```

---

## Components

### 1. GitHub Actions — `.github/workflows/deploy.yml`

- Trigger: `push` to `main`
- Runs on `ubuntu-latest`
- Single step: `curl` POST to `https://deploy.myloft.cloud/hooks/deploy-senji`
  - Header: `X-Webhook-Secret: ${{ secrets.WEBHOOK_SECRET }}`
  - `--max-time 300` / `timeout-minutes: 6` — waits for the full deploy to complete before marking the job green or red
- GitHub Action succeeds/fails based on the HTTP response code from the webhook

### 2. Cloudflare Tunnel

- Public hostname `deploy.myloft.cloud` → `localhost:9000` on the Proxmox VM
- No firewall ports opened on the VM; all inbound traffic goes through Cloudflare
- TLS terminated by Cloudflare; traffic from tunnel to VM is plain HTTP on localhost

### 3. adnanh/webhook — `webhook/hooks.json` + `senji-webhook.service`

- Binary: `/usr/bin/webhook`, port `9000`
- Systemd service: `senji-webhook.service` (`Restart=always`)
- Config loaded from `/etc/senji-hooks-live.json` (generated at deploy time — never the raw repo file)
- Hook `deploy-senji`:
  - Auth: `X-Webhook-Secret` header must match `WEBHOOK_SECRET` from `.env`
  - On match: executes `/bin/bash /opt/stacks/homelab/senji/scripts/deploy.sh`
  - Response: `"Deploy triggered"` (synchronous — curl blocks until script exits)

#### Shared webhook drop-in pattern (multi-consumer composition)

The webhook daemon at `:9000` is shared with sibling projects on the same VM (currently `otoflow`). The daemon takes multiple `-hooks` flags — one per consumer's `*-hooks-live.json`. To compose this safely without one project's deploy clobbering another's hooks file, every consumer:

1. Treats the base unit `/etc/systemd/system/senji-webhook.service` as a **one-time bootstrap artifact**. Installed once during initial VM setup (README Step 4). Never rewritten by any deploy.
2. Installs its own systemd drop-in at `/etc/systemd/system/senji-webhook.service.d/<consumer>.conf`. Drop-in directories survive base-unit rewrites and merge cleanly across consumers.
3. Each drop-in clears the inherited `ExecStart=` then re-sets it with the full list of every sibling's hooks file:

   ```ini
   [Service]
   ExecStart=
   ExecStart=/usr/bin/webhook -hooks /etc/senji-hooks-live.json -hooks /etc/otoflow-hooks-live.json -port 9000 -verbose
   ```

senji ships `webhook/senji.conf` and `deploy.sh` installs it to `/etc/systemd/system/senji-webhook.service.d/senji.conf`. otoflow does the equivalent from its repo.

**Pattern: A4 "mirror"** — every drop-in lists every sibling's hooks file. systemd merges drop-ins alphabetically; whichever is parsed last wins `ExecStart=`. Because all drop-ins set identical content, order is irrelevant in steady state.

**Brittleness (accepted trade-off):** any addition or removal of a sibling requires updating every consumer's drop-in in lockstep. If senji.conf and otoflow.conf disagree, the alphabetically-last one silently wins and the other's hooks are dropped — same failure mode as the bug this pattern was introduced to fix, just at a different layer. Detection: `systemctl cat senji-webhook.service` and `journalctl -u senji-webhook | grep loaded` post-deploy must show every sibling's hooks loaded.

**If a sibling leaves the VM:** every remaining consumer must remove that sibling's `-hooks /etc/<gone>-hooks-live.json` from its drop-in. The webhook daemon fails to start if a `-hooks` path doesn't exist.

**Acceptance check after any senji deploy:**

```bash
systemctl cat senji-webhook.service           # shows base unit + merged drop-ins
journalctl -u senji-webhook --since '5 min ago' --no-pager | grep loaded
# expect: deploy-senji AND deploy-otoflow both loaded
```

### 4. deploy.sh — `scripts/deploy.sh`

Runs as `root` inside the VM. Steps in order:

| Step | Detail |
|---|---|
| `git fetch origin` + `git reset --hard origin/main` | Hard reset — discards any local drift |
| Self-refresh | Checks `SENJI_REFRESHED` env var; re-execs itself via `exec env SENJI_REFRESHED=1 bash deploy.sh` so the newly-pulled script version runs for the rest of the deploy |
| Source `.env` | Loads `WEBHOOK_SECRET` and other env vars |
| Generate live hooks | `sed` replaces `REPLACE_WITH_YOUR_WEBHOOK_SECRET` in `webhook/hooks.json` → `/etc/senji-hooks-live.json` |
| Rebuild services | `docker compose up -d --build --force-recreate gateway readability` |
| Start obsidian-remote | `docker compose up -d obsidian-remote` (no rebuild needed) |
| Health-check loop | 24 × 5s polls; checks `(healthy)` status for both `gateway` and `readability`; fails after 120s |
| Self-test | `python3 tests/agentic_self_test.py` — 9 end-to-end tests against localhost |
| On pass | `install webhook/senji.conf → /etc/systemd/system/senji-webhook.service.d/senji.conf` + `systemctl daemon-reload` + `systemctl restart senji-webhook` (drop-in only — base unit is never rewritten; see "Shared webhook drop-in pattern") |
| On fail | `git stash` + `docker compose up -d --build --force-recreate gateway readability` → exit 1 (propagates failure to GitHub Actions) |

All steps append to `/var/log/senji-deploy.log` with UTC timestamps.

#### Self-refresh mechanism

The deploy script re-execs itself after `git reset --hard` so the rest of the deploy always runs the version just pulled from `main`, not the version that was on disk when the webhook fired. This prevents stale script logic from running new code.

```bash
[[ "${SENJI_REFRESHED:-0}" == "1" ]] || exec env SENJI_REFRESHED=1 bash "$REPO/scripts/deploy.sh"
```

### 5. Watchdog — `scripts/watchdog.sh`

- Systemd timer: `senji-watchdog.timer` (periodic, not part of the deploy path)
- Finds containers stuck in `Created` state (e.g. failed NFS/bind mounts at boot)
- Docker's `restart` policy never fires for `Created` — only for `Exited` — so this fills the gap
- Recovery: `docker rm -f <container>` then `docker compose up -d <service>`
- Logs to `journald` under tag `senji-watchdog`

---

## Secrets

| Secret | Where stored | How used |
|---|---|---|
| `WEBHOOK_SECRET` | GitHub repo secret + VM `.env` | GitHub Actions sends it as `X-Webhook-Secret`; webhook validates it; deploy.sh injects it into live hooks config |

---

## Key Files

| File | Purpose |
|---|---|
| `.github/workflows/deploy.yml` | GitHub Actions: trigger webhook on push to main |
| `webhook/hooks.json` | Webhook hook definition (template — contains placeholder secret) |
| `webhook/senji-webhook.service` | Systemd base unit for adnanh/webhook daemon (one-time bootstrap; never rewritten by deploy) |
| `webhook/senji.conf` | Systemd drop-in installed by every deploy to `/etc/systemd/system/senji-webhook.service.d/senji.conf` (shared-webhook composition; see "Shared webhook drop-in pattern") |
| `webhook/senji-watchdog.service` | Systemd unit for watchdog |
| `webhook/senji-watchdog.timer` | Systemd timer that schedules watchdog runs |
| `scripts/deploy.sh` | Full deploy logic: pull → build → health-check → self-test → rollback |
| `scripts/watchdog.sh` | Recovers containers stuck in Created state |
| `/etc/senji-hooks-live.json` | Runtime hooks config (generated by deploy.sh, never committed) |
| `/var/log/senji-deploy.log` | Timestamped deploy log on the VM |

---

## Observing a Deploy

```bash
# Live webhook daemon logs
journalctl -u senji-webhook -f

# Live deploy log
tail -f /var/log/senji-deploy.log

# Manual trigger (from any machine)
curl -f -X POST https://deploy.myloft.cloud/hooks/deploy-senji \
  -H "X-Webhook-Secret: YOUR_SECRET_HERE"
```
