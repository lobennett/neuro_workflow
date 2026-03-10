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
