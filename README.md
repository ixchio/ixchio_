# ixchio — Deep Research Engine

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-green?style=for-the-badge&logo=fastapi)
![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-purple?style=for-the-badge)
![Free](https://img.shields.io/badge/Cost-100%25%20Free-orange?style=for-the-badge)

**Multi-agent research system with STORM perspectives, reflection loops, and adaptive search.**

Built on free-tier APIs. No credit card required.

</div>

---

## What it does

You ask a research question → ixchio breaks it down, generates expert personas that debate the topic (STORM), searches the web using the best engine per sub-query, extracts full page content via Jina Reader, synthesizes with hybrid search, writes a report, self-critiques it, fills gaps with follow-up searches, and validates quality through 3-model consensus voting.

All of that runs as a single LangGraph pipeline. You get a WebSocket stream of progress and a markdown report at the end.

---

## Architecture

```
ixchio/
├── ixchio-backend/       ← FastAPI backend
│   ├── main.py          ← App entrypoint (~200 lines)
│   ├── auth.py          ← JWT signup/login
│   ├── clients/         ← API provider clients
│   ├── core/            ← Cache, DBs, rate limiters
│   └── pipeline/        ← Deep research graph orchestration
└── ixchio-client/       ← Next.js frontend
```

### Research Pipeline

```
Plan (Cerebras) → STORM Perspectives → Adaptive Search (Tavily/Jina)
→ Deep Extract (Jina Reader) → Synthesize (BM25 + Vector)
→ Write Report → Reflect (self-critique) → [Follow-up if gaps]
→ Validate (3-model consensus) → Done
```

| Stage | What happens |
|-------|-------------|
| **Plan** | Cerebras decomposes query into typed sub-questions (news/technical/general) |
| **STORM** | 3 expert personas generated, each asks 2 critical questions |
| **Adaptive Search** | Technical queries → Jina Search, news/general → Tavily |
| **Deep Extract** | Top 3 URLs scraped via Jina Reader for full page content |
| **Synthesize** | BM25 + vector hybrid fusion, deduplicated |
| **Write** | Report weaves in expert perspectives + gap fixes |
| **Reflect** | Self-critique finds 2-3 factual gaps or weak claims |
| **Follow-up** | Targeted searches to fill the gaps, then rewrites |
| **Validate** | Groq + OpenRouter + Cerebras vote on relevancy (0-10) |

---

## Providers

All free tier. Zero cost.

| Provider | Model | Free Tier | Role |
|----------|-------|-----------|------|
| **Groq** | Llama 3.3 70B Versatile | 14,400 RPD | Report writing, synthesis |
| **Cerebras** | Llama 3.3 70B | 1M tokens/day | Planning, reflection (speed brain) |
| **OpenRouter** | Llama 3.2 3B | 200 RPD | Consensus voting |
| **Tavily** | — | 1,000 credits/month | Web search (news/general) |
| **Jina AI** | — | 10M tokens | Page extraction + search grounding |
| **Pinecone** | — | 2GB free | Vector storage (production) |

---

## Quick Start

```bash
# 1. clone
git clone https://github.com/ixchio/ixchio.git
cd ixchio

# 2. backend setup
cd ixchio-backend
cp .env.example .env
# fill in your API keys (all free to get)

# 3. install
pip install -r requirements.txt

# 4. run
python main.py
```

Server starts at `http://localhost:8000`. API docs at `/docs`.

### Frontend

```bash
cd ixchio-client
npm install
npm run dev
```

Opens at `http://localhost:3000`. Sign up, then start researching.

---

## API

### Auth

```bash
# signup
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "you@email.com", "password": "pass123", "name": "You"}'

# returns: {"access_token": "eyJ...", "token_type": "bearer"}
```

### Research

```bash
# start research (needs auth token)
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"query": "impact of quantum computing on cryptography", "depth": "medium"}'

# returns: {"task_id": "abc-123", "status": "pending"}

# check status
curl http://localhost:8000/api/v1/research/abc-123
```

### WebSocket

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/research/abc-123");
ws.onmessage = (e) => {
  const { status, progress, report } = JSON.parse(e.data);
  // status: pending → running → completed/failed
  // progress: 0-100
  // report: markdown string (when completed)
};
```

---

## Environment Variables

```env
# required
GROQ_API_KEY=
OPENROUTER_API_KEY=
TAVILY_API_KEY=

# new providers (free)
CEREBRAS_API_KEY=
JINA_API_KEY=

# vector DB (set for production, leave empty for local ChromaDB)
PINECONE_API_KEY=
CHROMA_PATH=./chroma_db

# auth
JWT_SECRET=          # auto-generated if not set
PW_SALT=ixchio-salt

# server
PORT=8000
```

---

## Docker (Backend)

```bash
cd ixchio-backend
docker build -t ixchio-backend .
docker run -p 8000:8000 --env-file .env ixchio-backend
```

---

## License

MIT
