"""Tests for prevalence-map aggregation from per-subject GIFTIs.

These cover the bits of the pipeline that touch I/O and array stacking,
plus the scientific invariants of ``compute_prevalence`` against synthetic
data with known prevalence.
"""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from neuro_workflow.analysis.prevalence.aggregate import (
    PrevalenceResult,
    compute_prevalence,
    find_subject_zmaps,
    load_gifti_data,
    save_prevalence_gifti,
    stack_subject_zmaps,
    z_alpha_two_sided,
)


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
# z_alpha
# ---------------------------------------------------------------------------


def test_z_alpha_two_sided_0_05_is_1_96():
    """Smoke-check the standard z-critical-value math."""
    assert z_alpha_two_sided(0.05) == pytest.approx(1.96, abs=1e-3)
    assert z_alpha_two_sided(0.01) == pytest.approx(2.576, abs=1e-3)


# ---------------------------------------------------------------------------
# find_subject_zmaps + stack
# ---------------------------------------------------------------------------


def test_find_subject_zmaps_globs_and_orders(tmp_path):
    """``find_subject_zmaps`` returns one file per subject, sorted by name."""
    for subj in ('sub-s10', 'sub-s03', 'sub-s19'):
        p = (tmp_path / subj / 'task-flanker' / 'fixed_effects' /
             f'{subj}_hemi-L_space-fsaverage6_task-flanker_'
             f'contrast-incongruent-congruent_rtmodel-RTDur_stat-fixed-effects-z_score.func.gii')
        _write_gifti(p, np.random.randn(10))
    found = find_subject_zmaps(
        tmp_path, task='flanker', contrast='incongruent-congruent', hemisphere='L',
    )
    assert [p.parent.parent.parent.name for p in found] == ['sub-s03', 'sub-s10', 'sub-s19']


def test_find_subject_zmaps_filters_by_subjects_whitelist(tmp_path):
    """Optional ``subjects`` argument restricts to a cohort whitelist."""
    for subj in ('sub-s10', 'sub-s03', 'sub-s19'):
        p = (tmp_path / subj / 'task-flanker' / 'fixed_effects' /
             f'{subj}_hemi-L_space-fsaverage6_task-flanker_'
             f'contrast-incongruent-congruent_rtmodel-RTDur_stat-fixed-effects-z_score.func.gii')
        _write_gifti(p, np.random.randn(10))
    found = find_subject_zmaps(
        tmp_path, task='flanker', contrast='incongruent-congruent', hemisphere='L',
        subjects=['sub-s10', 'sub-s19'],
    )
    names = [p.parent.parent.parent.name for p in found]
    assert sorted(names) == ['sub-s10', 'sub-s19']


def test_stack_subject_zmaps_returns_array_and_ids(tmp_path):
    paths = []
    for subj in ('sub-s03', 'sub-s10'):
        p = tmp_path / f'{subj}_x.func.gii'
        _write_gifti(p, np.arange(5, dtype=float) + (0 if subj == 'sub-s03' else 10))
        paths.append(p)
    arr, subjects = stack_subject_zmaps(paths)
    assert arr.shape == (2, 5)
    assert subjects == ['sub-s03', 'sub-s10']
    np.testing.assert_array_equal(arr[0], [0, 1, 2, 3, 4])
    np.testing.assert_array_equal(arr[1], [10, 11, 12, 13, 14])


def test_stack_raises_on_mismatched_vertex_counts(tmp_path):
    """Mixing fsaverage6 (40k v/hemi) and fsLR (32k v/hemi) must error."""
    p1 = tmp_path / 'sub-s03_a.func.gii'; _write_gifti(p1, np.zeros(40))
    p2 = tmp_path / 'sub-s10_a.func.gii'; _write_gifti(p2, np.zeros(32))
    with pytest.raises(ValueError, match='Inconsistent vertex counts'):
        stack_subject_zmaps([p1, p2])


# ---------------------------------------------------------------------------
# compute_prevalence — synthetic data with known prevalence
# ---------------------------------------------------------------------------


def test_compute_prevalence_recovers_known_high_low_pattern():
    """Build a synthetic z-map cohort with a known per-vertex prevalence and
    verify ``compute_prevalence`` recovers MAPs in the right ballpark.

    Vertex 0: every subject has z = 3.0 (well above 1.96)  → k=n, gamma≈1
    Vertex 1: every subject has z = 0.0                    → k=0, gamma≈0
    Vertex 2: 25 of 50 subjects significant                → gamma_map≈(0.5-α)/(1-α)
    """
    rng = np.random.default_rng(0)
    n_subjects, n_vertices = 50, 4
    z = np.zeros((n_subjects, n_vertices))
    z[:, 0] = 3.0
    z[:, 1] = 0.0
    z[:25, 2] = 3.0  # half significant
    z[:, 3] = rng.normal(size=n_subjects)  # noise — about α significant

    res = compute_prevalence(z, alpha=0.05, two_sided=True, level=0.96)

    assert res.k_count[0] == n_subjects
    assert res.map[0] == pytest.approx(1.0, abs=1e-9)

    assert res.k_count[1] == 0
    assert res.map[1] == pytest.approx(0.0, abs=1e-9)

    # k=25, n=50 → MAP = (0.5 - 0.05)/0.95 ≈ 0.474
    assert res.k_count[2] == 25
    assert res.map[2] == pytest.approx((0.5 - 0.05) / 0.95, abs=1e-6)


def test_compute_prevalence_propagates_nan_vertices():
    """A vertex where any subject has NaN must propagate NaN through the
    output maps and produce a sentinel k of -1.  Silently counting it as
    zero would bias the prevalence map toward false negatives.
    """
    z = np.random.randn(10, 5)
    z[3, 2] = np.nan  # one subject's vertex-2 is NaN
    res = compute_prevalence(z, alpha=0.05)
    assert np.isnan(res.map[2])
    assert np.isnan(res.hpdi_lo[2])
    assert np.isnan(res.hpdi_hi[2])
    assert res.k_count[2] == -1
    assert res.n_vertices_invalid == 1
    # Other vertices unaffected
    assert np.isfinite(res.map[0])
    assert res.k_count[0] >= 0


def test_compute_prevalence_one_sided_vs_two_sided():
    """One-sided only counts strongly-positive subjects; two-sided counts
    strongly-positive OR strongly-negative.  Build z-maps with both signs
    and check the k-counts differ as expected.
    """
    n_subjects = 20
    z = np.zeros((n_subjects, 1))
    z[:10, 0] = 3.0   # 10 positive
    z[10:18, 0] = -3.0  # 8 negative
    z[18:, 0] = 0.0   # 2 null

    one = compute_prevalence(z, alpha=0.05, two_sided=False)
    two = compute_prevalence(z, alpha=0.05, two_sided=True)
    assert one.k_count[0] == 10
    assert two.k_count[0] == 18


def test_compute_prevalence_requires_at_least_two_subjects():
    """Prevalence inference on n=1 has no information; refuse."""
    z = np.array([[1.0, 2.0, 3.0]])
    with pytest.raises(ValueError, match='at least 2'):
        compute_prevalence(z)


def test_compute_prevalence_accepts_explicit_z_threshold():
    """A caller passing a permutation-derived z threshold should bypass the
    α→z conversion (so the strong-control assumption can be applied via
    FWER-corrected thresholds, per the paper)."""
    z = np.zeros((10, 1))
    z[:, 0] = 5.0
    res_default = compute_prevalence(z, alpha=0.05)
    res_custom = compute_prevalence(z, alpha=0.05, z_threshold=10.0)
    # Default z_α≈1.96 → all 10 subjects significant
    assert res_default.k_count[0] == 10
    # Custom threshold 10.0 → none of the subjects (all at z=5) significant
    assert res_custom.k_count[0] == 0


# ---------------------------------------------------------------------------
# save_prevalence_gifti
# ---------------------------------------------------------------------------


def test_save_prevalence_gifti_writes_four_files(tmp_path):
    result = PrevalenceResult(
        map=np.array([0.1, 0.5, 0.9], dtype=np.float32),
        hpdi_lo=np.array([0.0, 0.3, 0.7], dtype=np.float32),
        hpdi_hi=np.array([0.2, 0.7, 1.0], dtype=np.float32),
        k_count=np.array([0, 5, 9]),
        n_subjects=10,
        alpha=0.05,
        z_threshold=1.96,
        level=0.96,
        n_vertices_invalid=0,
    )
    files = save_prevalence_gifti(result, tmp_path, 'sub-cohort_task-flanker_hemi-L_contrast-X')
    assert set(files.keys()) == {'map', 'hpdi_lo', 'hpdi_hi', 'k_count'}
    for path in files.values():
        assert path.exists()
        # Round-trip: loaded data matches written data
        loaded = load_gifti_data(path)
        assert loaded.shape == (3,)
