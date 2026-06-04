"""Per-subject MSHBM input-prep orchestration.

Ties together discovery (:mod:`.discover`) and the external transform wrappers
(:mod:`.transforms`) to project a subject's task-residual and rest-BOLD data to
fsaverage6 NIfTIs named for the CBIG MSHBM MATLAB code. Each ``process_*``
helper returns a count of failed conversions; ``process_subject`` is the
top-level entry point the CLI (:mod:`.run`) calls.
"""

import logging
import subprocess
from pathlib import Path

from neuro_workflow.analysis.mshbm.discover import (
    discover_rest_bold_fsaverage6,
    discover_rest_bold_surface,
    discover_rest_bold_volume,
    discover_task_residuals_surface,
    discover_task_residuals_volume,
    filter_by_sessions,
    find_anat_dir,
    find_mni_to_t1w_transform,
    find_t1w_reference,
    make_output_name,
    parse_bids_entities,
)
from neuro_workflow.analysis.mshbm.transforms import (
    apply_mni_to_t1w,
    create_lowres_reference,
    ensure_fsaverage6,
    resolve_fs_subject,
    surf2surf,
    vol2surf,
)

logger = logging.getLogger(__name__)

# Maps a BIDS hemisphere entity (L/R) to the FreeSurfer hemi label (lh/rh).
HEMI_MAP = {'L': 'lh', 'R': 'rh'}


def process_surface_residuals(
    residual_files: list[Path],
    subject: str,
    subjects_dir: Path,
    subj_output: Path,
) -> int:
    """Process fsnative GIFTI residuals -> fsaverage6 NIfTI. Returns error count."""
    errors = 0
    for gii_path in residual_files:
        entities = parse_bids_entities(gii_path.name)
        bids_hemi = entities.get('hemi')
        if not bids_hemi or bids_hemi not in HEMI_MAP:
            logger.warning('Cannot determine hemisphere from: %s', gii_path.name)
            errors += 1
            continue

        fs_hemi = HEMI_MAP[bids_hemi]
        out_name = make_output_name(gii_path, fs_hemi)
        out_path = subj_output / out_name

        if out_path.exists():
            logger.info('SKIP (exists): %s', out_name)
            continue

        logger.info('Processing residual: %s', gii_path.name)
        try:
            surf2surf(gii_path, out_path, subject, 'fsaverage6',
                      fs_hemi, subjects_dir)
            logger.info('Created: %s', out_name)
        except subprocess.CalledProcessError as e:
            logger.error(
                'mri_surf2surf failed for %s: %s', gii_path.name, e.stderr,
            )
            errors += 1

    return errors


def process_volume_residuals(
    residual_files: list[Path],
    subject: str,
    subjects_dir: Path,
    subj_output: Path,
    residuals_space: str,
    transform: Path | None,
    t1w_ref: Path | None,
) -> int:
    """Process volumetric residuals (MNI or T1w) -> fsaverage6 NIfTI. Returns error count."""
    errors = 0
    for res_path in residual_files:
        logger.info('Processing residual: %s', res_path.name)

        if residuals_space == 'MNI':
            # MNI -> T1w -> fsaverage6
            t1w_name = res_path.name.replace('.nii.gz', '_space-T1w.nii.gz')
            t1w_intermediate = subj_output / t1w_name
            try:
                apply_mni_to_t1w(res_path, t1w_intermediate, transform, t1w_ref)
            except subprocess.CalledProcessError as e:
                logger.error(
                    'antsApplyTransforms failed for %s (rc=%d)\n  stdout: %s\n  stderr: %s',
                    res_path.name, e.returncode,
                    e.output.strip() if e.output else '(empty)',
                    e.stderr.strip() if e.stderr else '(empty)',
                )
                errors += 1
                continue
            vol_for_surf = t1w_intermediate
        else:
            # T1w -> fsaverage6 (direct)
            vol_for_surf = res_path

        # Project to fsaverage6 (both hemispheres)
        for hemi in ['lh', 'rh']:
            out_name = make_output_name(res_path, hemi)
            out_path = subj_output / out_name

            if out_path.exists():
                logger.info('SKIP (exists): %s', out_name)
                continue

            try:
                vol2surf(vol_for_surf, out_path, subject, hemi, subjects_dir)
                logger.info('Created: %s', out_name)
            except subprocess.CalledProcessError as e:
                logger.error(
                    'mri_vol2surf failed for %s/%s: %s',
                    res_path.name, hemi, e.stderr,
                )
                errors += 1

        # Delete intermediate T1w volume if created
        if residuals_space == 'MNI' and t1w_intermediate.exists():
            t1w_intermediate.unlink()
            logger.debug('Deleted intermediate: %s', t1w_intermediate.name)

    return errors


def process_rest_fsaverage6(
    rest_files: list[Path],
    subjects_dir: Path,
    subj_output: Path,
) -> int:
    """Convert fsaverage6 GIFTI rest BOLD -> NIfTI via identity mri_surf2surf.

    Handles the case where fmriprep already outputs fsaverage6 surfaces.
    Uses mri_surf2surf with srcsubject=trgsubject=fsaverage6 to produce NIfTIs
    with FreeSurfer's dim=-1 convention needed by CBIG MSHBM MATLAB code.
    """
    errors = 0
    for gii_path in rest_files:
        entities = parse_bids_entities(gii_path.name)
        bids_hemi = entities.get('hemi')
        if not bids_hemi or bids_hemi not in HEMI_MAP:
            logger.warning('Cannot determine hemisphere from: %s', gii_path.name)
            errors += 1
            continue

        fs_hemi = HEMI_MAP[bids_hemi]
        out_name = make_output_name(gii_path, fs_hemi)
        out_path = subj_output / out_name

        if out_path.exists():
            logger.info('SKIP (exists): %s', out_name)
            continue

        logger.info('Processing rest (fsaverage6 GIFTI -> NIfTI): %s', gii_path.name)
        try:
            surf2surf(gii_path, out_path, 'fsaverage6', 'fsaverage6',
                      fs_hemi, subjects_dir)
            logger.info('Created: %s', out_name)
        except subprocess.CalledProcessError as e:
            logger.error(
                'mri_surf2surf failed for %s: %s', gii_path.name, e.stderr,
            )
            errors += 1

    return errors


def process_rest_fsnative(
    rest_files: list[Path],
    subject: str,
    subjects_dir: Path,
    subj_output: Path,
) -> int:
    """Resample fsnative rest BOLD GIFTI -> fsaverage6 NIfTI. Returns error count."""
    errors = 0
    for gii_path in rest_files:
        entities = parse_bids_entities(gii_path.name)
        bids_hemi = entities.get('hemi')
        if not bids_hemi or bids_hemi not in HEMI_MAP:
            logger.warning('Cannot determine hemisphere from: %s', gii_path.name)
            errors += 1
            continue

        fs_hemi = HEMI_MAP[bids_hemi]
        out_name = make_output_name(gii_path, fs_hemi)
        out_path = subj_output / out_name

        if out_path.exists():
            logger.info('SKIP (exists): %s', out_name)
            continue

        logger.info('Processing rest (fsnative -> fsaverage6): %s', gii_path.name)
        try:
            surf2surf(gii_path, out_path, subject, 'fsaverage6',
                      fs_hemi, subjects_dir)
            logger.info('Created: %s', out_name)
        except subprocess.CalledProcessError as e:
            logger.error(
                'mri_surf2surf failed for %s: %s', gii_path.name, e.stderr,
            )
            errors += 1

    return errors


def process_rest_volume(
    rest_files: list[Path],
    subject: str,
    subjects_dir: Path,
    subj_output: Path,
) -> int:
    """Project T1w rest BOLD volumes -> fsaverage6 NIfTI. Returns error count."""
    errors = 0
    for rest_path in rest_files:
        logger.info('Processing rest (T1w volume -> fsaverage6): %s', rest_path.name)
        for hemi in ['lh', 'rh']:
            out_name = make_output_name(rest_path, hemi)
            out_path = subj_output / out_name

            if out_path.exists():
                logger.info('SKIP (exists): %s', out_name)
                continue

            try:
                vol2surf(rest_path, out_path, subject, hemi, subjects_dir)
                logger.info('Created: %s', out_name)
            except subprocess.CalledProcessError as e:
                logger.error(
                    'mri_vol2surf failed for %s/%s: %s',
                    rest_path.name, hemi, e.stderr,
                )
                errors += 1

    return errors


def process_subject(
    subject: str,
    glm_dir: Path | None,
    fmriprep_dir: Path,
    output_dir: Path,
    residuals_space: str = 'surface',
    rest_fmriprep_dir: Path | None = None,
    sessions: set[str] | None = None,
    rest_only: bool = False,
) -> int:
    """Process all data for one subject. Returns error count."""
    subj_output = output_dir / subject
    subj_output.mkdir(parents=True, exist_ok=True)

    # FreeSurfer subjects dir (try main fmriprep first, then rest fmriprep)
    subjects_dir = fmriprep_dir / 'sourcedata' / 'freesurfer'
    if not subjects_dir.exists() and rest_fmriprep_dir:
        subjects_dir = rest_fmriprep_dir / 'sourcedata' / 'freesurfer'
    if not subjects_dir.exists():
        raise FileNotFoundError(
            f'FreeSurfer subjects dir not found under {fmriprep_dir}'
            + (f' or {rest_fmriprep_dir}' if rest_fmriprep_dir else '')
        )
    logger.info('FreeSurfer SUBJECTS_DIR: %s', subjects_dir)

    ensure_fsaverage6(subjects_dir)

    # Resolve actual FS subject dir name (fmriprep may use sub-X or sub-X_ses-Y).
    fs_subject = resolve_fs_subject(subjects_dir, subject)
    if fs_subject != subject:
        logger.info('FreeSurfer subject dir: %s (BIDS: %s)', fs_subject, subject)

    errors = 0

    # --- Task residuals -> fsaverage6 ---
    if not rest_only:
        if residuals_space == 'surface':
            # fsnative GIFTI -> fsaverage6 (mri_surf2surf)
            residual_files = discover_task_residuals_surface(glm_dir, subject)
            residual_files = filter_by_sessions(residual_files, sessions)
            errors += process_surface_residuals(
                residual_files, fs_subject, subjects_dir, subj_output,
            )
        else:
            # Volumetric (MNI or T1w) -> fsaverage6
            anat_dir = find_anat_dir(fmriprep_dir, subject)
            transform = None
            t1w_ref = None
            if residuals_space == 'MNI':
                transform = find_mni_to_t1w_transform(anat_dir)
                t1w_ref_fullres = find_t1w_reference(anat_dir)
                # Downsample T1w reference to 2mm to avoid OOM on 4D transforms
                t1w_ref = create_lowres_reference(t1w_ref_fullres, subj_output)

            residual_files = discover_task_residuals_volume(glm_dir, subject)
            residual_files = filter_by_sessions(residual_files, sessions)
            errors += process_volume_residuals(
                residual_files, fs_subject, subjects_dir, subj_output,
                residuals_space, transform, t1w_ref,
            )

    # --- Rest BOLD -> fsaverage6 ---
    # Priority: fsaverage6 GIFTI (from rest fmriprep) > fsnative GIFTI > T1w volume
    rest_dir = rest_fmriprep_dir if rest_fmriprep_dir else fmriprep_dir

    # 1. Check for fsaverage6 GIFTIs (already in target space, just format conversion)
    rest_fsavg6 = discover_rest_bold_fsaverage6(rest_dir, subject)
    rest_fsavg6 = filter_by_sessions(rest_fsavg6, sessions)
    if rest_fsavg6:
        errors += process_rest_fsaverage6(rest_fsavg6, subjects_dir, subj_output)
    else:
        # 2. Check for fsnative GIFTIs
        rest_fsnative = discover_rest_bold_surface(rest_dir, subject)
        rest_fsnative = filter_by_sessions(rest_fsnative, sessions)
        if rest_fsnative:
            errors += process_rest_fsnative(
                rest_fsnative, subject, subjects_dir, subj_output,
            )
        else:
            # 3. Fallback: T1w volumes
            rest_vol = discover_rest_bold_volume(rest_dir, subject)
            rest_vol = filter_by_sessions(rest_vol, sessions)
            if rest_vol:
                errors += process_rest_volume(
                    rest_vol, subject, subjects_dir, subj_output,
                )
            else:
                logger.warning('No rest BOLD data found for %s', subject)

    # Summary
    output_files = list(subj_output.glob('*_fsaverage6_sm0.nii.gz'))
    logger.info(
        'Total MSHBM surface files for %s: %d (%d errors)',
        subject, len(output_files), errors,
    )
    return errors
