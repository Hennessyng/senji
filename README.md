# Senji
Version: 20260421-02

Self-hosted web clipper. Converts URLs, HTML, PDFs, and DOCX files to clean Obsidian-formatted markdown. Trigger from iOS/macOS Share Sheet via Apple Shortcuts.

```
Share URL (iOS / macOS)
      ↓  Apple Shortcut
https://markdown.myloft.cloud   ← Cloudflare Tunnel
      ↓  senji-gateway (FastAPI)
      ├─ senji-readability (Node, Readability.js + Turndown)
      └─ senji-docling     (Python, PDF/DOCX)
      ↓
iCloud Drive / Obsidian / [vault] / Clippings / [title].md
```

---

## Deploy on Proxmox (Production)

### Prerequisites

- Docker VM on Proxmox with Docker + Docker Compose installed
- Cloudflare Tunnel configured: `markdown.myloft.cloud` → `localhost:8000`
- Git available on the VM

### 1. Copy files to the VM

```bash
# From your Mac
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.ruff_cache' --exclude='.DS_Store' \
  /Users/hennessy/Documents/senji/ user@proxmox-vm:/opt/stacks/homelab/senji/
```

Or clone directly on the VM:

```bash
ssh user@proxmox-vm
git clone https://github.com/youruser/senji.git /opt/stacks/homelab/senji
```

### 2. Configure environment

```bash
cd /opt/stacks/homelab/senji
cp .env.example .env
```

Edit `.env`:

```env
SENJI_TOKEN=<your-secure-token>       # openssl rand -hex 32
DOCLING_URL=http://docling:5001
READABILITY_URL=http://readability:3000
```

> **Keep this token** — you'll need it in the Apple Shortcut.

### 3. Start services

```bash
docker compose up -d --build
docker compose ps          # all three should show (healthy)
```

First start takes ~2 min (docling image is large). Check with:

```bash
docker compose logs -f
```

### 4. Verify

```bash
curl -s http://localhost:8000/health
# → {"status":"ok"}

curl -s -X POST http://localhost:8000/api/convert/url \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | head -c 200
```

### 5. Cloudflare Tunnel

In Cloudflare Zero Trust → Tunnels → your tunnel → Public Hostname:

| Subdomain | Domain | Service |
|---|---|---|
| `markdown` | `myloft.cloud` | `http://localhost:7878` |

No TLS config needed — Cloudflare handles it.

### Update (re-deploy)

```bash
cd /opt/stacks/homelab/senji
git pull                              # or rsync from Mac again
docker compose up -d --build gateway readability
```

Docling updates slowly (large image); only rebuild it when needed:

```bash
docker compose pull docling && docker compose up -d docling
```

---

## Apple Shortcuts Setup

One shortcut works on both iOS and macOS. It clips any URL from the Share Sheet and saves a `.md` file to your Obsidian vault in iCloud Drive.

### Generate the shortcut file

```bash
# Install deps (if not already)
pip install httpx   # only needed for self-test, not the generator

# Generate (replace MyVault with your actual Obsidian vault name)
python scripts/generate_shortcut.py --vault "MyVault" --token "<your-token>"

# Output: senji-clipper.shortcut
```

### Import

**macOS**: Double-click `senji-clipper.shortcut` → Shortcuts app opens → Add Shortcut

**iOS**: AirDrop `senji-clipper.shortcut` from Mac → tap on iPhone → Add Shortcut

### Usage

1. Open any page in Safari (or any browser)
2. Share → Shortcuts → **Senji Clipper**
3. Wait ~2–5 s
4. Notification: "Saved to Obsidian ✓ [title]"
5. Note appears at: `iCloud Drive/Obsidian/[vault]/Clippings/[title].md`

### First-run note

On first use, Shortcuts will ask permission to access iCloud Drive. Allow it. After that it's fully automatic.

---

## Self-Test (Agentic TDD)

Verify the full stack end-to-end (9 tests):

```bash
# Against local dev (port 7878)
python tests/agentic_self_test.py

# Against production
python tests/agentic_self_test.py \
  --url https://theunwindai.com/p/how-agents-think

# With full log dump on failure
python tests/agentic_self_test.py --verbose

# Self-fix loop (run 3 times with 5s gaps)
python tests/agentic_self_test.py --loop 3
```

Each failure prints `[DIAG]` (container logs) and `[FIX]` (exact corrective command).

---

## Local Development

```bash
# Start with hot-reload (port 7878)
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d

# Gateway reloads on file save (senji-gateway/app/)
# Readability reloads on file save (senji-readability/src/)

# Run unit tests
cd senji-gateway && python -m pytest tests/ -v
```

---

## Services & Ports

| Service | Internal port | External (dev) | Purpose |
|---|---|---|---|
| gateway | 8000 | 7878 (dev + prod) | FastAPI, dashboard, auth |
| readability | 3000 | internal only | HTML → markdown (Readability.js) |
| docling | 5001 | internal only | PDF / DOCX → markdown |

---

## CI/CD — GitHub Actions + Webhook

Every push to `main` triggers: unit tests → webhook → VM pulls + rebuilds + self-test.
No SSH exposed to the internet. Cloudflare Tunnel secures the webhook endpoint.

```
git push main
    ↓
GitHub Actions — runs unit tests
    ↓ (on pass)
POST https://deploy.myloft.cloud/hooks/deploy-senji
    ↓ Cloudflare Tunnel
VM port 9000 — adnanh/webhook (systemd service)
    ↓
scripts/deploy.sh
    git pull → docker compose up --build → health check → agentic_self_test.py
    ↓ (on self-test fail)
    auto-rollback: git stash + rebuild previous version
```

### Prerequisites

- Senji repo cloned to `/opt/stacks/homelab/senji` on the VM (see [Deploy on Proxmox](#deploy-on-proxmox))
- `adnanh/webhook` binary available on the VM

### Step 1 — VM: install the webhook binary

SSH into your Proxmox VM, then:

```bash
apt install webhook
webhook -version    # should print: webhook version X.Y.Z
```

If `apt install webhook` gives an old version, grab the latest binary from
[github.com/adnanh/webhook/releases](https://github.com/adnanh/webhook/releases):

```bash
wget https://github.com/adnanh/webhook/releases/download/2.8.1/webhook-linux-amd64.tar.gz
tar -xzf webhook-linux-amd64.tar.gz
mv webhook-linux-amd64/webhook /usr/local/bin/webhook
webhook -version
```

### Step 2 — VM: generate and set the webhook secret

```bash
# Generate a strong secret — copy the output
openssl rand -hex 32
```

The file `webhook/hooks.json` is already in the repo (cloned in Step 1 of [Deploy on Proxmox](#deploy-on-proxmox)). Edit it to set your secret:

```bash
nano /opt/stacks/homelab/senji/webhook/hooks.json
# Find: "REPLACE_WITH_YOUR_WEBHOOK_SECRET"
# Replace with your generated secret
# Save: Ctrl+O → Enter → Ctrl+X
```

Or with a one-liner (replace `YOUR_SECRET_HERE`):

```bash
SECRET="YOUR_SECRET_HERE"
sed -i "s/REPLACE_WITH_YOUR_WEBHOOK_SECRET/$SECRET/" \
  /opt/stacks/homelab/senji/webhook/hooks.json
```

### Step 3 — VM: make the deploy script executable

```bash
chmod +x /opt/stacks/homelab/senji/scripts/deploy.sh
```

### Step 4 — VM: install and start the systemd service

```bash
cp /opt/stacks/homelab/senji/webhook/senji-webhook.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now senji-webhook
```

Verify it started:

```bash
systemctl status senji-webhook
# Should show: Active: active (running)

curl -s http://localhost:9000/hooks/deploy-senji
# Expected: {"error":"Hook rules were not satisfied."} — correct, secret is missing
```

### Step 5 — Cloudflare Tunnel: expose the webhook

In [Cloudflare Zero Trust](https://one.dash.cloudflare.com) → Networks → Tunnels → your tunnel → Edit → Public Hostnames → Add a public hostname:

| Field | Value |
|---|---|
| Subdomain | `deploy` |
| Domain | `myloft.cloud` |
| Type | `HTTP` |
| URL | `localhost:9000` |

Save. Test from your Mac:

```bash
curl -s https://deploy.myloft.cloud/hooks/deploy-senji
# Expected: {"error":"Hook rules were not satisfied."} — tunnel is working
```

### Step 6 — GitHub: add the webhook secret

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Name | Value |
|---|---|
| `WEBHOOK_SECRET` | your secret from Step 2 |

### Step 7 — trigger a deploy

The GitHub Actions workflow (`.github/workflows/deploy.yml`) is already in the repo.
Push any commit to `main` to trigger it:

```bash
git commit --allow-empty -m "chore: trigger first CI deploy"
git push origin main
```

Watch it run at `https://github.com/Hennessyng/senji/actions`.

### Verify the deploy

On the VM:

```bash
# Live webhook logs
journalctl -u senji-webhook -f

# Live deploy log (git pull, docker build, self-test output)
tail -f /var/log/senji-deploy.log
```

Manual trigger from Mac (useful for testing without a code push):

```bash
curl -f -X POST https://deploy.myloft.cloud/hooks/deploy-senji \
  -H "X-Webhook-Secret: YOUR_SECRET_HERE"
# Returns: Deploy triggered
```

---

## Troubleshooting

**`PayloadTooLargeError` in readability logs**
```bash
# Already fixed: express.json({ limit: '10mb' }) in senji-readability/src/index.js
docker compose restart readability
```

**401 on all requests**
```bash
# Check token matches
grep SENJI_TOKEN .env
# Force-recreate to pick up env change
docker compose up --force-recreate gateway
```

**Docling 503 on PDF upload**
```bash
docker compose logs docling --tail=20
# First request triggers model download (~2 GB) — wait and retry
```
