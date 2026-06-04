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
    MAIN_CELLS,
    DirectionalPrevalenceResult,
    PrevalenceResult,
    compute_directional_prevalence,
    compute_prevalence,
    find_subject_instance_zmaps,
    find_subject_zmaps,
    load_gifti_data,
    save_prevalence_gifti,
    stack_subject_zmaps,
    z_alpha_two_sided,
)


def test_main_cells_is_the_canonical_eight_task_contrast_pairs():
    """Single source of truth for the 8 main (task, contrast) prevalence cells.

    Three driver/figure scripts previously each hard-coded this list; pinning
    it here guards the consolidated definition against drift (RF-6).
    """
    assert MAIN_CELLS == [
        ('cuedTS', 'task_switch_cost'),
        ('directedForgetting', 'neg-con'),
        ('flanker', 'incongruent-congruent'),
        ('goNogo', 'nogo_success-go'),
        ('nBack', 'twoBack-oneBack'),
        ('shapeMatching', 'main_vars'),
        ('spatialTS', 'task_switch_cost'),
        ('stopSignal', 'stop_success-go'),
    ]


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


# ---------------------------------------------------------------------------
# find_subject_instance_zmaps — pick the N-th session per subject
# ---------------------------------------------------------------------------


def _write_indiv_zmap(root: Path, subj: str, ses: str, task: str,
                       contrast: str, hemi: str = 'L') -> Path:
    p = (root / subj / f'task-{task}' / 'indiv_contrasts' /
         f'{subj}_ses-{ses}_task-{task}_run-1_hemi-{hemi}_'
         f'contrast-{contrast}_rtmodel-RTDur_stat-z_score.func.gii')
    _write_gifti(p, np.random.randn(10))
    return p


def test_find_subject_instance_zmaps_picks_nth_session_per_subject(tmp_path):
    """instance_idx=2 returns each subject's second-earliest session."""
    for subj, sessions in (
        ('sub-s10', ('01', '03', '05')),
        ('sub-s03', ('02', '04', '06')),
    ):
        for ses in sessions:
            _write_indiv_zmap(tmp_path, subj, ses, 'flanker', 'incongruent-congruent')
    found = find_subject_instance_zmaps(
        tmp_path, task='flanker', contrast='incongruent-congruent',
        hemisphere='L', instance_idx=2,
    )
    sessions = [p.name.split('_ses-')[1].split('_')[0] for p in found]
    subjects_in_order = [p.name.split('_')[0] for p in found]
    assert subjects_in_order == ['sub-s03', 'sub-s10']
    assert sessions == ['04', '03']  # s03's 2nd is ses-04, s10's is ses-03


def test_find_subject_instance_zmaps_skips_subjects_without_nth(tmp_path):
    """Subjects with fewer than N sessions silently drop out of the result."""
    _write_indiv_zmap(tmp_path, 'sub-s10', '01', 'flanker', 'incongruent-congruent')
    _write_indiv_zmap(tmp_path, 'sub-s10', '03', 'flanker', 'incongruent-congruent')
    _write_indiv_zmap(tmp_path, 'sub-s03', '02', 'flanker', 'incongruent-congruent')
    # sub-s03 has only 1 session; asking for instance-2 should drop it
    found = find_subject_instance_zmaps(
        tmp_path, task='flanker', contrast='incongruent-congruent',
        hemisphere='L', instance_idx=2,
    )
    assert len(found) == 1
    assert 'sub-s10' in found[0].name


def test_find_subject_instance_zmaps_sorts_sessions_numerically(tmp_path):
    """ses-10 must come AFTER ses-09 in instance order (numeric not string sort)."""
    for ses in ('09', '10', '01'):
        _write_indiv_zmap(tmp_path, 'sub-s10', ses, 'flanker', 'incongruent-congruent')
    found = find_subject_instance_zmaps(
        tmp_path, task='flanker', contrast='incongruent-congruent',
        hemisphere='L', instance_idx=3,
    )
    assert len(found) == 1
    assert '_ses-10_' in found[0].name


def test_find_subject_instance_zmaps_respects_whitelist(tmp_path):
    for subj in ('sub-s10', 'sub-s03'):
        _write_indiv_zmap(tmp_path, subj, '01', 'flanker', 'incongruent-congruent')
    found = find_subject_instance_zmaps(
        tmp_path, task='flanker', contrast='incongruent-congruent',
        hemisphere='L', instance_idx=1, subjects=['sub-s10'],
    )
    assert [p.name.split('_')[0] for p in found] == ['sub-s10']


def test_find_subject_instance_zmaps_rejects_zero_or_negative(tmp_path):
    with pytest.raises(ValueError, match='instance_idx'):
        find_subject_instance_zmaps(
            tmp_path, task='flanker', contrast='incongruent-congruent',
            hemisphere='L', instance_idx=0,
        )


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


def test_compute_prevalence_accepts_per_subject_z_threshold_array():
    """Per-subject thresholds let each subject pass at its own FWER-corrected
    level (matching the Ince 2021 strong-control prescription)."""
    n_subjects = 5
    z = np.zeros((n_subjects, 3))
    z[:, 0] = 4.0   # all subjects have z=4 at vertex 0
    z[:, 1] = 2.5   # all subjects have z=2.5 at vertex 1
    z[:, 2] = 0.0
    # Subject-specific thresholds: 3 subjects pass z=4 at threshold 3.0;
    # the other 2 have threshold 5.0 (don't pass).  At vertex 1 (z=2.5),
    # only the 3 with threshold 3.0 also fail (2.5 < 3.0), and the 2 with
    # threshold 5.0 also fail.  k for vertex 0 should be 3; vertex 1 should
    # be 0.
    per_subject = np.array([3.0, 3.0, 3.0, 5.0, 5.0])
    res = compute_prevalence(z, z_threshold=per_subject)
    assert res.k_count[0] == 3
    assert res.k_count[1] == 0
    assert res.k_count[2] == 0
    # Stored threshold is the mean over subjects.
    np.testing.assert_allclose(res.z_threshold, np.mean(per_subject), rtol=1e-12)


def test_compute_prevalence_per_subject_threshold_wrong_length_raises():
    z = np.zeros((4, 2))
    with pytest.raises(ValueError, match='Per-subject z_threshold length'):
        compute_prevalence(z, z_threshold=np.array([1.0, 2.0, 3.0]))


# ---------------------------------------------------------------------------
# Per-subject BH-FDR thresholding
# ---------------------------------------------------------------------------


def test_compute_prevalence_per_subject_fdr_rejects_only_strong_signals():
    """BH-FDR at q across each subject's vertices should declare clearly
    significant vertices (huge z) and leave noise alone."""
    rng = np.random.default_rng(0)
    n_subjects, n_vertices = 8, 1000
    # Pure null background; inject a strong-signal block at vertices [0:50]
    # in every subject.  Under FDR at q=0.05, BH should reject those 50
    # (highly significant) without rejecting much of the noise.
    z = rng.standard_normal((n_subjects, n_vertices))
    z[:, :50] += 8.0  # huge z's
    res = compute_prevalence(z, alpha=0.05, per_subject_fdr_q=0.05, two_sided=True)
    # All 8 subjects significant at the strong-signal vertices.
    assert (res.k_count[:50] == 8).all()
    # Noise vertices: BH at q=0.05 across 950 nulls should reject few; with
    # 8 subjects independently FDR-thresholded we expect <<8 subjects "active"
    # at any null vertex.  Use a generous bound to keep the test robust.
    assert (res.k_count[50:] <= 3).all()


def test_compute_prevalence_per_subject_fdr_stores_q_in_result():
    z = np.zeros((4, 100))
    z[:, 0] = 10.0  # one clearly significant vertex
    res = compute_prevalence(z, per_subject_fdr_q=0.1)
    assert res.fdr_q == 0.1
    # When FDR is in use, z_threshold isn't a single scalar; encoded as NaN.
    assert np.isnan(res.z_threshold)


def test_compute_prevalence_per_subject_fdr_one_vs_two_sided():
    """One-sided FDR should ignore negative z; two-sided should pick them up."""
    z = np.zeros((6, 50))
    z[:, 0] = -8.0  # strong negative signal across all subjects
    z[:, 1] = 8.0   # strong positive signal across all subjects
    res_two = compute_prevalence(z, per_subject_fdr_q=0.05, two_sided=True)
    res_one = compute_prevalence(z, per_subject_fdr_q=0.05, two_sided=False)
    # Two-sided rejects both directions
    assert res_two.k_count[0] == 6
    assert res_two.k_count[1] == 6
    # One-sided (positive) ignores the negative
    assert res_one.k_count[0] == 0
    assert res_one.k_count[1] == 6


def test_compute_prevalence_per_subject_fdr_propagates_nan_vertices():
    z = np.ones((4, 5)) * 8.0  # everywhere significant
    z[1, 2] = np.nan  # one subject NaN at vertex 2
    res = compute_prevalence(z, per_subject_fdr_q=0.05)
    # Vertex 2 invalidated (NaN in subject 1)
    assert np.isnan(res.map[2])
    assert res.k_count[2] == -1
    # All other vertices: 4 subjects significant
    assert (res.k_count[[0, 1, 3, 4]] == 4).all()


def test_compute_prevalence_per_subject_fdr_mutually_exclusive_with_z_threshold():
    z = np.zeros((4, 10))
    with pytest.raises(ValueError, match='mutually exclusive'):
        compute_prevalence(z, z_threshold=2.0, per_subject_fdr_q=0.05)


def test_compute_prevalence_per_subject_fdr_q_out_of_range_raises():
    z = np.zeros((4, 10))
    with pytest.raises(ValueError, match='per_subject_fdr_q must lie in'):
        compute_prevalence(z, per_subject_fdr_q=0.0)
    with pytest.raises(ValueError, match='per_subject_fdr_q must lie in'):
        compute_prevalence(z, per_subject_fdr_q=1.0)


# ---------------------------------------------------------------------------
# Direction-resolved prevalence (compute_directional_prevalence)
# ---------------------------------------------------------------------------


def test_compute_directional_prevalence_partitions_overall_into_pos_plus_neg():
    """Per vertex, k_overall must equal k_pos + k_neg for non-invalid vertices."""
    rng = np.random.default_rng(1)
    n_subj, n_vert = 10, 200
    z = rng.standard_normal((n_subj, n_vert))
    z[:, :20] += 6.0   # positive signal block
    z[:, 20:40] -= 6.0 # negative signal block
    res = compute_directional_prevalence(z, per_subject_fdr_q=0.05, two_sided=True)
    # Where vertices are valid, k_overall == k_pos + k_neg
    valid = res.overall.k_count >= 0
    assert np.all(
        res.overall.k_count[valid]
        == res.positive.k_count[valid] + res.negative.k_count[valid]
    )


def test_compute_directional_prevalence_pure_positive_signal_lands_in_positive():
    z = np.full((6, 50), 0.0)
    z[:, 0] = 8.0   # strong positive across all subjects
    z[:, 1] = -8.0  # strong negative across all subjects
    res = compute_directional_prevalence(z, per_subject_fdr_q=0.05, two_sided=True)
    assert res.positive.k_count[0] == 6
    assert res.negative.k_count[0] == 0
    assert res.positive.k_count[1] == 0
    assert res.negative.k_count[1] == 6


def test_compute_directional_prevalence_directionality_signed_balance():
    """Directionality ∈ [-1, +1]: +1 all positive, -1 all negative, 0 even split."""
    z = np.zeros((10, 5))
    z[:, 0] = 8.0       # all 10 positive
    z[:, 1] = -8.0      # all 10 negative
    z[:5, 2] = 8.0      # 5 positive, 5 below threshold
    z[:5, 3] = 8.0      # 5 pos
    z[5:, 3] = -8.0     # 5 neg → split
    res = compute_directional_prevalence(z, per_subject_fdr_q=0.05, two_sided=True)
    assert res.directionality[0] == pytest.approx(1.0)   # all pos
    assert res.directionality[1] == pytest.approx(-1.0)  # all neg
    assert res.directionality[2] == pytest.approx(1.0)   # all (5) pos, 0 neg
    assert res.directionality[3] == pytest.approx(0.0)   # 5 vs 5 → 0
    # vertex 4: no significant subjects → NaN
    assert np.isnan(res.directionality[4])


def test_compute_directional_prevalence_consistency_metric_bounds():
    """Consistency ∈ [0.5, 1] for vertices with any direction; NaN otherwise."""
    z = np.zeros((10, 6))
    z[:5, 0] = 8.0   # 5 positive, 0 negative → consistency = 1.0
    z[5:, 0] = -0.1  # remaining 5 below threshold (negligible)
    z[:5, 1] = 8.0
    z[5:, 1] = -8.0  # 5 pos + 5 neg → consistency = 0.5
    z[:, 2] = 8.0    # 10 positive → consistency = 1.0
    # vertex 3,4,5: pure noise → likely k_pos = k_neg = 0 → consistency = NaN
    res = compute_directional_prevalence(z, per_subject_fdr_q=0.05, two_sided=True)
    assert res.consistency[0] == pytest.approx(1.0)
    assert res.consistency[1] == pytest.approx(0.5)
    assert res.consistency[2] == pytest.approx(1.0)
    # NaN where no significant subjects in either direction
    assert np.isnan(res.consistency[3])


def test_compute_directional_prevalence_propagates_nan_vertices():
    z = np.full((4, 4), 8.0)
    z[1, 2] = np.nan
    res = compute_directional_prevalence(z, per_subject_fdr_q=0.05, two_sided=True)
    assert res.n_vertices_invalid == 1
    assert np.isnan(res.overall.map[2])
    assert np.isnan(res.positive.map[2])
    assert np.isnan(res.negative.map[2])
    assert np.isnan(res.consistency[2])
    assert res.overall.k_count[2] == -1


def test_compute_directional_prevalence_returns_dataclass():
    z = np.zeros((3, 5))
    z[:, 0] = 5.0
    res = compute_directional_prevalence(z, per_subject_fdr_q=0.05)
    assert isinstance(res, DirectionalPrevalenceResult)
    assert isinstance(res.overall, PrevalenceResult)
    assert isinstance(res.positive, PrevalenceResult)
    assert isinstance(res.negative, PrevalenceResult)


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
