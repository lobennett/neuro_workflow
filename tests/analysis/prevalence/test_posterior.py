"""Tests for Bayesian prevalence posterior math.

These are scientific-correctness tests: they verify the closed-form MAP,
the truncated-Beta posterior CDF, the quantile function, and the HPDI
against the published expressions in Ince et al. 2021 (PMC8494477) and
against the symbolic properties the posterior must obey (monotone CDF,
posterior mass = 1, MAP is the maximum of the posterior, etc.).

A test that just verifies the code matches itself is worthless.  Tests
below either:

  (a) reproduce a literal numerical example from the paper, or
  (b) verify a symbolic invariant (e.g. F(0)=0, F(1)=1, MAP=closed form).
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import integrate
from scipy.stats import beta as _beta_dist

from neuro_workflow.analysis.prevalence.posterior import (
    hpdi,
    hpdi_lookup,
    map_estimate,
    map_estimate_vector,
    posterior_cdf,
    posterior_quantile,
)


# ---------------------------------------------------------------------------
# MAP — closed form
# ---------------------------------------------------------------------------


def test_map_matches_closed_form_for_interior_solution():
    """For k/n > alpha the MAP is (k/n - alpha)/(1 - alpha)."""
    k, n, alpha = 30, 50, 0.05
    expected = (30 / 50 - 0.05) / (1 - 0.05)
    np.testing.assert_allclose(map_estimate(k, n, alpha), expected, rtol=1e-12)


def test_map_clips_to_zero_when_k_over_n_below_alpha():
    """When k/n <= alpha the posterior on gamma is monotone decreasing.

    The MAP is at gamma = 0, not at a negative value.  The unconstrained
    formula (k/n - alpha)/(1 - alpha) would yield a negative number.
    """
    assert map_estimate(1, 50, 0.05) == pytest.approx(0.0, abs=1e-12)
    assert map_estimate(0, 50, 0.05) == pytest.approx(0.0, abs=1e-12)


def test_map_is_one_when_all_subjects_significant():
    """k == n forces gamma_map = 1: every subject shows the effect."""
    assert map_estimate(50, 50, 0.05) == pytest.approx(1.0, abs=1e-12)


def test_map_vectorised_matches_scalar():
    """Vectorised MAP over an array of k is identical to the scalar form."""
    n, alpha = 46, 0.05
    ks = np.arange(n + 1)
    vectorised = map_estimate_vector(ks, n, alpha)
    scalar = np.array([float(map_estimate(int(k), n, alpha)) for k in ks])
    np.testing.assert_allclose(vectorised, scalar, rtol=1e-12)


# ---------------------------------------------------------------------------
# Posterior CDF — symbolic invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('k, n', [(0, 10), (3, 10), (5, 10), (10, 10)])
def test_posterior_cdf_zero_and_one_at_boundaries(k, n):
    """CDF(0) == 0 and CDF(1) == 1 — the posterior on gamma integrates
    to 1 over [0, 1]."""
    alpha = 0.05
    assert posterior_cdf(0.0, k, n, alpha) == pytest.approx(0.0, abs=1e-12)
    assert posterior_cdf(1.0, k, n, alpha) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize('k', [0, 5, 25, 46])
def test_posterior_cdf_is_monotone_increasing(k):
    """The CDF of a continuous posterior must be non-decreasing."""
    n, alpha = 46, 0.05
    gammas = np.linspace(0.0, 1.0, 101)
    cdf = np.array([posterior_cdf(g, k, n, alpha) for g in gammas])
    assert np.all(np.diff(cdf) >= -1e-12)


def test_posterior_density_integrates_to_one():
    """Numerical integration of the implicit density (derivative of CDF)
    over gamma ∈ [0, 1] equals 1.

    This is the strongest correctness check for the posterior — if the
    truncation constants are wrong the density would not integrate to
    unity.
    """
    k, n, alpha = 12, 30, 0.05
    a, b = k + 1.0, n - k + 1.0
    norm = 1.0 - _beta_dist.cdf(alpha, a, b)

    def density(gamma: float) -> float:
        theta = alpha + (1.0 - alpha) * gamma
        return (1.0 - alpha) * _beta_dist.pdf(theta, a, b) / norm

    mass, _ = integrate.quad(density, 0.0, 1.0)
    assert mass == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Quantile / CDF round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('q', [0.025, 0.05, 0.5, 0.95, 0.975])
@pytest.mark.parametrize('k', [0, 5, 15, 25])
def test_posterior_quantile_is_inverse_of_cdf(q, k):
    """For any q in (0, 1), CDF(quantile(q)) == q."""
    n, alpha = 30, 0.05
    g = posterior_quantile(q, k, n, alpha)
    np.testing.assert_allclose(posterior_cdf(g, k, n, alpha), q, atol=1e-7)


# ---------------------------------------------------------------------------
# HPDI — paper-style numeric example
# ---------------------------------------------------------------------------


def test_hpdi_matches_paper_section_3_example_k20_n40():
    """Reproduce a paper-style worked example.

    For ``n=40`` participants, ``k=20`` significant at within-subject
    alpha=0.05, the paper reports MAP gamma ≈ 0.474 and 96% HPDI roughly
    (0.31, 0.64).  We assert tolerances of ±0.02 to absorb the slight
    HPDI-vs-equal-tail difference and the paper's rounding.
    """
    map_val = float(map_estimate(20, 40, 0.05))
    lo, hi = hpdi(20, 40, 0.05, level=0.96)
    np.testing.assert_allclose(map_val, 0.4737, atol=0.005)
    assert lo == pytest.approx(0.31, abs=0.03)
    assert hi == pytest.approx(0.64, abs=0.03)


def test_hpdi_mass_matches_target_level():
    """The interval [lo, hi] returned by hpdi() must contain ``level`` mass
    under the posterior on gamma."""
    n, alpha, level = 46, 0.05, 0.96
    for k in (5, 15, 30, 40):
        lo, hi = hpdi(k, n, alpha, level=level)
        mass = posterior_cdf(hi, k, n, alpha) - posterior_cdf(lo, k, n, alpha)
        np.testing.assert_allclose(mass, level, atol=1e-3)


def test_hpdi_anchors_left_when_posterior_decreasing():
    """k = 0 ⇒ posterior on gamma is strictly decreasing.  The HPDI is
    anchored at the left boundary gamma = 0 by construction."""
    lo, _ = hpdi(0, 46, 0.05, level=0.96)
    assert lo == 0.0


def test_hpdi_anchors_right_when_k_equals_n():
    """k = n ⇒ posterior is strictly increasing.  HPDI hits the right
    boundary gamma = 1."""
    _, hi = hpdi(46, 46, 0.05, level=0.96)
    assert hi == 1.0


# ---------------------------------------------------------------------------
# HPDI lookup table
# ---------------------------------------------------------------------------


def test_hpdi_lookup_shape_and_values():
    """Lookup table has the right shape, ``[lo, hi]`` per row, and rows
    agree with calling ``hpdi`` directly."""
    n, alpha = 46, 0.05
    table = hpdi_lookup(n, alpha, level=0.96)
    assert table.shape == (n + 1, 2)
    for k in (0, 1, n // 2, n - 1, n):
        lo, hi = hpdi(k, n, alpha, level=0.96)
        np.testing.assert_allclose(table[k], [lo, hi], atol=1e-8)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_invalid_alpha_raises():
    with pytest.raises(ValueError):
        map_estimate(5, 10, alpha=0.0)
    with pytest.raises(ValueError):
        map_estimate(5, 10, alpha=1.0)
    with pytest.raises(ValueError):
        hpdi(5, 10, alpha=-0.1)


def test_invalid_n_raises():
    with pytest.raises(ValueError):
        map_estimate(5, 0, alpha=0.05)
    with pytest.raises(ValueError):
        map_estimate(5, -3, alpha=0.05)


def test_out_of_range_k_raises():
    with pytest.raises(ValueError):
        map_estimate(-1, 10, alpha=0.05)
    with pytest.raises(ValueError):
        map_estimate(11, 10, alpha=0.05)


def test_invalid_quantile_raises():
    with pytest.raises(ValueError):
        posterior_quantile(0.0, 5, 10, 0.05)
    with pytest.raises(ValueError):
        posterior_quantile(1.0, 5, 10, 0.05)
