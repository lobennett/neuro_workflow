import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import tempfile
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


def test_process_subject_session_downloads_physio(tmp_path):
    """Physio CSVs are downloaded and converted when gephysio analyses exist."""
    # Build a minimal session with one BOLD acquisition
    session_info = {
        "bids_session": "ses-01",
        "fw_session": MagicMock(),
    }
    session_info["fw_session"].reload.return_value = session_info["fw_session"]

    # Mock acquisition
    acq = MagicMock()
    acq.label = "task-rest_bold"
    acq.id = "acq_rest_id"
    acq.timestamp = "2025-01-01T00:00:00"
    acq.reload.return_value = acq

    # Multi-echo files
    nifti = MagicMock()
    nifti.name = "bold_e1.nii.gz"
    nifti.type = "nifti"
    nifti.size = 100
    nifti.created = "2025-01-01T00:00:00"

    json_f = MagicMock()
    json_f.name = "bold_e1.json"
    json_f.type = "source code"
    json_f.size = 50
    json_f.created = "2025-01-01T00:00:00"

    acq.files = [nifti, json_f]

    # Mock gephysio analysis
    physio_analysis = MagicMock()
    ppg_file = MagicMock()
    ppg_file.name = "PPG_FltData.csv"
    resp_file = MagicMock()
    resp_file.name = "RESP_FltData.csv"
    physio_analysis.files = [ppg_file, resp_file]

    log_entries = []
    bidsignore_entries = []

    with patch("neuro_workflow.bidsify.run.find_gephysio_analyses") as mock_find, \
         patch("neuro_workflow.bidsify.run.match_analyses_to_acquisitions") as mock_match, \
         patch("neuro_workflow.bidsify.run.download_physio_analysis") as mock_dl, \
         patch("neuro_workflow.bidsify.run.convert_physio_to_bids") as mock_convert, \
         patch("neuro_workflow.bidsify.run._check_bold_4d", return_value=True), \
         patch("neuro_workflow.bidsify.run.patch_sidecar"), \
         patch("neuro_workflow.bidsify.run.download_and_place") as mock_download:

        mock_download.return_value = {
            "fw_filename": "bold_e1.nii.gz",
            "bids_path": str(tmp_path / "bold_e1.nii.gz"),
            "size": 100,
            "created": "2025-01-01T00:00:00",
        }

        mock_find.return_value = [physio_analysis]
        mock_match.return_value = [
            {"task": "rest", "run": 1, "analysis": physio_analysis}
        ]
        mock_dl.return_value = tmp_path / "physio_tmp"

        process_subject_session(
            "s1175", session_info, [acq], tmp_path, log_entries,
            bidsignore_entries=bidsignore_entries,
        )

        mock_find.assert_called_once()
        mock_match.assert_called_once()
        assert mock_convert.call_count == 2  # cardiac + respiratory
