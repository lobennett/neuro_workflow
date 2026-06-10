"""Unit tests for query_exclusions — written RED-first before implementation."""
import pytest
from neuro_workflow.core.exclusions import query_exclusions

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

COMPILED = [
    {
        "subject": "sub-s10",
        "session": "ses-05",
        "task": "task-goNogo",
        "run": "run-1",
        "source": "behavioral-qc",
        "action": "exclude",
        "reason": "go_rt (1043ms) > 1000ms",
        "metrics": {"go_rt_ms": 1043},
    },
    {
        "subject": "sub-s10",
        "session": "ses-07",
        "task": "task-rest",
        "run": "run-1",
        "source": "motion",
        "action": "exclude",
        "reason": "High FD",
        "metrics": {},
    },
    {
        "subject": "sub-s10",
        "session": "ses-09",
        "task": "task-flanker",
        "run": "run-1",
        "source": "neg-events",
        "action": "trim",
        "reason": "Non-monotonic onsets",
        "metrics": {"onset_trim_index": 80, "rows_to_keep": 200},
    },
    {
        "subject": "sub-s19",
        "session": "ses-02",
        "task": "task-goNogo",
        "run": "run-1",
        "source": "motion",
        "action": "exclude",
        "reason": "High FD",
        "metrics": {},
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_query_by_subject_only():
    """Returns all entries for a given subject."""
    result = query_exclusions(COMPILED, "sub-s10")
    subjects = {e["subject"] for e in result}
    assert subjects == {"sub-s10"}
    assert len(result) == 3


def test_query_by_subject_and_task():
    """Filters to subject + task when task is given."""
    result = query_exclusions(COMPILED, "sub-s10", task="task-goNogo")
    assert len(result) == 1
    assert result[0]["task"] == "task-goNogo"
    assert result[0]["session"] == "ses-05"


def test_query_by_subject_session_task():
    """Full triple filter: subject + session + task."""
    result = query_exclusions(COMPILED, "sub-s10", session="ses-07", task="task-rest")
    assert len(result) == 1
    assert result[0]["action"] == "exclude"
    assert result[0]["source"] == "motion"


def test_query_prefix_insensitive_subject_no_prefix():
    """Accepts 's10' (no 'sub-' prefix) as equivalent to 'sub-s10'."""
    result = query_exclusions(COMPILED, "s10")
    assert len(result) == 3


def test_query_prefix_insensitive_with_prefix():
    """Accepts 'sub-s10' as equivalent to 's10'."""
    result = query_exclusions(COMPILED, "sub-s10")
    assert len(result) == 3


def test_query_prefix_insensitive_session():
    """Accepts '05' or 'ses-05' for session."""
    result_bare = query_exclusions(COMPILED, "sub-s10", session="05")
    result_full = query_exclusions(COMPILED, "sub-s10", session="ses-05")
    assert len(result_bare) == 1
    assert result_bare == result_full


def test_query_prefix_insensitive_task():
    """Accepts 'goNogo' or 'task-goNogo' for task."""
    result_bare = query_exclusions(COMPILED, "sub-s10", task="goNogo")
    result_full = query_exclusions(COMPILED, "sub-s10", task="task-goNogo")
    assert len(result_bare) == 1
    assert result_bare == result_full


def test_query_empty_result():
    """Returns empty list when no entries match."""
    result = query_exclusions(COMPILED, "sub-s99")
    assert result == []


def test_query_empty_compiled():
    """Works on an empty compiled list."""
    result = query_exclusions([], "sub-s10")
    assert result == []


def test_query_result_sorted_by_session_task_run():
    """Results are sorted by (session, task, run) for readable output."""
    result = query_exclusions(COMPILED, "sub-s10")
    sessions = [e["session"] for e in result]
    assert sessions == sorted(sessions)
