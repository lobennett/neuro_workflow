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

from pathlib import Path
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
    "write_confounds_tsv",
    "write_fmriprep_bold",
    "make_fmriprep_run",
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


# --------------------------------------------------------------------------- #
# fMRIPrep-derivative stubs for end-to-end pipeline simulation.
#
# These manufacture a minimal-but-real fMRIPrep derivative set for ONE scan so
# the *production* file-discovery (analysis/io/file_discovery.py::FileFinder)
# discovers it and the *production* motion-exclusion generator
# (exclusions/motion.py::MotionGenerator) reads it. Filenames reproduce
# FileFinder's globs and MotionGenerator's confounds-filename regex EXACTLY;
# the confounds columns are the exact two MotionGenerator consumes
# (framewise_displacement, std_dvars) plus a handful of realistic extras.
# --------------------------------------------------------------------------- #

# Sentinel fMRIPrep writes for the first FD/DVARS frame (no preceding volume to
# difference against). pandas.read_csv parses "n/a" to NaN, and MotionGenerator
# drops NaN via to_numeric(errors="coerce").dropna() — matching production.
_NA = "n/a"

# fMRIPrep volume-template defaults used in this project's production output;
# kept in sync with FileFinder's defaults (MNI152NLin6Asym, res-2).
_MNI_TEMPLATE = "MNI152NLin6Asym"
_MNI_RES = "2"

# Confounds columns beyond the two MotionGenerator reads. Present so the TSV
# looks like a real fmriprep confounds file and so callers exercising other
# confound-consuming code (lev1) find plausible columns. MotionGenerator only
# reads framewise_displacement + std_dvars; these are inert for it.
_EXTRA_CONFOUND_COLUMNS = (
    "dvars",
    "global_signal",
    "csf",
    "white_matter",
    "trans_x",
    "trans_y",
    "trans_z",
    "rot_x",
    "rot_y",
    "rot_z",
)


def write_confounds_tsv(
    func_dir: Path,
    *,
    prefix: str,
    n_trs: int,
    fd_mean: float = 0.05,
    fd_spikes: int = 0,
    dvars_spikes: int = 0,
    seed: int = 0,
) -> Path:
    """Write a synthetic fMRIPrep ``desc-confounds_timeseries.tsv``.

    The filename is ``<prefix>_desc-confounds_timeseries.tsv`` — the exact
    suffix both ``FileFinder`` (``desc-confounds_timeseries.tsv`` substring)
    and ``MotionGenerator._parse_confounds_filename`` (full
    ``sub-..._ses-..._task-..._run-..._desc-confounds_timeseries.tsv`` regex)
    expect. The table always contains ``framewise_displacement`` and
    ``std_dvars`` (the two columns ``MotionGenerator._compute_metrics`` reads),
    each with ``n/a`` in the first row to mirror fmriprep (no preceding volume
    to difference), plus a handful of realistic extra columns.

    ``fd_spikes`` / ``dvars_spikes`` plant that many high-motion frames so a
    caller can deterministically trip (or stay under) the proportion
    thresholds: each FD spike is set to 0.8 (> the 0.5 cutoff
    ``MotionGenerator`` counts) and each DVARS spike to 2.0 (> the 1.5 std_dvars
    cutoff). Spikes are placed in the non-first frames; baseline frames sit at
    ``fd_mean`` (FD) / 1.0 (std_dvars), both below threshold.

    Args:
        func_dir: Destination ``.../func`` directory (created if absent).
        prefix: BIDS filename prefix
            (``sub-X_ses-Y_task-T_run-N``); no trailing underscore.
        n_trs: Number of rows (volumes) in the TSV.
        fd_mean: Baseline framewise-displacement value for non-spike frames.
        fd_spikes: Count of frames forced to FD = 0.8 (> 0.5).
        dvars_spikes: Count of frames forced to std_dvars = 2.0 (> 1.5).
        seed: RNG seed (currently only used to add tiny jitter to the extra
            nuisance columns; FD/DVARS baselines are deterministic constants so
            the threshold decision is fully controllable).

    Returns:
        Path to the written TSV.

    Raises:
        ValueError: if ``fd_spikes`` or ``dvars_spikes`` exceeds the number of
            non-first frames (``n_trs - 1``).
    """
    func_dir = Path(func_dir)
    func_dir.mkdir(parents=True, exist_ok=True)

    n_usable = max(n_trs - 1, 0)
    if fd_spikes > n_usable or dvars_spikes > n_usable:
        raise ValueError(
            f"requested more spikes (fd={fd_spikes}, dvars={dvars_spikes}) than "
            f"non-first frames available ({n_usable}) for n_trs={n_trs}"
        )

    rng = np.random.default_rng(seed)

    # Build float arrays first; the first frame is overwritten with the n/a
    # sentinel at write time. Spikes occupy the FIRST `n` non-first frames,
    # which keeps the planted proportion exact and independent of the seed.
    fd = np.full(n_trs, float(fd_mean), dtype=float)
    dvars_std = np.ones(n_trs, dtype=float)
    if n_trs > 0:
        if fd_spikes:
            fd[1 : 1 + fd_spikes] = 0.8
        if dvars_spikes:
            dvars_std[1 : 1 + dvars_spikes] = 2.0

    # Realistic-looking raw dvars (BOLD-intensity units) and nuisance regressors.
    # MotionGenerator ignores these; they exist so the file resembles fmriprep
    # output and so a wrong reader (raw `dvars`) would behave differently.
    raw_dvars = 15.0 + rng.normal(0.0, 0.5, size=n_trs)
    columns: Dict[str, list] = {
        "framewise_displacement": _format_with_na(fd),
        "std_dvars": _format_with_na(dvars_std),
        "dvars": _format_with_na(raw_dvars),
    }
    for col in _EXTRA_CONFOUND_COLUMNS:
        if col in columns:
            continue
        vals = rng.normal(0.0, 0.1, size=n_trs)
        columns[col] = [f"{v:.6f}" for v in vals]

    df = pd.DataFrame(columns)
    path = func_dir / f"{prefix}_desc-confounds_timeseries.tsv"
    df.to_csv(path, sep="\t", index=False)
    return path


def _format_with_na(values: np.ndarray) -> list:
    """Format a float column for a confounds TSV with an ``n/a`` first row.

    fmriprep writes the first framewise-displacement / std_dvars value as
    ``n/a`` (there is no preceding volume to difference against). Subsequent
    rows are plain floats. Returning strings lets a single column hold the
    ``n/a`` sentinel alongside numeric values, exactly as the real TSV does.
    """
    out = [f"{v:.6f}" for v in values]
    if out:
        out[0] = _NA
    return out


def _write_surface_gifti(path: Path, n_trs: int, n_vertices: int, seed: int) -> Path:
    """Write a small, genuinely loadable ``.func.gii`` time series.

    One GIFTI data array per timepoint (NIFTI_INTENT_TIME_SERIES), each a
    1-D float32 vector over vertices — the layout fmriprep BOLD GIFTIs use.
    """
    rng = np.random.default_rng(seed)
    darrays = []
    for _ in range(n_trs):
        data = rng.normal(0.0, 1.0, size=n_vertices).astype(np.float32)
        darrays.append(
            nib.gifti.GiftiDataArray(
                data=data,
                intent="NIFTI_INTENT_TIME_SERIES",
                datatype="NIFTI_TYPE_FLOAT32",
            )
        )
    gii = nib.gifti.GiftiImage(darrays=darrays)
    nib.save(gii, str(path))
    return path


def _write_cifti_dtseries(path: Path, n_trs: int, n_grayordinates: int) -> Path:
    """Write a small ``.dtseries.nii`` placeholder (a NIfTI-2 container).

    A real CIFTI dtseries carries a CIFTI-2 XML extension describing brain
    models; that is heavyweight and nothing in the discovery/motion path reads
    it. We write a loadable NIfTI-2 image of shape (1, 1, 1, 1, n_trs,
    n_grayordinates) so ``nib.load`` succeeds and the filename matches
    FileFinder's glob exactly. Callers needing a true CIFTI should build one
    explicitly.
    """
    rng = np.random.default_rng(0)
    data = rng.normal(0.0, 1.0, size=(1, 1, 1, 1, n_trs, n_grayordinates)).astype(np.float32)
    img = nib.Nifti2Image(data, affine=np.eye(4))
    nib.save(img, str(path))
    return path


def write_fmriprep_bold(
    func_dir: Path,
    *,
    prefix: str,
    space: str,
    n_trs: int,
    n_voxels: int = 4,
    n_vertices: int = 32,
    n_grayordinates: int = 64,
    seed: int = 0,
) -> Dict[str, Path]:
    """Write the BOLD (and brain mask) derivative file(s) for one space.

    Suffixes reproduce ``FileFinder``'s globs EXACTLY:

    =============  ===========================================================
    ``space``      files written (keyed by FileFinder file-type)
    =============  ===========================================================
    ``"MNI"``      ``mni_data``  ``space-{T}_res-{R}_desc-preproc_bold.nii.gz``
                   ``mni_brain_mask`` ``space-{T}_res-{R}_desc-brain_mask.nii.gz``
    ``"T1w"``      ``t1w_data``  ``space-T1w_desc-preproc_bold.nii.gz``
                   ``t1w_brain_mask`` ``space-T1w_desc-brain_mask.nii.gz``
    ``"surface"`` / ``left_surface``  ``hemi-L_space-fsnative_bold.func.gii``
    ``"fsnative"`` ``right_surface`` ``hemi-R_space-fsnative_bold.func.gii``
    ``"fsaverage6"`` ``left/right_surface`` ``hemi-{L,R}_space-fsaverage6_bold.func.gii``
    ``"fsLR"``     ``cifti_bold`` ``space-fsLR_den-91k_bold.dtseries.nii``
    =============  ===========================================================

    where ``T`` = ``MNI152NLin6Asym`` and ``R`` = ``2`` (this project's
    production MNI variant, matching ``FileFinder`` defaults).

    Volume files are real 4D NIfTIs (via :func:`as_4d_nifti`) with a matching
    3D all-ones mask (:func:`make_mask`); surface files are loadable
    ``.func.gii`` time series; the cifti is a loadable NIfTI-2 ``.dtseries.nii``
    placeholder.

    Args:
        func_dir: Destination ``.../func`` directory (created if absent).
        prefix: BIDS filename prefix (``sub-X_ses-Y_task-T_run-N``).
        space: One of ``MNI``, ``T1w``, ``surface``/``fsnative``,
            ``fsaverage6``, ``fsLR``.
        n_trs: Number of timepoints.
        n_voxels: Spatial block side for volume BOLD (see :func:`as_4d_nifti`).
        n_vertices: Per-hemisphere vertex count for surface GIFTIs.
        n_grayordinates: Grayordinate count for the cifti placeholder.
        seed: RNG seed for the synthesized signal.

    Returns:
        Mapping of FileFinder file-type key -> written :class:`~pathlib.Path`.

    Raises:
        ValueError: on an unknown ``space``.
    """
    func_dir = Path(func_dir)
    func_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    def _vol(name: str) -> Path:
        ts = rng.normal(0.0, 1.0, size=n_trs)
        img = as_4d_nifti(ts, n_voxels=n_voxels)
        path = func_dir / name
        nib.save(img, str(path))
        return path

    def _mask(name: str) -> Path:
        # Build a 3D all-ones mask matching the volume geometry.
        ref = as_4d_nifti(np.zeros(max(n_trs, 1)), n_voxels=n_voxels)
        path = func_dir / name
        nib.save(make_mask(ref), str(path))
        return path

    written: Dict[str, Path] = {}

    if space == "MNI":
        tag = f"space-{_MNI_TEMPLATE}_res-{_MNI_RES}"
        written["mni_data"] = _vol(f"{prefix}_{tag}_desc-preproc_bold.nii.gz")
        written["mni_brain_mask"] = _mask(f"{prefix}_{tag}_desc-brain_mask.nii.gz")
    elif space == "T1w":
        written["t1w_data"] = _vol(f"{prefix}_space-T1w_desc-preproc_bold.nii.gz")
        written["t1w_brain_mask"] = _mask(f"{prefix}_space-T1w_desc-brain_mask.nii.gz")
    elif space in ("surface", "fsnative", "fsaverage6"):
        surf_space = "fsnative" if space in ("surface", "fsnative") else "fsaverage6"
        written["left_surface"] = _write_surface_gifti(
            func_dir / f"{prefix}_hemi-L_space-{surf_space}_bold.func.gii",
            n_trs,
            n_vertices,
            seed,
        )
        written["right_surface"] = _write_surface_gifti(
            func_dir / f"{prefix}_hemi-R_space-{surf_space}_bold.func.gii",
            n_trs,
            n_vertices,
            seed + 1,
        )
    elif space == "fsLR":
        written["cifti_bold"] = _write_cifti_dtseries(
            func_dir / f"{prefix}_space-fsLR_den-91k_bold.dtseries.nii",
            n_trs,
            n_grayordinates,
        )
    else:
        raise ValueError(
            f"unknown space {space!r}; expected one of "
            "MNI, T1w, surface, fsnative, fsaverage6, fsLR"
        )

    return written


def make_fmriprep_run(
    fmriprep_dir: Path,
    subject: str,
    session: str,
    task: str,
    run: str,
    *,
    space: str,
    n_trs: int,
    version: str = "25.2.4",
    motion: str = "clean",
    n_voxels: int = 4,
    seed: int = 0,
) -> Dict[str, Path]:
    """Synthesize a full fMRIPrep derivative set for ONE scan.

    Creates ``<fmriprep_dir>/sub-{subject}/ses-{session}/func/`` and writes a
    confounds TSV plus the space-appropriate BOLD/mask file(s), all sharing the
    BIDS prefix ``sub-{subject}_ses-{session}_task-{task}_run-{run}`` so the
    real ``FileFinder`` discovers them and the real ``MotionGenerator`` parses
    them.

    ``motion`` controls the planted confounds:

    * ``"clean"`` — FD mean 0.05, no spikes; std_dvars ~1.0. Stays under the
      project thresholds (task: proportion FD>0.5 == 0; rest: FD mean 0.05 <
      0.2; proportion std_dvars>1.5 == 0), so ``MotionGenerator`` emits no
      exclusion.
    * ``"high"`` — plants 30 FD spikes (FD=0.8) and 30 std_dvars spikes
      (=2.0) into a 100-frame baseline-equivalent run. With ``n_trs`` frames
      the spike count scales as ``round(0.3 * n_trs)`` so the planted
      proportion (~0.30) and the rest FD mean both clear the 0.2 thresholds
      regardless of run length, making the exclusion deterministic.

    Note that ``fmriprep_dir`` is whatever directory the consumer treats as the
    derivatives root: ``FileFinder`` is constructed with this path directly,
    whereas ``MotionGenerator`` expects it at
    ``<bids_dir>/derivatives/fmriprep_{version}`` — pass that nested path as
    ``fmriprep_dir`` when driving the motion generator.

    Args:
        fmriprep_dir: fMRIPrep derivatives root (subject dirs created beneath).
        subject: Subject label without the ``sub-`` prefix (e.g. ``"s01"``).
        session: Session label without the ``ses-`` prefix (e.g. ``"01"``).
        task: Task name (e.g. ``"flanker"``, ``"rest"``).
        run: Run label without the ``run-`` prefix (e.g. ``"1"``).
        space: Analysis space (see :func:`write_fmriprep_bold`).
        n_trs: Number of timepoints / confounds rows.
        version: fMRIPrep version (recorded for traceability; the caller is
            responsible for placing ``fmriprep_dir`` consistently with it).
        motion: ``"clean"`` or ``"high"`` (see above).
        n_voxels: Spatial block side for volume BOLD.
        seed: RNG seed threaded into the confounds and BOLD writers.

    Returns:
        Mapping of written file-type key -> :class:`~pathlib.Path`, including
        ``"confounds"`` and the space-appropriate BOLD/mask keys.

    Raises:
        ValueError: on an unknown ``motion`` mode (delegated ``space`` errors
            propagate from :func:`write_fmriprep_bold`).
    """
    if motion not in ("clean", "high"):
        raise ValueError(f"motion must be 'clean' or 'high', got {motion!r}")

    func_dir = Path(fmriprep_dir) / f"sub-{subject}" / f"ses-{session}" / "func"
    prefix = f"sub-{subject}_ses-{session}_task-{task}_run-{run}"

    if motion == "high":
        # ~30% of frames spike — well over the 0.2 proportion threshold, and
        # (for rest) enough to pull FD mean over 0.2. Scales with run length.
        n_spikes = max(1, round(0.30 * n_trs))
        fd_mean = 0.05
        fd_spikes = n_spikes
        dvars_spikes = n_spikes
    else:
        fd_mean = 0.05
        fd_spikes = 0
        dvars_spikes = 0

    written: Dict[str, Path] = {}
    written["confounds"] = write_confounds_tsv(
        func_dir,
        prefix=prefix,
        n_trs=n_trs,
        fd_mean=fd_mean,
        fd_spikes=fd_spikes,
        dvars_spikes=dvars_spikes,
        seed=seed,
    )
    written.update(
        write_fmriprep_bold(
            func_dir,
            prefix=prefix,
            space=space,
            n_trs=n_trs,
            n_voxels=n_voxels,
            seed=seed,
        )
    )
    return written
