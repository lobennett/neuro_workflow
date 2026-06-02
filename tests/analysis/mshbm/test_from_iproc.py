"""Tests for src/neuro_workflow/analysis/mshbm/from_iproc.py."""
from __future__ import annotations

import nibabel as nib
import numpy as np
import pytest

from neuro_workflow.analysis.mshbm.from_iproc import (
    FSAVERAGE6_NVERTICES,
    discover_iproc_rest,
    iproc_surf_to_mshbm_nifti,
    make_mshbm_name,
)


def test_make_mshbm_name_matches_wrapper_glob():
    name = make_mshbm_name("lh", "01", "004")
    assert name == "lh_ses-01_task-rest_run-004_nat_resid_bpss_fsaverage6_sm0.nii.gz"
    # Must satisfy the CBIG wrapper's glob + group-by-session regex.
    assert name.startswith("lh")
    assert "fsaverage6_sm" in name
    assert "_ses-01_" in name


def test_make_mshbm_name_rejects_bad_hemi():
    with pytest.raises(ValueError):
        make_mshbm_name("left", "01", "004")


def _write_iproc_surf(path, nvert=FSAVERAGE6_NVERTICES, n_t=5, fold=3, seed=0):
    """Write a folded (nvert/fold, 1, fold, T) overlay like iProc/FreeSurfer."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal((nvert, n_t)).astype(np.float32)  # canonical (V, T)
    folded = vec.reshape(nvert // fold, 1, fold, n_t, order="F")
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(folded, affine=np.eye(4)), str(path))
    return vec


def test_iproc_surf_to_mshbm_nifti_roundtrips_vertex_order(tmp_path):
    """Column-major reshape must invert the FreeSurfer fold exactly."""
    src = tmp_path / "lh.01_bld004_tedana_bpss_fsaverage6_sm0p0.nii.gz"
    canonical = _write_iproc_surf(src)
    out = tmp_path / "out.nii.gz"
    iproc_surf_to_mshbm_nifti(src, out)

    arr = np.asarray(nib.load(str(out)).dataobj, dtype=np.float32)
    assert arr.shape == (FSAVERAGE6_NVERTICES, 1, 1, 5)
    np.testing.assert_allclose(arr.reshape(FSAVERAGE6_NVERTICES, 5), canonical, rtol=1e-5)


def test_iproc_surf_to_mshbm_nifti_zeroes_nans(tmp_path):
    src = tmp_path / "lh.01_bld004_tedana_bpss_fsaverage6_sm0p0.nii.gz"
    vec = _write_iproc_surf(src)
    # poison one value via a fresh write with a NaN injected
    arr = np.asarray(nib.load(str(src)).dataobj, dtype=np.float32)
    arr[0, 0, 0, 0] = np.nan
    nib.save(nib.Nifti1Image(arr, affine=np.eye(4)), str(src))

    out = tmp_path / "out.nii.gz"
    iproc_surf_to_mshbm_nifti(src, out)
    res = np.asarray(nib.load(str(out)).dataobj, dtype=np.float32)
    assert np.isfinite(res).all()


def test_iproc_surf_to_mshbm_nifti_rejects_wrong_vertex_count(tmp_path):
    src = tmp_path / "lh.01_bld004_tedana_bpss_fsaverage6_sm0p0.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((100, 1, 3, 4), np.float32), np.eye(4)), str(src))
    with pytest.raises(ValueError, match="fsaverage6"):
        iproc_surf_to_mshbm_nifti(src, tmp_path / "out.nii.gz")


def test_discover_iproc_rest_pairs_hemis(tmp_path):
    fs6 = tmp_path / "mri_data" / "s10" / "FS6"
    for ses in ("01", "02"):
        d = fs6 / ses / "REST_004"
        d.mkdir(parents=True)
        for hemi in ("lh", "rh"):
            (d / f"{hemi}.{ses}_bld004_tedana_bpss_fsaverage6_sm0p0.nii.gz").touch()
    # a task scan that must NOT be discovered (rest-only)
    tdir = fs6 / "01" / "FLANKER_009"
    tdir.mkdir(parents=True)
    (tdir / "lh.01_bld009_tedana_bpss_fsaverage6_sm0p0.nii.gz").touch()

    scans = discover_iproc_rest(tmp_path / "mri_data" / "s10")
    assert [s.session for s in scans] == ["01", "02"]
    assert all(s.run == "004" for s in scans)
    assert all(s.lh_path.name.startswith("lh") and s.rh_path.name.startswith("rh")
               for s in scans)


def test_discover_iproc_rest_skips_unpaired(tmp_path):
    d = tmp_path / "mri_data" / "s10" / "FS6" / "03" / "REST_004"
    d.mkdir(parents=True)
    (d / "lh.03_bld004_tedana_bpss_fsaverage6_sm0p0.nii.gz").touch()  # no rh
    scans = discover_iproc_rest(tmp_path / "mri_data" / "s10")
    assert scans == []


def test_discover_iproc_scans_includes_task_and_rest(tmp_path):
    from neuro_workflow.analysis.mshbm.from_iproc import discover_iproc_scans
    fs6 = tmp_path / "mri_data" / "s10" / "FS6"
    specs = [("01", "REST_004", "004", "REST"),
             ("01", "FLANKER_009", "009", "FLANKER")]
    for ses, cell, run, _ in specs:
        d = fs6 / ses / cell
        d.mkdir(parents=True)
        for hemi in ("lh", "rh"):
            (d / f"{hemi}.{ses}_bld{run}_tedana_bpss_fsaverage6_sm0p0.nii.gz").touch()
    scans = discover_iproc_scans(tmp_path / "mri_data" / "s10")
    tasks = sorted(s.task for s in scans)
    assert tasks == ["FLANKER", "REST"]
    assert all(s.lh_path.name.startswith("lh") and s.rh_path.name.startswith("rh")
               for s in scans)


def test_make_mshbm_name_uses_task_label():
    from neuro_workflow.analysis.mshbm.from_iproc import make_mshbm_name
    n = make_mshbm_name("lh", "01", "009", task="flanker")
    assert n == "lh_ses-01_task-flanker_run-009_nat_resid_bpss_fsaverage6_sm0.nii.gz"
