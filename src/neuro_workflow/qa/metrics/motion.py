"""Motion metrics extracted from fmriprep confounds TSV files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class MotionMetrics:
    n_vols: int
    fd_mean: float
    fd_max: float
    fd_prop_over_05: float
    dvars_mean: float
    dvars_max: float
    dvars_prop_over_15: float
    n_motion_outliers: int
    fd_series: pd.Series
    dvars_series: pd.Series


def compute_motion(confounds_tsv: Path) -> MotionMetrics:
    """Compute per-scan motion metrics from a fmriprep confounds TSV.

    Returns zeros (not NaN) for any metric whose source column is missing or
    all-NaN, so downstream tables stay numeric.
    """
    df = pd.read_csv(confounds_tsv, sep="\t")

    fd = df["framewise_displacement"].dropna() if "framewise_displacement" in df.columns else pd.Series(dtype=float)
    dvars = df["std_dvars"].dropna() if "std_dvars" in df.columns else pd.Series(dtype=float)

    n_motion_outliers = sum(1 for c in df.columns if c.startswith("motion_outlier"))

    return MotionMetrics(
        n_vols=len(df),
        fd_mean=float(fd.mean()) if len(fd) else 0.0,
        fd_max=float(fd.max()) if len(fd) else 0.0,
        fd_prop_over_05=float((fd > 0.5).mean()) if len(fd) else 0.0,
        dvars_mean=float(dvars.mean()) if len(dvars) else 0.0,
        dvars_max=float(dvars.max()) if len(dvars) else 0.0,
        dvars_prop_over_15=float((dvars > 1.5).mean()) if len(dvars) else 0.0,
        n_motion_outliers=n_motion_outliers,
        fd_series=fd,
        dvars_series=dvars,
    )
