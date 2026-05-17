"""Bayesian inference for the prevalence of true effects (Ince et al. 2021).

Reference
---------
Ince, R. A. A., Paton, A. T., Kay, J. W., & Schyns, P. G. (2021).
"Bayesian inference for the prevalence of true effects."
NeuroImage 240, 118378.  PMC8494477.

Model
-----
Per the paper:
- A within-participant NHST is applied with strong family-wise error rate
  control at false-positive rate ``alpha`` (commonly 0.05).
- For each test (vertex, voxel, parcel, …) the binary outcome per
  participant is "significant at the within-subject test" or not.
- Let ``k`` of ``n`` participants test positive.  The observed positivity
  rate ``theta`` is

      theta = (1 - gamma) * alpha + gamma

  where ``gamma`` ∈ [0, 1] is the population prevalence of a true effect.

- Under a uniform Beta(1, 1) prior on theta with truncation to [alpha, 1]
  (since theta cannot fall below the false-positive rate alpha when
  gamma = 0), the posterior on theta is a truncated Beta(k+1, n-k+1):

      p(theta | k, n) = TruncBeta(k+1, n-k+1; lo=alpha, hi=1)

  and the posterior on gamma is obtained by the change of variable
  gamma = (theta - alpha) / (1 - alpha).

Outputs
-------
This module exposes:

- ``map_estimate(k, n, alpha)`` — closed-form MAP of gamma.
- ``posterior_quantile(k, n, alpha, q)`` — inverse-CDF of the truncated
  Beta posterior on gamma at quantile ``q``.  Equal-tailed credible
  intervals are formed by ``posterior_quantile(..., q=(1-level)/2)`` and
  ``posterior_quantile(..., q=1-(1-level)/2)``.
- ``hpdi(k, n, alpha, level)`` — Highest Posterior Density Interval on
  gamma.  For the high-information regime (n moderate, k away from {0, n})
  this is very close to the equal-tail interval, but it is the
  estimate the original paper reports (e.g. their 96% HPDI).

All functions accept scalar or array inputs and broadcast accordingly.
Vectorised: per-vertex ``k`` arrays compute thousands of posteriors at
once when ``n`` and ``alpha`` are scalar.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from scipy import optimize
from scipy.stats import beta as _beta_dist


# ---------------------------------------------------------------------------
# Closed-form MAP
# ---------------------------------------------------------------------------


def map_estimate(k, n: int, alpha: float):
    """Maximum a-posteriori estimate of population prevalence ``gamma``.

    Under a uniform Beta(1,1) prior the unconstrained MAP of ``theta`` is
    ``k / n``.  Mapping back to ``gamma`` gives::

        gamma_map = (k/n - alpha) / (1 - alpha)

    When ``k/n < alpha`` the truncated posterior peaks at the lower
    boundary ``theta = alpha`` (i.e. ``gamma = 0``).  We clip to that
    boundary so the estimate is always a valid prevalence in [0, 1].

    Args:
        k: Number of participants with a significant within-participant
           test.  Scalar or numpy array.
        n: Total number of participants tested.  Must be a positive
           integer.
        alpha: Within-participant test false-positive rate (e.g. 0.05).

    Returns:
        Scalar or array of MAP ``gamma`` estimates in [0, 1].
    """
    _check_alpha(alpha)
    _check_n(n)
    k = np.asarray(k, dtype=float)
    if np.any(k < 0) or np.any(k > n):
        raise ValueError(f'k must lie in [0, {n}]; got {k}')

    raw = (k / n - alpha) / (1.0 - alpha)
    return np.clip(raw, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Truncated Beta CDF/quantile in terms of gamma
# ---------------------------------------------------------------------------


def posterior_cdf(gamma, k: int, n: int, alpha: float) -> float:
    """CDF of the posterior on gamma at value ``gamma``.

    Computed as the conditional CDF of a Beta(k+1, n-k+1) restricted to
    [alpha, 1], reparameterised in terms of gamma:

        theta = alpha + (1 - alpha) * gamma
        F(gamma) = (F_Beta(theta) - F_Beta(alpha)) / (1 - F_Beta(alpha))

    Args:
        gamma: prevalence value (or array) in [0, 1].
        k, n, alpha: see :func:`map_estimate`.

    Returns:
        Probability mass at or below ``gamma`` under the posterior.
    """
    _check_alpha(alpha)
    _check_n(n)
    if not (0 <= k <= n):
        raise ValueError(f'k must lie in [0, {n}]; got {k}')

    gamma = np.asarray(gamma, dtype=float)
    if np.any((gamma < 0) | (gamma > 1)):
        raise ValueError('gamma must be in [0, 1]')

    a, b = k + 1.0, n - k + 1.0
    theta = alpha + (1.0 - alpha) * gamma
    norm = 1.0 - _beta_dist.cdf(alpha, a, b)
    if norm <= 0:
        # Posterior is a point mass at theta=1 (k=n, alpha→1); use degenerate CDF.
        return np.where(gamma >= 1.0, 1.0, 0.0)
    return (_beta_dist.cdf(theta, a, b) - _beta_dist.cdf(alpha, a, b)) / norm


def posterior_quantile(q, k: int, n: int, alpha: float) -> float:
    """Inverse-CDF (quantile) of the posterior on gamma.

    Args:
        q: quantile in (0, 1).  Scalar.
        k, n, alpha: see :func:`map_estimate`.

    Returns:
        Gamma value such that ``posterior_cdf(gamma) == q``.
    """
    _check_alpha(alpha)
    _check_n(n)
    if not (0 <= k <= n):
        raise ValueError(f'k must lie in [0, {n}]; got {k}')
    if not (0.0 < q < 1.0):
        raise ValueError(f'q must lie in (0, 1); got {q}')

    a, b = k + 1.0, n - k + 1.0
    # Lower truncation at theta = alpha.  Conditional quantile is
    #   theta_q = Beta_ppf(F_Beta(alpha) + q * (1 - F_Beta(alpha)))
    cdf_at_alpha = _beta_dist.cdf(alpha, a, b)
    theta_q = _beta_dist.ppf(cdf_at_alpha + q * (1.0 - cdf_at_alpha), a, b)
    gamma_q = (theta_q - alpha) / (1.0 - alpha)
    # Floating-point can produce small negative values when q is tiny and
    # cdf_at_alpha is large; clip for cleanliness.
    return float(np.clip(gamma_q, 0.0, 1.0))


# ---------------------------------------------------------------------------
# HPDI
# ---------------------------------------------------------------------------


def hpdi(k: int, n: int, alpha: float, level: float = 0.96) -> Tuple[float, float]:
    """Highest Posterior Density Interval on gamma at the given mass level.

    For the Beta posterior truncated to [alpha, 1] (always unimodal when
    ``a = k + 1 >= 1`` and ``b = n - k + 1 >= 1``), the HPDI is the
    shortest [lo, hi] such that ``P(lo <= gamma <= hi) = level``.  We
    locate it by 1-D minimisation of the interval width over the lower
    endpoint, using ``scipy.optimize.minimize_scalar``.

    Boundary cases:
      - If the MAP lies at the truncation boundary (i.e. ``k/n <= alpha``,
        so the posterior is monotone decreasing on [0, 1]), the HPDI runs
        from 0 to the ``level``-quantile.
      - If the MAP lies at 1 (``k == n``), the HPDI runs from the
        ``1 - level``-quantile to 1.

    Args:
        k, n, alpha: see :func:`map_estimate`.
        level: target posterior mass (default 0.96, matching Ince et al.).

    Returns:
        ``(lo, hi)`` pair bounding the HPDI on gamma.
    """
    _check_alpha(alpha)
    _check_n(n)
    if not (0 <= k <= n):
        raise ValueError(f'k must lie in [0, {n}]; got {k}')
    if not (0.0 < level < 1.0):
        raise ValueError(f'level must lie in (0, 1); got {level}')

    map_val = float(map_estimate(k, n, alpha))

    # Monotone-decreasing posterior → HPDI is left-anchored.
    if map_val <= 0.0:
        hi = posterior_quantile(level, k, n, alpha)
        return (0.0, hi)

    # Monotone-increasing posterior → HPDI is right-anchored.
    if map_val >= 1.0:
        lo = posterior_quantile(1.0 - level, k, n, alpha)
        return (lo, 1.0)

    # Interior mode → minimise interval width subject to mass constraint.
    # Parameterise by lower-tail quantile q ∈ (0, 1 - level); upper end is
    # the (q + level) quantile.
    def width(q: float) -> float:
        lo = posterior_quantile(q, k, n, alpha)
        hi = posterior_quantile(q + level, k, n, alpha)
        return hi - lo

    res = optimize.minimize_scalar(
        width,
        bounds=(1e-9, 1.0 - level - 1e-9),
        method='bounded',
        options={'xatol': 1e-6},
    )
    q_lo = float(res.x)
    return (
        posterior_quantile(q_lo, k, n, alpha),
        posterior_quantile(q_lo + level, k, n, alpha),
    )


# ---------------------------------------------------------------------------
# Vectorised per-vertex MAP + HPDI lookup
# ---------------------------------------------------------------------------


def map_estimate_vector(k_per_vertex, n: int, alpha: float):
    """Vectorised closed-form MAP across an array of per-vertex counts."""
    return map_estimate(k_per_vertex, n, alpha)


def hpdi_lookup(n: int, alpha: float, level: float = 0.96) -> np.ndarray:
    """Pre-compute HPDIs for every k ∈ [0, n] at fixed (n, alpha, level).

    Returns an ``(n+1, 2)`` array where row ``k`` is ``[lo, hi]``.  Use
    this to broadcast HPDIs across millions of vertices without paying
    the numerical-optimisation cost per vertex.
    """
    out = np.zeros((n + 1, 2), dtype=float)
    for k in range(n + 1):
        out[k] = hpdi(k, n, alpha, level=level)
    return out


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _check_alpha(alpha: float) -> None:
    if not (0.0 < alpha < 1.0):
        raise ValueError(f'alpha must lie in (0, 1); got {alpha}')


def _check_n(n: int) -> None:
    if not (isinstance(n, (int, np.integer)) and n > 0):
        raise ValueError(f'n must be a positive integer; got {n}')
