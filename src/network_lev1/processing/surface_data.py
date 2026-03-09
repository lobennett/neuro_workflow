"""Surface data loading and processing utilities."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Use non-interactive backend for HPC environments without display
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import nibabel as nib
import numpy as np
import pandas as pd
from nilearn.glm.first_level import run_glm
from nilearn.glm.contrasts import compute_contrast

from network_lev1.task_config.loader import DUMMY_SCANS

logger = logging.getLogger(__name__)


def get_surface_scan_info(gii_file: Union[str, Path]) -> Tuple[int, int]:
    """Get scan count information from GIFTI file.

    Args:
        gii_file: Path to GIFTI functional file (.func.gii)

    Returns:
        Tuple of (total_scans, n_vertices)

    Examples:
        >>> total_scans, n_verts = get_surface_scan_info('hemi-L_bold.func.gii')
    """
    gii_img = nib.load(gii_file)
    total_scans = len(gii_img.darrays)
    n_vertices = gii_img.darrays[0].data.shape[0] if total_scans > 0 else 0
    return total_scans, n_vertices


def load_surface_data(
    gii_file: Union[str, Path], dummy_scans: int = DUMMY_SCANS
) -> np.ndarray:
    """Load surface BOLD data from GIFTI file as numpy array.

    Args:
        gii_file: Path to GIFTI functional file (.func.gii)
        dummy_scans: Number of dummy scans to remove from beginning

    Returns:
        2D numpy array of shape (n_timepoints, n_vertices)

    Examples:
        >>> data = load_surface_data('hemi-L_bold.func.gii', 7)
        >>> print(data.shape)  # (n_timepoints-7, n_vertices)
    """
    gii_img = nib.load(gii_file)

    # Extract data from darrays - each darray is one timepoint
    # Stack into (n_timepoints, n_vertices) array
    data_list = [darray.data for darray in gii_img.darrays]
    data = np.stack(data_list, axis=0)

    # Remove dummy scans
    if dummy_scans > 0:
        data = data[dummy_scans:, :]

    return data


def find_freesurfer_subjects_dir(fmriprep_dir: Path) -> Optional[Path]:
    """Find FreeSurfer SUBJECTS_DIR from fMRIPrep output.

    Args:
        fmriprep_dir: Path to fMRIPrep derivatives directory

    Returns:
        Path to SUBJECTS_DIR, or None if not found
    """
    fmriprep_dir = Path(fmriprep_dir)
    for candidate in [
        fmriprep_dir / 'sourcedata' / 'freesurfer',
        fmriprep_dir.parent / 'sourcedata' / 'freesurfer',
    ]:
        if candidate.exists():
            return candidate
    return None


def smooth_surface_gifti(
    input_file: Union[str, Path],
    output_file: Union[str, Path],
    subject_id: str,
    hemisphere: str,
    fwhm: float,
    subjects_dir: Union[str, Path],
) -> Path:
    """Smooth a surface GIFTI file using FreeSurfer mri_surf2surf.

    Requires FreeSurfer 8.1.0 (module load biology freesurfer/8.1.0).

    TODO: Consider removing this smoothing step in the future if
    downstream analyses do not require it.

    Args:
        input_file: Path to input GIFTI file
        output_file: Path to save smoothed GIFTI file
        subject_id: FreeSurfer subject ID (e.g., 'sub-s03')
        hemisphere: 'L' or 'R'
        fwhm: Smoothing FWHM in mm
        subjects_dir: Path to FreeSurfer SUBJECTS_DIR

    Returns:
        Path to smoothed output file

    Raises:
        FileNotFoundError: If mri_surf2surf is not available
        RuntimeError: If mri_surf2surf fails
    """
    import os
    import subprocess

    hemi = 'lh' if hemisphere == 'L' else 'rh'
    cmd = [
        'mri_surf2surf',
        '--s', subject_id,
        '--hemi', hemi,
        '--sval', str(input_file),
        '--tval', str(output_file),
        '--fwhm', str(fwhm),
    ]
    env = {**os.environ, 'SUBJECTS_DIR': str(subjects_dir)}

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    except FileNotFoundError:
        raise FileNotFoundError(
            'mri_surf2surf not found. Run: module load biology freesurfer/8.1.0'
        ) from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f'mri_surf2surf failed: {e.stderr}') from e

    logger.info('Surface smoothing (%.1fmm FWHM): %s', fwhm, output_file)
    return Path(output_file)


class SurfaceGLM:
    """GLM for surface data using nilearn's run_glm with AR(1) noise model.

    This ensures statistical consistency with the volumetric pipeline which
    uses FirstLevelModel with noise_model='ar1'. Both pipelines now properly
    account for temporal autocorrelation in fMRI data through pre-whitening.
    """

    def __init__(
        self,
        t_r: float,
        noise_model: str = 'ar1',
    ):
        """Initialize surface GLM.

        Args:
            t_r: Repetition time in seconds
            noise_model: Noise model ('ols' or 'ar1'). Default 'ar1' for
                consistency with volumetric pipeline.
        """
        self.t_r = t_r
        self.noise_model = noise_model
        self.labels_ = None
        self.results_ = None
        self.design_matrix_ = None

    def fit(
        self, surface_data: np.ndarray, design_matrix: pd.DataFrame
    ) -> 'SurfaceGLM':
        """Fit GLM to surface data using nilearn's run_glm.

        Uses AR(1) noise model by default to properly account for temporal
        autocorrelation, matching the volumetric pipeline's FirstLevelModel.

        Args:
            surface_data: 2D array of shape (n_timepoints, n_vertices)
            design_matrix: Design matrix with shape (n_timepoints, n_regressors)

        Returns:
            Self with fitted results
        """
        n_timepoints, n_vertices = surface_data.shape
        X = design_matrix.values

        if X.shape[0] != n_timepoints:
            raise ValueError(
                f'Design matrix rows ({X.shape[0]}) != data timepoints ({n_timepoints})'
            )

        self.design_matrix_ = design_matrix
        self.regressor_names_ = list(design_matrix.columns)
        self.surface_data_ = surface_data

        # Use nilearn's run_glm with specified noise model
        # AR(1) performs pre-whitening to correct for temporal autocorrelation
        self.labels_, self.results_ = run_glm(
            surface_data, X, noise_model=self.noise_model
        )

        return self

    def get_residuals(self) -> np.ndarray:
        """Compute residuals as Y - X * beta.

        Returns:
            2D array of shape (n_timepoints, n_vertices) containing residuals.
        """
        if self.results_ is None:
            raise ValueError('Model must be fit before computing residuals')

        X = self.design_matrix_.values
        Y = self.surface_data_
        n_timepoints, n_vertices = Y.shape

        # Reconstruct fitted values from per-label betas
        # theta shape: (n_regressors, n_verts_in_group) — each vertex has
        # its own beta estimates even when vertices share an AR(1) coefficient.
        Y_hat = np.zeros_like(Y)
        for label in np.unique(self.labels_):
            mask = self.labels_ == label
            Y_hat[:, mask] = X @ self.results_[label].theta

        return Y - Y_hat

    def compute_contrast(
        self, contrast_def: str, output_type: str = 'all'
    ) -> Dict[str, Any]:
        """Compute a contrast using nilearn's compute_contrast.

        Args:
            contrast_def: Contrast definition string (e.g., 'go - stop')
            output_type: Type of output ('z_score', 'effect_size', 'effect_variance', 'all')

        Returns:
            Dictionary with contrast results as SurfaceResult objects
        """
        # Parse contrast definition into contrast vector
        contrast_vector = self._parse_contrast(contrast_def)

        # Use nilearn's compute_contrast which properly handles AR(1) results
        contrast_result = compute_contrast(
            self.labels_,
            self.results_,
            contrast_vector,
            contrast_type='t',
        )

        # Extract results from nilearn's Contrast object
        effect_size = contrast_result.effect_size()
        effect_variance = contrast_result.effect_variance()
        z_score = contrast_result.z_score()

        # Keep NaN for invalid vertices; downstream code handles NaN properly
        n_invalid = np.sum(~np.isfinite(z_score))
        if n_invalid > 0:
            logger.warning('%d vertices have non-finite z-scores', n_invalid)
        z_score = np.where(np.isfinite(z_score), z_score, np.nan)

        results = {
            'effect_size': SurfaceResult(effect_size),
            'effect_variance': SurfaceResult(effect_variance),
            'z_score': SurfaceResult(z_score),
        }

        if output_type == 'all':
            return results
        else:
            return results.get(output_type)

    def _parse_contrast(self, contrast_def: str) -> np.ndarray:
        """Parse contrast definition string into contrast vector.

        Args:
            contrast_def: String like 'go-stop', 'go - stop', or 'go + stop - 2*baseline'

        Returns:
            Contrast vector of shape (n_regressors,)
        """
        import re

        contrast_vector = np.zeros(len(self.regressor_names_))

        # Normalize: ensure spaces around + and - for consistent parsing
        # First, add spaces around operators (handles both 'a-b' and 'a - b')
        normalized = re.sub(r'(?<=[a-zA-Z0-9_])\s*-\s*(?=[a-zA-Z0-9_])', ' - ', contrast_def)
        normalized = re.sub(r'(?<=[a-zA-Z0-9_])\s*\+\s*(?=[a-zA-Z0-9_])', ' + ', normalized)

        # Now replace ' - ' with ' + -' for easier splitting
        normalized = normalized.replace(' - ', ' + -')
        terms = [t.strip() for t in normalized.split('+')]

        for term in terms:
            if not term:
                continue

            # Parse coefficient and regressor name
            # Match optional coefficient (including negative), optional *, then regressor name
            match = re.match(r'^(-?\d*\.?\d*)\s*\*?\s*(.+)$', term.strip())
            if match:
                coef_str, regressor = match.groups()
                coef = float(coef_str) if coef_str and coef_str != '-' else (
                    -1.0 if coef_str == '-' else 1.0
                )
            else:
                coef = 1.0
                regressor = term.strip()

            # Find regressor in labels
            regressor = regressor.strip()
            if regressor in self.regressor_names_:
                idx = self.regressor_names_.index(regressor)
                contrast_vector[idx] = coef

        return contrast_vector


class SurfaceResult:
    """Container for surface GLM results that mimics nilearn's interface."""

    def __init__(self, data: np.ndarray):
        """Initialize with 1D array of vertex values."""
        self.data = data

    def to_filename(self, filename: Union[str, Path]) -> None:
        """Save result to GIFTI file."""
        filename = str(filename)

        # Create GIFTI image with single darray
        darray = nib.gifti.GiftiDataArray(
            data=self.data.astype(np.float32),
            intent='NIFTI_INTENT_NONE',
            datatype='NIFTI_TYPE_FLOAT32',
        )
        gii_img = nib.GiftiImage(darrays=[darray])
        nib.save(gii_img, filename)


def load_surface_stat_map(gii_file: Union[str, Path]) -> np.ndarray:
    """Load a surface statistic map from GIFTI file.

    Args:
        gii_file: Path to GIFTI file with single stat map

    Returns:
        1D numpy array of vertex values
    """
    gii_img = nib.load(gii_file)
    if len(gii_img.darrays) != 1:
        raise ValueError(f'Expected 1 darray in stat map, got {len(gii_img.darrays)}')
    return gii_img.darrays[0].data


def compute_surface_fixed_effects(
    effect_files: list,
    variance_files: list,
    precision_weighted: bool = False,
) -> Tuple[SurfaceResult, SurfaceResult, SurfaceResult]:
    """Compute fixed effects for surface data.

    Args:
        effect_files: List of paths to effect size GIFTI files
        variance_files: List of paths to variance GIFTI files
        precision_weighted: Whether to use precision weighting

    Returns:
        Tuple of (fixed_effect, fixed_variance, fixed_stat) as SurfaceResult objects
    """
    if len(effect_files) != len(variance_files):
        raise ValueError('Number of effect and variance files must match')

    # Load all effect and variance maps
    effects = [load_surface_stat_map(f) for f in effect_files]
    variances = [load_surface_stat_map(f) for f in variance_files]

    # Stack into arrays
    effects = np.stack(effects, axis=0)  # (n_runs, n_vertices)
    variances = np.stack(variances, axis=0)  # (n_runs, n_vertices)

    n_runs = len(effect_files)

    # Log NaN vertex counts per run and across runs
    nan_per_run = np.sum(~np.isfinite(effects), axis=1)
    for i, count in enumerate(nan_per_run):
        if count > 0:
            logger.debug('Run %d: %d NaN vertices in effect map', i + 1, count)

    # Vertices where some (but not all) runs have NaN — data would be lost
    # without NaN-safe aggregation
    any_nan = np.any(~np.isfinite(effects), axis=0)
    all_nan = np.all(~np.isfinite(effects), axis=0)
    partial_nan = np.sum(any_nan & ~all_nan)
    if partial_nan > 0:
        logger.warning(
            '%d vertices have NaN in some runs but valid data in others; '
            'using NaN-safe aggregation to preserve valid runs',
            partial_nan,
        )

    if precision_weighted:
        # Precision-weighted fixed effects
        # weight = 1/variance; NaN variance → weight=0 (run excluded)
        with np.errstate(divide='ignore', invalid='ignore'):
            weights = 1.0 / variances
            weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)

        # NaN effects must not contribute: zero their weights too
        weights = np.where(np.isfinite(effects), weights, 0.0)

        # Weighted mean: sum(w * effect) / sum(w)
        sum_weights = np.sum(weights, axis=0)
        with np.errstate(divide='ignore', invalid='ignore'):
            safe_effects = np.nan_to_num(effects, nan=0.0)
            fixed_effect = np.sum(weights * safe_effects, axis=0) / sum_weights
            fixed_effect = np.nan_to_num(fixed_effect, nan=0.0)
            fixed_variance = 1.0 / sum_weights
            fixed_variance = np.nan_to_num(fixed_variance, nan=0.0, posinf=0.0)
    else:
        # NaN-safe unweighted averaging: use only valid runs per vertex
        import warnings

        with np.errstate(invalid='ignore', divide='ignore'), warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            n_valid = np.sum(np.isfinite(effects), axis=0)
            fixed_effect = np.nanmean(effects, axis=0)
            # Variance of mean = sum(var) / n_valid^2
            fixed_variance = np.nansum(variances, axis=0) / (n_valid ** 2)
            # Where no valid runs exist, set to 0
            fixed_effect = np.nan_to_num(fixed_effect, nan=0.0)
            fixed_variance = np.nan_to_num(fixed_variance, nan=0.0)

    # Compute z-score
    with np.errstate(divide='ignore', invalid='ignore'):
        fixed_stat = fixed_effect / np.sqrt(fixed_variance)
        fixed_stat = np.nan_to_num(fixed_stat, nan=0.0, posinf=0.0, neginf=0.0)

    return (
        SurfaceResult(fixed_effect),
        SurfaceResult(fixed_variance),
        SurfaceResult(fixed_stat),
    )


def plot_surface_stat_map(
    stat_file: Union[str, Path],
    output_path: Union[str, Path],
    hemisphere: str,
    title: Optional[str] = None,
    threshold: Optional[float] = None,
    vmax: Optional[float] = None,
    cmap: str = 'cold_hot',
    fmriprep_dir: Optional[Union[str, Path]] = None,
    subject_id: Optional[str] = None,
) -> Path:
    """Plot surface stat map and save as PNG.

    Args:
        stat_file: Path to GIFTI stat map file
        output_path: Path to save PNG file
        hemisphere: Hemisphere ('L' or 'R')
        title: Optional title for the plot
        threshold: Optional threshold for displaying stats
        vmax: Optional max value for colormap
        cmap: Colormap name (default 'cold_hot')
        fmriprep_dir: Optional path to fMRIPrep dir for fsnative surfaces
        subject_id: Optional subject ID for fsnative surfaces

    Returns:
        Path to saved PNG file
    """
    from nilearn import datasets, plotting, surface

    stat_file = Path(stat_file)
    output_path = Path(output_path)

    # Load the stat map data
    stat_data = load_surface_stat_map(stat_file)

    # Map hemisphere to nilearn naming
    hemi_map = {'L': 'left', 'R': 'right'}
    hemi_name = hemi_map.get(hemisphere, 'left')

    # Try to use fsnative surfaces if available, otherwise fall back to fsaverage
    surf_mesh = None
    sulc_map = None
    space_used = 'fsaverage'

    if fmriprep_dir is not None and subject_id is not None:
        # Try to find fsnative surfaces in fMRIPrep output
        fmriprep_dir = Path(fmriprep_dir)
        # fMRIPrep stores surfaces in sourcedata/freesurfer or in the anat folder
        possible_surf_dirs = [
            fmriprep_dir / 'sourcedata' / 'freesurfer' / subject_id / 'surf',
            fmriprep_dir.parent / 'sourcedata' / 'freesurfer' / subject_id / 'surf',
            fmriprep_dir / subject_id / 'anat',
        ]

        hemi_prefix = 'lh' if hemisphere == 'L' else 'rh'

        for surf_dir in possible_surf_dirs:
            if surf_dir.exists():
                # Look for inflated surface
                inflated_file = surf_dir / f'{hemi_prefix}.inflated'
                if inflated_file.exists():
                    surf_mesh = str(inflated_file)
                    # Also try to get sulcal depth for shading
                    sulc_file = surf_dir / f'{hemi_prefix}.sulc'
                    if sulc_file.exists():
                        sulc_map = str(sulc_file)
                    space_used = 'fsnative'
                    break

    # Fall back to fsaverage if fsnative not available
    if surf_mesh is None:
        fsaverage = datasets.fetch_surf_fsaverage('fsaverage')
        surf_mesh = fsaverage[f'infl_{hemi_name}']
        sulc_map = fsaverage[f'sulc_{hemi_name}']

    # Create figure with multiple views
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), subplot_kw={'projection': '3d'})

    # Determine views based on hemisphere
    if hemisphere == 'L':
        views = ['lateral', 'medial']
    else:
        views = ['lateral', 'medial']

    # Auto-determine vmax if not provided
    if vmax is None:
        abs_max = np.nanpercentile(np.abs(stat_data), 99)
        vmax = abs_max if abs_max > 0 else 1.0

    # Plot each view
    for ax, view in zip(axes, views):
        plotting.plot_surf_stat_map(
            surf_mesh,
            stat_data,
            hemi=hemi_name,
            view=view,
            threshold=threshold,
            vmax=vmax,
            cmap=cmap,
            bg_map=sulc_map,
            axes=ax,
            colorbar=False,
        )

    # Add colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=-vmax, vmax=vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation='horizontal', fraction=0.05, pad=0.1)
    cbar.set_label('Effect Size')

    # Add title
    if title is None:
        title = f'{stat_file.stem} ({space_used})'
    fig.suptitle(title, fontsize=12)

    # Save figure
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    return output_path


def plot_surface_contrast_qc(
    contrast_files: Dict[str, Path],
    output_dir: Path,
    hemisphere: str,
    subject_id: str,
    session: str,
    run: str,
    task_name: str,
    fmriprep_dir: Optional[Path] = None,
) -> List[Path]:
    """Generate QC plots for all contrasts from a run.

    Args:
        contrast_files: Dict mapping contrast names to file paths
        output_dir: Directory to save QC plots
        hemisphere: Hemisphere ('L' or 'R')
        subject_id: Subject ID
        session: Session ID
        run: Run ID
        task_name: Task name
        fmriprep_dir: Optional path to fMRIPrep dir for fsnative surfaces

    Returns:
        List of paths to saved PNG files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_plots = []

    for contrast_name, file_path in contrast_files.items():
        # Only plot effect size maps
        if 'effect-size' not in str(file_path):
            continue

        # Generate output filename
        output_filename = f'{subject_id}_{session}_task-{task_name}_{run}_hemi-{hemisphere}_contrast-{contrast_name}_qc.png'
        output_path = output_dir / output_filename

        try:
            title = f'{subject_id} {session} {run} - {contrast_name} (hemi-{hemisphere})'
            plot_surface_stat_map(
                file_path,
                output_path,
                hemisphere,
                title=title,
                fmriprep_dir=fmriprep_dir,
                subject_id=subject_id,
            )
            saved_plots.append(output_path)
        except Exception as e:
            logger.warning('Failed to plot %s: %s', contrast_name, e)

    return saved_plots
