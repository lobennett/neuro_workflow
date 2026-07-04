"""Tests for scripts/trim_bold.py"""

import json

import nibabel as nib
import numpy as np


def make_bold(tmp_path, sub="s01", ses="ses-01", task="rest", run=1, echo=1, n_vols=163):
    """Create a minimal BOLD NIfTI + sidecar JSON for testing."""
    func_dir = tmp_path / f"sub-{sub}" / ses / "func"
    func_dir.mkdir(parents=True, exist_ok=True)
    stem = f"sub-{sub}_{ses}_task-{task}_run-{run}_echo-{echo}_bold"

    data = np.zeros((2, 2, 2, n_vols), dtype=np.float32)
    img = nib.Nifti1Image(data, np.eye(4))
    nifti_path = func_dir / f"{stem}.nii.gz"
    nib.save(img, str(nifti_path))

    sidecar = {"RepetitionTime": 1.49, "EchoTime": 0.015}
    json_path = func_dir / f"{stem}.json"
    json_path.write_text(json.dumps(sidecar))

    return nifti_path, json_path


def test_trim_removes_7_volumes(tmp_path):
    from scripts.trim_bold import trim_bold_directory

    nifti_path, json_path = make_bold(tmp_path, n_vols=163)

    summary = trim_bold_directory(tmp_path)

    img = nib.load(str(nifti_path))
    assert img.shape[3] == 156

    sidecar = json.loads(json_path.read_text())
    assert sidecar["NumberOfVolumesDiscardedByUser"] == 7

    assert summary["trimmed"] == 1
    assert summary["skipped_already_trimmed"] == 0


def test_trim_is_idempotent(tmp_path):
    from scripts.trim_bold import trim_bold_directory

    nifti_path, json_path = make_bold(tmp_path, n_vols=163)

    trim_bold_directory(tmp_path)
    summary = trim_bold_directory(tmp_path)

    img = nib.load(str(nifti_path))
    assert img.shape[3] == 156
    assert summary["trimmed"] == 0
    assert summary["skipped_already_trimmed"] == 1


def test_trim_skips_short_bold(tmp_path):
    from scripts.trim_bold import trim_bold_directory

    nifti_path, json_path = make_bold(tmp_path, n_vols=1)

    summary = trim_bold_directory(tmp_path)

    img = nib.load(str(nifti_path))
    assert img.shape[3] == 1
    assert summary["trimmed"] == 0
    assert summary["skipped_too_short"] == 1
