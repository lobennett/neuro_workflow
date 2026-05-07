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


import nibabel as nib
import numpy as np

from neuro_workflow.qa.lev1_outliers import (
    compute_cohort_outliers,
    OutlierResult,
)


def _mk_nifti(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(arr.astype(np.float32), np.eye(4)), str(path))


def test_compute_cohort_outliers_known_counts(tmp_path: Path):
    """Five subjects, one contrast, 4×4×4 volume. Two subjects are uniform 0;
    one is uniform 100 — that one should have 100% outlier voxels at n_std=2.
    """
    base = tmp_path
    paths: list[Path] = []
    for i, val in enumerate([0.0, 0.0, 0.0, 0.0, 100.0]):
        sub = f"sub-s{i:02d}"
        p = (base / sub / "task-stopSignal/indiv_contrasts" /
             f"{sub}_ses-01_task-stopSignal_run-1_contrast-go_stat-effect-size.nii.gz")
        _mk_nifti(np.full((4, 4, 4), val, dtype=np.float32), p)
        paths.append(p)

    results = compute_cohort_outliers(paths, n_std=2.0)
    by_sub = {r.scan.subject: r for r in results}
    assert by_sub["sub-s04"].outlier_pct == pytest.approx(100.0)
    assert by_sub["sub-s00"].outlier_pct == pytest.approx(0.0)


def test_compute_cohort_outliers_groups_by_task_contrast(tmp_path: Path):
    """Subjects across two contrasts. Outlier counts are computed within each contrast group."""
    paths: list[Path] = []
    for i in range(3):
        sub = f"sub-s{i:02d}"
        # contrast A
        pa = (tmp_path / sub / "task-goNogo/indiv_contrasts" /
              f"{sub}_ses-01_task-goNogo_run-1_contrast-go_stat-effect-size.nii.gz")
        _mk_nifti(np.full((4, 4, 4), float(i), dtype=np.float32), pa)
        paths.append(pa)
        # contrast B
        pb = (tmp_path / sub / "task-goNogo/indiv_contrasts" /
              f"{sub}_ses-01_task-goNogo_run-1_contrast-stop_stat-effect-size.nii.gz")
        _mk_nifti(np.full((4, 4, 4), float(i) * 10, dtype=np.float32), pb)
        paths.append(pb)

    results = compute_cohort_outliers(paths, n_std=2.0)
    contrasts = {(r.scan.task, r.scan.contrast) for r in results}
    assert contrasts == {("goNogo", "go"), ("goNogo", "stop")}
