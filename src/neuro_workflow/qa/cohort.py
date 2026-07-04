"""Cohort-relative outlier detection for FreeSurfer Euler numbers."""

from __future__ import annotations

import numpy as np

from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics


def cohort_euler_outliers(
    metrics: dict[str, FreeSurferMetrics],
    n_sigma: float = 2.0,
) -> set[str]:
    """Identify subjects whose Euler number is unusually low for the cohort.

    Uses median absolute deviation (MAD): a subject is flagged if its
    `euler_mean` is more than `n_sigma * MAD` below the cohort median.

    Subjects with no Euler value are excluded from the cohort calculation
    and never flagged here (their FS status will already convey the issue).
    """
    values = {k: v.euler_mean for k, v in metrics.items() if v.euler_mean is not None}
    if not values:
        return set()

    arr = np.array(list(values.values()))
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    if mad == 0.0:
        return set()
    cutoff = median - n_sigma * mad
    return {sub for sub, v in values.items() if v < cutoff}
