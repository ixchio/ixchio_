"""
ixchio — Deep Research Engine
Thin FastAPI shell. All the real logic lives in pipeline/, clients/, and core/.
No auth required — open access.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import re
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.helpers import sanitize_query
from core.db import get_db, ensure_indexes, ping as mongo_ping
from core.demo_data import DEMO_TASK_DATA
from pipeline.graph import DeepResearchGraph

logger = logging.getLogger("ixchio")

_mem_tasks: dict[str, dict] = {}
_mem_task_by_query: dict[str, str] = {}
_tasks_lock = asyncio.Lock()

research_graph: DeepResearchGraph | None = None

MAX_TASK_AGE = 3600

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_valid_uuid(val: str) -> bool:
    return bool(_UUID_RE.match(val))


async def _evict_old_tasks():
    """Cleanup loop for in-memory mode. Mongo uses TTL indexes instead."""
    while True:
        await asyncio.sleep(600)
        db = get_db()
        if db is not None:
            continue

        now = _now_utc()
        async with _tasks_lock:
            dead = []
            for tid, info in _mem_tasks.items():
                try:
                    created = datetime.fromisoformat(info["created_at"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if (now - created).total_seconds() > MAX_TASK_AGE:
                        dead.append(tid)
                except (KeyError, ValueError):
                    dead.append(tid)

            for tid in dead:
                q = _mem_tasks[tid].get("query")
                if q and _mem_task_by_query.get(q) == tid:
                    del _mem_task_by_query[q]
                del _mem_tasks[tid]


def _get_cors_origins() -> list[str]:
    extra = os.getenv("CORS_ORIGINS", "")
    origins = [
        "https://ixchio.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:12000",
        "http://127.0.0.1:12000",
    ]
    if extra:
        origins.extend(o.strip() for o in extra.split(",") if o.strip())
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    global research_graph
    logger.info("booting ixchio...")

    await ensure_indexes()

    mongo_ok = await mongo_ping()
    logger.info("mongo %s", "connected" if mongo_ok else "unavailable — in-memory mode")

    if os.getenv("PINECONE_API_KEY"):
        from core.pinecone_db import PineconeDB
        vdb = PineconeDB()
        logger.info("pinecone loaded")
    else:
        from core.lightweight_vdb import LightweightVectorDB
        vdb = LightweightVectorDB()
        logger.info("lightweight in-memory vector DB (no torch/chromadb)")

    research_graph = DeepResearchGraph(vector_db=vdb)
    cleanup = asyncio.create_task(_evict_old_tasks())
    logger.info("ready")
    yield
    # cleanup aiohttp sessions on shutdown
    await research_graph.close()
    cleanup.cancel()


app = FastAPI(
    title="ixchio Deep Research Engine",
    description="Multi-agent deep research with STORM perspectives, reflection loops, and adaptive search routing. No auth required.",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- task helpers (mongo vs memory) ----

async def _save_task(task: dict):
    db = get_db()
    if db is not None:
        await db.research_tasks.update_one(
            {"task_id": task["task_id"]},
            {"$set": task},
            upsert=True,
        )
    else:
        async with _tasks_lock:
            _mem_tasks[task["task_id"]] = task


async def _get_task(task_id: str) -> dict | None:
    db = get_db()
    if db is not None:
        return await db.research_tasks.find_one({"task_id": task_id}, {"_id": 0})
    return _mem_tasks.get(task_id)


async def _find_task_by_query(query: str) -> dict | None:
    db = get_db()
    if db is not None:
        return await db.research_tasks.find_one(
            {"query": query, "status": {"$in": ["pending", "running", "completed"]}},
            {"_id": 0},
        )
    async with _tasks_lock:
        tid = _mem_task_by_query.get(query)
        if tid and tid in _mem_tasks:
            t = _mem_tasks[tid]
            if t.get("status") in ("pending", "running", "completed"):
                return t
    return None


# ---- research routes ----

VALID_DEPTHS = {"shallow", "medium", "deep"}


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    depth: str = Field(default="medium")
    max_sources: int = Field(default=10, ge=1, le=50)


@app.post("/api/v1/research", tags=["Research"])
async def create_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
):
    safe_q = sanitize_query(request.query)
    depth = request.depth if request.depth in VALID_DEPTHS else "medium"

    # demo mode
    if safe_q.lower() in ("demo", "impact of quantum computing on cryptography"):
        demo_copy = DEMO_TASK_DATA.copy()
        demo_copy["created_at"] = _now_utc().isoformat()
        demo_copy["task_id"] = str(uuid.uuid4())
        await _save_task(demo_copy)
        return {"task_id": demo_copy["task_id"], "status": "completed", "is_demo": True}

    # dedup check (mongo path doesn't need a lock)
    db = get_db()
    if db is not None:
        existing = await db.research_tasks.find_one(
            {"query": safe_q, "status": {"$in": ["pending", "running", "completed"]}},
            {"_id": 0},
        )
        if existing:
            return {"task_id": existing["task_id"], "status": "deduplicated"}
    else:
        async with _tasks_lock:
            tid = _mem_task_by_query.get(safe_q)
            if tid and tid in _mem_tasks:
                t = _mem_tasks[tid]
                if t.get("status") in ("pending", "running", "completed"):
                    return {"task_id": t["task_id"], "status": "deduplicated"}

    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "status": "pending",
        "query": safe_q,
        "depth": depth,
        "created_at": _now_utc().isoformat(),
        "progress": 0,
        "current_step": "Queued",
    }

    async with _tasks_lock:
        _mem_task_by_query[safe_q] = task_id

    await _save_task(task)

    request.query = safe_q
    request.depth = depth
    background_tasks.add_task(_run_research, task_id, request)
    return {"task_id": task_id, "status": "pending"}


async def _run_research(task_id: str, request: ResearchRequest):
    try:
        task = await _get_task(task_id) or {"task_id": task_id}
        task["status"] = "running"
        task["current_step"] = "Initializing pipeline"
        await _save_task(task)

        result = await research_graph.run(
            query=request.query,
            depth=request.depth,
            max_sources=request.max_sources,
            task_id=task_id,
        )

        task.update({
            "status": "completed",
            "report": result.get("report", ""),
            "progress": 100,
            "current_step": "Done",
            "sources": result.get("sources", []),
            "stats": {
                "api_calls": result.get("total_api_calls", 0),
                "cache_hits": result.get("cache_hits", 0),
                "errors": result.get("errors", []),
            },
        })
        await _save_task(task)

    except Exception as e:
        logger.exception("Research task %s failed", task_id)
        task = await _get_task(task_id) or {"task_id": task_id}
        task.update({"status": "failed", "error": str(e), "progress": 0})
        await _save_task(task)


@app.get("/api/v1/research/{task_id}", tags=["Research"])
async def get_research(task_id: str):
    if not _is_valid_uuid(task_id):
        raise HTTPException(400, "Invalid task ID format")
    task = await _get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


# ---- websocket (live progress) ----

@app.websocket("/ws/research/{task_id}")
async def ws_research(ws: WebSocket, task_id: str):
    if not _is_valid_uuid(task_id):
        await ws.close(code=4000)
        return

    await ws.accept()
    try:
        while True:
            task = await _get_task(task_id)
            if not task:
                await ws.send_json({"error": "not found"})
                break

            await ws.send_json({
                "status": task["status"],
                "progress": task.get("progress", 0),
                "current_step": task.get("current_step", ""),
                "report": task.get("report", ""),
                "sources": task.get("sources", []),
                "error": task.get("error", ""),
            })

            if task["status"] in ("completed", "failed"):
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for task %s", task_id)


# ---- health ----

@app.get("/health", tags=["System"])
async def health():
    mongo_ok = await mongo_ping()
    return {
        "status": "healthy",
        "mongo": "connected" if mongo_ok else "unavailable (in-memory mode)",
        "active_tasks": len(_mem_tasks),
        "cache_stats": research_graph.cache.get_stats() if research_graph else {},
    }


# ---- history (all tasks, no auth) ----

@app.get("/api/v1/history", tags=["Research"])
async def get_history():
    db = get_db()
    if db is None:
        all_tasks = [
            {k: t[k] for k in ("task_id", "query", "status", "created_at", "progress", "depth") if k in t}
            for t in _mem_tasks.values()
        ]
        return {"tasks": sorted(all_tasks, key=lambda x: x.get("created_at", ""), reverse=True)[:50]}

    cursor = db.research_tasks.find(
        {},
        {"_id": 0, "task_id": 1, "query": 1, "status": 1, "created_at": 1, "progress": 1, "depth": 1},
    ).sort("created_at", -1).limit(50)

    tasks = await cursor.to_list(length=50)
    return {"tasks": tasks}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
