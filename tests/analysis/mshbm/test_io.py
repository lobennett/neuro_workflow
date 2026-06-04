"""Tests for the shared MSHBM on-disk conventions (naming + NIfTI write)."""
import nibabel as nib
import numpy as np
import pytest

from neuro_workflow.analysis.mshbm.io import (
    check_hemi,
    make_mshbm_name,
    write_mshbm_nifti,
)


def test_make_mshbm_name_format():
    assert (
        make_mshbm_name("lh", "01", "004", "rest")
        == "lh_ses-01_task-rest_run-004_nat_resid_bpss_fsaverage6_sm0.nii.gz"
    )


def test_make_mshbm_name_defaults_to_rest():
    assert "task-rest" in make_mshbm_name("rh", "02", "001")


def test_make_mshbm_name_rejects_bad_hemi():
    with pytest.raises(ValueError):
        make_mshbm_name("LH", "01", "1", "rest")


def test_check_hemi_raises_on_unknown():
    with pytest.raises(ValueError):
        check_hemi("x")
    check_hemi("lh")  # no raise


def test_write_mshbm_nifti_shape_and_nan_zeroing(tmp_path):
    arr = np.array([[1.0, np.nan, 3.0], [4.0, 5.0, np.inf]], dtype=np.float32)  # (V=2, T=3)
    out = write_mshbm_nifti(arr, tmp_path / "sub" / "lh_x.nii.gz")
    assert out.exists()
    d = np.asarray(nib.load(str(out)).dataobj)
    assert d.shape == (2, 1, 1, 3)
    assert np.isfinite(d).all()
    assert d[0, 0, 0, 1] == 0.0 and d[1, 0, 0, 2] == 0.0  # NaN and Inf zeroed
