"""Tests for the XCP-D → MSHBM prep helpers."""
from __future__ import annotations


def test_module_imports():
    """Smoke import — verifies the package layout is sane."""
    from neuro_workflow.analysis.mshbm import from_xcpd  # noqa: F401


from pathlib import Path


def test_discover_xcpd_cells_returns_per_task_concatenated(tmp_path):
    """One Cell per (session × task) for `desc-denoised` files
    WITHOUT a `_run-N` token (the combine-runs concatenated variant)."""
    from neuro_workflow.analysis.mshbm.from_xcpd import discover_xcpd_cells, Cell

    sub_root = tmp_path / 'sub-s10'
    (sub_root / 'ses-01' / 'func').mkdir(parents=True)
    (sub_root / 'ses-02' / 'func').mkdir(parents=True)

    # Cells we want — no _run-N
    keep = [
        'ses-01/func/sub-s10_ses-01_task-rest_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
        'ses-01/func/sub-s10_ses-01_task-flanker_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
        'ses-02/func/sub-s10_ses-02_task-rest_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
    ]
    # Cells we want to skip — per-run variants
    skip = [
        'ses-01/func/sub-s10_ses-01_task-rest_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
        'ses-01/func/sub-s10_ses-01_task-flanker_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
    ]
    for rel in keep + skip:
        (sub_root / rel).touch()

    cells = discover_xcpd_cells(sub_root)
    assert len(cells) == 3
    assert all(isinstance(c, Cell) for c in cells)
    assert {(c.session, c.task) for c in cells} == {
        ('ses-01', 'rest'),
        ('ses-01', 'flanker'),
        ('ses-02', 'rest'),
    }


def test_discover_xcpd_cells_empty_root_returns_empty_list(tmp_path):
    from neuro_workflow.analysis.mshbm.from_xcpd import discover_xcpd_cells
    assert discover_xcpd_cells(tmp_path) == []


import nibabel as nib
import numpy as np


def test_gifti_to_mshbm_nifti_shape_and_dtype(tmp_path):
    """A (V, T) GIFTI → (V, 1, 1, T) float32 NIfTI."""
    from neuro_workflow.analysis.mshbm.from_xcpd import gifti_to_mshbm_nifti

    # Synthetic per-vertex time series: 100 vertices × 50 TRs
    V, T = 100, 50
    data = np.arange(V * T, dtype=np.float32).reshape(V, T)
    darrays = [
        nib.gifti.GiftiDataArray(data=data[:, t].astype(np.float32),
                                  intent='NIFTI_INTENT_NONE')
        for t in range(T)
    ]
    gii = nib.gifti.GiftiImage(darrays=darrays)
    gii_path = tmp_path / 'lh.func.gii'
    nib.save(gii, str(gii_path))

    out = tmp_path / 'lh.nii.gz'
    gifti_to_mshbm_nifti(gii_path, out)

    img = nib.load(str(out))
    assert img.shape == (V, 1, 1, T)
    assert img.get_fdata().dtype in (np.float32, np.float64)
    # Round-trip the data
    arr = img.get_fdata().reshape(V, T)
    np.testing.assert_allclose(arr, data)


def test_templateflow_paths_returns_existing_spheres():
    """Resolves the sphere + pial + white paths from the templateflow cache."""
    from neuro_workflow.analysis.mshbm.from_xcpd import templateflow_paths

    paths = templateflow_paths()
    for hemi in ('L', 'R'):
        assert paths[hemi]['fsLR_sphere'].is_file(), paths[hemi]['fsLR_sphere']
        assert paths[hemi]['fsaverage6_sphere'].is_file(), paths[hemi]['fsaverage6_sphere']
        assert paths[hemi]['fsaverage6_pial'].is_file(), paths[hemi]['fsaverage6_pial']
        assert paths[hemi]['fsaverage6_white'].is_file(), paths[hemi]['fsaverage6_white']
