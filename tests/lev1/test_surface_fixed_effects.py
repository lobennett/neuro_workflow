"""Tests for surface fixed effects NaN handling."""

import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from network_lev1.processing.surface_data import (
    SurfaceResult,
    compute_surface_fixed_effects,
)


def _write_gifti(path: Path, data: np.ndarray) -> None:
    """Write a 1D array to a single-darray GIFTI file."""
    darray = nib.gifti.GiftiDataArray(
        data=data.astype(np.float32),
        intent='NIFTI_INTENT_NONE',
        datatype='NIFTI_TYPE_FLOAT32',
    )
    nib.save(nib.GiftiImage(darrays=[darray]), str(path))


class TestComputeSurfaceFixedEffects:
    """Tests for compute_surface_fixed_effects."""

    def test_basic_unweighted(self, tmp_path):
        """Two runs with no NaN — simple average."""
        effects = [np.array([2.0, 4.0, 6.0]), np.array([4.0, 6.0, 8.0])]
        variances = [np.array([1.0, 1.0, 1.0]), np.array([1.0, 1.0, 1.0])]

        eff_files, var_files = [], []
        for i, (e, v) in enumerate(zip(effects, variances)):
            ep = tmp_path / f'eff_{i}.func.gii'
            vp = tmp_path / f'var_{i}.func.gii'
            _write_gifti(ep, e)
            _write_gifti(vp, v)
            eff_files.append(ep)
            var_files.append(vp)

        fe, fv, fs = compute_surface_fixed_effects(eff_files, var_files)

        np.testing.assert_allclose(fe.data, [3.0, 5.0, 7.0])
        np.testing.assert_allclose(fv.data, [0.5, 0.5, 0.5])  # sum(1,1)/4
        assert np.all(np.isfinite(fs.data))

    def test_nan_in_one_run_unweighted(self, tmp_path):
        """NaN in one run should not zero out the vertex — use valid runs."""
        effects = [np.array([2.0, np.nan, 6.0]), np.array([4.0, 6.0, 8.0])]
        variances = [np.array([1.0, np.nan, 1.0]), np.array([1.0, 1.0, 1.0])]

        eff_files, var_files = [], []
        for i, (e, v) in enumerate(zip(effects, variances)):
            ep = tmp_path / f'eff_{i}.func.gii'
            vp = tmp_path / f'var_{i}.func.gii'
            _write_gifti(ep, e)
            _write_gifti(vp, v)
            eff_files.append(ep)
            var_files.append(vp)

        fe, fv, fs = compute_surface_fixed_effects(eff_files, var_files)

        # Vertex 0: mean(2,4)=3, Vertex 1: nanmean(nan,6)=6, Vertex 2: mean(6,8)=7
        np.testing.assert_allclose(fe.data, [3.0, 6.0, 7.0])
        # Vertex 1: only 1 valid run, variance = 1/1^2 = 1.0
        np.testing.assert_allclose(fv.data[1], 1.0)
        # z-score at vertex 1 should be finite (not 0 from NaN propagation)
        assert fs.data[1] != 0.0
        assert np.isfinite(fs.data[1])

    def test_all_nan_vertex(self, tmp_path):
        """Vertex with NaN in ALL runs → z-score should be 0."""
        effects = [np.array([2.0, np.nan]), np.array([4.0, np.nan])]
        variances = [np.array([1.0, np.nan]), np.array([1.0, np.nan])]

        eff_files, var_files = [], []
        for i, (e, v) in enumerate(zip(effects, variances)):
            ep = tmp_path / f'eff_{i}.func.gii'
            vp = tmp_path / f'var_{i}.func.gii'
            _write_gifti(ep, e)
            _write_gifti(vp, v)
            eff_files.append(ep)
            var_files.append(vp)

        fe, fv, fs = compute_surface_fixed_effects(eff_files, var_files)

        # Vertex 0 is normal
        np.testing.assert_allclose(fe.data[0], 3.0)
        # Vertex 1: all NaN → should be 0 (no data)
        assert fe.data[1] == 0.0
        assert fs.data[1] == 0.0

    def test_precision_weighted_with_nan(self, tmp_path):
        """Precision-weighted path should exclude NaN runs per vertex."""
        effects = [np.array([2.0, np.nan, 6.0]), np.array([4.0, 6.0, 8.0])]
        variances = [np.array([1.0, np.nan, 1.0]), np.array([1.0, 1.0, 1.0])]

        eff_files, var_files = [], []
        for i, (e, v) in enumerate(zip(effects, variances)):
            ep = tmp_path / f'eff_{i}.func.gii'
            vp = tmp_path / f'var_{i}.func.gii'
            _write_gifti(ep, e)
            _write_gifti(vp, v)
            eff_files.append(ep)
            var_files.append(vp)

        fe, fv, fs = compute_surface_fixed_effects(
            eff_files, var_files, precision_weighted=True
        )

        # Vertex 1: only run 2 contributes (weight=1/1=1), so effect=6.0
        np.testing.assert_allclose(fe.data[1], 6.0)
        assert np.isfinite(fs.data[1])
        assert fs.data[1] != 0.0
