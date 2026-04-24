# Senji

Self-hosted knowledge ingestion and web clipping platform. Converts URLs, HTML, PDFs, and images to structured Obsidian markdown, with AI-powered wiki generation and semantic embeddings.

---

## Features

- **Web clipping** — Share any URL from iOS/macOS Share Sheet → note in Obsidian via Apple Shortcut
- **Async ingestion** — Queue URLs, PDFs, and images; processed in background with job status polling
- **PDF → markdown** — pymupdf + pymupdf4llm; full text extraction with page-aware chunking
- **Image ingestion** — Ollama Vision (qwen2.5vl) describes images and extracts text via OCR
- **Wiki generation** — Ollama LLM (qwen3:8b) generates structured wiki entries from ingested content
- **Semantic embeddings** — bge-m3 embeddings indexed for Open WebUI RAG
- **Browser Obsidian** — obsidian-remote runs full Obsidian at `:7899` against the server vault
- **AI chat over vault** — Open WebUI + Ollama at `:8080`, vault mounted read-only for context
- **Dashboard** — Static web UI served at `/` by the gateway
- **Self-hosted** — No third-party cloud; your data stays on your infrastructure
- **Secure** — Bearer token auth, Cloudflare Tunnel (no open ports), HTTPS everywhere
- **CI/CD with auto-rollback** — GitHub Actions → webhook → VM rebuild → self-test; rolls back on failure

---

## Infrastructure

```
Apple Shortcut (iOS/macOS)
      ↓  POST /api/convert/url  (sync)
senji-gateway :8000  (FastAPI, auth, dashboard, job queue)
      ├─ senji-readability :3000   (Readability.js + Turndown)
      └─ Ollama (external, OLLAMA_BASE_URL)
            ├─ qwen3:8b          — wiki generation
            ├─ qwen2.5vl:7b      — image OCR + description
            └─ bge-m3            — semantic embeddings
      ↓ writes to
/opt/vault/
  ├── raw/        ← clipped articles (slug.md + frontmatter)
  ├── wiki/       ← AI-generated wiki entries
  ├── assets/     ← downloaded media
  └── jobs.db     ← SQLite job queue

obsidian-remote :7899   (full Obsidian in browser, /opt/vault)
open-webui      :8080   (AI chat, Ollama RAG, /opt/vault read-only)
```

**CI/CD pipeline:**
```
git push main → GitHub Actions (unit tests)
      ↓ (pass)
POST https://deploy.myloft.cloud/hooks/deploy-senji  ← Cloudflare Tunnel
      ↓
adnanh/webhook :9000 (systemd)
      ↓
scripts/deploy.sh: git pull → docker compose up --build → health check → self-test
      ↓ (fail) auto-rollback: git stash + rebuild previous
```

**CI/CD pipeline:**
```
git push main
      ↓
GitHub Actions  — unit tests
      ↓ (on pass)
POST https://deploy.myloft.cloud/hooks/deploy-senji   ← Cloudflare Tunnel
      ↓
adnanh/webhook :9000  (systemd, VM)
      ↓
scripts/deploy.sh
      git pull → docker compose up --build → health check → agentic_self_test.py
      ↓ (on self-test fail)
      auto-rollback: git stash + rebuild previous version
```

### Services & Ports

| Service | Port | Purpose |
|---|---|---|
| gateway | 7878 (ext), 8000 (int) | FastAPI, auth, API, dashboard, job queue |
| readability | 3000 (int only) | HTML → markdown (Readability.js + Turndown) |
| obsidian-remote | 7899 | Full Obsidian in browser (KasmVNC, `/opt/vault`) |
| open-webui | 8080 | AI chat with vault RAG (Ollama backend) |

---

## API

### Convert — synchronous, returns markdown immediately

| Method | Path | Body | Description |
|---|---|---|---|
| `POST` | `/api/convert/url` | `{"url": "..."}` | Fetch URL → markdown (Apple Shortcut) |
| `POST` | `/api/convert/html` | `{"html": "...", "source_url": "..."}` | Raw HTML → markdown |
| `GET` | `/health` | — | Health check |

**Response schema:**
```json
{ "markdown": "...", "title": "...", "source": "...", "media": [] }
```

### Ingest — async, 202 accepted, poll for status

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ingest/url` | Queue URL for full pipeline (convert + wiki + embed) |
| `POST` | `/api/ingest/file` | Queue PDF or image (multipart/form-data) |
| `GET` | `/api/ingest/jobs/{job_id}` | Poll job status |

**Supported file types:**
- `application/pdf` — pymupdf text extraction
- `image/jpeg`, `image/png`, `image/webp` — Ollama Vision OCR + description
- `image/heic` / `image/heif` — **rejected** (415), convert client-side first

**Ingest pipeline per job:** fetch → convert → `raw/{slug}.md` → wiki → `wiki/{slug}.md` → embed

**Job status:**
```json
{ "job_id": "...", "type": "url|pdf|image", "status": "queued|processing|complete|failed",
  "files_written": ["raw/slug.md", "wiki/slug.md"], "error_detail": null }
```

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `SENJI_TOKEN` | `dev-token` | Yes | Bearer auth token |
| `OLLAMA_BASE_URL` | — | **Yes** | Ollama API URL (e.g. `http://10.1.1.222:11434`) |
| `READABILITY_URL` | `http://readability:3000` | No | Readability service URL |
| `VAULT_PATH` | `/opt/vault` | No | Vault root on server |
| `OLLAMA_MODEL` | `qwen3:8b` | No | LLM for wiki generation |
| `OLLAMA_VISION_MODEL` | `qwen2.5vl:7b` | No | Vision model for image ingest |
| `OLLAMA_EMBED_MODEL` | `bge-m3` | No | Embedding model |
| `MAX_FILE_SIZE_MB` | `50` | No | Upload size limit |
| `SQLITE_DB_PATH` | `/opt/vault/jobs.db` | No | Job queue database |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity |

---

## Quick Start

> Full prerequisites: Proxmox VM with Docker + Docker Compose, Cloudflare Tunnel configured, macOS with `shortcuts` CLI for shortcut generation.

**1. Clone and configure**

```bash
ssh user@proxmox-vm
git clone https://github.com/Hennessyng/senji.git /opt/stacks/homelab/senji
cd /opt/stacks/homelab/senji
cp .env.example .env
```

Edit `.env`:
```env
SENJI_TOKEN=$(openssl rand -hex 32)         # copy — needed for the shortcut
OLLAMA_BASE_URL=http://10.1.1.222:11434     # required — your Ollama host
READABILITY_URL=http://readability:3000
```

**2. Create vault and start**

```bash
mkdir -p /opt/vault
docker compose up -d --build
docker compose ps   # all services: healthy
```

**3. Verify**

```bash
curl -s http://localhost:8000/health
# → {"status":"ok"}
```

**4. Generate the Apple Shortcut (on your Mac)**

```bash
python scripts/generate_shortcut.py --vault "MyVault" --token "<SENJI_TOKEN>"
# Output: senji-clipper.shortcut
```

Double-click to import on macOS, or AirDrop to iPhone.

**5. Clip something**

Open any URL in Safari → Share → Shortcuts → **Senji Clipper** → note appears in `Clippings/`.

---

## Installation

### Requirements

| Component | Requirement |
|---|---|
| Proxmox VM | Docker + Docker Compose |
| Cloudflare | Tunnel configured to VM |
| Mac (shortcut gen) | Python 3.10+, `shortcuts` CLI (Xcode) |
| iPhone / Mac | Obsidian app, iCloud Drive enabled |

### Dependencies

**Server (auto-installed via Docker):**
- `senji-gateway` — FastAPI, httpx, pydantic, pymupdf, pymupdf4llm
- `senji-readability` — Node.js, @mozilla/readability, turndown
- `obsidian-remote` — `ghcr.io/sytone/obsidian-remote` (full Obsidian via KasmVNC)
- `open-webui` — `ghcr.io/open-webui/open-webui` (AI chat, connects to Ollama)
- **Ollama** — external; must be running separately at `OLLAMA_BASE_URL`

**Shortcut generator (local Mac only):**
```bash
# No pip install required — stdlib only (plistlib, uuid, subprocess)
python scripts/generate_shortcut.py --help
```

**Self-test (optional):**
```bash
pip install httpx
python tests/agentic_self_test.py
```

---

## Deploy on Proxmox (Production)

### Prerequisites

- Docker VM on Proxmox with Docker + Docker Compose installed
- Cloudflare Tunnel configured: `markdown.myloft.cloud` → `localhost:8000`
- Git available on the VM
- Vault directory at `/opt/vault` on the VM (used by obsidian-remote and open-webui)

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
git clone https://github.com/Hennessyng/senji.git /opt/stacks/homelab/senji
```

### 2. Configure environment

```bash
cd /opt/stacks/homelab/senji
cp .env.example .env
```

Edit `.env`:

```env
SENJI_TOKEN=<your-secure-token>             # openssl rand -hex 32
OLLAMA_BASE_URL=http://10.1.1.222:11434     # required — your Ollama host
READABILITY_URL=http://readability:3000
```

> **Keep `SENJI_TOKEN`** — you'll need it in the Apple Shortcut.

### 3. Create the vault directory

```bash
mkdir -p /opt/vault
```

### 4. Start services

```bash
docker compose up -d --build
docker compose ps          # all services should show (healthy)
docker compose logs -f
```

### 5. Verify

```bash
curl -s http://localhost:8000/health
# → {"status":"ok"}

curl -s -X POST http://localhost:8000/api/convert/url \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | head -c 200
```

### 6. Cloudflare Tunnel

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

---

## Apple Shortcuts Setup

One shortcut works on both iOS and macOS. It clips any URL from the Share Sheet and saves a `.md` file to your Obsidian vault in iCloud Drive.

### Generate the shortcut file

```bash
# Generate (replace MyVault with your actual Obsidian vault name)
python scripts/generate_shortcut.py --vault "MyVault" --token "<your-token>"

# Output: senji-clipper.shortcut

# Debug build — adds alert dialogs after each step for on-device troubleshooting
python scripts/generate_shortcut.py --vault "MyVault" --token "<your-token>" --debug
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

## CI/CD — GitHub Actions + Webhook

Every push to `main` triggers: unit tests → webhook → VM pulls + rebuilds + self-test.
No SSH exposed to the internet. Cloudflare Tunnel secures the webhook endpoint.

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

The file `webhook/hooks.json` is already in the repo. Edit it to set your secret:

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

### Step 6 — GitHub: add the webhook secret

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Name | Value |
|---|---|
| `WEBHOOK_SECRET` | your secret from Step 2 |

### Step 7 — trigger a deploy

```bash
git commit --allow-empty -m "chore: trigger first CI deploy"
git push origin main
```

Watch it run at `https://github.com/Hennessyng/senji/actions`.

### Verify the deploy

```bash
# Live webhook logs
journalctl -u senji-webhook -f

# Live deploy log
tail -f /var/log/senji-deploy.log
```

Manual trigger:

```bash
curl -f -X POST https://deploy.myloft.cloud/hooks/deploy-senji \
  -H "X-Webhook-Secret: YOUR_SECRET_HERE"
# Returns: Deploy triggered
```

---

## Troubleshooting

**401 on all requests**
```bash
grep SENJI_TOKEN .env
docker compose up --force-recreate gateway
```

**Gateway fails to start / `ValidationError: ollama_base_url`**
```bash
# OLLAMA_BASE_URL is required — must be set in .env
echo "OLLAMA_BASE_URL=http://10.1.1.222:11434" >> .env
docker compose up --force-recreate gateway
```

**`ollama_unavailable` on image ingest**
```bash
docker compose exec gateway curl -s $OLLAMA_BASE_URL/api/tags
# If this fails, Ollama is unreachable from the container
```

**Job stuck in `queued`**
```bash
docker compose logs gateway --tail=50
# Common cause: Ollama unreachable at startup → ollama_client.available = False
```

**`PayloadTooLargeError` in readability logs**
```bash
docker compose restart readability
```

**obsidian-remote blank screen**
```bash
docker compose restart obsidian-remote
# Known upstream bug — restart resolves it
```
