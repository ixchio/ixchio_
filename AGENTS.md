# ixchio — Agent Memory

## Project Overview
Multi-agent deep research engine. Users submit queries → LangGraph pipeline breaks them down via STORM perspectives, searches the web (Tavily/Jina), extracts content, synthesizes with BM25+vector hybrid, writes reports, self-critiques, and validates via 3-model consensus.

## Stack
- **Backend**: FastAPI + LangGraph + Motor (async MongoDB) + ChromaDB/Pinecone
- **Frontend**: Next.js 16 + React 19 + Tailwind 4 + Framer Motion
- **LLM Providers**: Groq (Llama 3.3 70B), Cerebras (Llama 3.3 70B), OpenRouter (Llama 3.2 3B)
- **Search**: Tavily (news/general), Jina AI (technical + page extraction)

## Key Paths
- `ixchio-backend/main.py` — FastAPI app entrypoint
- `ixchio-backend/pipeline/graph.py` — LangGraph research pipeline (the brain)
- `ixchio-backend/auth.py` — JWT auth with bcrypt
- `ixchio-backend/clients/` — API provider clients (groq, cerebras, openrouter, tavily, jina)
- `ixchio-backend/core/` — Cache, DB, rate limiter, circuit breaker, vector DBs
- `ixchio-client/src/app/page.tsx` — Single-page frontend (auth + chat UI)

## Build & Run
```bash
# Backend
cd ixchio-backend && pip install -r requirements.txt && python main.py

# Frontend
cd ixchio-client && npm install && npm run dev

# Tests
cd ixchio-backend && pytest
```

## Known Issues (from audit)
- aiohttp sessions never closed (resource leak)
- WebSocket endpoint auth is optional (security gap)
- `max_sources` and `depth` params are accepted but never used
- Shared RateLimiter not concurrency-safe
- ChromaDB ID generation has race condition
- `retry_count` shared between search and validation loops
- Frontend has no history page despite backend support
- No table rendering in markdown (missing remark-gfm)
