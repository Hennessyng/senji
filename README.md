# Senji

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
  /Users/hennessy/Documents/senji/ user@proxmox-vm:/opt/stacks/homelab/
```

Or clone directly on the VM:

```bash
ssh user@proxmox-vm
git clone https://github.com/youruser/senji.git /opt/stacks/homelab
```

### 2. Configure environment

```bash
cd /opt/stacks/homelab
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
cd /opt/stacks/homelab
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

No SSH needed. VM pulls on every push to `main`. Cloudflare Tunnel secures the webhook.

### Architecture

```
git push → GitHub Actions (unit tests) → POST https://deploy.myloft.cloud/hooks/deploy-senji
                                                       ↓ Cloudflare Tunnel
                                              VM webhook receiver (port 9000)
                                                       ↓
                                              scripts/deploy.sh
                                              git pull → docker compose up → self-test
```

### Step 1 — VM: install webhook binary

```bash
apt install webhook          # Debian/Ubuntu
# or download binary:
# https://github.com/adnanh/webhook/releases
```

### Step 2 — VM: set the webhook secret

Edit `webhook/hooks.json` — replace the placeholder:

```bash
cd /opt/stacks/homelab
# Generate a strong secret
openssl rand -hex 32
# Paste it into webhook/hooks.json → "value": "<your-secret>"
```

### Step 3 — VM: install and start the systemd service

```bash
cp /opt/stacks/homelab/webhook/senji-webhook.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now senji-webhook

# Verify it's listening
systemctl status senji-webhook
curl -s http://localhost:9000/hooks/deploy-senji  # should return 400 (missing secret = expected)
```

### Step 4 — VM: make deploy script executable

```bash
chmod +x /opt/stacks/homelab/scripts/deploy.sh
```

### Step 5 — Cloudflare Tunnel: add the deploy subdomain

In Cloudflare Zero Trust → Tunnels → your tunnel → Public Hostname → Add:

| Subdomain | Domain | Service |
|---|---|---|
| `deploy` | `myloft.cloud` | `http://localhost:9000` |

### Step 6 — GitHub: add secrets

In your GitHub repo → Settings → Secrets and variables → Actions → New secret:

| Name | Value |
|---|---|
| `WEBHOOK_SECRET` | the secret from Step 2 |

### Step 7 — push `.github/workflows/deploy.yml`

The workflow is already in the repo at `.github/workflows/deploy.yml`. Push to `main` to activate.

### Verify

```bash
# Check webhook logs live
journalctl -u senji-webhook -f

# Manually trigger (from your Mac, to test)
curl -f -X POST https://deploy.myloft.cloud/hooks/deploy-senji \
  -H "X-Webhook-Secret: <your-secret>"

# Check deploy log on VM
tail -f /var/log/senji-deploy.log
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
