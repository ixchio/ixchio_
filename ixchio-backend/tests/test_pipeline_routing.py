"""
Pipeline routing logic tests.
Tests conditional edge functions without running any LLM calls.
"""

import pytest

DEPTH_CONFIG = {
    "shallow": {"sub_queries": 3, "search_per_q": 2, "extract_top": 2, "max_reflect": 0},
    "medium":  {"sub_queries": 5, "search_per_q": 3, "extract_top": 3, "max_reflect": 1},
    "deep":    {"sub_queries": 8, "search_per_q": 5, "extract_top": 5, "max_reflect": 2},
}


def _make_state(**overrides):
    base = {
        "query": "test query",
        "depth": "medium",
        "search_results": [],
        "search_retry_count": 0,
        "search_round": 1,
        "reflection_gaps": [],
        "reflection_count": 0,
        "report": "",
    }
    base.update(overrides)
    return base


class FakeGraph:
    def _cfg(self, state):
        return DEPTH_CONFIG.get(state.get("depth", "medium"), DEPTH_CONFIG["medium"])

    def _retry_or_proceed(self, state) -> str:
        if not state["search_results"] and state["search_retry_count"] <= 2:
            return "retry"
        return "proceed"

    def _has_gaps_to_fill(self, state) -> str:
        gaps = state.get("reflection_gaps") or []
        if gaps and state["search_round"] <= 2:
            return "search_more"
        return "sufficient"

    def _needs_followup(self, state) -> str:
        gaps = state.get("reflection_gaps") or []
        cfg = self._cfg(state)
        if gaps and cfg["max_reflect"] > 0 and state["reflection_count"] < cfg["max_reflect"]:
            return "followup"
        return "done"


g = FakeGraph()


# ---- Search retry routing ----

def test_retry_when_no_results():
    assert g._retry_or_proceed(_make_state(search_results=[], search_retry_count=0)) == "retry"


def test_proceed_when_results_exist():
    assert g._retry_or_proceed(_make_state(search_results=[{"title": "x"}])) == "proceed"


def test_proceed_after_max_retries():
    assert g._retry_or_proceed(_make_state(search_results=[], search_retry_count=3)) == "proceed"


# ---- Gap analysis routing ----

def test_gap_analysis_triggers_search():
    state = _make_state(reflection_gaps=["missing X"], search_round=1)
    assert g._has_gaps_to_fill(state) == "search_more"


def test_gap_analysis_skips_when_no_gaps():
    assert g._has_gaps_to_fill(_make_state(reflection_gaps=[])) == "sufficient"


def test_gap_analysis_skips_after_round_limit():
    state = _make_state(reflection_gaps=["gap"], search_round=3)
    assert g._has_gaps_to_fill(state) == "sufficient"


# ---- Reflection routing ----

def test_followup_when_gaps_found():
    state = _make_state(reflection_gaps=["missing data"], reflection_count=0)
    assert g._needs_followup(state) == "followup"


def test_done_when_no_gaps():
    assert g._needs_followup(_make_state(reflection_gaps=[])) == "done"


def test_done_after_max_reflections():
    # medium max_reflect=1, so count=1 means done
    state = _make_state(reflection_gaps=["gaps"], reflection_count=1)
    assert g._needs_followup(state) == "done"


def test_shallow_skips_reflection():
    state = _make_state(depth="shallow", reflection_gaps=["gap"], reflection_count=0)
    assert g._needs_followup(state) == "done"


def test_deep_allows_more_reflections():
    # deep max_reflect=2, count=1 means still has room
    state = _make_state(depth="deep", reflection_gaps=["gap"], reflection_count=1)
    assert g._needs_followup(state) == "followup"


def test_deep_stops_at_limit():
    state = _make_state(depth="deep", reflection_gaps=["gap"], reflection_count=2)
    assert g._needs_followup(state) == "done"
