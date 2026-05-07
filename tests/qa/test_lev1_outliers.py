"""Tests for src/neuro_workflow/qa/lev1_outliers.py — discovery + parsing."""
from __future__ import annotations

from pathlib import Path

import pytest

from neuro_workflow.qa.lev1_outliers import (
    ScanContrast,
    discover_contrast_files,
    parse_contrast_path,
)


def test_parse_contrast_path():
    p = Path(
        "/lev1/sub-s03/task-stopSignal/indiv_contrasts/"
        "sub-s03_ses-01_task-stopSignal_run-1_contrast-stop_success-go_rtmodel-rt_centered_stat-effect-size.nii.gz"
    )
    sc = parse_contrast_path(p)
    assert sc.subject == "sub-s03"
    assert sc.session == "ses-01"
    assert sc.task == "stopSignal"
    assert sc.run == "1"
    assert sc.contrast == "stop_success-go"


def test_discover_contrast_files(tmp_path: Path):
    # Build a tiny fixture
    f1 = (tmp_path / "sub-s03/task-goNogo/indiv_contrasts" /
          "sub-s03_ses-01_task-goNogo_run-1_contrast-go_stat-effect-size.nii.gz")
    f1.parent.mkdir(parents=True)
    f1.touch()
    f2 = (tmp_path / "sub-s10/task-goNogo/indiv_contrasts" /
          "sub-s10_ses-01_task-goNogo_run-1_contrast-go_stat-effect-size.nii.gz")
    f2.parent.mkdir(parents=True)
    f2.touch()
    # red herring that should NOT match
    (tmp_path / "sub-s03/task-goNogo/indiv_contrasts" /
     "junk.txt").touch()

    found = discover_contrast_files(
        [tmp_path],
        glob_pattern="sub-s*/task-*/indiv_contrasts/*stat-effect-size.nii.gz",
    )
    assert sorted(p.name for p in found) == sorted([f1.name, f2.name])
