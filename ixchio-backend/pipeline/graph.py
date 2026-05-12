"""
Deep Research Graph — the brain of ixchio.

Architecture (inspired by Anthropic orchestrator-worker + Google Deep Research):
  plan -> STORM -> parallel search -> gap analysis -> targeted search ->
  rerank -> extract -> synthesize -> write -> verify citations ->
  reflect -> [followup if gaps] -> done

Key upgrades over vanilla STORM:
  1. Parallel search: sub-queries run concurrently via asyncio.gather
  2. Gap analysis: after initial search, detect missing coverage and generate
     targeted follow-up queries BEFORE writing (Google Deep Research pattern)
  3. LLM reranking: fast LLM scores results by relevance (SOTA RAG technique)
  4. Citation verification: replaces 3-model consensus with per-claim source
     mapping (Anthropic citation agent pattern)
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

from clients import GroqClient, OpenRouterClient, TavilyClient, CerebrasClient, JinaClient, DuckDuckGoClient

DEPTH_CONFIG = {
    "shallow": {"sub_queries": 3, "search_per_q": 2, "extract_top": 2, "max_reflect": 0},
    "medium":  {"sub_queries": 5, "search_per_q": 3, "extract_top": 3, "max_reflect": 1},
    "deep":    {"sub_queries": 8, "search_per_q": 5, "extract_top": 5, "max_reflect": 2},
}


class DeepResearchGraph:
    def __init__(self, vector_db=None):
        rl = RateLimiter()
        self.groq = GroqClient(rl, CircuitBreaker())
        self.openrouter = OpenRouterClient(rl, CircuitBreaker())
        self.tavily = TavilyClient(rl, CircuitBreaker())
        self.cerebras = CerebrasClient(rl, CircuitBreaker())
        self.jina = JinaClient(rl, CircuitBreaker())
        self.ddg = DuckDuckGoClient(rl, CircuitBreaker())
        self._clients = [self.groq, self.openrouter, self.tavily, self.cerebras, self.jina]
        self.cache = SemanticCache()
        self.vector_db = vector_db or PersistentVectorDB()
        self.graph = self._wire_graph()

    async def close(self):
        for c in self._clients:
            if hasattr(c, "_session") and c._session and not c._session.closed:
                await c._session.close()

    def _wire_graph(self) -> StateGraph:
        g = StateGraph(ResearchState)
        g.add_node("plan", self._plan)
        g.add_node("storm", self._storm_perspectives)
        g.add_node("search", self._parallel_search)
        g.add_node("gap_analysis", self._gap_analysis)
        g.add_node("targeted_search", self._targeted_search)
        g.add_node("rerank", self._rerank)
        g.add_node("extract", self._deep_extract)
        g.add_node("synthesize", self._synthesize)
        g.add_node("write", self._write_report)
        g.add_node("verify", self._verify_citations)
        g.add_node("reflect", self._reflect)
        g.add_node("followup", self._followup_search)

        g.set_entry_point("plan")
        g.add_edge("plan", "storm")
        g.add_edge("storm", "search")
        g.add_conditional_edges("search", self._retry_or_proceed, {
            "retry": "search", "proceed": "gap_analysis"
        })
        g.add_conditional_edges("gap_analysis", self._has_gaps_to_fill, {
            "search_more": "targeted_search", "sufficient": "rerank"
        })
        g.add_edge("targeted_search", "rerank")
        g.add_edge("rerank", "extract")
        g.add_edge("extract", "synthesize")
        g.add_edge("synthesize", "write")
        g.add_edge("write", "verify")
        g.add_edge("verify", "reflect")
        g.add_conditional_edges("reflect", self._needs_followup, {
            "followup": "followup", "done": END
        })
        g.add_edge("followup", "write")
        return g.compile()

    def _cfg(self, state: ResearchState) -> dict:
        return DEPTH_CONFIG.get(state.get("depth", "medium"), DEPTH_CONFIG["medium"])

    # ---- routing helpers ----

    def _retry_or_proceed(self, state: ResearchState) -> str:
        if not state["search_results"] and state["search_retry_count"] <= 2:
            return "retry"
        return "proceed"

    def _has_gaps_to_fill(self, state: ResearchState) -> str:
        gaps = state.get("reflection_gaps") or []
        if gaps and state["search_round"] <= 2:
            return "search_more"
        return "sufficient"

    def _needs_followup(self, state: ResearchState) -> str:
        gaps = state.get("reflection_gaps") or []
        cfg = self._cfg(state)
        if gaps and cfg["max_reflect"] > 0 and state["reflection_count"] < cfg["max_reflect"]:
            return "followup"
        return "done"

    # ---- NODE: Plan ----

    async def _plan(self, state: ResearchState) -> ResearchState:
        cfg = self._cfg(state)
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

    # ---- NODE: STORM perspectives ----

    async def _storm_perspectives(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Generating expert perspectives"
        prompt = (
            f"Topic: '{state['query']}'\n"
            f"Create 3 expert personas with different angles on this topic.\n"
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

        extra_qs = [{"query": q, "type": "general"}
                    for ex in experts for q in ex.get("questions", [])]

        plan = state.get("research_plan") or {}
        existing = plan.get("search_queries", [])
        if existing and isinstance(existing[0], str):
            existing = [{"query": q, "type": "general"} for q in existing]
        plan["search_queries"] = existing + extra_qs[:4]
        state["research_plan"] = plan
        state["progress"] = 15
        state["total_api_calls"] += 1
        return state

    # ---- NODE: Parallel Search (Anthropic orchestrator-worker pattern) ----

    async def _parallel_search(self, state: ResearchState) -> ResearchState:
        cfg = self._cfg(state)
        state["current_step"] = f"Searching in parallel (round {state['search_round']})"

        plan = state.get("research_plan") or {}
        queries = plan.get("search_queries", [{"query": state["query"], "type": "general"}])
        if queries and isinstance(queries[0], str):
            queries = [{"query": q, "type": "general"} for q in queries]

        max_q = min(len(queries), state.get("max_sources", 10))
        results = state.get("search_results") or []

        async def _search_one(item):
            q = item["query"] if isinstance(item, dict) else str(item)
            q_type = item.get("type", "general") if isinstance(item, dict) else "general"
            hits = []
            try:
                if q_type == "technical":
                    for h in await self.jina.search(q):
                        hits.append({**h, "source_engine": "jina"})
                else:
                    try:
                        resp = await self.tavily.search(q, max_results=cfg["search_per_q"])
                    except Exception:
                        resp = await self.ddg.search(q, max_results=cfg["search_per_q"])
                    for r in resp.get("results", []):
                        hits.append({
                            "title": r.get("title", ""), "url": r.get("url", ""),
                            "content": r.get("content", ""), "score": r.get("score", 0),
                            "source_engine": "tavily",
                        })
            except Exception as e:
                state["errors"].append(f"search: {e}")
            return hits

        batch_results = await asyncio.gather(
            *[_search_one(q) for q in queries[:max_q]]
        )
        for batch in batch_results:
            results.extend(batch)
        state["total_api_calls"] += max_q

        state["search_results"] = results
        if not results:
            state["search_retry_count"] += 1
        state["progress"] = 30
        return state

    # ---- NODE: Gap Analysis (Google Deep Research pattern) ----

    async def _gap_analysis(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Analyzing coverage gaps"
        results = state.get("search_results") or []
        if not results or state["search_round"] > 1:
            state["reflection_gaps"] = []
            state["progress"] = 35
            return state

        snippets = "\n".join(r.get("content", "")[:150] for r in results[:10])
        prompt = (
            f"Research topic: {state['query']}\n\n"
            f"We found these results:\n{snippets}\n\n"
            f"What 2-3 important aspects of this topic are NOT covered by these results? "
            f"Generate targeted search queries to fill the gaps.\n"
            f'Return JSON: {{"gaps": ["description..."], "queries": [{{"query": "...", "type": "general"}}]}}'
        )
        try:
            raw = await self.cerebras.chat(
                [{"role": "user", "content": prompt}], temperature=0.3)
        except Exception:
            raw = await self.groq.chat(
                [{"role": "user", "content": prompt}], temperature=0.3)

        parsed = extract_json(raw)
        state["reflection_gaps"] = parsed.get("gaps", [])

        new_queries = parsed.get("queries", [])
        if new_queries:
            plan = state.get("research_plan") or {}
            plan["gap_queries"] = new_queries[:3]
            state["research_plan"] = plan

        state["total_api_calls"] += 1
        state["progress"] = 35
        return state

    # ---- NODE: Targeted Search (fills gaps found by gap_analysis) ----

    async def _targeted_search(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Filling coverage gaps"
        plan = state.get("research_plan") or {}
        gap_queries = plan.get("gap_queries", [])
        if not gap_queries:
            return state

        results = state.get("search_results") or []

        async def _search_gap(item):
            q = item["query"] if isinstance(item, dict) else str(item)
            hits = []
            try:
                try:
                    resp = await self.tavily.search(q, max_results=2)
                except Exception:
                    resp = await self.ddg.search(q, max_results=2)
                for r in resp.get("results", []):
                    hits.append({
                        "title": r.get("title", ""), "url": r.get("url", ""),
                        "content": r.get("content", ""), "score": r.get("score", 0),
                        "source_engine": "tavily",
                    })
            except Exception as e:
                state["errors"].append(f"gap_search: {e}")
            return hits

        batch = await asyncio.gather(*[_search_gap(q) for q in gap_queries[:3]])
        for hits in batch:
            results.extend(hits)
        state["total_api_calls"] += len(gap_queries[:3])

        state["search_results"] = results
        state["search_round"] += 1
        state["reflection_gaps"] = []
        state["progress"] = 40
        return state

    # ---- NODE: LLM Reranking (SOTA RAG technique) ----

    async def _rerank(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Reranking sources by relevance"
        results = state.get("search_results") or []
        if len(results) <= 3:
            state["reranked_results"] = results
            state["progress"] = 45
            return state

        # deduplicate by URL
        seen, unique = set(), []
        for r in results:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(r)

        items = "\n".join(
            f"[{i}] {r.get('title', 'Untitled')}: {r.get('content', '')[:120]}"
            for i, r in enumerate(unique[:20])
        )
        prompt = (
            f"Research query: {state['query']}\n\n"
            f"Rank these search results by relevance (most relevant first). "
            f"Return the indices of the top 10 most relevant results.\n\n"
            f"{items}\n\n"
            f'Return JSON: {{"ranked_indices": [0, 3, 7, ...]}}'
        )
        try:
            raw = await self.cerebras.chat(
                [{"role": "user", "content": prompt}], temperature=0.1)
            parsed = extract_json(raw)
            indices = parsed.get("ranked_indices", [])
            if indices and all(isinstance(i, int) for i in indices):
                reranked = [unique[i] for i in indices if i < len(unique)]
                picked = set(indices)
                for i, r in enumerate(unique):
                    if i not in picked:
                        reranked.append(r)
                state["reranked_results"] = reranked
            else:
                state["reranked_results"] = unique
        except Exception:
            state["reranked_results"] = unique

        state["total_api_calls"] += 1
        state["progress"] = 45
        return state

    # ---- NODE: Deep Extract ----

    async def _deep_extract(self, state: ResearchState) -> ResearchState:
        cfg = self._cfg(state)
        state["current_step"] = "Extracting full page content"
        ranked = state.get("reranked_results") or state.get("search_results") or []

        top_urls, seen = [], set()
        for r in ranked:
            url = r.get("url", "")
            if url and url not in seen and len(top_urls) < cfg["extract_top"] + 2:
                top_urls.append(url)
                seen.add(url)

        extracted = [
            {"fact": r.get("content", "")[:300], "url": r.get("url", ""),
             "title": r.get("title", "")}
            for r in ranked[:state.get("max_sources", 10)]
        ]

        deep = []
        for url in top_urls[:cfg["extract_top"]]:
            try:
                content = await self.jina.read_url(url)
                deep.append({"url": url, "full_content": content[:3000]})
                state["total_api_calls"] += 1
            except Exception as e:
                state["errors"].append(f"extract: {e}")

        source_list, seen_urls = [], set()
        for r in ranked:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                source_list.append({
                    "title": r.get("title", ""), "url": url,
                    "engine": r.get("source_engine", ""), "score": r.get("score", 0),
                })
        state["sources"] = source_list
        state["extracted_data"] = extracted
        state["deep_extractions"] = deep
        state["progress"] = 55
        return state

    # ---- NODE: Synthesize (BM25 + Vector hybrid) ----

    async def _synthesize(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Synthesizing findings"
        texts = [f["fact"] for f in state["extracted_data"]]
        for de in (state.get("deep_extractions") or []):
            texts.append(de["full_content"][:500])

        metadata = [{"url": f.get("url", ""), "title": f.get("title", "")}
                    for f in state["extracted_data"]]

        if not texts:
            state["synthesized_content"] = {"key_facts": [], "fact_count": 0}
            state["progress"] = 65
            return state

        self.vector_db.add_documents(texts[:len(metadata)], metadata)
        vec_texts = [h["text"] for h in self.vector_db.search(state["query"], k=10)]

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
            "key_facts": combined[:15], "fact_count": len(combined[:15]),
        }
        state["progress"] = 65
        return state

    # ---- NODE: Write Report ----

    async def _write_report(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Writing report"
        facts = "\n".join(state["synthesized_content"]["key_facts"][:12])

        expert_block = ""
        for ex in (state.get("expert_perspectives") or []):
            qs = ", ".join(ex.get("questions", []))
            expert_block += f"\n- {ex.get('name', 'Expert')} ({ex.get('expertise', '')}): {qs}"

        gap_block = ""
        if state.get("reflection_gaps"):
            gap_block = "\nPrevious draft had gaps — address these:\n"
            gap_block += "\n".join(f"- {g}" for g in state["reflection_gaps"])

        citation_block = ""
        cr = state.get("citation_report") or {}
        if cr.get("unsupported"):
            citation_block = "\nFix these unsupported claims from previous draft:\n"
            citation_block += "\n".join(f"- {c}" for c in cr["unsupported"][:3])

        prompt = (
            f"Write a comprehensive research report on: {state['query']}\n\n"
            f"Key findings:\n{facts}\n\n"
            f"Expert perspectives:{expert_block}\n"
            f"{gap_block}{citation_block}\n\n"
            f"Structure: Executive Summary, Key Findings (cite sources), "
            f"Analysis, Conclusions. Use markdown. Be thorough and precise."
        )

        report = await self.groq.chat(
            [{"role": "system", "content": "Senior research analyst. Thorough, well-cited, factual."},
             {"role": "user", "content": prompt}],
            max_tokens=1500,
        )
        state["report"] = report
        state["progress"] = 80
        state["total_api_calls"] += 1
        return state

    # ---- NODE: Verify Citations (Anthropic citation agent pattern) ----

    async def _verify_citations(self, state: ResearchState) -> ResearchState:
        state["current_step"] = "Verifying citations"
        report = state.get("report", "")
        if len(report.split()) < 50:
            state["citation_report"] = {"verified": 0, "unsupported": []}
            state["progress"] = 85
            return state

        sources_summary = "\n".join(
            f"- {s.get('title', 'Untitled')}: {s.get('url', '')}"
            for s in (state.get("sources") or [])[:15]
        )
        facts_summary = "\n".join(
            state["synthesized_content"]["key_facts"][:8]
        )

        prompt = (
            f"You are a citation verifier. Check this report against the sources and evidence.\n\n"
            f"Report:\n{report[:2000]}\n\n"
            f"Available sources:\n{sources_summary}\n\n"
            f"Evidence collected:\n{facts_summary[:1500]}\n\n"
            f"Identify claims in the report that are NOT supported by the sources/evidence. "
            f"Also count how many claims ARE properly supported.\n"
            f'Return JSON: {{"verified_count": N, "unsupported": ["claim1...", "claim2..."]}}'
        )
        try:
            raw = await self.cerebras.chat(
                [{"role": "user", "content": prompt}], temperature=0.1)
        except Exception:
            raw = await self.groq.chat(
                [{"role": "user", "content": prompt}], temperature=0.1)

        parsed = extract_json(raw)
        state["citation_report"] = {
            "verified": parsed.get("verified_count", 0),
            "unsupported": parsed.get("unsupported", []),
        }
        state["total_api_calls"] += 1
        state["progress"] = 88
        return state

    # ---- NODE: Reflect ----

    async def _reflect(self, state: ResearchState) -> ResearchState:
        cfg = self._cfg(state)
        cr = state.get("citation_report") or {}
        unsupported = cr.get("unsupported", [])

        if cfg["max_reflect"] == 0 and not unsupported:
            state["reflection_gaps"] = []
            state["progress"] = 100
            state["current_step"] = "Complete"
            return state

        # feed unsupported claims back for rewrite
        if unsupported and state["reflection_count"] < cfg["max_reflect"] + 1:
            state["reflection_gaps"] = unsupported[:3]
            state["reflection_count"] += 1
            state["current_step"] = "Fixing unsupported claims"
            state["progress"] = 90
            return state

        if state["reflection_count"] >= cfg["max_reflect"]:
            state["reflection_gaps"] = []
            state["progress"] = 100
            state["current_step"] = "Complete"
            return state

        round_num = state["reflection_count"] + 1
        state["current_step"] = f"Self-critiquing (round {round_num})"
        prompt = (
            f"Tough reviewer. Report on '{state['query']}'. Find 2-3 factual gaps.\n\n"
            f"Report:\n{state['report'][:2500]}\n\n"
            f'Return JSON: {{"gaps": ["...", "..."]}}\n'
            f'If solid, return {{"gaps": []}}'
        )
        try:
            raw = await self.cerebras.chat(
                [{"role": "user", "content": prompt}], temperature=0.2)
        except Exception:
            raw = await self.groq.chat(
                [{"role": "user", "content": prompt}], temperature=0.2)

        parsed = extract_json(raw)
        state["reflection_gaps"] = parsed.get("gaps", [])
        state["reflection_count"] = round_num
        state["total_api_calls"] += 1
        state["progress"] = 92
        return state

    # ---- NODE: Follow-up Search ----

    async def _followup_search(self, state: ResearchState) -> ResearchState:
        gaps = state.get("reflection_gaps", [])
        state["current_step"] = f"Filling {len(gaps)} gaps"

        new_facts = []
        for gap in gaps[:3]:
            try:
                try:
                    resp = await self.tavily.search(
                        f"{state['query']} {gap}", max_results=2)
                except Exception:
                    resp = await self.ddg.search(
                        f"{state['query']} {gap}", max_results=2)
                for r in resp.get("results", []):
                    new_facts.append(r.get("content", "")[:300])
                state["total_api_calls"] += 1
            except Exception as e:
                state["errors"].append(f"followup: {e}")

        existing = state["synthesized_content"].get("key_facts", [])
        state["synthesized_content"]["key_facts"] = existing + new_facts
        state["synthesized_content"]["fact_count"] = len(
            state["synthesized_content"]["key_facts"])
        state["search_round"] += 1
        state["progress"] = 75
        return state

    # ---- Public entrypoint ----

    async def run(self, query: str, depth: str = "medium",
                  max_sources: int = 10, task_id: str = None) -> ResearchState:
        initial = ResearchState(
            query=query, depth=depth, max_sources=max_sources,
            task_id=task_id or str(uuid.uuid4()),
            research_plan=None, expert_perspectives=None,
            search_results=None, reranked_results=None,
            extracted_data=None, deep_extractions=None,
            synthesized_content=None, report=None,
            reflection_gaps=None, citation_report=None, sources=None,
            current_step="Initializing", progress=0,
            search_retry_count=0, search_round=1, reflection_count=0,
            errors=[], cache_hits=0, total_api_calls=0,
        )
        return await self.graph.ainvoke(initial)
