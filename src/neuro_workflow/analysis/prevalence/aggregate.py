"""Aggregate per-subject fixed-effects z-maps into Bayesian prevalence maps.

Pipeline
--------
Given a directory of subject-level fixed-effects GIFTI z-maps for one
``(task, contrast, hemisphere)`` cell, this module:

1. Loads all per-subject z-maps and stacks them into a ``(n_subjects,
   n_vertices)`` array.
2. Applies a within-subject NHST threshold ``z_alpha`` (default 1.96 →
   two-sided alpha 0.05; pass a different threshold to control the test's
   false-positive rate after multiple-comparison correction).
3. Counts ``k_per_vertex`` subjects with ``z > z_alpha`` (or, for negative
   contrasts, ``|z| > z_alpha`` if ``two_sided=True``).
4. Calls ``posterior.map_estimate_vector`` and ``posterior.hpdi_lookup``
   to compute the per-vertex MAP prevalence plus HPDI bounds.
5. Writes four GIFTI outputs (MAP, lower HPDI bound, upper HPDI bound,
   k_count) so the maps can be visualised in workbench / fsleyes and
   parcellated onto MSHBM labels downstream.

Inputs are filtered to the subjects present in a subjects file (so the
caller controls the cohort definition and exclusions are applied at the
file-glob level).  Vertices with NaN in *any* subject are propagated as
NaN through the prevalence output, so downstream group thresholds know
the count is incomplete.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

from neuro_workflow.analysis.prevalence.posterior import (
    hpdi_lookup,
    map_estimate_vector,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PrevalenceResult:
    """Per-vertex prevalence outputs ready to be saved as GIFTI."""

    map: np.ndarray            # gamma MAP per vertex, shape (n_vertices,)
    hpdi_lo: np.ndarray        # lower HPDI bound, shape (n_vertices,)
    hpdi_hi: np.ndarray        # upper HPDI bound, shape (n_vertices,)
    k_count: np.ndarray        # int count of significant subjects per vertex
    n_subjects: int            # total subjects contributing to a vertex
    alpha: float               # within-subject false-positive rate used
    z_threshold: float         # corresponding z-stat threshold (NaN if FDR)
    level: float               # HPDI mass level (e.g. 0.96)
    n_vertices_invalid: int    # vertices marked NaN due to subject NaN
    fdr_q: Optional[float] = None  # BH-FDR q if per-subject FDR was used


# ---------------------------------------------------------------------------
# Stacking
# ---------------------------------------------------------------------------


_SUBJECT_RE = re.compile(r'(sub-[a-zA-Z0-9]+)')


def find_subject_zmaps(
    lev1_root: Path,
    task: str,
    contrast: str,
    hemisphere: str,
    space: str = 'fsaverage6',
    subjects: Optional[list[str]] = None,
) -> list[Path]:
    """Glob the per-subject fixed-effects z-map files for one cell.

    Args:
        lev1_root: e.g. ``/scratch/.../derivatives/lev1_surface``.
        task: ``flanker``, ``nBack``, etc. — no ``task-`` prefix.
        contrast: ``incongruent-congruent``, ``task-baseline``, etc.
        hemisphere: ``L`` or ``R``.
        space: surface space tag (default ``fsaverage6``).
        subjects: optional whitelist of ``sub-X`` ids; when None, all
            matching files are returned.

    Returns:
        Sorted list of paths, one per subject.
    """
    pattern = (
        f'sub-*/task-{task}/fixed_effects/'
        f'sub-*_hemi-{hemisphere}_space-{space}_task-{task}_'
        f'contrast-{contrast}_rtmodel-RTDur_stat-fixed-effects-z_score.func.gii'
    )
    candidates = sorted(Path(lev1_root).glob(pattern))
    if subjects is None:
        return candidates
    keep = set(subjects)
    return [
        p for p in candidates
        if (m := _SUBJECT_RE.search(p.name)) and m.group(1) in keep
    ]


def load_gifti_data(path: Path) -> np.ndarray:
    """Load a 1-D ``.func.gii`` array (a single darray) into a numpy vector."""
    img = nib.load(str(path))
    if not img.darrays:
        raise ValueError(f'GIFTI has no data arrays: {path}')
    return np.asarray(img.darrays[0].data, dtype=np.float64)


def stack_subject_zmaps(paths: list[Path]) -> tuple[np.ndarray, list[str]]:
    """Load and stack subject z-maps into a ``(n_subjects, n_vertices)`` array.

    Subject ids are extracted from filenames so the caller knows the
    ordering.  Raises if vertex counts differ across files (would
    indicate mixed surface spaces).
    """
    if not paths:
        raise ValueError('No subject z-maps provided')
    arrays = []
    subjects = []
    for p in paths:
        m = _SUBJECT_RE.search(p.name)
        if m is None:
            raise ValueError(f'Cannot extract subject id from filename: {p.name}')
        subjects.append(m.group(1))
        arrays.append(load_gifti_data(p))
    shapes = {a.shape for a in arrays}
    if len(shapes) != 1:
        raise ValueError(
            f'Inconsistent vertex counts across subject z-maps: {shapes}.  '
            f'All subjects must be in the same surface space.'
        )
    return np.stack(arrays, axis=0), subjects


# ---------------------------------------------------------------------------
# Prevalence computation
# ---------------------------------------------------------------------------


def z_alpha_two_sided(alpha: float) -> float:
    """Return the positive z critical value for a two-sided test at false-positive rate alpha.

    Example: ``z_alpha_two_sided(0.05) ≈ 1.96``.
    """
    from scipy.stats import norm
    if not (0.0 < alpha < 1.0):
        raise ValueError(f'alpha must lie in (0, 1); got {alpha}')
    return float(norm.isf(alpha / 2.0))


def _bh_fdr_significance(
    zmaps: np.ndarray,
    q: float,
    two_sided: bool,
) -> np.ndarray:
    """Per-subject Benjamini–Hochberg FDR thresholding across vertices.

    Converts each subject's z-stats to p-values (two-sided via ``|z|`` or
    one-sided positive), then applies BH-FDR at level ``q`` across that
    subject's finite vertices.  Returns a boolean ``(n_subj, n_vert)``
    mask; NaN vertices are False (caller invalidates them downstream).
    """
    from scipy.stats import norm
    from statsmodels.stats.multitest import multipletests

    n_subj, n_vert = zmaps.shape
    sig = np.zeros((n_subj, n_vert), dtype=bool)
    for i in range(n_subj):
        z = zmaps[i]
        finite = np.isfinite(z)
        if not finite.any():
            continue
        if two_sided:
            p = 2.0 * norm.sf(np.abs(z[finite]))
        else:
            p = norm.sf(z[finite])
        rej, _, _, _ = multipletests(p, alpha=q, method='fdr_bh')
        sig[i, finite] = rej
    return sig


def _validate_prevalence_args(
    zmaps: np.ndarray,
    z_threshold: Optional[float | np.ndarray],
    per_subject_fdr_q: Optional[float],
) -> None:
    if per_subject_fdr_q is not None and z_threshold is not None:
        raise ValueError(
            'per_subject_fdr_q and z_threshold are mutually exclusive — '
            "they're alternative ways to threshold each subject's map."
        )
    if per_subject_fdr_q is not None and not (0.0 < per_subject_fdr_q < 1.0):
        raise ValueError(
            f'per_subject_fdr_q must lie in (0, 1); got {per_subject_fdr_q}'
        )
    if zmaps.ndim != 2:
        raise ValueError(
            f'zmaps must be 2-D (n_subjects, n_vertices); got shape {zmaps.shape}'
        )
    if zmaps.shape[0] < 2:
        raise ValueError(
            f'Bayesian prevalence is meaningless for n={zmaps.shape[0]} subjects; '
            f'need at least 2.'
        )


def _compute_sig_mask(
    zmaps: np.ndarray,
    alpha: float,
    z_threshold: Optional[float | np.ndarray],
    two_sided: bool,
    per_subject_fdr_q: Optional[float],
) -> tuple[np.ndarray, float, Optional[float]]:
    """Build the per-subject significance mask via one of three strategies.

    Returns ``(sig, z_thr_stored, fdr_q_stored)`` where ``sig`` is
    ``(n_subj, n_vert)`` boolean, ``z_thr_stored`` is the scalar threshold
    to record (NaN when FDR is used), and ``fdr_q_stored`` records the
    FDR q level when that strategy is used (else None).
    """
    n_subjects = zmaps.shape[0]
    if per_subject_fdr_q is not None:
        sig = _bh_fdr_significance(zmaps, per_subject_fdr_q, two_sided)
        return sig, float('nan'), float(per_subject_fdr_q)
    # z-threshold path: scalar or per-subject array
    if z_threshold is None:
        z_thr_arr = np.full(n_subjects, z_alpha_two_sided(alpha), dtype=np.float64)
        z_thr_stored = float(z_thr_arr[0])
    elif np.isscalar(z_threshold):
        z_thr_arr = np.full(n_subjects, float(z_threshold), dtype=np.float64)
        z_thr_stored = float(z_threshold)
    else:
        z_thr_arr = np.asarray(z_threshold, dtype=np.float64).ravel()
        if z_thr_arr.shape[0] != n_subjects:
            raise ValueError(
                f'Per-subject z_threshold length must equal n_subjects '
                f'({n_subjects}); got length {z_thr_arr.shape[0]}'
            )
        z_thr_stored = float(z_thr_arr.mean())
    if two_sided:
        sig = np.abs(zmaps) > z_thr_arr[:, None]
    else:
        sig = zmaps > z_thr_arr[:, None]
    return sig, z_thr_stored, None


def _build_result(
    k_per_vertex: np.ndarray,
    invalid_mask: np.ndarray,
    n_subjects: int,
    alpha: float,
    level: float,
    z_thr_stored: float,
    fdr_q_stored: Optional[float],
) -> PrevalenceResult:
    """Convert a per-vertex k count into a PrevalenceResult (MAP + HPDI)."""
    map_arr = np.where(
        invalid_mask, np.nan,
        map_estimate_vector(np.clip(k_per_vertex, 0, n_subjects), n_subjects, alpha),
    )
    table = hpdi_lookup(n_subjects, alpha, level=level)
    safe_k = np.clip(k_per_vertex, 0, n_subjects)
    hpdi_lo = np.where(invalid_mask, np.nan, table[safe_k, 0])
    hpdi_hi = np.where(invalid_mask, np.nan, table[safe_k, 1])
    n_invalid = int(invalid_mask.sum())
    return PrevalenceResult(
        map=map_arr,
        hpdi_lo=hpdi_lo,
        hpdi_hi=hpdi_hi,
        k_count=np.where(invalid_mask, -1, k_per_vertex),
        n_subjects=n_subjects,
        alpha=alpha,
        z_threshold=z_thr_stored,
        level=level,
        n_vertices_invalid=n_invalid,
        fdr_q=fdr_q_stored,
    )


def compute_prevalence(
    zmaps: np.ndarray,
    alpha: float = 0.05,
    z_threshold: Optional[float | np.ndarray] = None,
    two_sided: bool = True,
    level: float = 0.96,
    per_subject_fdr_q: Optional[float] = None,
) -> PrevalenceResult:
    """Compute per-vertex Bayesian prevalence from a stack of z-maps.

    Args:
        zmaps: ``(n_subjects, n_vertices)`` array of fixed-effects z-stats.
        alpha: within-subject false-positive rate used in the γ correction
            (default 0.05).  When ``per_subject_fdr_q`` is set, alpha is
            still applied in ``γ = (θ − α)/(1 − α)`` — pick it to reflect
            the assumed per-vertex Type I rate (a conservative choice is
            ``alpha = per_subject_fdr_q``).
        z_threshold: optional explicit z critical value.  May be a scalar
            (same threshold for every subject) or a ``(n_subjects,)``
            array (per-subject FWER-corrected thresholds derived e.g.
            from sign-flip permutations — the strong-control variant the
            Ince paper requires).  If None and ``per_subject_fdr_q`` is
            None, derived from ``alpha`` via :func:`z_alpha_two_sided`.
            Mutually exclusive with ``per_subject_fdr_q``.
        two_sided: when True (default) flag vertices with ``|z| > z_α``
            or use a two-sided p-value for FDR; when False, only positive
            direction (``z > z_α`` or one-sided p).
        level: HPDI mass level (default 0.96, matching the paper).
        per_subject_fdr_q: when set, apply Benjamini–Hochberg FDR at level
            ``q`` to each subject's vertices instead of a fixed z cutoff.
            Mutually exclusive with ``z_threshold``.

    Returns:
        :class:`PrevalenceResult` with MAP, HPDI bounds, k counts, and
        bookkeeping metadata.  When FDR is used ``z_threshold`` is NaN
        and ``fdr_q`` records the q level; otherwise ``fdr_q`` is None.
    """
    _validate_prevalence_args(zmaps, z_threshold, per_subject_fdr_q)
    n_subjects = zmaps.shape[0]
    sig, z_thr_stored, fdr_q_stored = _compute_sig_mask(
        zmaps, alpha, z_threshold, two_sided, per_subject_fdr_q,
    )
    invalid_mask = ~np.isfinite(zmaps).all(axis=0)
    k_per_vertex = np.where(invalid_mask, -1, sig.sum(axis=0).astype(int))
    if int(invalid_mask.sum()):
        logger.warning(
            'Prevalence computed with %d invalid vertices (NaN in >=1 subject); '
            'marked NaN in the output map.', int(invalid_mask.sum()),
        )
    return _build_result(
        k_per_vertex, invalid_mask, n_subjects, alpha, level,
        z_thr_stored, fdr_q_stored,
    )


@dataclass
class DirectionalPrevalenceResult:
    """Direction-resolved Bayesian prevalence.

    Built from a single per-subject significance test (typically two-sided
    FDR-BH at level q), then partitioned by sign of z into positive and
    negative direction subsets.  Each direction inherits the test's α /
    z_threshold / fdr_q metadata via its own ``PrevalenceResult``.

    ``consistency`` is per-vertex ``max(k_pos, k_neg) / (k_pos + k_neg)``
    bounded in ``[0.5, 1]``: 1 = all significant subjects agree on
    direction, 0.5 = an even split between positive and negative.  Vertices
    with ``k_pos + k_neg == 0`` are NaN (no significant subjects either
    way).  Invalid (NaN-bearing) vertices are NaN in every output.
    """

    overall: PrevalenceResult
    positive: PrevalenceResult
    negative: PrevalenceResult
    consistency: np.ndarray
    n_vertices_invalid: int


def compute_directional_prevalence(
    zmaps: np.ndarray,
    alpha: float = 0.05,
    z_threshold: Optional[float | np.ndarray] = None,
    two_sided: bool = True,
    level: float = 0.96,
    per_subject_fdr_q: Optional[float] = None,
) -> DirectionalPrevalenceResult:
    """Direction-resolved per-vertex Bayesian prevalence.

    The per-subject significance mask is computed exactly as in
    :func:`compute_prevalence` (defaults to two-sided), then the rejected
    set is partitioned by sign of z at each (subject, vertex):

    - ``sig_pos = sig & (z > 0)`` — subject's positive-direction activation
    - ``sig_neg = sig & (z < 0)`` — subject's negative-direction activation

    The resulting three k-counts (overall = ``k_pos + k_neg`` modulo NaN)
    feed the same Beta-posterior + HPDI machinery, producing three
    prevalence maps that share the same α / threshold metadata.

    A two-sided test is the natural input here (a one-sided test discards
    one tail entirely), but ``two_sided=False`` is accepted for symmetry
    — in that case the negative direction is always empty.

    Returns:
        :class:`DirectionalPrevalenceResult` with three
        :class:`PrevalenceResult` objects plus a per-vertex consistency map.
    """
    _validate_prevalence_args(zmaps, z_threshold, per_subject_fdr_q)
    n_subjects = zmaps.shape[0]
    sig, z_thr_stored, fdr_q_stored = _compute_sig_mask(
        zmaps, alpha, z_threshold, two_sided, per_subject_fdr_q,
    )
    invalid_mask = ~np.isfinite(zmaps).all(axis=0)

    # Partition the significant set by sign.  NaN z-values produce False
    # in both comparisons so they don't leak into either direction count.
    positive_mask = zmaps > 0
    negative_mask = zmaps < 0
    sig_pos = sig & positive_mask
    sig_neg = sig & negative_mask

    k_overall = np.where(invalid_mask, -1, sig.sum(axis=0).astype(int))
    k_pos = np.where(invalid_mask, -1, sig_pos.sum(axis=0).astype(int))
    k_neg = np.where(invalid_mask, -1, sig_neg.sum(axis=0).astype(int))

    overall = _build_result(
        k_overall, invalid_mask, n_subjects, alpha, level, z_thr_stored, fdr_q_stored,
    )
    positive = _build_result(
        k_pos, invalid_mask, n_subjects, alpha, level, z_thr_stored, fdr_q_stored,
    )
    negative = _build_result(
        k_neg, invalid_mask, n_subjects, alpha, level, z_thr_stored, fdr_q_stored,
    )

    # Consistency: agreement among the directional subjects.  We use the
    # positive counts (clipped at 0 to ignore the -1 invalid sentinel) so
    # arithmetic is well-defined; vertices with no significant subjects
    # at all and invalid vertices both end up NaN below.
    safe_k_pos = np.where(invalid_mask, 0, k_pos).astype(np.float64)
    safe_k_neg = np.where(invalid_mask, 0, k_neg).astype(np.float64)
    total = safe_k_pos + safe_k_neg
    with np.errstate(invalid='ignore', divide='ignore'):
        consistency = np.maximum(safe_k_pos, safe_k_neg) / total
    consistency = np.where(invalid_mask | (total == 0), np.nan, consistency)

    return DirectionalPrevalenceResult(
        overall=overall,
        positive=positive,
        negative=negative,
        consistency=consistency,
        n_vertices_invalid=int(invalid_mask.sum()),
    )


# ---------------------------------------------------------------------------
# GIFTI output
# ---------------------------------------------------------------------------


def save_prevalence_gifti(
    result: PrevalenceResult,
    output_dir: Path,
    base_filename: str,
) -> dict[str, Path]:
    """Save prevalence outputs as GIFTIs.

    Writes four files alongside each other with descriptive suffixes::

        <base>_stat-prevalence-map.func.gii
        <base>_stat-prevalence-hpdiLo.func.gii
        <base>_stat-prevalence-hpdiHi.func.gii
        <base>_stat-prevalence-kCount.func.gii

    Returns a dict mapping the four output kinds to their paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {}
    for key, suffix, arr in (
        ('map',      'prevalence-map',      result.map.astype(np.float32)),
        ('hpdi_lo',  'prevalence-hpdiLo',   result.hpdi_lo.astype(np.float32)),
        ('hpdi_hi',  'prevalence-hpdiHi',   result.hpdi_hi.astype(np.float32)),
        ('k_count',  'prevalence-kCount',   result.k_count.astype(np.float32)),
    ):
        darray = nib.gifti.GiftiDataArray(
            data=arr, intent='NIFTI_INTENT_NORMAL', datatype='NIFTI_TYPE_FLOAT32',
        )
        gifti = nib.gifti.GiftiImage()
        gifti.add_gifti_data_array(darray)
        path = output_dir / f'{base_filename}_stat-{suffix}.func.gii'
        gifti.to_filename(str(path))
        files[key] = path

    return files
