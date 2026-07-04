"""Tests for scripts/lev1_outliers.py — the cohort outlier QC driver.

Focus: the --exclusions-file flag must load the compiled exclusion registry
and forward the resulting key-set to detect_lev1_outliers, so excluded scans
are dropped *before* cohort outlier statistics are computed.
"""

import json
import sys
from unittest.mock import patch

import pytest

from scripts.lev1_outliers import main


def _write_compiled_exclusions(path):
    """One scan-level exclusion in the neuro_workflow compiled flat-list format."""
    path.write_text(
        json.dumps(
            [
                {
                    "subject": "sub-s10",
                    "session": "ses-05",
                    "task": "task-goNogo",
                    "run": "run-1",
                    "source": "qa_decisions",
                    "action": "exclude",
                    "reason": "x",
                },
            ]
        )
    )


def _run_main(argv):
    with (
        patch("scripts.lev1_outliers.detect_lev1_outliers") as mock_detect,
        patch.object(sys, "argv", argv),
    ):
        rc = main()
    return rc, mock_detect


def test_main_forwards_loaded_exclusions_to_detector(tmp_path):
    lev1 = tmp_path / "lev1"
    lev1.mkdir()
    excl = tmp_path / "compiled.json"
    _write_compiled_exclusions(excl)
    rc, mock_detect = _run_main(
        [
            "lev1_outliers.py",
            "--lev1-dir",
            str(lev1),
            "--output-dir",
            str(tmp_path / "out"),
            "--exclusions-file",
            str(excl),
        ]
    )
    assert rc == 0
    _, kwargs = mock_detect.call_args
    # Key format must match _make_exclusion_key in qa/lev1_outliers.py.
    assert kwargs["exclusions"] == {"sub-s10_ses-05_task-goNogo_run-1"}


def test_main_without_exclusions_passes_none(tmp_path):
    lev1 = tmp_path / "lev1"
    lev1.mkdir()
    rc, mock_detect = _run_main(
        [
            "lev1_outliers.py",
            "--lev1-dir",
            str(lev1),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    _, kwargs = mock_detect.call_args
    assert kwargs["exclusions"] is None


def test_main_missing_exclusions_file_errors_loud(tmp_path):
    lev1 = tmp_path / "lev1"
    lev1.mkdir()
    rc, mock_detect = _run_main(
        [
            "lev1_outliers.py",
            "--lev1-dir",
            str(lev1),
            "--output-dir",
            str(tmp_path / "out"),
            "--exclusions-file",
            str(tmp_path / "does_not_exist.json"),
        ]
    )
    assert rc == 1
    mock_detect.assert_not_called()
