"""
Research state — the data structure that flows through LangGraph.
Every node reads from it and writes back to it.
"""

from typing import TypedDict, Optional, List, Dict


class ResearchState(TypedDict):
    query: str
    depth: str
    max_sources: int
    task_id: str

    # what the agents produce
    research_plan: Optional[Dict]
    expert_perspectives: Optional[List[Dict]]
    search_results: Optional[List[Dict]]
    reranked_results: Optional[List[Dict]]
    extracted_data: Optional[List[Dict]]
    deep_extractions: Optional[List[Dict]]
    synthesized_content: Optional[Dict]
    report: Optional[str]
    reflection_gaps: Optional[List[str]]
    citation_report: Optional[Dict]
    sources: Optional[List[Dict]]

    # control flow
    current_step: str
    progress: int
    search_retry_count: int
    search_round: int
    reflection_count: int
    errors: List[str]

    # stats
    cache_hits: int
    total_api_calls: int
