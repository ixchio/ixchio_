# ixchio — Agent Memory

## Project Overview
Multi-agent deep research engine using agentic RAG architecture. Pipeline:
Plan → STORM → Parallel Search → Gap Analysis → Targeted Search → LLM Rerank →
Deep Extract → BM25+Vector Synthesize → Write → Citation Verification → Reflect → Done

## Stack
- **Backend**: FastAPI + LangGraph + Motor (async MongoDB) + ChromaDB/Pinecone
- **Frontend**: Next.js 16 + React 19 + Tailwind 4 (minimalist white/black)
- **LLM Providers**: Groq (Llama 3.3 70B), Cerebras (Llama 3.1 8B), OpenRouter (GPT-OSS 20B)
- **Search**: Tavily (news/general), Jina AI (technical + page extraction)
- **No auth required** — open access

## Architecture (SOTA techniques)
1. **Parallel search** (Anthropic orchestrator-worker): sub-queries run concurrently via asyncio.gather
2. **Gap analysis** (Google Deep Research): detect missing coverage BEFORE writing, then do targeted search
3. **LLM reranking** (SOTA RAG): Cerebras fast-ranks results by relevance to query
4. **Citation verification** (Anthropic citation agent): per-claim source mapping replaces old 3-model consensus

## Key Paths
- `ixchio-backend/main.py` — FastAPI app entrypoint (no auth)
- `ixchio-backend/pipeline/graph.py` — LangGraph agentic research pipeline
- `ixchio-backend/pipeline/state.py` — ResearchState TypedDict
- `ixchio-backend/clients/` — API clients (groq, cerebras, openrouter, tavily, jina)
- `ixchio-backend/core/` — Cache, DB, rate limiter, circuit breaker, vector DBs
- `ixchio-client/src/app/page.tsx` — Minimalist white/black frontend

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
