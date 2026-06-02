"""Quality + agreement metrics for MSHBM parcellation arms.

Network labels are aligned across arms by the shared DU15NET prior, so
vertex-wise agreement and per-network Dice are meaningful.
"""
from __future__ import annotations

import numpy as np


def vertex_agreement(a: np.ndarray, b: np.ndarray) -> float:
    """% of vertices labeled (>0) in BOTH that share the same label."""
    both = (a > 0) & (b > 0)
    return float(np.mean(a[both] == b[both])) if both.any() else float("nan")


def dice_per_network(a: np.ndarray, b: np.ndarray, n_networks: int = 15) -> np.ndarray:
    out = np.full(n_networks, np.nan)
    for n in range(1, n_networks + 1):
        A = a == n
        B = b == n
        s = A.sum() + B.sum()
        if s:
            out[n - 1] = 2 * np.sum(A & B) / s
    return out


def parcel_homogeneity(ts: np.ndarray, labels: np.ndarray) -> float:
    """Mean within-parcel functional homogeneity.

    For each parcel: correlate every vertex's timeseries with the parcel-mean
    timeseries, average those correlations; then average across parcels weighted
    by parcel size. ts is (V, T) on the SAME vertices as `labels` (V,).
    """
    vals, weights = [], []
    for n in np.unique(labels[labels > 0]):
        idx = np.where(labels == n)[0]
        if idx.size < 2:
            continue
        P = ts[idx]
        P = P - P.mean(axis=1, keepdims=True)
        mean_ts = P.mean(axis=0)
        mean_ts = mean_ts - mean_ts.mean()
        denom = np.linalg.norm(P, axis=1) * np.linalg.norm(mean_ts)
        denom[denom == 0] = np.nan
        r = (P @ mean_ts) / denom
        vals.append(np.nanmean(r))
        weights.append(idx.size)
    if not vals:
        return float("nan")
    return float(np.average(vals, weights=weights))


def temporal_snr(ts: np.ndarray) -> np.ndarray:
    """Per-vertex tSNR = mean/std over time. (V, T) -> (V,)."""
    mu = ts.mean(axis=1)
    sd = ts.std(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(sd > 0, mu / sd, 0.0)
    return out.astype(np.float64)
