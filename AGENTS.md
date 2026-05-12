# ixchio — Agent Memory

## Project Overview
Multi-agent deep research engine using agentic RAG architecture. Pipeline:
Plan → STORM → Parallel Search → Gap Analysis → Targeted Search → LLM Rerank →
Deep Extract → BM25+Vector Synthesize → Write → Citation Verification → Reflect → Done

## Stack
- **Backend**: FastAPI + LangGraph + Motor (async MongoDB)
- **Vector DB**: LightweightVectorDB (TF-IDF, pure Python) for free tier; PersistentVectorDB (ChromaDB) or PineconeDB for production
- **Frontend**: Next.js 16 + React 19 + Tailwind 4 (minimalist dark/light)
- **LLM Providers**: Groq (Llama 3.3 70B), Cerebras (Llama 3.1 8B), OpenRouter (GPT-OSS 20B)
- **Search**: Tavily (news/general), Jina AI (technical + page extraction), DuckDuckGo (free fallback)
- **No auth required** — open access

## Deployment
- **Backend**: Render free tier (ixchio.onrender.com) — auto-deploys from main
- **Frontend**: Vercel (ixchio.vercel.app) — auto-deploys from main
- **CRITICAL**: Render free tier = 512MB RAM, 0.1 CPU. No torch/chromadb/sentence-transformers — use LightweightVectorDB only.

## Architecture (SOTA techniques)
1. **Parallel search** (Anthropic orchestrator-worker): sub-queries run concurrently via asyncio.gather
2. **Gap analysis** (Google Deep Research): detect missing coverage BEFORE writing, then do targeted search
3. **LLM reranking** (SOTA RAG): Cerebras fast-ranks results by relevance to query
4. **Citation verification** (Anthropic citation agent): per-claim source mapping replaces old 3-model consensus
5. **Progress streaming**: on_progress callback from graph nodes → task store → WebSocket/polling → frontend

## Key Paths
- `ixchio-backend/main.py` — FastAPI app entrypoint (no auth)
- `ixchio-backend/pipeline/graph.py` — LangGraph agentic research pipeline
- `ixchio-backend/pipeline/state.py` — ResearchState TypedDict
- `ixchio-backend/clients/` — API clients (groq, cerebras, openrouter, tavily, jina, duckduckgo)
- `ixchio-backend/core/lightweight_vdb.py` — TF-IDF vector DB (zero deps, for free tier)
- `ixchio-backend/core/vector_db.py` — ChromaDB vector DB (needs torch, for production)
- `ixchio-backend/core/` — Cache, DB, rate limiter, circuit breaker, vector DBs
- `ixchio-client/src/app/page.tsx` — Minimalist dark/light frontend with conversation UI

## Build & Run
```bash
cd ixchio-backend && pip install -r requirements.txt && python main.py
cd ixchio-client && npm install && npm run dev
cd ixchio-backend && pytest  # 44 tests
```

## Depth Config
- **shallow**: 3 sub-queries, 2 results/query, 2 extractions, 0 reflection rounds
- **medium**: 5 sub-queries, 3 results/query, 3 extractions, 1 reflection round
- **deep**: 8 sub-queries, 5 results/query, 5 extractions, 2 reflection rounds

## Known Pitfalls (Learn from past bugs)
1. **asyncio.Lock is NOT re-entrant**: Never nest `async with _tasks_lock` calls. If function A holds the lock and calls function B which also acquires the lock → permanent deadlock. Inline the logic instead.
2. **Render free tier RAM**: 512MB total. torch alone uses ~800MB. Always use LightweightVectorDB for free tier deployments.
3. **Progress streaming**: LangGraph `ainvoke()` doesn't stream intermediate state. Must use `on_progress` callback and persist to task store manually.
4. **WebSocket fallback**: Always handle both `onerror` AND `onclose` in frontend WS code. Track completion state to avoid double polling.
5. **History refetch**: Don't re-fetch on every state change. Fetch once on mount + after research completion.
