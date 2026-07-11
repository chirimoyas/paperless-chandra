# Paperless-NGX Chandra 2 OCR Integration

Re-OCR Paperless-NGX documents with Chandra 2, then patch the improved markdown back into Paperless-NGX. Paperless-AI sees the better `content` on its next poll.

## Two backends, one script

**Datalab API (recommended — no GPU needed):**
- Uses the hosted Chandra 2 at `datalab.to`
- Async submit + poll API (`POST /api/v1/convert` → `GET /api/v1/convert/{id}`)
- $5 free credits, then per-page pricing
- Just needs an API key

**Local vLLM server:**
- OpenAI-compatible chat completions endpoint
- Requires an NVIDIA GPU (compute 7.0+, 12GB+ VRAM)
- Run `chandra_vllm` to start the server

The script auto-detects: if `CHANDRA_BASE_URL` contains `datalab.to`, it uses the Datalab client. Otherwise it uses vLLM.

## Quick start

```bash
cd /home/openclaw/projects/paperless-chandra
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Edit .env — set CHANDRA_API_KEY to your Datalab API key
#            — set PAPERLESS_BASE_URL and PAPERLESS_API_TOKEN

# Dry run (log only, no updates):
python -m chandra_paperless --dry-run --once

# Process specific documents by ID:
python -m chandra_paperless --process-id 42 --process-id 99

# Run as continuous poller:
python -m chandra_paperless

# Health check:
python -m chandra_paperless --health-check
```

## How it works

1. Polls Paperless-NGX for documents tagged `chandra-ocr`
2. Downloads the original file
3. Applies routing rules (skip native-text PDFs, page count, garbled text, etc.)
4. Sends to Chandra 2 (Datalab API or vLLM) for OCR
5. `PATCH`es the `content` field back to Paperless-NGX
6. Tags the document `chandra-processed` for idempotency
7. Paperless-AI picks up the improved content on its next poll

## Configuration

All settings via environment variables or a config file (JSON/YAML/TOML). Env vars win.

| Variable | Default | Description |
|---|---|---|
| `PAPERLESS_BASE_URL` | `http://localhost:8000` | Paperless-NGX URL |
| `PAPERLESS_API_TOKEN` | — | Paperless API token |
| `CHANDRA_BACKEND` | `auto` | `datalab`, `vllm`, or `auto` (detect from URL) |
| `CHANDRA_BASE_URL` | `http://localhost:8000/v1` | Chandra endpoint (vLLM) or `https://www.datalab.to` |
| `CHANDRA_API_KEY` | — | Datalab API key (required for Datalab) |
| `CHANDRA_MODEL` | `chandra` | Model name (vLLM only) |
| `POLL_INTERVAL` | `60` | Seconds between polls |
| `TAG_CHANDRA_OCR` | `chandra-ocr` | Tag that selects docs for processing |
| `PROCESSED_TAG` | `chandra-processed` | Idempotency tag (skip if present) |
| `MIN_PAGES` / `MAX_PAGES` | `1` / `0` | Page count filters |
| `SKIP_NATIVE_TEXT_PDFS` | `true` | Skip PDFs with embedded text |
| `REOCR_WHEN_GARBLED` | `false` | Only re-OCR if Tesseract output looks bad |
| `DRY_RUN` | `false` | Log but don't update Paperless |
| `ONCE` | `false` | Run one poll then exit |

## Layout

```
paperless-chandra/
├── src/chandra_paperless/
│   ├── config.py           # Settings (env + file)
│   ├── paperless_client.py # Paperless-NGX REST wrapper
│   ├── chandra_client.py   # Datalab API + vLLM client (auto-detect)
│   ├── rules.py            # Routing / filtering rules
│   ├── worker.py           # Process one document end-to-end
│   ├── daemon.py           # Polling loop
│   └── main.py             # CLI entrypoint
├── tests/                  # 42 unit tests
├── .env.example
└── pyproject.toml
```

## Datalab API details

The Datalab API is **not** OpenAI-compatible. It uses a submit-then-poll pattern:

1. `POST /api/v1/convert` with multipart file upload + `X-API-Key` header
   - Returns `{ request_id, request_check_url }`
2. `GET /api/v1/convert/{request_id}` — poll until `status: "complete"`
   - Returns `{ markdown, page_count, ... }`

The script handles all of this automatically — you just set `CHANDRA_BACKEND=datalab` and `CHANDRA_API_KEY=your-key`.

Sign up at [datalab.to](https://www.datalab.to) for an API key ($5 free credits).