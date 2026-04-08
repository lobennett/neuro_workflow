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


def test_process_subject_session_no_bidsignore_param():
    """process_subject_session signature must not accept bidsignore_entries."""
    import inspect
    sig = inspect.signature(process_subject_session)
    assert "bidsignore_entries" not in sig.parameters


def test_duplicate_anat_gets_run_number(tmp_path):
    """Two T1w scans in same session get run-1 and run-2."""
    session_info = {
        "bids_session": "ses-01",
        "fw_session": MagicMock(),
    }
    session_info["fw_session"].reload.return_value = session_info["fw_session"]

    # Two T1w acquisitions (same acq type, different timestamps)
    acq1 = MagicMock()
    acq1.label = "NEW Sag_MPRAGE_T1"
    acq1.id = "acq1_id"
    acq1.timestamp = "2025-01-01T09:00:00"
    acq1.reload.return_value = acq1
    nifti1 = MagicMock(); nifti1.name = "t1w_1.nii.gz"; nifti1.type = "nifti"
    nifti1.size = 100; nifti1.created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    json1 = MagicMock(); json1.name = "t1w_1.json"; json1.type = "source code"
    json1.size = 50; json1.created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    acq1.files = [nifti1, json1]

    acq2 = MagicMock()
    acq2.label = "NEW Sag_MPRAGE_T1"
    acq2.id = "acq2_id"
    acq2.timestamp = "2025-01-01T10:00:00"
    acq2.reload.return_value = acq2
    nifti2 = MagicMock(); nifti2.name = "t1w_2.nii.gz"; nifti2.type = "nifti"
    nifti2.size = 100; nifti2.created = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    json2 = MagicMock(); json2.name = "t1w_2.json"; json2.type = "source code"
    json2.size = 50; json2.created = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    acq2.files = [nifti2, json2]

    log_entries = []

    with patch("neuro_workflow.bidsify.run.download_and_place") as mock_dl, \
         patch("neuro_workflow.bidsify.run.patch_sidecar"), \
         patch("neuro_workflow.bidsify.run.find_gephysio_analyses", return_value=[]):
        mock_dl.return_value = {"fw_filename": "t1.nii.gz", "bids_path": "/tmp/t1.nii.gz", "size": 100, "created": None}

        warnings = process_subject_session(
            "s19", session_info, [acq1, acq2], tmp_path, log_entries,
        )

    # Check that download_and_place was called with run-1 and run-2 paths
    dl_calls = mock_dl.call_args_list
    bids_paths = [str(c[0][2]) for c in dl_calls]  # 3rd positional arg is dest_path
    run1_paths = [p for p in bids_paths if "run-1" in p]
    run2_paths = [p for p in bids_paths if "run-2" in p]
    assert len(run1_paths) >= 1, f"Expected run-1 in paths: {bids_paths}"
    assert len(run2_paths) >= 1, f"Expected run-2 in paths: {bids_paths}"


def test_write_session_timestamps(tmp_path):
    """session_timestamps.tsv is written with correct columns and data."""
    from neuro_workflow.bidsify.run import write_session_timestamps

    rows = [
        {"subject": "s03", "bids_session": "ses-01", "flywheel_session_label": "22751", "flywheel_timestamp": "2020-10-28T14:32:00+00:00"},
        {"subject": "s03", "bids_session": "ses-02", "flywheel_session_label": "22942", "flywheel_timestamp": "2020-11-18T09:15:00+00:00"},
    ]
    sourcedata = tmp_path / "sourcedata"
    sourcedata.mkdir()

    write_session_timestamps(rows, sourcedata)

    tsv_path = sourcedata / "session_timestamps.tsv"
    assert tsv_path.exists()
    lines = tsv_path.read_text().strip().split("\n")
    assert lines[0] == "subject\tbids_session\tflywheel_session_label\tflywheel_timestamp"
    assert lines[1].startswith("s03\tses-01\t22751\t")
    assert len(lines) == 3  # header + 2 data rows
