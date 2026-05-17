"""Tests for per-network and aggregate Dice math.

Covers:
- Closed-form ground truth for hand-picked label vectors.
- Boundary cases: identical labels (Dice = 1.0), disjoint (Dice = 0.0).
- Network absent in both halves → NaN (not 0) so caller can distinguish.
- Medial wall (label 0) excluded from Dice and vertex-agreement.
- DiceSummary aggregates per-network NaNs out of the mean.
"""

from __future__ import annotations

import numpy as np
import pytest

from neuro_workflow.analysis.parcellation_reliability.dice import (
    DiceSummary,
    dice_per_network,
    summarise_dice,
    vertex_label_agreement,
)


# ---------------------------------------------------------------------------
# dice_per_network
# ---------------------------------------------------------------------------


def test_dice_identical_labels_is_one():
    labels = np.array([1, 2, 3, 1, 2, 3])
    out = dice_per_network(labels, labels)
    np.testing.assert_allclose(out, [1.0, 1.0, 1.0])


def test_dice_disjoint_labels_is_zero():
    a = np.array([1, 1, 1, 1])
    b = np.array([2, 2, 2, 2])
    out = dice_per_network(a, b, n_networks=2)
    np.testing.assert_allclose(out, [0.0, 0.0])


def test_dice_closed_form_overlap():
    """Hand-computed Dice: 4 vertices, label 1 in a={0,1}, in b={0,2}.
    Intersection of {a==1}∩{b==1}: 1 vertex (idx 0).
    |a==1|=2, |b==1|=2 → Dice = 2 * 1 / (2 + 2) = 0.5
    """
    a = np.array([1, 1, 2, 2])
    b = np.array([1, 2, 1, 2])
    out = dice_per_network(a, b, n_networks=2)
    np.testing.assert_allclose(out, [0.5, 0.5])


def test_dice_network_absent_in_both_halves_returns_nan():
    """Network 3 doesn't appear in either half → NaN, not 0/0 division
    silently producing 0 or inf."""
    a = np.array([1, 1, 2, 2])
    b = np.array([1, 1, 2, 2])
    out = dice_per_network(a, b, n_networks=3)
    assert np.isnan(out[2])  # network 3 absent
    assert np.isclose(out[0], 1.0)
    assert np.isclose(out[1], 1.0)


def test_dice_ignores_label_zero_by_default():
    """The medial-wall label (0) should not appear in the per-network
    Dice output even if many vertices carry it."""
    a = np.array([0, 0, 1, 1, 0, 0])
    b = np.array([0, 0, 1, 1, 0, 0])
    out = dice_per_network(a, b)
    assert out.shape == (1,)
    np.testing.assert_allclose(out, [1.0])


def test_dice_ignore_label_can_be_overridden():
    """If a custom ignore_label is passed (e.g. -1 for some pipelines),
    label 0 is included in the Dice output."""
    a = np.array([0, 0, 1, 1])
    b = np.array([0, 0, 1, 1])
    out = dice_per_network(a, b, n_networks=2, ignore_label=-1)
    # Both label 1 and label 2 included; label 2 absent → NaN, label 1 = 1
    assert len(out) == 2
    assert np.isclose(out[0], 1.0)
    assert np.isnan(out[1])


def test_dice_shape_mismatch_raises():
    with pytest.raises(ValueError):
        dice_per_network(np.zeros(5), np.zeros(6))


# ---------------------------------------------------------------------------
# vertex_label_agreement
# ---------------------------------------------------------------------------


def test_vertex_agreement_full_identity_is_one():
    a = np.array([1, 2, 3, 1, 2, 3])
    assert vertex_label_agreement(a, a) == 1.0


def test_vertex_agreement_full_disagreement_is_zero():
    a = np.array([1, 1, 2, 2])
    b = np.array([2, 2, 1, 1])
    assert vertex_label_agreement(a, b) == 0.0


def test_vertex_agreement_excludes_medial_wall():
    """Vertices with label 0 in either half are dropped from numerator
    and denominator — even if they happen to agree."""
    a = np.array([0, 0, 1, 2, 2])
    b = np.array([0, 0, 1, 2, 1])
    # Vertices considered: indices 2, 3, 4 (label 0 dropped in both)
    # Agreements: idx 2 (1==1), idx 3 (2==2), idx 4 (2 vs 1, disagree)
    # → 2/3
    assert vertex_label_agreement(a, b) == pytest.approx(2 / 3, abs=1e-12)


def test_vertex_agreement_all_medial_wall_returns_nan():
    """When every vertex is medial wall in at least one half, agreement
    is undefined (zero denominator) — return NaN."""
    a = np.array([0, 0, 0, 0])
    b = np.array([0, 0, 0, 0])
    assert np.isnan(vertex_label_agreement(a, b))


# ---------------------------------------------------------------------------
# summarise_dice
# ---------------------------------------------------------------------------


def test_summarise_dice_returns_summary_with_mean_excluding_nan():
    """NaN networks (absent in both halves) must NOT depress the mean."""
    a = np.array([1, 1, 2, 2, 0, 0])
    b = np.array([1, 1, 2, 2, 0, 0])
    s = summarise_dice(a, b, n_networks=3)
    assert isinstance(s, DiceSummary)
    assert s.mean_dice == pytest.approx(1.0, abs=1e-12)
    assert s.vertex_agreement == pytest.approx(1.0)


def test_summarise_dice_partial_overlap_realistic():
    """Two halves agree on most vertices but differ on a few — confirms
    Dice and vertex-agreement track plausible reliability values."""
    rng = np.random.default_rng(0)
    n_vertices = 1000
    a = rng.integers(low=1, high=4, size=n_vertices)
    b = a.copy()
    # Corrupt 10% randomly
    flip = rng.choice(n_vertices, size=100, replace=False)
    b[flip] = (b[flip] % 3) + 1
    s = summarise_dice(a, b, n_networks=3)
    assert 0.85 < s.mean_dice < 1.0  # high but not perfect
    assert 0.85 < s.vertex_agreement < 1.0
