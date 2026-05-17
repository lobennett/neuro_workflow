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
    alpha: float               # within-subject FPR used
    z_threshold: float         # corresponding z-stat threshold
    level: float               # HPDI mass level (e.g. 0.96)
    n_vertices_invalid: int    # vertices marked NaN due to subject NaN


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
    """Return the positive z critical value for a two-sided test at FPR alpha.

    Example: ``z_alpha_two_sided(0.05) ≈ 1.96``.
    """
    from scipy.stats import norm
    if not (0.0 < alpha < 1.0):
        raise ValueError(f'alpha must lie in (0, 1); got {alpha}')
    return float(norm.isf(alpha / 2.0))


def compute_prevalence(
    zmaps: np.ndarray,
    alpha: float = 0.05,
    z_threshold: Optional[float] = None,
    two_sided: bool = True,
    level: float = 0.96,
) -> PrevalenceResult:
    """Compute per-vertex Bayesian prevalence from a stack of z-maps.

    Args:
        zmaps: ``(n_subjects, n_vertices)`` array of fixed-effects z-stats.
        alpha: within-subject NHST false-positive rate (default 0.05).
        z_threshold: optional explicit z critical value.  If None, derived
            from ``alpha`` via the standard normal — see
            :func:`z_alpha_two_sided`.  Pass an explicit, FWER-corrected
            z-threshold (e.g. from a permutation max-statistic) to apply
            the strong-control assumption the Ince paper requires.
        two_sided: when True (default) flag vertices with ``|z| > z_α``;
            when False, only ``z > z_α`` (one-sided positive direction).
        level: HPDI mass level (default 0.96, matching the paper).

    Returns:
        :class:`PrevalenceResult` with MAP, HPDI bounds, k counts, and
        bookkeeping metadata.
    """
    if zmaps.ndim != 2:
        raise ValueError(f'zmaps must be 2-D (n_subjects, n_vertices); got shape {zmaps.shape}')
    n_subjects, n_vertices = zmaps.shape
    if n_subjects < 2:
        raise ValueError(
            f'Bayesian prevalence is meaningless for n={n_subjects} subjects; '
            f'need at least 2.'
        )
    if z_threshold is None:
        z_threshold = z_alpha_two_sided(alpha)

    # Per-vertex significance: handle NaN-bearing vertices (subjects that
    # had no valid data at some surface location).  A vertex with NaN in
    # any subject is marked invalid; we set its outputs to NaN instead of
    # silently counting 0/n.
    invalid_mask = ~np.isfinite(zmaps).all(axis=0)
    if two_sided:
        sig = np.abs(zmaps) > z_threshold
    else:
        sig = zmaps > z_threshold
    # NaN inputs would have produced False under the comparison; force the
    # invalid vertices to NaN downstream rather than counting them as 0.
    k_per_vertex = np.where(invalid_mask, -1, sig.sum(axis=0).astype(int))

    # Vectorised MAP via closed form (cheap).
    map_arr = np.where(
        invalid_mask, np.nan, map_estimate_vector(np.clip(k_per_vertex, 0, n_subjects), n_subjects, alpha),
    )

    # HPDI: precompute lookup table at every k in [0, n], then index.
    table = hpdi_lookup(n_subjects, alpha, level=level)
    safe_k = np.clip(k_per_vertex, 0, n_subjects)
    hpdi_lo = np.where(invalid_mask, np.nan, table[safe_k, 0])
    hpdi_hi = np.where(invalid_mask, np.nan, table[safe_k, 1])

    n_invalid = int(invalid_mask.sum())
    if n_invalid:
        logger.warning(
            'Prevalence computed with %d invalid vertices (NaN in >=1 subject); '
            'marked NaN in the output map.', n_invalid,
        )

    return PrevalenceResult(
        map=map_arr,
        hpdi_lo=hpdi_lo,
        hpdi_hi=hpdi_hi,
        k_count=np.where(invalid_mask, -1, k_per_vertex),
        n_subjects=n_subjects,
        alpha=alpha,
        z_threshold=float(z_threshold),
        level=level,
        n_vertices_invalid=n_invalid,
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
