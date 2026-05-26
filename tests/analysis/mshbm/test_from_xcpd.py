"""Tests for the XCP-D → MSHBM prep helpers."""
from __future__ import annotations


def test_module_imports():
    """Smoke import — verifies the package layout is sane."""
    from neuro_workflow.analysis.mshbm import from_xcpd  # noqa: F401


from pathlib import Path


def test_discover_xcpd_cells_prefers_concatenated_over_per_run(tmp_path):
    """When both `_run-N` and a concatenated (no run suffix) file exist for the
    same (session, task), discover picks the concatenated form. When only the
    per-run file exists (single-run case), it falls back to that."""
    from neuro_workflow.analysis.mshbm.from_xcpd import discover_xcpd_cells, Cell

    sub_root = tmp_path / 'sub-s10'
    (sub_root / 'ses-01' / 'func').mkdir(parents=True)
    (sub_root / 'ses-02' / 'func').mkdir(parents=True)

    # ses-01 task-rest has BOTH per-run AND concatenated → pick concatenated
    (sub_root / 'ses-01/func/sub-s10_ses-01_task-rest_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii').touch()
    (sub_root / 'ses-01/func/sub-s10_ses-01_task-rest_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii').touch()
    # ses-01 task-flanker has ONLY per-run (single-run subject) → fall back
    (sub_root / 'ses-01/func/sub-s10_ses-01_task-flanker_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii').touch()
    # ses-02 task-rest has only concatenated → use it
    (sub_root / 'ses-02/func/sub-s10_ses-02_task-rest_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii').touch()

    cells = discover_xcpd_cells(sub_root)
    assert len(cells) == 3
    assert all(isinstance(c, Cell) for c in cells)
    cells_by_key = {(c.session, c.task): c for c in cells}
    assert set(cells_by_key) == {
        ('ses-01', 'rest'),
        ('ses-01', 'flanker'),
        ('ses-02', 'rest'),
    }
    # ses-01 task-rest must be the no-run-suffix file (single-element tuple)
    rest = cells_by_key[('ses-01', 'rest')]
    assert len(rest.dtseries_paths) == 1
    assert '_run-' not in rest.dtseries_paths[0].name
    # ses-01 task-flanker must be the run-1 file (fallback)
    flank = cells_by_key[('ses-01', 'flanker')]
    assert len(flank.dtseries_paths) == 1
    assert '_run-1_' in flank.dtseries_paths[0].name


def test_discover_xcpd_cells_returns_all_runs_when_no_concatenated(tmp_path):
    """When XCP-D emits multiple _run-N files for the same (session, task)
    but no concatenated variant, discover returns all per-run files in
    ascending run order so the driver can wb_command -cifti-merge them."""
    from neuro_workflow.analysis.mshbm.from_xcpd import discover_xcpd_cells

    sub_root = tmp_path / 'sub-s1481'
    (sub_root / 'ses-04' / 'func').mkdir(parents=True)
    # Two runs of rest in ses-04, no concatenated form (the s1481 case)
    (sub_root / 'ses-04/func/sub-s1481_ses-04_task-rest_run-2_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii').touch()
    (sub_root / 'ses-04/func/sub-s1481_ses-04_task-rest_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii').touch()

    cells = discover_xcpd_cells(sub_root)
    assert len(cells) == 1
    rest = cells[0]
    assert rest.session == 'ses-04'
    assert rest.task == 'rest'
    assert len(rest.dtseries_paths) == 2
    # Sorted ascending by run number
    assert '_run-1_' in rest.dtseries_paths[0].name
    assert '_run-2_' in rest.dtseries_paths[1].name


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


def test_gifti_to_mshbm_nifti_zeros_nan_inputs(tmp_path):
    """NaN values in the GIFTI (from wb_command -metric-resample holes) are
    zeroed in the output so MSHBM sees a single medial-wall sentinel."""
    from neuro_workflow.analysis.mshbm.from_xcpd import gifti_to_mshbm_nifti

    V, T = 50, 5
    data = np.ones((V, T), dtype=np.float32)
    # Salt some NaNs across vertices and timepoints
    data[3, :] = np.nan
    data[17, 2] = np.nan
    data[42, [0, 4]] = np.nan
    darrays = [
        nib.gifti.GiftiDataArray(data=data[:, t].astype(np.float32),
                                  intent='NIFTI_INTENT_NONE')
        for t in range(T)
    ]
    gii_path = tmp_path / 'lh.func.gii'
    nib.save(nib.gifti.GiftiImage(darrays=darrays), str(gii_path))

    out = tmp_path / 'lh.nii.gz'
    gifti_to_mshbm_nifti(gii_path, out)

    arr = nib.load(str(out)).get_fdata().reshape(V, T)
    assert not np.isnan(arr).any(), 'NaN should be zeroed'
    assert (arr[3, :] == 0.0).all()
    assert arr[17, 2] == 0.0
    assert (arr[42, [0, 4]] == 0.0).all()
    # Non-NaN values preserved
    assert arr[0, 0] == 1.0
    assert arr[17, 0] == 1.0


def test_templateflow_paths_returns_existing_spheres():
    """Resolves the sphere + pial + white paths from the templateflow cache."""
    from neuro_workflow.analysis.mshbm.from_xcpd import templateflow_paths

    paths = templateflow_paths()
    for hemi in ('L', 'R'):
        assert paths[hemi]['fsLR_sphere'].is_file(), paths[hemi]['fsLR_sphere']
        assert paths[hemi]['fsaverage6_sphere'].is_file(), paths[hemi]['fsaverage6_sphere']
        assert paths[hemi]['fsaverage6_pial'].is_file(), paths[hemi]['fsaverage6_pial']
        assert paths[hemi]['fsaverage6_white'].is_file(), paths[hemi]['fsaverage6_white']
