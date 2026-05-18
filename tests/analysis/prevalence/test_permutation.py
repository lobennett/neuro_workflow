"""Tests for sign-flip permutation derivation of per-subject FWER z-thresholds.

These tests cover the math the Ince 2021 framework relies on for "strong
control" of within-subject FPR.  The within-subject test is a permutation
sign-flip of run-level β estimates that mirrors the unweighted fixed-
effects combination used by ``compute_surface_fixed_effects``:

    z(v) = Σ_r s_r · β_r(v) / √(Σ_r σ²_r(v))

The n_runs factor cancels because ``fixed_effect = mean(β_r)`` and
``fixed_variance = sum(σ²_r) / n_runs²`` (the project's default FFX
combiner is unweighted, not precision-weighted).

Covered:
- ``compute_ffx_z`` matches the closed form on synthetic data.
- Sign flips zero out the signal when runs are identical.
- Batch (P × R) signs return (P, V) z-maps.
- NaN / zero-variance vertices are excluded from the max-statistic
  family so the threshold isn't contaminated by ill-defined ratios.
- ``signflip_max_z_null`` returns a length-P null distribution that
  agrees on identical seeds and disagrees on different seeds.
- ``subject_threshold`` is the (1-alpha) quantile.
- File discovery + loading round-trips against real GIFTI data.
"""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from neuro_workflow.analysis.prevalence.permutation import (
    compute_ffx_z,
    compute_subject_threshold,
    find_run_estimates,
    load_run_estimates,
    signflip_max_z_null,
    subject_threshold,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_gifti(path: Path, data: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    darray = nib.gifti.GiftiDataArray(
        data=data.astype(np.float32), intent='NIFTI_INTENT_NORMAL',
        datatype='NIFTI_TYPE_FLOAT32',
    )
    img = nib.gifti.GiftiImage()
    img.add_gifti_data_array(darray)
    img.to_filename(str(path))
    return path


# ---------------------------------------------------------------------------
# compute_ffx_z
# ---------------------------------------------------------------------------


def test_compute_ffx_z_single_run_is_beta_over_sqrt_var():
    """With one run, FFX z reduces to β / √σ²."""
    betas = np.array([[3.0, 1.0, -2.0]])           # (1 run, 3 verts)
    variances = np.array([[1.0, 4.0, 1.0]])
    z = compute_ffx_z(betas, variances)
    np.testing.assert_allclose(z, [3.0, 0.5, -2.0], rtol=1e-12)


def test_compute_ffx_z_matches_unweighted_closed_form():
    """Two identical runs.  fixed_effect = β; fixed_variance = σ²/2.
    z = β·√2/σ.
    """
    betas = np.tile([2.0, 4.0], (2, 1))           # (2 runs, 2 verts)
    variances = np.tile([1.0, 4.0], (2, 1))
    z = compute_ffx_z(betas, variances)
    # fixed_effect = [2, 4]; fixed_variance = [(1+1)/4, (4+4)/4] = [0.5, 2]
    # z = [2/sqrt(0.5), 4/sqrt(2)] = [2.828, 2.828]
    np.testing.assert_allclose(z, [np.sqrt(8), np.sqrt(8)], rtol=1e-12)


def test_compute_ffx_z_signs_cancel_signal():
    """β identical in both runs; signs [+1, -1] → effect zeroed → z = 0."""
    betas = np.tile([3.0, -5.0], (2, 1))
    variances = np.tile([1.0, 2.0], (2, 1))
    z = compute_ffx_z(betas, variances, signs=np.array([1, -1]))
    np.testing.assert_allclose(z, [0.0, 0.0], atol=1e-12)


def test_compute_ffx_z_batch_signs_produces_pv_array():
    """(P, R) signs → (P, V) z."""
    betas = np.array([[1.0, 2.0], [3.0, 4.0]])         # (2 runs, 2 verts)
    variances = np.array([[1.0, 1.0], [1.0, 1.0]])
    signs = np.array([
        [1,  1],   # both runs +
        [1, -1],   # second run flipped
        [-1, 1],   # first run flipped
    ])
    z = compute_ffx_z(betas, variances, signs=signs)
    # denom = sqrt(2) for both verts
    # P=0: num = [1+3, 2+4] = [4, 6] → [4/√2, 6/√2]
    # P=1: num = [1-3, 2-4] = [-2, -2] → [-2/√2, -2/√2]
    # P=2: num = [-1+3, -2+4] = [2, 2] → [2/√2, 2/√2]
    expected = np.array([[4, 6], [-2, -2], [2, 2]]) / np.sqrt(2.0)
    assert z.shape == (3, 2)
    np.testing.assert_allclose(z, expected, rtol=1e-12)


def test_compute_ffx_z_signs_shape_mismatch_raises():
    betas = np.zeros((3, 5))
    variances = np.ones((3, 5))
    with pytest.raises(ValueError, match='signs'):
        compute_ffx_z(betas, variances, signs=np.array([1, -1]))  # wrong n_runs


# ---------------------------------------------------------------------------
# NaN / zero-variance handling
# ---------------------------------------------------------------------------


def test_compute_ffx_z_returns_nan_at_invalid_vertices():
    """Any-run NaN in either β or σ², or σ² = 0, → NaN z at that vertex."""
    betas = np.array([
        [1.0, np.nan, 2.0, 3.0],
        [1.0, 1.0,    2.0, 3.0],
    ])
    variances = np.array([
        [1.0, 1.0, 0.0, 1.0],   # vertex 2: zero variance
        [1.0, 1.0, 1.0, 1.0],
    ])
    z = compute_ffx_z(betas, variances)
    assert np.isnan(z[1])  # NaN beta in run 0
    assert np.isnan(z[2])  # variance == 0 in run 0
    assert np.isfinite(z[0])
    assert np.isfinite(z[3])


# ---------------------------------------------------------------------------
# signflip_max_z_null + subject_threshold
# ---------------------------------------------------------------------------


def test_signflip_max_z_null_has_length_P():
    """Output length matches n_permutations."""
    rng = np.random.default_rng(0)
    R, V = 5, 200
    betas = rng.normal(size=(R, V))
    variances = np.ones((R, V))
    null = signflip_max_z_null(
        betas_L=betas, variances_L=variances,
        betas_R=betas, variances_R=variances,
        n_permutations=500, rng=np.random.default_rng(42),
    )
    assert null.shape == (500,)
    assert np.all(np.isfinite(null))
    assert np.all(null > 0)  # |z| ≥ 0 always


def test_signflip_max_z_null_deterministic_with_seed():
    rng = np.random.default_rng(0)
    R, V = 4, 50
    betas = rng.normal(size=(R, V))
    variances = rng.uniform(0.5, 1.5, size=(R, V))
    null_a = signflip_max_z_null(
        betas_L=betas, variances_L=variances,
        betas_R=betas * 0.5, variances_R=variances * 0.7,
        n_permutations=100, rng=np.random.default_rng(7),
    )
    null_b = signflip_max_z_null(
        betas_L=betas, variances_L=variances,
        betas_R=betas * 0.5, variances_R=variances * 0.7,
        n_permutations=100, rng=np.random.default_rng(7),
    )
    np.testing.assert_array_equal(null_a, null_b)


def test_signflip_max_z_null_seed_changes_distribution():
    rng = np.random.default_rng(0)
    R, V = 4, 50
    betas = rng.normal(size=(R, V))
    variances = np.ones((R, V))
    a = signflip_max_z_null(
        betas_L=betas, variances_L=variances,
        betas_R=betas, variances_R=variances,
        n_permutations=200, rng=np.random.default_rng(1),
    )
    b = signflip_max_z_null(
        betas_L=betas, variances_L=variances,
        betas_R=betas, variances_R=variances,
        n_permutations=200, rng=np.random.default_rng(2),
    )
    assert not np.allclose(a, b)


def test_signflip_max_z_null_pools_both_hemispheres():
    """When R is +ve much larger than L, max should come from R for most perms."""
    R, V = 4, 100
    rng = np.random.default_rng(0)
    betas_L = rng.normal(size=(R, V)) * 0.1   # tiny noise
    variances_L = np.ones((R, V))
    betas_R = rng.normal(size=(R, V)) * 5.0   # large noise
    variances_R = np.ones((R, V))
    null = signflip_max_z_null(
        betas_L=betas_L, variances_L=variances_L,
        betas_R=betas_R, variances_R=variances_R,
        n_permutations=200, rng=np.random.default_rng(3),
    )
    # If we pooled correctly, the max should be dominated by R hemisphere
    # — much larger than from L alone.
    null_L_only = signflip_max_z_null(
        betas_L=betas_L, variances_L=variances_L,
        betas_R=betas_L, variances_R=variances_L,  # same as L on both sides
        n_permutations=200, rng=np.random.default_rng(3),
    )
    assert null.mean() > null_L_only.mean() * 5


def test_signflip_max_z_null_skips_invalid_vertices():
    """Vertices with NaN or zero variance in any run must not contribute to
    the max — otherwise the threshold gets pulled to NaN or infinity."""
    R, V = 3, 20
    rng = np.random.default_rng(0)
    betas = rng.normal(size=(R, V))
    variances = np.ones((R, V))
    # Corrupt vertex 10 in R hemisphere
    betas_R = betas.copy()
    variances_R = variances.copy()
    variances_R[1, 10] = 0.0  # zero variance — invalid
    null = signflip_max_z_null(
        betas_L=betas, variances_L=variances,
        betas_R=betas_R, variances_R=variances_R,
        n_permutations=100, rng=np.random.default_rng(1),
    )
    assert np.all(np.isfinite(null))


def test_subject_threshold_returns_1_minus_alpha_quantile():
    null = np.linspace(0.0, 100.0, 1001)  # known sorted distribution
    thr_05 = subject_threshold(null, alpha=0.05)
    np.testing.assert_allclose(thr_05, 95.0, atol=0.2)
    thr_01 = subject_threshold(null, alpha=0.01)
    np.testing.assert_allclose(thr_01, 99.0, atol=0.2)


# ---------------------------------------------------------------------------
# find_run_estimates + load_run_estimates
# ---------------------------------------------------------------------------


def _populate_minimal_lev1_dir(
    root: Path, subject: str, task: str, contrast: str,
    n_sessions: int, n_runs_per_ses: int, n_vertices: int,
    rtmodel: str = 'RTDur',
) -> None:
    """Write a fake lev1 directory tree mimicking real layout."""
    contrast_dir = root / subject / f'task-{task}' / 'indiv_contrasts'
    rng = np.random.default_rng(0)
    for ses in range(1, n_sessions + 1):
        ses_tag = f'ses-{ses:02d}'
        for run in range(1, n_runs_per_ses + 1):
            for hemi in ('L', 'R'):
                base = (
                    f'{subject}_{ses_tag}_task-{task}_run-{run}_hemi-{hemi}'
                    f'_contrast-{contrast}_rtmodel-{rtmodel}'
                )
                _write_gifti(
                    contrast_dir / f'{base}_stat-effect-size.func.gii',
                    rng.normal(size=n_vertices),
                )
                _write_gifti(
                    contrast_dir / f'{base}_stat-variance.func.gii',
                    rng.uniform(0.5, 2.0, size=n_vertices),
                )


def test_find_run_estimates_globs_per_hemi(tmp_path):
    """find_run_estimates returns matching (β_paths, σ²_paths) per hemi."""
    _populate_minimal_lev1_dir(
        tmp_path, 'sub-x', 'flanker', 'incongruent-congruent',
        n_sessions=2, n_runs_per_ses=2, n_vertices=10,
    )
    eff_L, var_L = find_run_estimates(
        tmp_path, 'sub-x', 'flanker', 'incongruent-congruent', hemisphere='L',
    )
    # 2 sessions × 2 runs = 4 runs per hemi
    assert len(eff_L) == 4
    assert len(var_L) == 4
    # paired filenames
    for e, v in zip(eff_L, var_L):
        assert e.name.replace('stat-effect-size', 'stat-variance') == v.name


def test_load_run_estimates_stacks_rows(tmp_path):
    _populate_minimal_lev1_dir(
        tmp_path, 'sub-x', 'flanker', 'incongruent-congruent',
        n_sessions=2, n_runs_per_ses=1, n_vertices=7,
    )
    eff, var = find_run_estimates(
        tmp_path, 'sub-x', 'flanker', 'incongruent-congruent', hemisphere='L',
    )
    betas, variances = load_run_estimates(eff, var)
    assert betas.shape == (2, 7)
    assert variances.shape == (2, 7)


# ---------------------------------------------------------------------------
# compute_subject_threshold — end-to-end on synthetic data
# ---------------------------------------------------------------------------


def test_compute_subject_threshold_returns_dict_with_metadata(tmp_path):
    """End-to-end: a subject with synthetic null data → threshold somewhere
    in [2, 6] (typical permutation FWER threshold for 200 vertices, 4 runs).
    """
    _populate_minimal_lev1_dir(
        tmp_path, 'sub-x', 'flanker', 'incongruent-congruent',
        n_sessions=2, n_runs_per_ses=2, n_vertices=200,
    )
    result = compute_subject_threshold(
        lev1_root=tmp_path, subject='sub-x', task='flanker',
        contrast='incongruent-congruent',
        n_permutations=200, alpha=0.05,
        rng=np.random.default_rng(0),
    )
    assert isinstance(result, dict)
    assert result['subject'] == 'sub-x'
    assert result['n_runs'] == 4
    assert result['n_permutations'] == 200
    assert result['alpha'] == 0.05
    assert 2.0 < result['z_threshold'] < 6.0
    assert 'null_p50' in result
    assert 'null_p95' in result
