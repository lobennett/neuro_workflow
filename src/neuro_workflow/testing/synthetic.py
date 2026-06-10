"""Synthetic-data generators for scientific-validity tests.

These helpers manufacture a known ground truth so a test can plant a
contrast effect of a chosen magnitude, push the synthetic data through the
*real* lev1 design-matrix / first-level-fit / contrast code, and assert the
planted effect is recovered. The point is to validate that the GLM path
computes what it is supposed to — not to reimplement the GLM.

Dependency-light by design: numpy / pandas / nibabel only. No nilearn import
here so the module stays cheap to import; the nilearn-backed fit lives in the
test that consumes these helpers.

All randomness is explicitly seeded (``numpy.random.default_rng(seed)``) so
generated data is deterministic and tests are reproducible.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

import nibabel as nib
import numpy as np
import pandas as pd

__all__ = [
    "make_events",
    "plant_bold",
    "as_4d_nifti",
    "make_mask",
    "make_synthetic_run",
]


def make_events(
    task: str,
    n_trials: int,
    tr: float = 1.49,
    *,
    trial_types: Sequence[str] = ("congruent", "incongruent"),
    iti: float = 6.0,
    duration: float = 1.0,
    response_time: float = 0.5,
    start: float = 5.0,
) -> pd.DataFrame:
    """Build a valid events table for a real task's regressors.

    The default columns/values target the ``flanker`` task's regressor config
    (``congruent`` / ``incongruent`` trial types plus the columns its subset
    queries reference: ``key_press``, ``correct_response``, ``response_time``,
    ``trial_id``, ``omission``, ``commission``, ``rt_too_fast``). Trials of
    each ``trial_types`` entry are interleaved at a fixed inter-trial interval
    so onsets are well-separated and the resulting regressors are estimable.

    Args:
        task: Task name (recorded on the frame for traceability; the column
            layout is generic enough for the single-task flanker-style configs).
        n_trials: Number of trials *per* trial type.
        tr: Repetition time (seconds). Recorded for the caller's convenience;
            onsets themselves are TR-independent.
        trial_types: Ordered trial-type labels to interleave.
        iti: Inter-trial interval (seconds) between successive trial onsets.
        duration: Per-trial stimulus duration (seconds).
        response_time: Per-trial response time (seconds); all trials are
            scored as correct responses so they pass the flanker subset query.
        start: Onset (seconds) of the first trial.

    Returns:
        An events DataFrame with one row per trial, sorted by onset.
    """
    n_types = len(trial_types)
    rows = []
    for i in range(n_trials):
        for j, ttype in enumerate(trial_types):
            onset = start + (i * n_types + j) * iti
            rows.append(
                {
                    "onset": onset,
                    "duration": duration,
                    "trial_type": ttype,
                    "trial_id": "test_trial",
                    # Correct response: key_press matches correct_response so
                    # the flanker subset query (key_press == correct_response
                    # and response_time >= 0.2) selects every trial.
                    "key_press": 1,
                    "correct_response": 1,
                    "response_time": response_time,
                    # Error-trial indicator columns (all clean): the flanker
                    # config builds omission/commission/rt_fast regressors from
                    # these amplitude columns. Zero amplitude -> zero regressor.
                    "omission": 0,
                    "commission": 0,
                    "rt_too_fast": 0,
                }
            )
    events = pd.DataFrame(rows)
    events["task"] = task
    return events.sort_values("onset").reset_index(drop=True)


def plant_bold(
    design: pd.DataFrame,
    betas: Mapping[str, float],
    *,
    noise_sd: float = 1.0,
    seed: int = 0,
) -> np.ndarray:
    """Synthesize a 1-D BOLD timeseries from a design matrix and known betas.

    Computes ``y = design @ beta_vector + N(0, noise_sd)``, where the beta
    vector is built from ``betas`` (any design column not named in ``betas``
    gets coefficient 0.0). This is the ground-truth signal the GLM should
    recover.

    Args:
        design: Design matrix (rows = timepoints, columns = regressors). The
            same matrix that will be handed to the real first-level fit.
        betas: Mapping of design-column name -> planted coefficient.
        noise_sd: Standard deviation of additive Gaussian noise. 0 yields a
            noiseless timeseries (exact recovery).
        seed: Seed for the local RNG; identical seeds give identical output.

    Returns:
        1-D ``float64`` array of length ``len(design)``.

    Raises:
        KeyError: If ``betas`` names a column absent from ``design``.
    """
    missing = [name for name in betas if name not in design.columns]
    if missing:
        raise KeyError(
            f"betas reference columns not in design: {missing} "
            f"(available: {list(design.columns)})"
        )

    beta_vec = np.array(
        [float(betas.get(col, 0.0)) for col in design.columns],
        dtype=float,
    )
    clean = design.to_numpy(dtype=float) @ beta_vec

    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, noise_sd, size=clean.shape) if noise_sd else 0.0
    return (clean + noise).astype(np.float64)


def as_4d_nifti(
    timeseries: np.ndarray,
    *,
    n_voxels: int = 8,
    affine: Optional[np.ndarray] = None,
) -> nib.Nifti1Image:
    """Wrap a 1-D BOLD timeseries into a small 4D NIfTI image.

    nilearn's ``FirstLevelModel`` expects a 4D image (x, y, z, t). The same
    timeseries is broadcast into a tiny spatial block of identical voxels so
    auto-masking has something to work with and the fit is well-defined.

    Args:
        timeseries: 1-D array of length n_timepoints.
        n_voxels: Side count -> image is (n_voxels, 1, 1, T) identical voxels.
        affine: Optional 4x4 affine; defaults to identity.

    Returns:
        A ``nibabel.Nifti1Image`` of shape (n_voxels, 1, 1, n_timepoints).
    """
    ts = np.asarray(timeseries, dtype=np.float64).ravel()
    n_t = ts.shape[0]
    # (x, y, z, t): a 1-D row of identical voxels over time.
    data = np.broadcast_to(ts, (n_voxels, 1, 1, n_t)).astype(np.float32)
    if affine is None:
        affine = np.eye(4)
    return nib.Nifti1Image(np.ascontiguousarray(data), affine)


def make_mask(
    img: nib.Nifti1Image,
    *,
    affine: Optional[np.ndarray] = None,
) -> nib.Nifti1Image:
    """Build an all-ones 3D brain mask matching a 4D BOLD image's geometry.

    nilearn's auto EPI-masking rejects synthetic data whose voxels are
    spatially uniform (it computes an empty mask). Passing an explicit mask
    to the real ``fit_run_glm`` (which accepts ``mask_img``) sidesteps that
    without leaving the production code path.

    Args:
        img: A 4D NIfTI (e.g. from ``as_4d_nifti``); its first 3 dims and
            affine define the mask geometry.
        affine: Optional affine override; defaults to ``img``'s affine.

    Returns:
        A 3D ``uint8`` all-ones ``nibabel.Nifti1Image``.
    """
    spatial_shape = img.shape[:3]
    mask_data = np.ones(spatial_shape, dtype=np.uint8)
    if affine is None:
        affine = img.affine
    return nib.Nifti1Image(mask_data, affine)


def make_synthetic_run(
    design: pd.DataFrame,
    betas: Mapping[str, float],
    *,
    noise_sd: float = 1.0,
    seed: int = 0,
    n_voxels: int = 8,
) -> Tuple[nib.Nifti1Image, Dict[str, float]]:
    """Convenience: plant a timeseries and wrap it as a 4D NIfTI in one call.

    Args:
        design: Design matrix to plant into.
        betas: Planted coefficients keyed by design-column name.
        noise_sd: Gaussian noise SD (see ``plant_bold``).
        seed: RNG seed (see ``plant_bold``).
        n_voxels: Spatial block size (see ``as_4d_nifti``).

    Returns:
        Tuple of (4D NIfTI image, the planted-beta mapping as plain floats).
    """
    ts = plant_bold(design, betas, noise_sd=noise_sd, seed=seed)
    img = as_4d_nifti(ts, n_voxels=n_voxels)
    planted = {k: float(v) for k, v in betas.items()}
    return img, planted
