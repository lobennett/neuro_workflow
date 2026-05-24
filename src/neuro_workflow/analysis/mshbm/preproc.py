"""Rest-fMRI preprocessing for MSHBM input alignment with CBIG.

Implements: confound regression, motion mask, bad-frame interpolation,
bandpass filter. All functions operate on numpy arrays (vertex × time);
I/O lives in run.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt


def regress_confounds(Y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Regress confound design matrix X out of vertex × time data Y.

    Adds intercept + linear ramp internally (so callers should pass only
    nuisance regressors, not detrend columns).

    Args:
        Y: (V, T) — vertex × time data.
        X: (T, K) — confound regressors. NaN-rows are zeroed (fmriprep
           emits NaN in the first row of derivatives/squares).

    Returns:
        (V, T) residuals.
    """
    if Y.ndim != 2 or X.ndim != 2 or Y.shape[1] != X.shape[0]:
        raise ValueError(f'Y shape {Y.shape}, X shape {X.shape} mismatch')

    T = Y.shape[1]
    X = np.nan_to_num(X, nan=0.0).astype(np.float64, copy=True)
    intercept = np.ones((T, 1))
    ramp = np.linspace(-1.0, 1.0, T)[:, None]
    quad = (ramp ** 2 - (1.0 / 3.0))  # zero-mean quadratic
    Xfull = np.concatenate([intercept, ramp, quad, X], axis=1)

    # Solve once: betas = (X'X)^-1 X' Y'
    Yt = Y.T.astype(np.float64, copy=False)  # (T, V)
    betas, *_ = np.linalg.lstsq(Xfull, Yt, rcond=None)
    Y_resid = (Yt - Xfull @ betas).T  # (V, T)
    return Y_resid.astype(Y.dtype, copy=False)


def build_motion_mask(
    fd: np.ndarray,
    dvars: np.ndarray,
    fd_thresh: float,
    dvars_thresh: float,
) -> np.ndarray:
    """Return int8 mask (1=keep, 0=drop) over T frames.

    Drop a frame if FD > fd_thresh OR DVARS > dvars_thresh OR either is NaN.
    DVARS is interpreted as fmriprep's std_dvars (z-scored).
    """
    fd = np.asarray(fd, dtype=np.float64)
    dvars = np.asarray(dvars, dtype=np.float64)
    bad = (fd > fd_thresh) | (dvars > dvars_thresh) | np.isnan(fd) | np.isnan(dvars)
    return (~bad).astype(np.int8)


def interpolate_bad_frames(Y: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Linear-interpolate over time at frames where mask == 0.

    Edge bad frames are clamped to the nearest good neighbor (no extrapolation).
    If all frames are bad, returns Y unchanged (caller should reject upstream).

    Args:
        Y: (V, T)
        mask: (T,) int8, 1=keep, 0=drop.

    Returns:
        (V, T) with bad frames replaced.
    """
    mask = np.asarray(mask, dtype=bool)
    T = Y.shape[1]
    if not mask.any():
        return Y.copy()
    good_idx = np.where(mask)[0]
    Yi = Y.copy().astype(np.float64, copy=False)
    for v in range(Y.shape[0]):
        Yi[v] = np.interp(np.arange(T), good_idx, Y[v, good_idx])
    return Yi.astype(Y.dtype, copy=False)


def bandpass_filter(
    Y: np.ndarray,
    tr: float,
    lowcut: float,
    highcut: float,
    order: int = 4,
) -> np.ndarray:
    """Two-pass Butterworth bandpass filter applied along the time axis.

    Args:
        Y: (V, T) data.
        tr: repetition time in seconds.
        lowcut: low cutoff Hz (e.g. 0.009).
        highcut: high cutoff Hz (e.g. 0.08).
        order: Butterworth order (default 4, applied twice via filtfilt).

    Returns:
        (V, T) filtered.
    """
    nyq = 0.5 / tr
    low = lowcut / nyq
    high = highcut / nyq
    if not (0 < low < high < 1):
        raise ValueError(f'invalid band: low={lowcut} high={highcut} TR={tr}')
    b, a = butter(order, [low, high], btype='bandpass')
    return filtfilt(b, a, Y, axis=1).astype(Y.dtype, copy=False)


_MOTION_BASE = ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z']


def build_regressor_matrix(confounds_df: pd.DataFrame) -> np.ndarray:
    """Select 31 nuisance regressors from a fmriprep confounds DataFrame.

    Layout: 6 motion + 6 derivatives + 6 squares + 6 deriv-squares
    + WM + CSF + first 5 aCompCor.
    GSR is NOT included (per spec). NaN replaced by 0.

    Returns:
        (T, 31) float64 numpy array.
    """
    cols = (
        _MOTION_BASE
        + [c + '_derivative1' for c in _MOTION_BASE]
        + [c + '_power2' for c in _MOTION_BASE]
        + [c + '_derivative1_power2' for c in _MOTION_BASE]
        + ['white_matter', 'csf']
        + [f'a_comp_cor_0{i}' for i in range(5)]
    )
    missing = [c for c in cols if c not in confounds_df.columns]
    if missing:
        raise KeyError(f'confounds.tsv missing required columns: {missing}')
    X = confounds_df.loc[:, cols].to_numpy(dtype=np.float64)
    return np.nan_to_num(X, nan=0.0)


def build_regressor_matrix_du2025(confounds_df: pd.DataFrame) -> np.ndarray:
    """Du et al. 2025 Neuron-style 18-regressor nuisance matrix.

    Per their methods (Du et al. 2025, p. 19): six head motion + whole-brain
    (GSR) + ventricular (CSF) + deep cerebral white matter signals, plus the
    temporal derivatives of each.  Total = 9 base + 9 derivatives = 18.
    NaN replaced by 0 (fmriprep emits NaN in the first row of derivatives).

    fmriprep confounds.tsv naming used:
      - 6 motion: trans_x, trans_y, trans_z, rot_x, rot_y, rot_z
      - 1 whole-brain (GSR): global_signal
      - 1 ventricular (CSF mask signal): csf
      - 1 deep white matter (eroded WM mask signal): white_matter
      - + their *_derivative1 versions

    Returns:
        (T, 18) float64 numpy array.
    """
    base = (
        list(_MOTION_BASE)
        + ['global_signal', 'csf', 'white_matter']
    )
    cols = base + [c + '_derivative1' for c in base]
    missing = [c for c in cols if c not in confounds_df.columns]
    if missing:
        raise KeyError(f'confounds.tsv missing Du-2025 columns: {missing}')
    X = confounds_df.loc[:, cols].to_numpy(dtype=np.float64)
    return np.nan_to_num(X, nan=0.0)


def write_censor_tsv(mask: np.ndarray, out_path: Path) -> None:
    """Write single-column 0/1 censor file (CBIG MSHBM convention)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(str(int(v)) for v in mask) + '\n')
