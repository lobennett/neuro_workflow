"""Sign-flip permutation test for per-subject FWER z-thresholds.

The Bayesian-prevalence framework in Ince et al. 2021 (PMC8494477)
assumes the within-subject test controls the false-positive rate
strongly across the family of vertex tests.  A naïve ``|z| > 1.96``
threshold inflates the family-wise error rate to nearly 1 with ~80k
vertices per subject.

This module implements the standard within-subject sign-flip
permutation procedure (the same one FSL ``randomise`` uses for second-
level inference) to derive a per-subject FWER-corrected z-threshold.

The procedure mirrors the unweighted fixed-effects combination used by
``compute_surface_fixed_effects``::

    fixed_effect = mean(β_r)
    fixed_variance = sum(σ²_r) / n_runs²
    z = fixed_effect / √fixed_variance

Under sign-flipping (``β_r → s_r · β_r``) the ``n_runs`` factor cancels::

    z_perm(v) = Σ_r s_r · β_r(v) / √(Σ_r σ²_r(v))

So one batch matrix multiply (``signs @ β``) divided by a precomputed
denominator gives all P permuted z-maps at once.  Both hemispheres
pool into a single max-statistic family per subject (one threshold
applied to both hemis downstream).

The output threshold for one subject is the ``(1 - α)`` quantile of the
null max-|z| distribution.

Validity: sign-flipping is exchangeable across runs under the global
null hypothesis (no effect for the subject at any vertex).  This is the
standard assumption for second-level fMRI permutation tests with
independent runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FFX combiner (signed)
# ---------------------------------------------------------------------------


def compute_ffx_z(
    betas: np.ndarray,
    variances: np.ndarray,
    signs: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Compute the unweighted FFX z-statistic, optionally with sign-flips.

    Mirrors the project's existing combiner
    (:func:`compute_surface_fixed_effects` with ``precision_weighted=False``)::

        fixed_effect = mean(β_r)
        fixed_variance = sum(σ²_r) / n_runs²
        z = β / √var = Σ s_r β_r / √(Σ σ²_r)     (n_runs cancels)

    Args:
        betas: ``(n_runs, n_vertices)`` per-run effect estimates.
        variances: ``(n_runs, n_vertices)`` per-run variances.
        signs: optional sign vector.  Either ``None`` (all +1 — recovers
            the canonical FFX z), a ``(n_runs,)`` array of ±1, or a
            ``(P, n_runs)`` batch of P permutations.

    Returns:
        If ``signs`` is None or ``(n_runs,)``: ``(n_vertices,)`` z-map.
        If ``signs`` is ``(P, n_runs)``: ``(P, n_vertices)`` batch.

        Vertices where any run is NaN, or where the variance sum is
        non-positive, are returned as NaN.
    """
    if betas.shape != variances.shape:
        raise ValueError(
            f'betas and variances must have the same shape; '
            f'got {betas.shape} vs {variances.shape}'
        )
    n_runs, _ = betas.shape

    # Validity mask: per-vertex, are all runs finite and is variance > 0?
    valid = (
        np.isfinite(betas).all(axis=0)
        & np.isfinite(variances).all(axis=0)
        & (variances > 0).all(axis=0)
    )

    denom = np.sqrt(np.sum(variances, axis=0))         # (V,)

    if signs is None:
        signs_arr = np.ones(n_runs, dtype=np.float64)
    else:
        signs_arr = np.asarray(signs, dtype=np.float64)
        if signs_arr.ndim == 1 and signs_arr.shape[0] != n_runs:
            raise ValueError(
                f'signs vector length must match n_runs={n_runs}; '
                f'got length {signs_arr.shape[0]}'
            )
        if signs_arr.ndim == 2 and signs_arr.shape[1] != n_runs:
            raise ValueError(
                f'signs batch must have shape (P, n_runs={n_runs}); '
                f'got {signs_arr.shape}'
            )

    # signs.shape ∈ {(R,), (P, R)} → num.shape ∈ {(V,), (P, V)}
    num = signs_arr @ betas

    with np.errstate(divide='ignore', invalid='ignore'):
        z = num / denom  # broadcasts over the leading P dimension if present

    # Mask invalid vertices to NaN.
    if z.ndim == 1:
        z = np.where(valid, z, np.nan)
    else:
        z = np.where(valid[None, :], z, np.nan)

    return z


# ---------------------------------------------------------------------------
# Permutation engine
# ---------------------------------------------------------------------------


def _max_abs_z_pooled(
    signs: np.ndarray,
    betas_L: np.ndarray, denom_L: np.ndarray, valid_L: np.ndarray,
    betas_R: np.ndarray, denom_R: np.ndarray, valid_R: np.ndarray,
) -> np.ndarray:
    """One batch of permutations.  Returns ``(P,)`` of max |z| pooled
    across the valid vertices of both hemispheres."""
    z_L = (signs @ betas_L) / denom_L[None, :]
    z_R = (signs @ betas_R) / denom_R[None, :]
    # Pool only valid vertices.  np.abs of NaN would be NaN; mask first.
    abs_L = np.abs(z_L[:, valid_L])
    abs_R = np.abs(z_R[:, valid_R])
    pooled = np.concatenate([abs_L, abs_R], axis=1)
    return pooled.max(axis=1)


def signflip_max_z_null(
    betas_L: np.ndarray,
    variances_L: np.ndarray,
    betas_R: np.ndarray,
    variances_R: np.ndarray,
    n_permutations: int,
    rng: np.random.Generator,
    batch_size: int = 200,
) -> np.ndarray:
    """Return the null distribution of pooled max |z| under sign-flip H₀.

    Args:
        betas_L, variances_L, betas_R, variances_R: ``(n_runs, n_vertices)``
            per-run effect and variance for each hemisphere.  The same
            ``n_runs`` is required across hemispheres because each
            permutation flips the signs of the same R run-level estimates
            on both sides.
        n_permutations: number of sign-flip permutations to draw.
        rng: numpy ``Generator`` for reproducibility.
        batch_size: how many permutations to materialise at once.  Trade
            speed against memory: 200 perms × 80k verts × 8 bytes ≈ 128 MB
            per batch, which is comfortable on a typical HPC node.

    Returns:
        ``(n_permutations,)`` array of max |z| values — one per
        permutation, pooled across the valid vertices of both
        hemispheres.
    """
    if betas_L.shape[0] != betas_R.shape[0]:
        raise ValueError(
            f'Both hemispheres must have the same run count; '
            f'got L={betas_L.shape[0]} R={betas_R.shape[0]}'
        )
    n_runs = betas_L.shape[0]

    # Per-hemisphere precomputations.
    valid_L = (
        np.isfinite(betas_L).all(axis=0)
        & np.isfinite(variances_L).all(axis=0)
        & (variances_L > 0).all(axis=0)
    )
    valid_R = (
        np.isfinite(betas_R).all(axis=0)
        & np.isfinite(variances_R).all(axis=0)
        & (variances_R > 0).all(axis=0)
    )
    denom_L = np.sqrt(np.sum(variances_L, axis=0))
    denom_R = np.sqrt(np.sum(variances_R, axis=0))
    # Replace zero denominators on invalid vertices with 1 to suppress
    # divide warnings (those vertices are masked out anyway).
    denom_L = np.where(denom_L > 0, denom_L, 1.0)
    denom_R = np.where(denom_R > 0, denom_R, 1.0)

    out = np.empty(n_permutations, dtype=np.float64)
    for start in range(0, n_permutations, batch_size):
        end = min(start + batch_size, n_permutations)
        signs = rng.choice([-1.0, 1.0], size=(end - start, n_runs))
        out[start:end] = _max_abs_z_pooled(
            signs, betas_L, denom_L, valid_L, betas_R, denom_R, valid_R,
        )
    return out


def subject_threshold(null_dist: np.ndarray, alpha: float = 0.05) -> float:
    """Return the ``(1 - α)`` quantile of the null max-|z| distribution.

    This is the FWER-corrected within-subject z-threshold at level ``α``.
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f'alpha must lie in (0, 1); got {alpha}')
    return float(np.quantile(null_dist, 1.0 - alpha))


# ---------------------------------------------------------------------------
# I/O for per-run lev1 outputs
# ---------------------------------------------------------------------------


def find_run_estimates(
    lev1_root: Path,
    subject: str,
    task: str,
    contrast: str,
    hemisphere: str,
    rtmodel: str = 'RTDur',
) -> tuple[list[Path], list[Path]]:
    """Locate the per-run β + σ² GIFTI paths for one (subject, task, contrast).

    Pairs are sorted by filename (so ses-01/run-1 comes before ses-01/run-2,
    then ses-02/..., etc).  Returns paired lists: ``len(eff) == len(var)``
    and ``eff[i].name`` differs from ``var[i].name`` only in the stat token.
    """
    contrast_dir = Path(lev1_root) / subject / f'task-{task}' / 'indiv_contrasts'
    eff_pattern = (
        f'{subject}_ses-*_task-{task}_run-*_hemi-{hemisphere}'
        f'_contrast-{contrast}_rtmodel-{rtmodel}_stat-effect-size.func.gii'
    )
    effects = sorted(contrast_dir.glob(eff_pattern))
    variances: list[Path] = []
    for e in effects:
        v = e.with_name(e.name.replace('stat-effect-size', 'stat-variance'))
        if not v.exists():
            raise FileNotFoundError(
                f'Variance file missing for effect {e}; expected {v}.'
            )
        variances.append(v)
    return effects, variances


def load_run_estimates(
    effect_paths: list[Path],
    variance_paths: list[Path],
) -> tuple[np.ndarray, np.ndarray]:
    """Load and stack per-run GIFTIs into ``(n_runs, n_vertices)`` arrays."""
    if len(effect_paths) != len(variance_paths):
        raise ValueError(
            f'effect_paths ({len(effect_paths)}) and variance_paths '
            f'({len(variance_paths)}) must have the same length'
        )
    eff_arrays = [
        np.asarray(nib.load(str(p)).darrays[0].data, dtype=np.float64)
        for p in effect_paths
    ]
    var_arrays = [
        np.asarray(nib.load(str(p)).darrays[0].data, dtype=np.float64)
        for p in variance_paths
    ]
    return np.stack(eff_arrays, axis=0), np.stack(var_arrays, axis=0)


# ---------------------------------------------------------------------------
# End-to-end per-subject API
# ---------------------------------------------------------------------------


@dataclass
class SubjectThresholdResult:
    """Returned by compute_subject_threshold (we expose it as a dict for
    forward-compat with downstream TSV writing)."""

    subject: str
    n_runs: int
    n_vertices_L: int
    n_vertices_R: int
    n_vertices_valid_L: int
    n_vertices_valid_R: int
    z_threshold: float
    n_permutations: int
    alpha: float
    null_p50: float
    null_p95: float
    null_p99: float
    null_max: float

    def to_dict(self) -> dict:
        return {
            'subject': self.subject,
            'n_runs': self.n_runs,
            'n_vertices_L': self.n_vertices_L,
            'n_vertices_R': self.n_vertices_R,
            'n_vertices_valid_L': self.n_vertices_valid_L,
            'n_vertices_valid_R': self.n_vertices_valid_R,
            'z_threshold': self.z_threshold,
            'n_permutations': self.n_permutations,
            'alpha': self.alpha,
            'null_p50': self.null_p50,
            'null_p95': self.null_p95,
            'null_p99': self.null_p99,
            'null_max': self.null_max,
        }


def compute_subject_threshold(
    lev1_root: Path,
    subject: str,
    task: str,
    contrast: str,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    rtmodel: str = 'RTDur',
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """Compute the per-subject FWER-corrected z-threshold via sign-flip perm.

    Loads the subject's run-level β + σ² GIFTIs for both hemispheres,
    constructs ``n_permutations`` sign-flipped FFX z-maps, takes the max
    |z| across vertices (pooled across hemispheres) per permutation,
    and returns the ``(1 - α)`` quantile of that null distribution.

    Returns a dict with provenance fields (subject, n_runs, threshold,
    null percentiles) suitable for serialising to TSV.
    """
    if rng is None:
        rng = np.random.default_rng()

    eff_L, var_L = find_run_estimates(
        lev1_root, subject, task, contrast, hemisphere='L', rtmodel=rtmodel,
    )
    eff_R, var_R = find_run_estimates(
        lev1_root, subject, task, contrast, hemisphere='R', rtmodel=rtmodel,
    )
    if not eff_L or not eff_R:
        raise FileNotFoundError(
            f'No run-level contrast files found for {subject} '
            f'task-{task} contrast-{contrast}'
        )
    if len(eff_L) != len(eff_R):
        raise ValueError(
            f'{subject}: L and R hemispheres have different run counts '
            f'({len(eff_L)} vs {len(eff_R)})'
        )

    betas_L, variances_L = load_run_estimates(eff_L, var_L)
    betas_R, variances_R = load_run_estimates(eff_R, var_R)

    n_runs = betas_L.shape[0]
    logger.info(
        '%s: loaded %d runs, %d/%d vertices for L/R hemispheres',
        subject, n_runs, betas_L.shape[1], betas_R.shape[1],
    )

    null = signflip_max_z_null(
        betas_L=betas_L, variances_L=variances_L,
        betas_R=betas_R, variances_R=variances_R,
        n_permutations=n_permutations, rng=rng,
    )

    thr = subject_threshold(null, alpha=alpha)

    valid_L = (
        np.isfinite(betas_L).all(axis=0)
        & np.isfinite(variances_L).all(axis=0)
        & (variances_L > 0).all(axis=0)
    )
    valid_R = (
        np.isfinite(betas_R).all(axis=0)
        & np.isfinite(variances_R).all(axis=0)
        & (variances_R > 0).all(axis=0)
    )

    result = SubjectThresholdResult(
        subject=subject,
        n_runs=n_runs,
        n_vertices_L=int(betas_L.shape[1]),
        n_vertices_R=int(betas_R.shape[1]),
        n_vertices_valid_L=int(valid_L.sum()),
        n_vertices_valid_R=int(valid_R.sum()),
        z_threshold=thr,
        n_permutations=n_permutations,
        alpha=alpha,
        null_p50=float(np.quantile(null, 0.50)),
        null_p95=float(np.quantile(null, 0.95)),
        null_p99=float(np.quantile(null, 0.99)),
        null_max=float(null.max()),
    )
    return result.to_dict()
