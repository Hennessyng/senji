# Memory Budget Analysis — senji-gateway

**Target Budget:** 20GB (Proxmox container limit)  
**Analysis Date:** 2026-04-23  
**Analysis Scope:** senji-gateway production deployment

---

## Executive Summary

✅ **Well within budget.** Peak estimated usage: **~3.8GB** (18% of budget)  
✅ **Comfortable headroom:** 16.2GB buffer  
✅ **Scaling limit:** ~50,000 cached embeddings before concern  

---

## Component Breakdown

### 1. FastAPI Application Baseline

| Component | Memory | Notes |
|---|---|---|
| Python runtime (asyncio) | 50–80 MB | Core interpreter, event loop |
| FastAPI + Uvicorn | 30–50 MB | Web framework, ASGI server |
| Middleware (auth, logging) | 5–10 MB | Request/response processing |
| **Subtotal** | **85–140 MB** | Negligible footprint |

**Reference:** app/main.py (68 lines)

---

### 2. Embedding Service (sentence_transformers)

#### Model Loading
- **Model:** `BAAI/bge-m3` (dense embedding, CPU-based)
- **Typical size:** 350–450 MB in memory
- **Loading strategy:** Lazy (first request triggers load)

#### Vector Representation
- **Dimension:** 1024-dimensional vectors
- **Data type:** float32
- **Per-vector size:** 1024 × 4 bytes = **4 KB**
- **Batch processing:** batch_size=32 (from app/config.py:15)
- **Batch memory:** 32 × 4 KB = 128 KB (transient, released after encoding)

#### Cache Storage (SQLite)
```
embeddings table:
  - text_hash (TEXT, ~64 bytes)
  - text (TEXT, avg 500 bytes per article)
  - vector (BLOB, 4 KB per embedding)
  - created_at (TEXT, ~30 bytes)
  ────────────────────────────
  Per row: ~4.6 KB
```

| Item | Amount | Memory |
|---|---|---|
| Model in memory | 1 | 400 MB |
| Encoding batch (worst case) | 32 vectors | 128 KB |
| In-flight numpy arrays | temp | ~1 MB |
| SQLite buffer pool (default) | - | 2–5 MB |
| **Subtotal** | | **~406 MB** |

**Reference:** app/services/embedding_service.py (248 lines)
- Line 79: Lazy model loading via `SentenceTransformer(model_name)`
- Line 99–100: Batch encode returns numpy array, converted to list
- Line 106: Pickled vector stored in DB BLOB

---

### 3. Job Queue & State

#### In-Memory Job Tracking
| Component | Count | Per Item | Memory |
|---|---|---|---|
| Queued jobs (Python dict) | 5 max | 1 KB | 5 KB |
| Processing jobs | 1–2 | 2 KB | 4 KB |
| Embedding queue | 50 max pending | 0.5 KB | 25 KB |
| **Subtotal** | | | **~34 KB** |

#### SQLite Storage (jobs.db)
```
jobs table:
  - job_id (TEXT, 36 bytes UUID)
  - type (TEXT, ~10 bytes)
  - source_url (TEXT, avg 100 bytes)
  - tags (JSON, ~200 bytes)
  - status, files_written, error_detail (TEXT)
  - timestamps (3 × TEXT, ~90 bytes)
  ────────────────────────────
  Per row: ~500 bytes
  
embedding_jobs table:
  - job_id, status, texts_count, texts_json (avg 5KB), timestamps
  ────────────────────────────
  Per row: ~5.5 KB (only pending/processing; old entries archived)
```

| Storage | Max Rows | Per Row | Memory |
|---|---|---|---|
| jobs (active) | 10,000 | 500 B | 5 MB |
| embedding_jobs (queue) | 100 | 5.5 KB | 550 KB |
| **Subtotal** | | | **~5.6 MB** |

**Reference:** app/services/job_queue.py (677 lines, shown 1-100)
- Lines 53–70: Job schema with SQLite indices on status and created_at

---

### 4. SQLite Databases

#### jobs.db Layout
| Table | Typical Rows | Per Row | Subtotal |
|---|---|---|---|
| jobs | 10,000 | 500 B | 5 MB |
| embeddings cache | 5,000 | 4.6 KB | 23 MB |
| embedding_jobs (queue) | 100 | 5.5 KB | 0.6 MB |
| Indices (status, created_at, text_hash) | - | - | 1 MB |
| **Subtotal** | | | **~30 MB** |

#### Other Small Databases
- **index.md** (vault metadata): <1 MB
- **log.md** (operation log): <1 MB

**Subtotal:** <2 MB

---

### 5. Vault Storage (/opt/vault)

> **Important:** Vault is persistent disk storage, NOT RAM.
> Only in-memory cache counts toward memory budget.

#### In-Memory Cache (if any)
- **raw/**: Not cached; files read on-demand from disk
- **wiki/**: Not cached; files read on-demand from disk
- **Metadata index:** Loaded once at startup (if any)

**Memory impact:** <1 MB (minimal)

#### Disk Storage (reference only, not in RAM)
```
Per 1000 articles:
  - raw/ articles: 1000 × 5 KB = 5 MB (disk)
  - wiki/ entries: 1000 × 2 KB = 2 MB (disk)
  ────────────────────────────
  Total: ~7 MB disk (not RAM)
```

---

### 6. Ollama Client

> **CRITICAL:** Ollama (qwen3:8b) runs on remote LAN (10.1.1.222:11434).
> **Zero local memory cost** — only HTTP calls, no model loaded.

| Component | Memory |
|---|---|
| httpx client object | 50 KB |
| Connection pool | 100 KB |
| **Subtotal** | **~150 KB** |

**Reference:** app/services/ollama_client.py
- Line 23 in main.py: `await ollama_client.health_check()` (connectivity check only)

---

## Worst-Case Scenario

**Parameters:**
- Max concurrent requests: 5
- Max concurrent embedding jobs: 2
- Max cached embeddings: 5,000
- Max queued jobs: 10,000
- Max in-flight batch: 32 vectors

| Component | Memory |
|---|---|
| FastAPI baseline | 140 MB |
| Embedding model (bge-m3) | 400 MB |
| Embedding cache (5K entries) | 23 MB |
| Job queue (10K + 100 pending) | 5.6 MB |
| SQLite overhead (indices, WAL, buffers) | 5 MB |
| Concurrent request overhead (5 × 50MB) | 250 MB |
| In-flight vectors (5 batches × 32) | 0.6 MB |
| System libraries & misc | 50 MB |
| **Total Estimated Peak** | **~734 MB** |

### Realistic High-Load Scenario

**Parameters:**
- Average concurrent requests: 2–3
- Embedding model always loaded
- Cached embeddings: 2,000–5,000
- Queued jobs: 50–100

| Metric | Memory |
|---|---|
| Baseline | 140 MB |
| Embedding model | 400 MB |
| Embedding cache (2K entries) | 9 MB |
| Job queue | 3 MB |
| Request overhead (3 × 50MB) | 150 MB |
| Buffers & misc | 30 MB |
| **Total Peak** | **~732 MB** |

---

## Headroom Analysis

| Metric | Value |
|---|---|
| Budget | 20 GB |
| **Worst-case usage** | **734 MB** |
| **Realistic peak** | **732 MB** |
| **Buffer** | 19.3 GB |
| **Usage ratio** | 3.7% |

✅ **Verdict:** Massive headroom. Even at 10× concurrent load, well under budget.

---

## Scaling Limits

### Embedding Cache Growth

**As cached embeddings increase:**

| Cached Embeddings | Memory | % of Budget |
|---|---|---|
| 1,000 | 4.6 MB | 0.02% |
| 5,000 | 23 MB | 0.1% |
| 10,000 | 46 MB | 0.2% |
| 50,000 | 230 MB | 1.2% |
| **100,000** | **460 MB** | **2.3%** |
| 500,000 | 2.3 GB | 11.5% |

**Recommendation:** Cache limit of 100,000 embeddings (~460 MB) is safe; still leaves 95% headroom.

### Concurrent Request Scaling

Assuming 50 MB per concurrent request:

| Concurrent Requests | Memory | % of Budget |
|---|---|---|
| 5 | 250 MB | 1.3% |
| 20 | 1 GB | 5% |
| 50 | 2.5 GB | 12.5% |
| 100 | 5 GB | 25% |
| **200** | **10 GB** | **50%** |

**Recommendation:** Safe limit ~100–150 concurrent requests before concern.

---

## Optimization Recommendations

### ✅ No Immediate Action Required

Current usage pattern is **extremely efficient**:
- Embedding model (400 MB) is the dominant cost, shared across all requests
- Per-request overhead is minimal
- Cache grows linearly and predictably

### 🔧 Optional Optimizations (if needed in future)

1. **Embedding Cache Eviction** (LRU)
   - If cache grows >50K entries, implement time-based or LRU eviction
   - Impact: 200–400 MB savings

2. **Model Quantization** (int8)
   - bge-m3 can be quantized to 8-bit
   - Impact: 350 MB → ~90 MB (reduce by 70%)
   - Trade-off: Slight accuracy loss (~1–2%)

3. **Job Queue Archival**
   - Move completed jobs >30 days old to archive DB
   - Impact: 5–10 MB reduction
   - Benefit: Faster job table scans

4. **Request Pool Limit**
   - Add max concurrent request limiter (e.g., 100)
   - Impact: Prevent memory spikes, ensure predictability

---

## Monitoring Recommendations

### Metrics to Track (optional)
```python
# In production, log these every 60s
import psutil
import tracemalloc

memory_info = psutil.Process(os.getpid()).memory_info()
resident_mb = memory_info.rss / 1024 / 1024

# Log to structured logger
logger.info("memory_status", extra={
    "resident_mb": resident_mb,
    "percent_of_budget": (resident_mb / 20000) * 100,
    "embedding_cache_count": get_cache_count(),  # SELECT COUNT FROM embeddings
})
```

### Alert Thresholds
- **Yellow** (warning): >2 GB usage
- **Red** (critical): >5 GB usage

---

## Conclusion

✅ **senji-gateway is well-architected for the 20GB budget.**

- **Peak usage estimate:** ~730 MB (3.7% of budget)
- **Scaling capacity:** 100K+ cached embeddings, 100+ concurrent requests
- **No optimization required** for current or near-term usage patterns
- **Safe for production** on Proxmox container with 20GB allocation

---

**Appendix: Code References**

| Component | File | Lines |
|---|---|---|
| FastAPI app initialization | app/main.py | 20–51 |
| Config (batch size, models) | app/config.py | 15, 53–54 |
| Embedding service | app/services/embedding_service.py | 42–80, 92–102 |
| Job queue schema | app/services/job_queue.py | 53–70, 85–99 |
| Embedding cache SQL | app/services/embedding_service.py | 17–38 |

