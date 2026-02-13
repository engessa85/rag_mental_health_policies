# RAG PDF Chat App (Next.js + Django + pgvector + Docker)

This project lets you:
- Preload and index a local PDF (`Book and policies.pdf`)
- Split and embed its text
- Store embeddings in Postgres with pgvector
- Chat with your PDF using retrieval-augmented generation (RAG)

## Stack
- Frontend: Next.js (TypeScript)
- Backend: Django + Django REST Framework
- Vector DB: PostgreSQL + pgvector
- LLM + Embeddings: OpenRouter API
- Orchestration: Docker Compose

## Project structure
- `backend/`: Django API for upload + chat
- `frontend/`: Next.js UI
- `docker-compose.yml`: runs all services

## Quick start
1. Create env file:
   - `cp .env.example .env`
2. Set your OpenRouter key in `.env`:
   - `OPENROUTER_API_KEY=...`
3. Build and run:
   - `docker compose up --build`
4. Open app:
   - Frontend: http://localhost:3000
   - Backend health: http://localhost:8000/api/health/

## API endpoints
- `POST /api/chat/`
  - JSON: `{ "message": "...", "document_id": 1 }`
  - `document_id` optional (if omitted, searches all docs)

## Notes
- Embedding model defaults to `openai/text-embedding-3-small` with `OPENROUTER_EMBEDDING_DIM=768`.
- Chat model defaults to `openai/gpt-4o-mini`.
- Default mode is LM-generated answers grounded in the PDF with page citations (`USE_GENERATIVE_ANSWER=1`).
- Backend startup runs `preload_pdf` and indexes `/app/data/book.pdf` once.
- On backend startup, migrations run and pgvector extension is enabled automatically.

## Common issues
- If uploads fail with empty text, the PDF may be scanned image-only (no selectable text).
- If chat/upload fail with provider errors, verify `OPENROUTER_API_KEY` and OpenRouter credits.
