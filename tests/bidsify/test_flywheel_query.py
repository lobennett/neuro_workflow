"""Tests for flywheel_query module."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from neuro_workflow.bidsify.flywheel_query import (
    build_session_timeline,
    collect_subject_sessions,
    query_project_subjects,
)


def _mock_session(label, timestamp, acq_labels=None):
    """Create a mock FW session object."""
    sess = MagicMock()
    sess.label = label
    sess.timestamp = timestamp
    sess.acquisitions.return_value = [MagicMock(label=a) for a in (acq_labels or [])]
    return sess


def _mock_subject(label, sessions=None):
    """Create a mock FW subject object."""
    subj = MagicMock()
    subj.label = label
    subj.sessions.return_value = sessions or []
    return subj


class TestCollectSubjectSessions:
    def test_collect_merges_aliases(self):
        """s43 + s43-2 should merge; s43-2 session (earlier) comes first."""
        sess_main = _mock_session("session1", datetime(2024, 3, 1), ["t1w"])
        sess_alias = _mock_session("session2", datetime(2024, 1, 15), ["bold"])

        subj_main = _mock_subject("s43", [sess_main])
        subj_alias = _mock_subject("s43-2", [sess_alias])
        subj_other = _mock_subject("s99", [_mock_session("x", datetime(2024, 5, 1))])

        all_subjects = [subj_main, subj_alias, subj_other]
        aliases = {"s43-2": "s43"}

        result = collect_subject_sessions("s43", all_subjects, aliases)

        assert len(result) == 2
        # Earlier timestamp first
        assert result[0]["fw_session"] is sess_alias
        assert result[1]["fw_session"] is sess_main
        assert result[0]["fw_subject"] is subj_alias
        assert result[1]["fw_subject"] is subj_main

    def test_collect_skips_unrelated_subjects(self):
        """Only collects sessions from matching labels."""
        sess = _mock_session("ses1", datetime(2024, 1, 1))
        subj_match = _mock_subject("s43", [sess])
        subj_other = _mock_subject("s99", [_mock_session("x", datetime(2024, 2, 1))])

        result = collect_subject_sessions("s43", [subj_match, subj_other], {})

        assert len(result) == 1
        assert result[0]["fw_subject"] is subj_match

    def test_collect_empty_sessions(self):
        """Subject with no sessions returns empty list."""
        subj = _mock_subject("s43", [])
        result = collect_subject_sessions("s43", [subj], {})
        assert result == []

    # --- session_overrides tests ---

    def test_exclude_override_skips_session(self):
        """Override with 'exclude' action should remove that session."""
        sess_a = _mock_session("22752", datetime(2024, 1, 1))
        sess_b = _mock_session("25210", datetime(2024, 2, 1))
        sess_c = _mock_session("good", datetime(2024, 3, 1))
        subj = _mock_subject("s03", [sess_a, sess_b, sess_c])

        overrides = {
            "s03/25210": {"action": "exclude"},
        }
        result = collect_subject_sessions(
            "s03", [subj], {}, session_overrides=overrides
        )

        labels = [r["fw_session"].label for r in result]
        assert len(result) == 2
        assert "25210" not in labels

    def test_reassign_override_removes_from_source(self):
        """Reassigned session should not appear for the source subject."""
        sess_a = _mock_session("22752", datetime(2024, 1, 1))
        sess_b = _mock_session("good", datetime(2024, 3, 1))
        subj = _mock_subject("s03", [sess_a, sess_b])

        overrides = {
            "s03/22752": {"action": "reassign_to", "target": "s10"},
        }
        result = collect_subject_sessions(
            "s03", [subj], {}, session_overrides=overrides
        )

        assert len(result) == 1
        assert result[0]["fw_session"].label == "good"

    def test_reassign_override_adds_to_target(self):
        """Reassigned session should appear when collecting for the target subject."""
        sess_reassigned = _mock_session("22752", datetime(2024, 1, 1))
        sess_own = _mock_session("own_sess", datetime(2024, 4, 1))
        subj_s03 = _mock_subject("s03", [sess_reassigned])
        subj_s10 = _mock_subject("s10", [sess_own])

        overrides = {
            "s03/22752": {"action": "reassign_to", "target": "s10"},
        }
        result = collect_subject_sessions(
            "s10", [subj_s03, subj_s10], {}, session_overrides=overrides
        )

        labels = [r["fw_session"].label for r in result]
        assert len(result) == 2
        assert "22752" in labels
        assert "own_sess" in labels
        # 22752 has earlier timestamp, should come first
        assert result[0]["fw_session"].label == "22752"

    def test_no_overrides_backward_compatible(self):
        """Calling without session_overrides kwarg works as before."""
        sess = _mock_session("ses1", datetime(2024, 6, 1))
        subj = _mock_subject("s50", [sess])

        result = collect_subject_sessions("s50", [subj], {})

        assert len(result) == 1
        assert result[0]["fw_session"].label == "ses1"

    def test_override_on_alias_subject(self):
        """Override keyed by alias subject label should apply during merge."""
        sess_alias = _mock_session("22542", datetime(2024, 1, 1))
        sess_canon = _mock_session("good", datetime(2024, 5, 1))
        subj_alias = _mock_subject("s19-2", [sess_alias])
        subj_canon = _mock_subject("s19", [sess_canon])

        aliases = {"s19-2": "s19"}
        overrides = {
            "s19-2/22542": {"action": "exclude"},
        }
        result = collect_subject_sessions(
            "s19", [subj_canon, subj_alias], aliases, session_overrides=overrides
        )

        labels = [r["fw_session"].label for r in result]
        assert len(result) == 1
        assert labels == ["good"]


class TestBuildSessionTimeline:
    def test_assigns_sequential_labels(self):
        sessions = [
            {"fw_session": MagicMock(), "timestamp": datetime(2024, 1, 1)},
            {"fw_session": MagicMock(), "timestamp": datetime(2024, 2, 1)},
            {"fw_session": MagicMock(), "timestamp": datetime(2024, 3, 1)},
        ]
        result = build_session_timeline(sessions)

        assert result[0]["bids_session"] == "ses-01"
        assert result[1]["bids_session"] == "ses-02"
        assert result[2]["bids_session"] == "ses-03"


class TestQueryProjectSubjects:
    def test_returns_subjects_and_project(self):
        mock_project = MagicMock()
        mock_subjects = [MagicMock(), MagicMock()]
        mock_project.subjects.return_value = mock_subjects

        fw_client = MagicMock()
        fw_client.projects.find_first.return_value = mock_project

        subjects, project = query_project_subjects(fw_client, "r01network")

        assert subjects is mock_subjects
        assert project is mock_project

    def test_raises_if_project_not_found(self):
        fw_client = MagicMock()
        fw_client.projects.find_first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            query_project_subjects(fw_client, "nonexistent")
