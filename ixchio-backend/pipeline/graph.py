"""
Deep Research Graph — the brain of ixchio.

Pipeline flow:
  plan (Cerebras) → STORM perspectives → adaptive search (Tavily/Jina) →
  deep extract (Jina Reader) → synthesize (BM25 + Vector) → write report →
  reflect (self-critique) → [follow-up search if gaps] → validate (3-model consensus)

Each node is a pure async function that takes ResearchState and returns ResearchState.
LangGraph handles the wiring and conditional routing.
"""

import asyncio
import uuid
import numpy as np
from typing import List, Dict
from rank_bm25 import BM25Okapi

from langgraph.graph import StateGraph, END

from pipeline.state import ResearchState
from core.helpers import extract_json
from core.cache import SemanticCache
from core.circuit_breaker import CircuitBreaker
from core.rate_limiter import RateLimiter
from core.vector_db import PersistentVectorDB

from clients import GroqClient, OpenRouterClient, TavilyClient, CerebrasClient, JinaClient

# depth → (sub_queries, max_search_per_query, extract_top_n, max_reflection)
DEPTH_CONFIG = {
    "shallow": {"sub_queries": 3, "search_per_q": 2, "extract_top": 2, "max_reflect": 0},
    "medium":  {"sub_queries": 5, "search_per_q": 3, "extract_top": 3, "max_reflect": 2},
    "deep":    {"sub_queries": 8, "search_per_q": 5, "extract_top": 5, "max_reflect": 3},
}


class DeepResearchGraph:
    def __init__(self, vector_db=None):
        rl = RateLimiter()

        self.groq = GroqClient(rl, CircuitBreaker())
        self.openrouter = OpenRouterClient(rl, CircuitBreaker())
        self.tavily = TavilyClient(rl, CircuitBreaker())
        self.cerebras = CerebrasClient(rl, CircuitBreaker())
        self.jina = JinaClient(rl, CircuitBreaker())

        self._clients = [self.groq, self.openrouter, self.tavily, self.cerebras, self.jina]

        self.cache = SemanticCache()
        self.vector_db = vector_db or PersistentVectorDB()

        self.graph = self._wire_graph()

    async def close(self):
        """Shut down all aiohttp sessions cleanly."""
        for client in self._clients:
            if hasattr(client, "_session") and client._session and not client._session.closed:
                await client._session.close()

    def _wire_graph(self) -> StateGraph:
        g = StateGraph(ResearchState)

        g.add_node("plan", self._plan)
        g.add_node("storm", self._storm_perspectives)
        g.add_node("search", self._adaptive_search)
        g.add_node("extract", self._deep_extract)
        g.add_node("synthesize", self._synthesize)
        g.add_node("write", self._write_report)
        g.add_node("reflect", self._reflect)
        g.add_node("followup", self._followup_search)
        g.add_node("validate", self._validate)

        g.set_entry_point("plan")

        g.add_edge("plan", "storm")
        g.add_edge("storm", "search")
        g.add_conditional_edges("search", self._retry_or_proceed, {
            "retry": "search", "proceed": "extract"
        })
        g.add_edge("extract", "synthesize")
        g.add_edge("synthesize", "write")
        g.add_edge("write", "reflect")
        g.add_conditional_edges("reflect", self._needs_followup, {
            "followup": "followup", "done": "validate"
        })
        g.add_edge("followup", "write")
        g.add_conditional_edges("validate", self._accept_or_redo, {
            "accept": END, "redo": "write", "fail": END
        })

        return g.compile()

    def _depth_cfg(self, state: ResearchState) -> dict:
        return DEPTH_CONFIG.get(state.get("depth", "medium"), DEPTH_CONFIG["medium"])

    # ------------------------------------------------------------------
    # helpers for routing (separate counters for search vs validation)
    # ------------------------------------------------------------------
    def _retry_or_proceed(self, state: ResearchState) -> str:
        if not state["search_results"] and state["search_retry_count"] <= 2:
            return "retry"
        return "proceed"

    def _needs_followup(self, state: ResearchState) -> str:
        gaps = state.get("reflection_gaps") or []
        cfg = self._depth_cfg(state)
        if gaps and cfg["max_reflect"] > 0 and state["reflection_count"] < cfg["max_reflect"]:
            return "followup"
        return "done"

    def _accept_or_redo(self, state: ResearchState) -> str:
        word_count = len((state.get("report") or "").split())
        if word_count < 100 and state["validate_retry_count"] <= 2:
            return "redo"
        if word_count < 50:
            return "fail"
        return "accept"

    # ------------------------------------------------------------------
    # NODE: Plan — Cerebras speed brain decomposes the query
    # ------------------------------------------------------------------
    async def _plan(self, state: ResearchState) -> ResearchState:
        cfg = self._depth_cfg(state)
        print(f"⚡ [plan] breaking down: {state['query'][:60]}...")
        state["current_step"] = "Planning research"

        async def _do_plan():
            prompt = (
                f"Break this research query into {cfg['sub_queries']} diverse sub-queries. "
                f"Classify each as 'news', 'technical', or 'general'.\n"
                f"Query: {state['query']}\n"
                f'Return JSON: {{"search_queries": [{{"query": "...", "type": "news|technical|general"}}]}}'
            )
            msgs = [
                {"role": "system", "content": "Research planner. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ]
            try:
                raw = await self.cerebras.chat(msgs, temperature=0.3)
            except Exception:
                raw = await self.groq.chat(msgs, temperature=0.3)
            return extract_json(raw)

        plan, cache_status = await self.cache.get_or_compute(
            f"plan:{state['query']}", _do_plan
        )
        state["research_plan"] = plan or {}
        state["progress"] = 10
        if cache_status == "cache_hit":
            state["cache_hits"] += 1
        else:
            state["total_api_calls"] += 1
        return state

    # ------------------------------------------------------------------
    # NODE: STORM — generate expert personas who question the topic
    # ------------------------------------------------------------------
    async def _storm_perspectives(self, state: ResearchState) -> ResearchState:
        print("🧑‍🔬 [storm] generating expert panel...")
        state["current_step"] = "Generating expert panel (STORM)"

        prompt = (
            f"Topic: '{state['query']}'\n"
            f"Create 3 expert personas with *different* angles on this topic.\n"
            f"Each has: name, expertise, and 2 sharp questions they'd ask.\n"
            f'Return JSON: {{"experts": [{{"name": "...", "expertise": "...", "questions": ["...", "..."]}}]}}'
        )
        msgs = [
            {"role": "system", "content": "Academic panel organizer. JSON only."},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = await self.cerebras.chat(msgs, temperature=0.7)
        except Exception:
            raw = await self.groq.chat(msgs, temperature=0.7)

        parsed = extract_json(raw)
        experts = parsed.get("experts", [])
        state["expert_perspectives"] = experts

        extra_qs = []
        for expert in experts:
            for q in expert.get("questions", []):
                extra_qs.append({"query": q, "type": "general"})

        plan = state.get("research_plan") or {}
        existing = plan.get("search_queries", [])
        if existing and isinstance(existing[0], str):
            existing = [{"query": q, "type": "general"} for q in existing]

        plan["search_queries"] = existing + extra_qs[:4]
        state["research_plan"] = plan
        state["progress"] = 15
        state["total_api_calls"] += 1
        return state

    # ------------------------------------------------------------------
    # NODE: Adaptive Search — route each query to the right engine
    # ------------------------------------------------------------------
    async def _adaptive_search(self, state: ResearchState) -> ResearchState:
        cfg = self._depth_cfg(state)
        print(f"🔍 [search] round {state['search_round']}...")
        state["current_step"] = f"Searching (round {state['search_round']})"

        plan = state.get("research_plan") or {}
        queries = plan.get(
            "search_queries", [{"query": state["query"], "type": "general"}]
        )
        if queries and isinstance(queries[0], str):
            queries = [{"query": q, "type": "general"} for q in queries]

        max_queries = min(len(queries), state.get("max_sources", 10))
        results = state.get("search_results") or []

        for item in queries[:max_queries]:
            q = item["query"] if isinstance(item, dict) else str(item)
            q_type = item.get("type", "general") if isinstance(item, dict) else "general"

            try:
                if q_type == "technical":
                    hits = await self.jina.search(q)
                    for h in hits:
                        results.append({**h, "source_engine": "jina"})
                else:
                    resp = await self.tavily.search(q, max_results=cfg["search_per_q"])
                    for r in resp.get("results", []):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", ""),
                            "score": r.get("score", 0),
                            "source_engine": "tavily",
                        })
                state["total_api_calls"] += 1
            except Exception as e:
                state["errors"].append(f"search/{q_type}: {e}")

        state["search_results"] = results
        if not results:
            state["search_retry_count"] += 1
        state["progress"] = 30
        return state

    # ------------------------------------------------------------------
    # NODE: Deep Extract — Jina Reader pulls full page content
    # ------------------------------------------------------------------
    async def _deep_extract(self, state: ResearchState) -> ResearchState:
        cfg = self._depth_cfg(state)
        print("📖 [extract] pulling top sources via Jina Reader...")
        state["current_step"] = "Extracting source content"

        seen, top_urls = set(), []
        for r in sorted(state["search_results"], key=lambda x: x.get("score", 0), reverse=True):
            url = r.get("url", "")
            if url and url not in seen and len(top_urls) < cfg["extract_top"] + 2:
                top_urls.append(url)
                seen.add(url)

        extracted = []
        for r in state["search_results"][:state.get("max_sources", 10)]:
            extracted.append({
                "fact": r.get("content", "")[:300],
                "url": r.get("url", ""),
                "title": r.get("title", ""),
            })

        deep = []
        for url in top_urls[:cfg["extract_top"]]:
            try:
                content = await self.jina.read_url(url)
                deep.append({"url": url, "full_content": content[:3000]})
                state["total_api_calls"] += 1
            except Exception as e:
                state["errors"].append(f"jina_reader: {e}")

        # collect sources for the frontend
        source_list = []
        seen_urls = set()
        for r in state["search_results"]:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                source_list.append({
                    "title": r.get("title", ""),
                    "url": url,
                    "engine": r.get("source_engine", ""),
                    "score": r.get("score", 0),
                })
        state["sources"] = source_list

        state["extracted_data"] = extracted
        state["deep_extractions"] = deep
        state["progress"] = 50
        return state

    # ------------------------------------------------------------------
    # NODE: Synthesize — BM25 + Vector hybrid fusion
    # ------------------------------------------------------------------
    async def _synthesize(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Synthesizing findings"
        texts = [f["fact"] for f in state["extracted_data"]]

        for de in (state.get("deep_extractions") or []):
            texts.append(de["full_content"][:500])

        metadata = [
            {"url": f.get("url", ""), "title": f.get("title", "")}
            for f in state["extracted_data"]
        ]

        if not texts:
            state["synthesized_content"] = {"key_facts": [], "fact_count": 0}
            state["progress"] = 65
            return state

        self.vector_db.add_documents(texts[: len(metadata)], metadata)

        vec_hits = self.vector_db.search(state["query"], k=10)
        vec_texts = [h["text"] for h in vec_hits]

        tokenized = [t.split() for t in texts]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(state["query"].split())
        top_idx = np.argsort(scores)[-10:][::-1]
        bm25_texts = [texts[i] for i in top_idx if scores[i] > 0]

        combined, seen = [], set()
        for t in vec_texts + bm25_texts:
            if t not in seen:
                seen.add(t)
                combined.append(t)

        state["synthesized_content"] = {
            "key_facts": combined[:12],
            "fact_count": len(combined[:12]),
        }
        state["progress"] = 65
        return state

    # ------------------------------------------------------------------
    # NODE: Write Report
    # ------------------------------------------------------------------
    async def _write_report(self, state: ResearchState) -> ResearchState:
        print("✍️ [write] drafting report...")
        state["current_step"] = "Writing report"

        facts = "\n".join(state["synthesized_content"]["key_facts"][:10])

        expert_block = ""
        for ex in (state.get("expert_perspectives") or []):
            qs = ", ".join(ex.get("questions", []))
            expert_block += f"\n- {ex.get('name', 'Expert')} ({ex.get('expertise', '')}): {qs}"

        gap_block = ""
        if state.get("reflection_gaps"):
            gap_block = "\n\nPrevious draft had gaps — address these:\n"
            gap_block += "\n".join(f"- {g}" for g in state["reflection_gaps"])

        prompt = (
            f"Write a comprehensive research report on: {state['query']}\n\n"
            f"Key findings:\n{facts}\n\n"
            f"Expert perspectives to consider:{expert_block}\n"
            f"{gap_block}\n\n"
            f"Structure: Executive Summary, Key Findings (cite sources), "
            f"Perspectives Analysis, Conclusions. Use markdown."
        )

        report = await self.groq.chat(
            [
                {"role": "system", "content": "Senior research analyst. Thorough, well-cited."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
        )

        state["report"] = report
        state["progress"] = 80
        state["total_api_calls"] += 1
        return state

    # ------------------------------------------------------------------
    # NODE: Reflect — self-critique the draft
    # ------------------------------------------------------------------
    async def _reflect(self, state: ResearchState) -> ResearchState:
        cfg = self._depth_cfg(state)
        if cfg["max_reflect"] == 0:
            state["reflection_gaps"] = []
            state["progress"] = 90
            return state

        round_num = state["reflection_count"] + 1
        print(f"🤔 [reflect] round {round_num}...")
        state["current_step"] = f"Self-critiquing (round {round_num})"

        prompt = (
            f"You're a tough reviewer. Read this report on '{state['query']}' "
            f"and find 2-3 factual gaps or weak claims.\n\n"
            f"Report:\n{state['report'][:2500]}\n\n"
            f'Return JSON: {{"gaps": ["...", "..."]}}\n'
            f'If it\'s solid, return {{"gaps": []}}'
        )

        try:
            raw = await self.cerebras.chat([{"role": "user", "content": prompt}], temperature=0.2)
        except Exception:
            raw = await self.groq.chat([{"role": "user", "content": prompt}], temperature=0.2)

        parsed = extract_json(raw)
        state["reflection_gaps"] = parsed.get("gaps", [])
        state["reflection_count"] = round_num
        state["total_api_calls"] += 1
        state["progress"] = 85
        return state

    # ------------------------------------------------------------------
    # NODE: Follow-up Search — targeted gap-filling
    # ------------------------------------------------------------------
    async def _followup_search(self, state: ResearchState) -> ResearchState:
        gaps = state.get("reflection_gaps", [])
        print(f"🔄 [followup] filling {len(gaps)} gaps...")
        state["current_step"] = f"Filling {len(gaps)} knowledge gaps"

        new_facts = []
        for gap in gaps[:3]:
            try:
                resp = await self.tavily.search(f"{state['query']} {gap}", max_results=2)
                for r in resp.get("results", []):
                    new_facts.append(r.get("content", "")[:300])
                state["total_api_calls"] += 1
            except Exception as e:
                state["errors"].append(f"followup: {e}")

        existing = state["synthesized_content"].get("key_facts", [])
        state["synthesized_content"]["key_facts"] = existing + new_facts
        state["synthesized_content"]["fact_count"] = len(state["synthesized_content"]["key_facts"])
        state["search_round"] += 1
        state["progress"] = 70
        return state

    # ------------------------------------------------------------------
    # NODE: Validate — 3-model consensus vote
    # ------------------------------------------------------------------
    async def _validate(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Validating report quality"
        report = state.get("report", "")
        if len(report.split()) < 100:
            state["validate_retry_count"] += 1
            state["progress"] = 100
            return state

        prompt = (
            f"Rate this report for '{state['query']}' on relevancy and consistency (0-10).\n\n"
            f"Report:\n{report[:2000]}\n\n"
            f'Return JSON: {{"relevancy": N, "consistency": N}}'
        )

        evals = [
            self.groq.chat([{"role": "user", "content": prompt}], temperature=0.1),
            self.openrouter.chat([{"role": "user", "content": prompt}], temperature=0.1),
        ]
        try:
            evals.append(self.cerebras.chat([{"role": "user", "content": prompt}], temperature=0.1))
        except Exception:
            evals.append(self.groq.chat([{"role": "user", "content": prompt}], temperature=0.5))

        results = await asyncio.gather(*evals, return_exceptions=True)

        scores = []
        for res in results:
            if not isinstance(res, Exception):
                parsed = extract_json(res)
                if "relevancy" in parsed:
                    scores.append(parsed)

        if scores:
            avg = sum(s.get("relevancy", 5) for s in scores) / len(scores)
            print(f"🔬 [validate] consensus: {avg:.1f}/10")
            if avg < 6.0:
                state["validate_retry_count"] += 1

        state["progress"] = 100
        state["current_step"] = "Complete"
        return state

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    async def run(self, query: str, depth: str = "medium", max_sources: int = 10, task_id: str = None) -> ResearchState:
        initial = ResearchState(
            query=query,
            depth=depth,
            max_sources=max_sources,
            task_id=task_id or str(uuid.uuid4()),
            research_plan=None,
            expert_perspectives=None,
            search_results=None,
            extracted_data=None,
            deep_extractions=None,
            synthesized_content=None,
            report=None,
            reflection_gaps=None,
            sources=None,
            current_step="Initializing",
            progress=0,
            search_retry_count=0,
            validate_retry_count=0,
            search_round=1,
            reflection_count=0,
            errors=[],
            cache_hits=0,
            total_api_calls=0,
        )
        return await self.graph.ainvoke(initial)
