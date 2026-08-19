# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A RAG (retrieval-augmented generation) chat app over a single preloaded PDF (`Book and policies.pdf`, mental health policies). Three services run under Docker Compose:

- `frontend/` — Next.js 14 (App Router, TypeScript) chat UI, single page (`app/page.tsx`) rendering `components/PdfChat.tsx`.
- `backend/` — Django + Django REST Framework API (`config/` project, `rag/` app).
- `db` — Postgres with the `pgvector` extension, storing chunk embeddings.

LLM chat completions and embeddings both go through **OpenAI directly** (via the `openai` Python client). Default chat model is `gpt-5-mini` (GPT-5 models require `max_completion_tokens` instead of the deprecated `max_tokens`, reject a custom `temperature`, and burn hidden reasoning tokens out of the same completion-token budget as visible output — see `_chat_completion_kwargs` in `services.py`, which branches on model name to handle this).

## Commands

Everything is designed to run via Docker Compose; there are no host-native dev servers configured (no local venv/npm workflow documented).

```bash
# First-time setup
cp .env.example .env   # then set OPENAI_API_KEY

# Build and run all services (frontend :3000, backend :8000, db :5432)
docker compose up --build

# Rebuild a single service
docker compose up --build backend
docker compose up --build frontend

# Tail logs
docker compose logs -f backend

# Django management commands inside the running backend container
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations rag
docker compose exec backend python manage.py preload_pdf   # re-index the configured PDF if not already indexed
docker compose exec backend python manage.py shell

# Frontend lint (from frontend/, or via the container)
docker compose exec frontend npm run lint
```

There is no test suite in this repo currently.

### Backend startup sequence (`backend/entrypoint.sh`)

On every backend container start, in order: enable the `vector` extension → run `migrate` → run `preload_pdf` (indexes `/app/data/book.pdf`, skipped if a `Document` with that filename already exists) → start `gunicorn`. When changing ingestion/chunking behavior, remember re-indexing only happens automatically for a *new* filename — delete the existing `Document` row (cascades to `DocumentChunk`) or bump `PRELOAD_PDF_NAME` to force a re-index.

## Architecture

### Backend (`backend/rag/`)

- `models.py` — `Document` (one row per ingested PDF) and `DocumentChunk` (page-scoped text chunk + `VectorField(dimensions=768)` embedding, FK to `Document`). Embedding dimension is hardcoded to 768 in the model but also configurable via `OPENAI_EMBEDDING_DIM` in settings — these must stay in sync, and changing the dimension requires a new migration.
- `services.py` — all RAG logic, no business logic lives in views:
  - `extract_pdf_pages` / `chunk_text` — PDF → per-page text → fixed-size character chunks with overlap (`CHUNK_SIZE`/`CHUNK_OVERLAP`), no token-aware splitting.
  - `embed_texts` — batches embedding calls (batch size 64) through OpenAI.
  - `ingest_pdf` / `ingest_pdf_path` — full ingestion pipeline: extract → chunk → embed → bulk create `DocumentChunk` rows.
  - `retrieve_context` — embeds the query, ranks `DocumentChunk`s by `CosineDistance` (pgvector), optionally scoped to one `document_id`, limited to `TOP_K`.
  - `generate_answer` / `stream_answer` — build a context block from retrieved chunks (page-cited), call the chat model via `_chat_completion_kwargs()` (model-aware param handling, see above). Both fall back to `_exact_quote_answer` (raw excerpts, no LLM) when `USE_GENERATIVE_ANSWER=0` **or** when the provider call raises a quota/rate-limit/insufficient-credit error (`_is_quota_error`) — this fallback path is a deliberate degradation, not a bug, so preserve it when touching error handling.
- `views.py` — thin `@api_view` functions; `chat_stream` returns newline-delimited JSON (`application/x-ndjson`) with `{"type": "delta"|"sources"|"done"|"error"}` events, consumed by the frontend's manual `ReadableStream` reader (see `PdfChat.tsx`).
- `urls.py` → mounted at `/api/` by `config/urls.py`. Endpoints: `health/`, `init-vector/`, `upload/`, `chat/`, `chat/stream/`.
- `management/commands/preload_pdf.py` — idempotent by filename (`settings.PRELOAD_PDF_NAME`), used by the entrypoint.

All tunables (chunk size/overlap, top-k, context char budget, model names, embedding dim) are environment-driven through `config/settings.py` — check there before hardcoding values.

### Frontend (`frontend/`)

Single-component app: `components/PdfChat.tsx` owns all chat state and talks directly to the backend's streaming endpoint via `fetch` + manual `ReadableStream`/`TextDecoder` parsing of the ndjson protocol above (no SSE/websocket library). `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000/api`) points at the backend. Theme (dark/light) is stored in `localStorage` and applied via a `data-theme` attribute on `<html>`, styled in `app/globals.css`.

### Data flow

1. Backend boot indexes the preloaded PDF (or `POST /api/upload/` indexes an ad-hoc PDF) → pages extracted → chunked → embedded → stored in `DocumentChunk` with pgvector embeddings.
2. `POST /api/chat/stream/` (or `/api/chat/`) embeds the incoming question, does a cosine-similarity nearest-neighbor search in Postgres, then either asks the LLM to answer grounded in the retrieved chunks (with `[Page X]` citations) or returns raw excerpts, streaming deltas back as ndjson.

### Cross-service contracts to keep in sync

- `OPENAI_EMBEDDING_DIM` (env) must match `DocumentChunk.embedding`'s `VectorField(dimensions=...)` in `models.py` — mismatches require a new migration.
- The ndjson event shape in `views.chat_stream`'s `event_stream()` and the parser in `PdfChat.tsx`'s `handleAsk` must be changed together.
- `docker-compose.yml` env defaults, `.env.example`, and `config/settings.py` `os.getenv` defaults should stay consistent when adding new settings.
