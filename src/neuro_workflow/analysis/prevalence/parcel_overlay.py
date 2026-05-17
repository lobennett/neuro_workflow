"""Summarise per-vertex prevalence maps onto MSHBM individual parcels.

The Allen et al. 2021 Bayesian-prevalence pipeline produces a per-vertex
MAP prevalence and HPDI bounds for each (cohort, task, contrast,
hemisphere).  The original brainstorming explicitly anchors these maps
in **subject-specific MSHBM parcellations** rather than a fixed group
atlas: each subject's prevalence support is summed inside their own
individually-mapped networks.

This module computes the parcel-level summary in two complementary ways:

1. **Subject-mean prevalence per parcel** — for each subject, mean
   per-vertex prevalence inside each of their K MSHBM parcels.  Output
   shape: ``(n_subjects, K)``.  Useful for ranking which networks carry
   the contrast effect for each individual.

2. **Cohort prevalence summary per parcel** — for each subject's K
   parcels, what fraction of vertices inside the parcel have a MAP
   prevalence above a threshold (e.g. >0.5).  Then average that
   fraction across subjects.  Output shape: ``(K,)``.  This is the
   "where in the cortex does the effect concentrate" summary the
   downstream analyses care about.

Inputs:
- ``prevalence_map`` (n_vertices,) — the per-vertex MAP prevalence from
  ``aggregate.compute_prevalence``.
- ``subject_dlabels`` mapping ``sub-X`` → 1-D int array of MSHBM parcel
  labels for THAT subject, same vertex space as ``prevalence_map``.
- ``ignore_label`` — typically 0 (medial wall / unassigned), excluded
  from both per-parcel statistics and the across-parcel summary.

MSHBM dlabels are individual parcellations, so each subject's parcel-K
covers a different anatomical region.  Aggregating "mean prevalence
inside parcel-K across subjects" is meaningful precisely because the
network identity is consistent across subjects (Kong 2019); only the
parcel's anatomical location varies.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ParcelOverlay:
    """Per-subject and across-cohort parcel-level prevalence summaries."""

    subject_parcel_mean: np.ndarray   # shape (n_subjects, K)
    cohort_parcel_mean: np.ndarray    # shape (K,) — mean across subjects of subject_parcel_mean
    cohort_parcel_high_frac: np.ndarray  # shape (K,) — mean over subjects of "fraction of parcel vertices with MAP > threshold"
    n_subjects: int
    n_networks: int
    threshold: float


def summarise_parcels(
    prevalence_map: np.ndarray,
    subject_dlabels: dict[str, np.ndarray],
    n_networks: int,
    threshold: float = 0.5,
    ignore_label: int = 0,
) -> ParcelOverlay:
    """Summarise a single per-vertex prevalence map across subject parcels.

    Args:
        prevalence_map: ``(n_vertices,)`` MAP prevalence (one number per
            vertex).  This is *one* cohort-level map computed across all
            subjects, then projected back onto each subject's individual
            parcellation.
        subject_dlabels: dict ``sub-X`` → ``(n_vertices,)`` int parcel
            labels for that subject.  All arrays must share the vertex
            space of ``prevalence_map``.
        n_networks: number of MSHBM networks (K).  Used to fix the
            output shape so a subject without a particular parcel does
            not silently shrink the table.
        threshold: prevalence threshold for the "high-prevalence
            fraction" summary.  0.5 = "majority of population shows
            effect".
        ignore_label: parcel label to skip (default 0 = medial wall).

    Returns:
        :class:`ParcelOverlay` with three matrices: per-subject mean
        prevalence per parcel, cohort-average per parcel, and
        cohort-average of the high-prevalence fraction per parcel.
    """
    if prevalence_map.ndim != 1:
        raise ValueError(
            f'prevalence_map must be 1-D; got shape {prevalence_map.shape}'
        )
    subjects = sorted(subject_dlabels.keys())
    n_subjects = len(subjects)
    if n_subjects == 0:
        raise ValueError('No subjects provided')

    subject_parcel_mean = np.full((n_subjects, n_networks), np.nan, dtype=np.float64)
    subject_parcel_high = np.full((n_subjects, n_networks), np.nan, dtype=np.float64)

    finite_prev = np.isfinite(prevalence_map)

    for i, subj in enumerate(subjects):
        labels = subject_dlabels[subj]
        if labels.shape != prevalence_map.shape:
            raise ValueError(
                f'{subj}: dlabel shape {labels.shape} != prevalence shape '
                f'{prevalence_map.shape}'
            )
        for k in range(1, n_networks + 1):
            if k == ignore_label:
                continue
            in_parcel = (labels == k) & finite_prev
            if not in_parcel.any():
                continue
            parcel_vals = prevalence_map[in_parcel]
            subject_parcel_mean[i, k - 1] = float(parcel_vals.mean())
            subject_parcel_high[i, k - 1] = float((parcel_vals > threshold).mean())

    with np.errstate(invalid='ignore'):
        cohort_parcel_mean = np.nanmean(subject_parcel_mean, axis=0)
        cohort_parcel_high = np.nanmean(subject_parcel_high, axis=0)

    return ParcelOverlay(
        subject_parcel_mean=subject_parcel_mean,
        cohort_parcel_mean=cohort_parcel_mean,
        cohort_parcel_high_frac=cohort_parcel_high,
        n_subjects=n_subjects,
        n_networks=n_networks,
        threshold=threshold,
    )