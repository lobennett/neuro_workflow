import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from neuro_workflow.bidsify.run import build_reconciliation, process_subject_session


def _mock_obj(label):
    obj = MagicMock()
    obj.label = label
    return obj


def test_build_reconciliation():
    """Test reconciliation output structure."""
    acq1 = [_mock_obj("fmap-fieldmap"), _mock_obj("task-rest_bold")]
    acq2 = [_mock_obj("fmap-fieldmap"), _mock_obj("task-rest_bold")]
    sessions = [
        {
            "fw_subject": _mock_obj("s43-2"),
            "fw_session": _mock_obj("20201112"),
            "timestamp": datetime(2020, 11, 12, tzinfo=timezone.utc),
            "bids_session": "ses-01",
            "acquisitions": acq1,
        },
        {
            "fw_subject": _mock_obj("s43"),
            "fw_session": _mock_obj("22473"),
            "timestamp": datetime(2020, 11, 19, tzinfo=timezone.utc),
            "bids_session": "ses-02",
            "acquisitions": acq2,
        },
    ]
    recon = build_reconciliation("s43", sessions, ["s43", "s43-2"])
    assert recon["total_sessions"] == 2
    assert recon["flywheel_sources"] == ["s43", "s43-2"]
    assert recon["sessions"][0]["bids_session"] == "ses-01"
    assert recon["sessions"][0]["fw_subject"] == "s43-2"
