import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from neuro_workflow.bidsify.run import build_reconciliation, process_subject_session


def test_build_reconciliation():
    """Test reconciliation output structure."""
    sessions = [
        {
            "fw_subject": "s43-2",
            "fw_session": "20201112",
            "timestamp": datetime(2020, 11, 12, tzinfo=timezone.utc),
            "bids_session": "ses-01",
            "acquisitions": ["fmap-fieldmap", "task-rest_bold"],
        },
        {
            "fw_subject": "s43",
            "fw_session": "22473",
            "timestamp": datetime(2020, 11, 19, tzinfo=timezone.utc),
            "bids_session": "ses-02",
            "acquisitions": ["fmap-fieldmap", "task-rest_bold"],
        },
    ]
    recon = build_reconciliation("s43", sessions, ["s43", "s43-2"])
    assert recon["total_sessions"] == 2
    assert recon["flywheel_sources"] == ["s43", "s43-2"]
    assert recon["sessions"][0]["bids_session"] == "ses-01"
    assert recon["sessions"][0]["fw_subject"] == "s43-2"
