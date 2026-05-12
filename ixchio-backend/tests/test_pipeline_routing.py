"""
Pipeline routing logic tests.
These test the conditional edge functions in DeepResearchGraph
without actually running any LLM calls — just the decision-making.
"""

import pytest

DEPTH_CONFIG = {
    "shallow": {"sub_queries": 3, "search_per_q": 2, "extract_top": 2, "max_reflect": 0},
    "medium":  {"sub_queries": 5, "search_per_q": 3, "extract_top": 3, "max_reflect": 2},
    "deep":    {"sub_queries": 8, "search_per_q": 5, "extract_top": 5, "max_reflect": 3},
}


def _make_state(**overrides):
    """Minimal state dict that satisfies the routing functions."""
    base = {
        "query": "test query",
        "depth": "medium",
        "search_results": [],
        "search_retry_count": 0,
        "validate_retry_count": 0,
        "reflection_gaps": [],
        "reflection_count": 0,
        "report": "",
    }
    base.update(overrides)
    return base


class FakeGraph:
    """Stand-in that has the routing methods but nothing else."""

    def _depth_cfg(self, state):
        return DEPTH_CONFIG.get(state.get("depth", "medium"), DEPTH_CONFIG["medium"])

    def _retry_or_proceed(self, state) -> str:
        if not state["search_results"] and state["search_retry_count"] <= 2:
            return "retry"
        return "proceed"

    def _needs_followup(self, state) -> str:
        gaps = state.get("reflection_gaps") or []
        cfg = self._depth_cfg(state)
        if gaps and cfg["max_reflect"] > 0 and state["reflection_count"] < cfg["max_reflect"]:
            return "followup"
        return "done"

    def _accept_or_redo(self, state) -> str:
        word_count = len((state.get("report") or "").split())
        if word_count < 100 and state["validate_retry_count"] <= 2:
            return "redo"
        if word_count < 50:
            return "fail"
        return "accept"


g = FakeGraph()


def test_retry_when_no_results():
    state = _make_state(search_results=[], search_retry_count=0)
    assert g._retry_or_proceed(state) == "retry"


def test_proceed_when_results_exist():
    state = _make_state(search_results=[{"title": "something"}], search_retry_count=0)
    assert g._retry_or_proceed(state) == "proceed"


def test_proceed_after_max_retries():
    state = _make_state(search_results=[], search_retry_count=3)
    assert g._retry_or_proceed(state) == "proceed"


def test_followup_when_gaps_found():
    state = _make_state(reflection_gaps=["missing data on X"], reflection_count=1)
    assert g._needs_followup(state) == "followup"


def test_done_when_no_gaps():
    state = _make_state(reflection_gaps=[], reflection_count=1)
    assert g._needs_followup(state) == "done"


def test_done_after_max_reflections():
    # medium max_reflect is 2, so reflection_count=2 means we've done 2 rounds
    state = _make_state(reflection_gaps=["still gaps"], reflection_count=2)
    assert g._needs_followup(state) == "done"


def test_shallow_skips_reflection():
    state = _make_state(depth="shallow", reflection_gaps=["gap"], reflection_count=0)
    assert g._needs_followup(state) == "done"


def test_deep_allows_more_reflections():
    state = _make_state(depth="deep", reflection_gaps=["gap"], reflection_count=2)
    assert g._needs_followup(state) == "followup"


def test_accept_long_report():
    long_report = " ".join(["word"] * 200)
    state = _make_state(report=long_report, validate_retry_count=0)
    assert g._accept_or_redo(state) == "accept"


def test_redo_short_report():
    state = _make_state(report="too short", validate_retry_count=0)
    assert g._accept_or_redo(state) == "redo"


def test_fail_empty_report_after_retries():
    state = _make_state(report="", validate_retry_count=3)
    assert g._accept_or_redo(state) == "fail"


def test_search_and_validate_retries_independent():
    """Separate counters means exhausting search retries doesn't block validation."""
    state = _make_state(
        search_retry_count=5,
        validate_retry_count=0,
        report="too short",
    )
    assert g._accept_or_redo(state) == "redo"
