"""Tests for parcel-overlay summaries of prevalence maps.

Covers:
- Per-subject parcel mean: vertex-mean prevalence inside each MSHBM
  network for that subject.
- Cohort summary: nan-mean across subjects.
- High-fraction summary: fraction of parcel vertices with MAP > threshold,
  averaged across subjects.
- Medial wall (label 0) excluded from all per-parcel stats.
- NaN prevalence vertices skipped within parcels (they don't dilute).
- Subject-specific parcel mapping respected (subject A's parcel-3 covers
  different vertices than subject B's parcel-3 — the summary aligns by
  *network identity*, not anatomy).
"""

from __future__ import annotations

import numpy as np
import pytest

from neuro_workflow.analysis.prevalence.parcel_overlay import (
    ParcelOverlay,
    summarise_parcels,
)


def test_parcel_mean_recovers_known_values():
    """Build a 10-vertex prevalence map and a simple dlabel: vertices
    [0..4] are parcel-1, [5..9] are parcel-2.  Mean prevalence in
    parcel-1 = 0.2 (5 vertices of 0.2); in parcel-2 = 0.8.
    """
    prev = np.array([0.2, 0.2, 0.2, 0.2, 0.2, 0.8, 0.8, 0.8, 0.8, 0.8])
    dlabels = {'sub-x': np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2])}
    out = summarise_parcels(prev, dlabels, n_networks=2)
    assert out.subject_parcel_mean.shape == (1, 2)
    np.testing.assert_allclose(out.subject_parcel_mean[0], [0.2, 0.8])
    np.testing.assert_allclose(out.cohort_parcel_mean, [0.2, 0.8])


def test_parcel_high_frac_uses_threshold():
    """Threshold 0.5 → parcel-1 has 0% > 0.5, parcel-2 has 100% > 0.5."""
    prev = np.array([0.2, 0.2, 0.8, 0.8])
    dlabels = {'sub-x': np.array([1, 1, 2, 2])}
    out = summarise_parcels(prev, dlabels, n_networks=2, threshold=0.5)
    np.testing.assert_allclose(out.cohort_parcel_high_frac, [0.0, 1.0])


def test_parcel_summary_excludes_medial_wall():
    """Vertices with parcel label 0 must NOT contribute to any parcel
    statistic.  Build a case where the medial wall has anomalously-high
    prevalence and verify it doesn't leak into network 1 or 2."""
    prev = np.array([0.99, 0.99, 0.2, 0.2, 0.8, 0.8])
    dlabels = {'sub-x': np.array([0, 0, 1, 1, 2, 2])}
    out = summarise_parcels(prev, dlabels, n_networks=2, ignore_label=0)
    np.testing.assert_allclose(out.subject_parcel_mean[0], [0.2, 0.8])


def test_parcel_summary_drops_nan_prevalence_vertices():
    """A NaN-prevalence vertex in a parcel must be skipped from the
    parcel mean — not silently averaged in as nan and propagating."""
    prev = np.array([0.4, np.nan, 0.6])
    dlabels = {'sub-x': np.array([1, 1, 1])}
    out = summarise_parcels(prev, dlabels, n_networks=1)
    # Mean over the two finite vertices = 0.5
    assert out.subject_parcel_mean[0, 0] == pytest.approx(0.5, abs=1e-12)


def test_parcel_summary_handles_two_subjects_with_different_anatomy():
    """Subject A's parcel-1 covers indices [0,1]; subject B's parcel-1
    covers [2,3].  Per-subject parcel means should reflect the
    individual mapping, and the cohort mean over network-1 should be
    the average of the two subject means (network identity preserved
    across subjects)."""
    prev = np.array([0.1, 0.3, 0.7, 0.9])
    dlabels = {
        'sub-a': np.array([1, 1, 2, 2]),  # parcel-1 = [0,1], parcel-2 = [2,3]
        'sub-b': np.array([2, 2, 1, 1]),  # parcel-1 = [2,3], parcel-2 = [0,1]
    }
    out = summarise_parcels(prev, dlabels, n_networks=2)
    # sub-a parcel-1 mean = (0.1+0.3)/2 = 0.2
    # sub-b parcel-1 mean = (0.7+0.9)/2 = 0.8
    # cohort parcel-1 mean = (0.2+0.8)/2 = 0.5
    np.testing.assert_allclose(out.cohort_parcel_mean, [0.5, 0.5])


def test_parcel_summary_nan_when_subject_lacks_network():
    """A subject whose parcellation never assigns network-K gets NaN
    for that parcel — nanmean across subjects then excludes it."""
    prev = np.array([0.5, 0.5, 0.5])
    dlabels = {
        'sub-a': np.array([1, 1, 1]),  # all parcel-1
        'sub-b': np.array([2, 2, 2]),  # all parcel-2
    }
    out = summarise_parcels(prev, dlabels, n_networks=2)
    # sub-a parcel-2 → NaN; sub-b parcel-1 → NaN
    assert np.isnan(out.subject_parcel_mean[0, 1])  # sub-a parcel-2
    assert np.isnan(out.subject_parcel_mean[1, 0])  # sub-b parcel-1
    # Cohort mean: parcel-1 = sub-a's 0.5; parcel-2 = sub-b's 0.5
    np.testing.assert_allclose(out.cohort_parcel_mean, [0.5, 0.5])


def test_parcel_summary_validates_shape():
    """A subject dlabel whose vertex count differs from prev → ValueError."""
    prev = np.array([0.5, 0.5, 0.5])
    dlabels = {'sub-x': np.array([1, 1])}
    with pytest.raises(ValueError, match='shape'):
        summarise_parcels(prev, dlabels, n_networks=2)


def test_parcel_summary_returns_dataclass_with_metadata():
    prev = np.array([0.5, 0.5])
    dlabels = {'sub-x': np.array([1, 1])}
    out = summarise_parcels(prev, dlabels, n_networks=1, threshold=0.3)
    assert isinstance(out, ParcelOverlay)
    assert out.n_subjects == 1
    assert out.n_networks == 1
    assert out.threshold == 0.3
