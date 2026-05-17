#!/usr/bin/env python3
"""Level 1 GLM Analysis script using modular analysis package."""

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd

from neuro_workflow.analysis.config import Config
from neuro_workflow.analysis.core.task_utils import detect_sample_type, get_expected_sessions
from neuro_workflow.analysis.core.utils import (
    check_behavioral_trim_threshold,
    load_exclusions,
    load_exclusions_by_type,
    normalize_subject_id,
)
from neuro_workflow.analysis.io.file_discovery import FileFinder
from neuro_workflow.analysis.lev1.processing.confounds import get_fc_confounds, load_and_process_confounds
from neuro_workflow.analysis.lev1.processing.contrasts import (
    compute_run_contrasts,
    filter_contrasts_for_dropped_columns,
)
from neuro_workflow.analysis.lev1.processing.design import create_design_matrix
from neuro_workflow.analysis.lev1.processing.events import (
    add_junk_trials,
    load_bold_data_with_dummy_removal,
    preprocess_events,
    save_simplified_events,
)
from neuro_workflow.analysis.lev1.processing.fixed_effects import compute_subject_fixed_effects
from neuro_workflow.analysis.lev1.processing.glm import (
    fit_run_glm,
    handle_zero_variance_columns,
    validate_design_matrix,
    validate_glm_inputs,
)
from neuro_workflow.analysis.lev1.processing.masks import MaskProcessor
from neuro_workflow.analysis.lev1.processing.quality_control import run_quality_control
from neuro_workflow.analysis.lev1.processing.residuals import process_run_residuals, process_surface_residuals
from neuro_workflow.analysis.lev1.processing.surface_data import (
    SurfaceGLM,
    find_freesurfer_subjects_dir,
    get_surface_scan_info,
    load_surface_data,
    plot_surface_stat_map,
    resolve_freesurfer_subject,
    smooth_surface_gifti,
)
from neuro_workflow.analysis.task_config.loader import get_task_contrasts, get_task_parameters

logger = logging.getLogger(__name__)


def _positive_int(value: str) -> int:
    """Argparse type that accepts only integers >= 1."""
    iv = int(value)
    if iv < 1:
        raise argparse.ArgumentTypeError('--min-runs must be >= 1')
    return iv


def setup_logging(verbose: bool = False) -> None:
    """Configure root logger for the analysis pipeline.

    Args:
        verbose: If True, set level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout,
    )


def is_surface_space(space: str) -> bool:
    """Check if the analysis space is a surface space."""
    return space in ('surface', 'fsaverage6', 'fsLR')


def resolve_surface_space(space: str) -> str | None:
    """Return the surface template name, or None for volumetric."""
    mapping = {
        'surface': 'fsnative',
        'fsaverage6': 'fsaverage6',
        'fsLR': 'fsLR',
    }
    return mapping.get(space)


def get_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Level 1 GLM Analysis for Network R01 dataset'
    )
    parser.add_argument('--subj-id', type=str, required=True, help='Subject ID')
    parser.add_argument('--task-name', type=str, required=True, help='Task name')
    parser.add_argument(
        '--bids-dir', type=str, required=True, help='BIDS directory path'
    )
    parser.add_argument(
        '--fmriprep-dir', type=str, required=True, help='fMRIPrep directory path'
    )
    parser.add_argument(
        '--results-dir',
        type=str,
        required=False,
        default='./results/',
        help='GLM results directory',
    )
    parser.add_argument(
        '--space',
        choices=['T1w', 'MNI', 'surface', 'fsaverage6', 'fsLR'],
        default='MNI',
        help='Analysis space. T1w/MNI for volumetric; surface for fsnative; '
        'fsaverage6 for fsaverage6 GIFTI; fsLR for fsLR den-91k CIFTI',
    )
    parser.add_argument(
        '--within-subject-threshold',
        type=float,
        default=1.0,
        help='Threshold for mask intersection (0.0-1.0)',
    )
    parser.add_argument(
        '--exclusions-file',
        type=str,
        required=True,
        help='Path to exclusions JSON file',
    )
    parser.add_argument(
        '--residuals',
        action='store_true',
        default=False,
        help='Compute residuals (default: false)',
    )
    # TODO: Consider removing smoothing if downstream analyses do not
    # require it (added per Du et al. 2025, Neuron).  For surface space
    # this calls FreeSurfer mri_surf2surf (module load biology
    # freesurfer/8.1.0).
    parser.add_argument(
        '--smoothing-fwhm',
        type=float,
        default=None,
        help='Spatial smoothing FWHM in mm applied to BOLD before GLM '
        '(affects all outputs). None means no smoothing.',
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        default=False,
        help='Skip runs where residual files already exist (useful for resuming)',
    )
    parser.add_argument(
        '--fc-confounds',
        action='store_true',
        default=False,
        help='Regress tissue confounds (global signal, WM, CSF) from residuals '
        'for FC analysis. Requires --residuals. Follows Du et al. 2025.',
    )
    parser.add_argument(
        '--mni-template',
        default='MNI152NLin6Asym',
        help='fMRIPrep MNI template name for --space MNI '
        '(default: MNI152NLin6Asym)',
    )
    parser.add_argument(
        '--mni-res',
        default='2',
        help='Resolution suffix for --space MNI (default: 2)',
    )
    parser.add_argument(
        '--min-runs',
        type=_positive_int,
        default=2,
        help='Minimum runs required to compute a non-tagged fixed-effects map. '
             'Below this threshold, the saved map is tagged _desc-belowMinRuns '
             'and lev2 will filter it out (default: 2).',
    )
    parser.add_argument(
        '--skip-qc-plots',
        action='store_true',
        default=False,
        help='Skip per-contrast surface QC plots (matplotlib renders ~10 plots '
        'per hemisphere per run; for a 46-subject cohort this adds many hours '
        'of wall time with no impact on the science). The contrast .func.gii '
        'files are still saved and can be re-plotted offline.',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=False,
        help='Enable debug logging',
    )
    return parser


def setup_analysis(args):
    """Set up configuration, exclusions, and output directories.

    Returns:
        Tuple of (config, sample_type, expected_sessions, exclusions,
                  exclusions_by_type, dirs).
    """
    args.subj_id = normalize_subject_id(args.subj_id)

    config = Config(
        bids_dir=Path(args.bids_dir),
        fmriprep_dir=Path(args.fmriprep_dir),
        output_dir=Path(args.results_dir),
        subject_id=args.subj_id,
        task_name=args.task_name,
    )

    sample_type = detect_sample_type(config.bids_dir)
    expected_sessions = get_expected_sessions(args.task_name)

    logger.info('Level 1 GLM: %s / %s / %s / %s', args.subj_id, args.task_name, args.space, sample_type)

    # Load exclusions
    trim_exclusions = check_behavioral_trim_threshold(
        args.exclusions_file, threshold=0.5
    )
    exclusions_by_type = load_exclusions_by_type(args.exclusions_file)
    if 'behavioral_exclusions' not in exclusions_by_type:
        exclusions_by_type['behavioral_exclusions'] = set()
    exclusions_by_type['behavioral_exclusions'].update(trim_exclusions)

    exclusions = load_exclusions(args.exclusions_file)
    exclusions.update(trim_exclusions)
    logger.info('Loaded %d exclusions (%d trim-based)', len(exclusions), len(trim_exclusions))

    # Create subject-specific directories
    dirs = config.create_subject_dirs(clean_existing=True)

    return config, sample_type, expected_sessions, exclusions, exclusions_by_type, dirs


def discover_and_validate_files(config, args):
    """Discover BIDS and fMRIPrep files and validate completeness.

    Returns:
        files dict from FileFinder.
    """
    finder = FileFinder(
        config.bids_dir,
        config.fmriprep_dir,
        mni_template=getattr(args, 'mni_template', 'MNI152NLin6Asym'),
        mni_res=getattr(args, 'mni_res', '2'),
    )
    required_files = FileFinder.get_required_files_for_space(args.space)
    surface_space = resolve_surface_space(args.space)
    files = finder.get_files(
        args.subj_id, args.task_name,
        required_files=required_files,
        surface_space=surface_space,
    )

    if not files:
        raise ValueError(
            'No complete runs found! Check that all required files are present.'
        )

    validation = finder.validate_file_completeness(files, args.task_name)
    logger.info(
        'Found %d complete runs across %d sessions',
        validation['complete_runs'],
        validation['total_sessions'],
    )

    return files


def setup_masks(files, args, dirs):
    """Process brain masks for volumetric analysis.

    Returns:
        Path to combined mask or None for surface space.
    """
    if is_surface_space(args.space):
        logger.info('Skipping mask processing for surface space')
        return None

    mask_info = MaskProcessor.get_mask_info(files, args.space)
    logger.info('Found %d %s brain masks', mask_info['total_masks'], args.space)

    if not mask_info['all_valid']:
        raise ValueError('Some masks are invalid - cannot proceed')

    mask_filename = f'{args.subj_id}_space-{args.space}_desc-combinedMask.nii.gz'
    combined_mask_path = dirs['masks'] / mask_filename
    MaskProcessor.create_combined_mask(
        files, args.space, args.within_subject_threshold, combined_mask_path
    )
    logger.info('Combined mask saved: %s', combined_mask_path)
    return combined_mask_path


def process_volumetric_run(
    bold_data, design_matrix, contrasts, run_files, args, dirs, base_filename, tr, mask_key, compute_residuals,
    fc_confounds=None,
):
    """Fit volumetric GLM and compute contrasts (and optional residuals).

    ``fc_confounds``, when provided, is regressed from the post-GLM residuals
    via nilearn.signal.clean — matching the surface path so that
    ``--fc-confounds`` produces FC-quality residuals in either space.

    Returns:
        Dict of contrast results.
    """
    validation = validate_glm_inputs(bold_data, design_matrix, run_files[mask_key])
    if not validation['is_valid']:
        raise ValueError(f'GLM validation failed: {validation["errors"]}')

    run_mask = run_files[mask_key]

    # When residuals are requested, fit once with minimize_memory=False
    # so the same model can be used for both contrasts and residuals.
    analysis_type = 'residual' if compute_residuals else 'task'
    fitted_glm = fit_run_glm(
        bold_data, design_matrix, analysis_type, args.subj_id, tr,
        smoothing_fwhm=args.smoothing_fwhm, mask_img=run_mask,
    )

    contrast_results = compute_run_contrasts(
        fitted_glm, args.task_name, dirs['indiv_contrasts'],
        base_filename, contrasts=contrasts,
    )
    logger.info('Saved %d contrasts', len(contrast_results))

    # Process residuals if requested
    if compute_residuals:
        residuals_result = process_run_residuals(
            fitted_glm, dirs['task_residuals'], base_filename, tr,
            mask_img=run_mask, fc_confounds=fc_confounds,
        )
        if not residuals_result['success']:
            logger.warning('Residuals processing had issues: %s', residuals_result['errors'])

    return contrast_results


def process_surface_run(
    run_files, design_matrix, contrasts, args, dirs, base_filename, tr, dummy_scans,
    compute_residuals=False, surface_space='fsnative', fc_confounds=None,
):
    """Fit surface GLM per hemisphere and compute contrasts (and optional residuals).

    Returns:
        Dict mapping hemispheres to contrast results.
    """
    all_hemisphere_results = {}

    # Find FreeSurfer subjects dir + resolve the FS-subject name used by
    # mri_surf2surf. The choice depends on the BOLD's surface space:
    #
    #   fsaverage / fsaverage6  -> use 'fsaverage6' (40962 v/hemi). The BOLD
    #                              has been resampled to the group template;
    #                              smoothing must operate on that mesh.
    #   fsnative                -> use the per-subject FS recon (resolved via
    #                              `resolve_freesurfer_subject` because
    #                              fmriprep's longitudinal anat workflow
    #                              names recons `sub-X_ses-Y`).
    #
    # Passing the per-subject recon while smoothing fsaverage6 BOLD produces
    # the dimension-mismatch error (e.g. 131403 vs 40962 vertices).
    subjects_dir = None
    fs_subject = args.subj_id
    if args.smoothing_fwhm is not None:
        subjects_dir = find_freesurfer_subjects_dir(Path(args.fmriprep_dir))
        if subjects_dir is None:
            raise FileNotFoundError(
                'Cannot find FreeSurfer subjects dir for surface smoothing'
            )
        if surface_space in ('fsaverage', 'fsaverage6'):
            fs_subject = 'fsaverage6'
        else:
            fs_subject = resolve_freesurfer_subject(args.subj_id, subjects_dir)

    for hemisphere, bold_key in [('L', 'left_surface'), ('R', 'right_surface')]:
        bold_path = run_files[bold_key]
        logger.info('Processing hemisphere %s...', hemisphere)

        # Apply spatial smoothing to BOLD if requested
        if args.smoothing_fwhm is not None:
            with tempfile.TemporaryDirectory() as tmp_dir:
                smoothed_path = Path(tmp_dir) / f'smoothed_hemi-{hemisphere}.func.gii'
                smooth_surface_gifti(
                    bold_path, smoothed_path, fs_subject,
                    hemisphere, args.smoothing_fwhm, subjects_dir,
                )
                surface_data = load_surface_data(smoothed_path, dummy_scans=dummy_scans)
        else:
            surface_data = load_surface_data(bold_path, dummy_scans=dummy_scans)
        logger.debug('Surface data shape: %s', surface_data.shape)

        # Validate inputs before fitting. The volumetric branch (process_volumetric_run)
        # has called validate_glm_inputs for a long time; the surface branch
        # historically had no equivalent and would have silently propagated NaN /
        # mis-shaped designs through nilearn run_glm into garbage contrast maps.
        # We validate once per hemisphere because each hemisphere produces its own
        # surface_data and the row-count check needs that array's first dim.
        validation = validate_design_matrix(design_matrix, n_scans=surface_data.shape[0])
        if not validation['is_valid']:
            raise ValueError(
                f'Surface GLM validation failed (hemi-{hemisphere}): '
                f'{validation["errors"]}'
            )

        surface_glm = SurfaceGLM(t_r=tr)
        surface_glm.fit(surface_data, design_matrix)

        contrast_results = {}
        for contrast_name, contrast_formula in contrasts.items():
            try:
                result = surface_glm.compute_contrast(contrast_formula, output_type='all')
                contrast_base = (
                    f'{base_filename}_hemi-{hemisphere}'
                    f'_contrast-{contrast_name}_rtmodel-RTDur'
                )
                effect_path = dirs['indiv_contrasts'] / f'{contrast_base}_stat-effect-size.func.gii'
                result['effect_size'].to_filename(effect_path)

                var_path = dirs['indiv_contrasts'] / f'{contrast_base}_stat-variance.func.gii'
                result['effect_variance'].to_filename(var_path)

                z_path = dirs['indiv_contrasts'] / f'{contrast_base}_stat-z_score.func.gii'
                result['z_score'].to_filename(z_path)

                contrast_results[contrast_name] = {
                    'effect_size': effect_path,
                    'effect_variance': var_path,
                    'z_score': z_path,
                }
            except Exception as e:
                logger.error('Failed to compute contrast %s (hemi-%s): %s', contrast_name, hemisphere, e)

        logger.info('Saved %d contrasts for hemisphere %s', len(contrast_results), hemisphere)

        # Generate QC plots (skipped under --skip-qc-plots; matplotlib renders
        # are slow at cohort scale — ~10 plots × 2 hemis × N runs adds many
        # hours of wall time per subject. The .func.gii files are persisted
        # above and can be re-plotted offline if review is needed.)
        if getattr(args, 'skip_qc_plots', False):
            logger.debug('Skipping QC plots for hemisphere %s (--skip-qc-plots)', hemisphere)
            continue
        qc_count = 0
        for contrast_name, paths in contrast_results.items():
            try:
                qc_filename = (
                    f'{base_filename}_hemi-{hemisphere}'
                    f'_contrast-{contrast_name}_qc.png'
                )
                qc_path = dirs['quality_control'] / qc_filename
                title = f'{args.subj_id} - {contrast_name} (hemi-{hemisphere})'
                plot_surface_stat_map(
                    paths['effect_size'], qc_path, hemisphere,
                    title=title, fmriprep_dir=Path(args.fmriprep_dir),
                    subject_id=args.subj_id,
                )
                qc_count += 1
            except Exception as e:
                logger.debug('Failed to plot %s: %s', contrast_name, e)
        logger.debug('Saved %d QC plots for hemisphere %s', qc_count, hemisphere)

        # Process surface residuals if requested
        if compute_residuals:
            process_surface_residuals(
                surface_glm, dirs['task_residuals'], base_filename,
                hemisphere, tr, fc_confounds=fc_confounds,
                surface_space=surface_space,
            )

        all_hemisphere_results[hemisphere] = contrast_results

    return all_hemisphere_results


def process_single_run(session, run, run_files, args, config, sample_type, dirs, task_params, exclusions, combined_mask_path):
    """Process a single run (volumetric or surface).

    Returns:
        True if successful, False if failed.
    """
    tr = task_params['tr']
    run_key = f'{args.subj_id}_{session}_task-{args.task_name}_{run}'

    if run_key in exclusions:
        logger.info('Skipping excluded run: %s/%s', session, run)
        return True  # Not a failure, just skipped

    # Skip if all output files already exist
    if args.skip_existing:
        base_filename = f'{args.subj_id}_{session}_task-{args.task_name}_{run}'
        if is_surface_space(args.space) and args.residuals:
            lh_res = dirs['task_residuals'] / f'{base_filename}_hemi-L_task-regressed-residuals.func.gii'
            rh_res = dirs['task_residuals'] / f'{base_filename}_hemi-R_task-regressed-residuals.func.gii'
            if lh_res.exists() and rh_res.exists():
                logger.info('Skipping %s (outputs already exist)', run_key)
                return True
        elif not is_surface_space(args.space) and args.residuals:
            vol_res = dirs['task_residuals'] / f'{base_filename}_task-regressed-residuals.nii.gz'
            if vol_res.exists():
                logger.info('Skipping %s (outputs already exist)', run_key)
                return True

    logger.info('Processing %s/%s...', session, run)

    # Load BOLD data or get scan count
    if is_surface_space(args.space):
        if 'left_surface' not in run_files or 'right_surface' not in run_files:
            raise ValueError(f'Missing surface files for {session}/{run}')
        n_scans_total, _ = get_surface_scan_info(run_files['left_surface'])
        # BOLD is already trimmed by trim_bold.py; do not remove dummy scans again
        dummy_scans = 0
        n_scans = n_scans_total
    else:
        mask_key = f'{args.space.lower()}_brain_mask'
        data_key = f'{args.space.lower()}_data'
        if mask_key not in run_files or data_key not in run_files:
            raise ValueError(f'Missing required files for {session}/{run}')
        # BOLD is already trimmed by trim_bold.py; load without further removal
        bold_data = load_bold_data_with_dummy_removal(run_files[data_key], dummy_scans=0)
        n_scans = bold_data.shape[3]

    # Load and preprocess events
    # Onsets are already adjusted for dummy scans during event file creation
    # (shifted by -7*1.49s = -10.43s); do not adjust again
    events_df = pd.read_csv(run_files['events'], sep='\t')
    processed_events = preprocess_events(
        events_df, args.task_name, n_scans=n_scans, tr=tr
    )
    processed_events_with_junk, percent_junk = add_junk_trials(
        processed_events, args.task_name
    )

    # Load confounds. BOLD is pre-trimmed by scripts/trim_bold.py and fMRIPrep
    # is run with --dummy-scans 0, so the confounds TSV already matches the
    # trimmed BOLD length. Do not trim confounds further.
    selected_confounds = load_and_process_confounds(
        run_files['confounds'], args.task_name, sample_type, dummy_scans=0
    )
    if len(selected_confounds) != n_scans:
        raise ValueError(
            f'Confounds length mismatch: {len(selected_confounds)} != {n_scans}'
        )

    # Create design matrix
    design_matrix, regressor_3cols = create_design_matrix(
        processed_events_with_junk, selected_confounds, args.task_name, n_scans, tr,
    )
    logger.debug('Design matrix shape: %s', design_matrix.shape)

    # Handle zero-variance columns
    design_matrix, dropped_columns = handle_zero_variance_columns(design_matrix)

    # Get and filter contrasts
    all_contrasts = get_task_contrasts(args.task_name)
    contrasts, skipped_contrasts = filter_contrasts_for_dropped_columns(
        all_contrasts, dropped_columns
    )

    # Quality control
    vifs, qa_failed = run_quality_control(
        design_matrix, contrasts, percent_junk, dirs['quality_control'],
        subject_id=args.subj_id, session=session, run=run, task_name=args.task_name,
    )

    # Save simplified events
    if regressor_3cols:
        simplified_events_file = (
            dirs['simplified_events']
            / f'{args.subj_id}_{session}_task-{args.task_name}_{run}_desc-simplifiedEvents.csv'
        )
        save_simplified_events(regressor_3cols, simplified_events_file)

    if qa_failed:
        logger.error('Skipping GLM fitting due to QA failure')
        return False

    base_filename = f'{args.subj_id}_{session}_task-{args.task_name}_{run}'

    # Load FC confounds once if requested — used by both surface and
    # volumetric residual paths so `--fc-confounds` has identical semantics
    # in either space (previously volumetric silently ignored the flag).
    fc_confounds = None
    if args.residuals and args.fc_confounds:
        confounds_df = pd.read_csv(run_files['confounds'], sep='\t', na_values=['n/a']).fillna(0)
        fc_confounds_df = get_fc_confounds(confounds_df)
        if not fc_confounds_df.empty:
            # BOLD is pre-trimmed and fMRIPrep runs with --dummy-scans 0,
            # so confounds TSV already matches trimmed BOLD length.
            fc_confounds = fc_confounds_df.values
            logger.info('FC confounds: %d columns', fc_confounds.shape[1])

    if is_surface_space(args.space):
        surface_space = resolve_surface_space(args.space)

        process_surface_run(
            run_files, design_matrix, contrasts, args, dirs,
            base_filename, tr, 0,  # BOLD already trimmed
            compute_residuals=args.residuals,
            surface_space=surface_space,
            fc_confounds=fc_confounds,
        )
    else:
        compute_residuals = args.residuals
        process_volumetric_run(
            bold_data, design_matrix, contrasts, run_files, args, dirs,
            base_filename, tr, mask_key, compute_residuals,
            fc_confounds=fc_confounds,
        )

    return True


def compute_fixed_effects_all(
    args, files, dirs, exclusions, exclusions_by_type, expected_sessions,
    combined_mask_path, failed_runs, run_count,
):
    """Compute fixed effects across runs, supporting partial-run analysis.

    Tags output with desc-partialRuns if any runs failed.
    """
    # Compute fixed effects on available successful runs (partial run support)
    successful_runs = run_count - len(failed_runs)
    if successful_runs == 0:
        logger.error('No successful runs - skipping fixed effects')
        return

    if failed_runs:
        logger.warning(
            'Computing fixed effects on %d/%d successful runs (partial)',
            successful_runs, run_count,
        )

    logger.info('Computing fixed effects...')
    try:
        if is_surface_space(args.space):
            surface_space = resolve_surface_space(args.space)
            for hemisphere in ['L', 'R']:
                logger.info('Fixed effects for hemisphere %s...', hemisphere)
                results = compute_subject_fixed_effects(
                    args.subj_id, args.task_name, dirs['indiv_contrasts'],
                    dirs['fixed_effects'], mask_img=None, exclusions=exclusions,
                    min_runs=args.min_runs,
                    hemisphere=hemisphere,
                    surface_space=surface_space,
                )
                logger.info('Fixed effects: %d contrasts (hemi-%s)', len(results), hemisphere)
        else:
            results = compute_subject_fixed_effects(
                args.subj_id, args.task_name, dirs['indiv_contrasts'],
                dirs['fixed_effects'], combined_mask_path, exclusions,
                min_runs=args.min_runs,
            )
            logger.info('Fixed effects: %d contrasts', len(results))
    except Exception as e:
        logger.error('Fixed effects computation failed: %s', e)


def main():
    """Run level 1 analysis with command line arguments."""
    parser = get_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    # Setup
    config, sample_type, expected_sessions, exclusions, exclusions_by_type, dirs = (
        setup_analysis(args)
    )

    # File discovery
    files = discover_and_validate_files(config, args)

    # Masks
    combined_mask_path = setup_masks(files, args, dirs)

    # Get task parameters
    task_params = get_task_parameters(args.task_name)

    # Process each run
    run_count = 0
    failed_runs = []

    for session in sorted(files.keys()):
        for run in sorted(files[session].keys()):
            run_count += 1
            try:
                success = process_single_run(
                    session, run, files[session][run], args, config,
                    sample_type, dirs, task_params, exclusions, combined_mask_path,
                )
                if not success:
                    failed_runs.append(f'{session}/{run}')
            except Exception as e:
                logger.error('Failed to process %s/%s: %s', session, run, e)
                failed_runs.append(f'{session}/{run}')

    # Fixed effects (compute even with partial failures)
    compute_fixed_effects_all(
        args, files, dirs, exclusions, exclusions_by_type, expected_sessions,
        combined_mask_path, failed_runs, run_count,
    )

    # Summary
    successful_runs = run_count - len(failed_runs)
    logger.info(
        'Analysis complete: %d/%d runs successful', successful_runs, run_count
    )
    if failed_runs:
        logger.warning('Failed runs: %s', ', '.join(failed_runs))

    return 1 if len(failed_runs) > 0 else 0


if __name__ == '__main__':
    exit(main())
