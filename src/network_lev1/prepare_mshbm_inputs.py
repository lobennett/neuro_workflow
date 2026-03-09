#!/usr/bin/env python3
"""Prepare fsaverage6 surface inputs for MSHBM.

Consolidates task residual projection and rest BOLD format conversion into
a single script. Produces MSHBM-compatible NIfTI files organized by subject:

    {output_dir}/{subject}/{lh,rh}_ses-XX_task-XXX_run-X_nat_resid_bpss_fsaverage6_sm0.nii.gz

Data sources and processing paths:
- Task residuals (surface/fsnative): fsnative -> fsaverage6 via mri_surf2surf
- Task residuals (MNI): MNI -> T1w (antsApplyTransforms) -> fsaverage6 (mri_vol2surf)
- Task residuals (T1w): T1w -> fsaverage6 via mri_vol2surf
- Rest BOLD (fsaverage6 GIFTI): format conversion via identity mri_surf2surf
- Rest BOLD (fsnative GIFTI): fsnative -> fsaverage6 via mri_surf2surf
- Rest BOLD (T1w volume): T1w -> fsaverage6 via mri_vol2surf (fallback)

Usage:
    uv run python src/helpers/prepare_mshbm_inputs.py \\
        --subj-id s03 \\
        --glm-dir /path/to/glm/results \\
        --fmriprep-dir /path/to/fmriprep \\
        --rest-fmriprep-dir /path/to/rest/fmriprep
"""

import argparse
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

HEMI_MAP = {'L': 'lh', 'R': 'rh'}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def parse_bids_entities(filename: str) -> dict[str, str]:
    """Extract BIDS entities (sub, ses, task, run, hemi) from a filename.

    Only keeps the first match for each entity key to avoid confusion when
    'task-' appears in both the task name and a suffix (e.g., task-regressed).
    """
    entities = {}
    for match in re.finditer(r'(sub|ses|task|run|hemi)-([a-zA-Z0-9]+)', filename):
        key = match.group(1)
        if key not in entities:
            entities[key] = match.group(2)
    return entities


def filter_by_sessions(
    files: list[Path], sessions: set[str] | None
) -> list[Path]:
    """Filter file list to only include files from specified sessions.

    Args:
        files: List of Paths with BIDS-style filenames.
        sessions: Set of session labels (e.g., {'01', '02'}).
                  If None, all files are returned (no filtering).
    """
    if sessions is None:
        return files

    filtered = []
    for f in files:
        entities = parse_bids_entities(f.name)
        ses = entities.get('ses')
        if ses and ses in sessions:
            filtered.append(f)
        elif not ses:
            logger.warning('No session entity in %s -- skipping', f.name)

    logger.info(
        'Session filter (%s): %d / %d files kept',
        ', '.join(sorted(sessions)), len(filtered), len(files),
    )
    return filtered


def find_anat_dir(fmriprep_dir: Path, subject: str) -> Path:
    """Find the session containing T1w anatomical data for a subject.

    The anat directory lives in a different session per subject
    (e.g., s03->ses-05, s10->ses-09). Some sessions may have an anat
    dir with only T2w data; this function finds the one with T1w.
    """
    subj_dir = fmriprep_dir / subject
    if not subj_dir.exists():
        raise FileNotFoundError(f'Subject directory not found: {subj_dir}')

    for ses_dir in sorted(subj_dir.iterdir()):
        if not ses_dir.is_dir():
            continue
        anat_dir = ses_dir / 'anat'
        if anat_dir.is_dir() and list(anat_dir.glob('*desc-preproc_T1w.nii.gz')):
            logger.info('Found anat dir: %s', anat_dir)
            return anat_dir

    raise FileNotFoundError(f'No anat directory with T1w data found for {subject}')


def find_mni_to_t1w_transform(anat_dir: Path) -> Path:
    """Find the MNI-to-T1w .h5 transform file from fmriprep."""
    pattern = '*from-MNI152NLin2009cAsym_to-T1w*xfm.h5'
    matches = sorted(anat_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(f'No MNI-to-T1w transform found in {anat_dir}')
    logger.info('Found transform: %s', matches[0].name)
    return matches[0]


def find_t1w_reference(anat_dir: Path) -> Path:
    """Find the T1w reference NIfTI from fmriprep."""
    pattern = '*desc-preproc_T1w.nii.gz'
    matches = sorted(anat_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(f'No T1w reference found in {anat_dir}')
    logger.info('Found T1w reference: %s', matches[0].name)
    return matches[0]


def discover_task_residuals_volume(glm_dir: Path, subject: str) -> list[Path]:
    """Discover volumetric task-regressed residual NIfTIs for a subject."""
    subj_dir = glm_dir / subject
    if not subj_dir.exists():
        logger.warning('GLM subject directory not found: %s', subj_dir)
        return []

    files = sorted(
        subj_dir.glob('task-*/task_residuals/*_task-regressed-residuals.nii.gz')
    )
    logger.info('Found %d volumetric task residual files', len(files))
    return files


def discover_task_residuals_surface(glm_dir: Path, subject: str) -> list[Path]:
    """Discover surface (fsnative GIFTI) task-regressed residuals for a subject."""
    subj_dir = glm_dir / subject
    if not subj_dir.exists():
        logger.warning('GLM subject directory not found: %s', subj_dir)
        return []

    files = sorted(
        subj_dir.glob('task-*/task_residuals/*_task-regressed-residuals.func.gii')
    )
    logger.info('Found %d surface task residual files', len(files))
    return files


def discover_rest_bold_fsaverage6(fmriprep_dir: Path, subject: str) -> list[Path]:
    """Discover fsaverage6-space rest BOLD GIFTI files from fmriprep output."""
    subj_dir = fmriprep_dir / subject
    if not subj_dir.exists():
        logger.warning('fmriprep subject directory not found: %s', subj_dir)
        return []

    files = sorted(
        subj_dir.glob('ses-*/func/*task-rest*space-fsaverage6*bold.func.gii')
    )
    logger.info('Found %d rest BOLD files (fsaverage6 GIFTI)', len(files))
    return files


def discover_rest_bold_surface(fmriprep_dir: Path, subject: str) -> list[Path]:
    """Discover fsnative-space rest BOLD GIFTI files across all sessions."""
    subj_dir = fmriprep_dir / subject
    if not subj_dir.exists():
        logger.warning('fmriprep subject directory not found: %s', subj_dir)
        return []

    files = sorted(
        subj_dir.glob('ses-*/func/*task-rest*space-fsnative*bold.func.gii')
    )
    logger.info('Found %d rest BOLD files (fsnative surface)', len(files))
    return files


def discover_rest_bold_volume(fmriprep_dir: Path, subject: str) -> list[Path]:
    """Discover T1w-space rest BOLD files across all sessions."""
    subj_dir = fmriprep_dir / subject
    if not subj_dir.exists():
        logger.warning('fmriprep subject directory not found: %s', subj_dir)
        return []

    files = sorted(
        subj_dir.glob('ses-*/func/*task-rest*space-T1w*desc-preproc_bold.nii.gz')
    )
    logger.info('Found %d rest BOLD files (T1w space)', len(files))
    return files


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def ensure_fsaverage6(subjects_dir: Path) -> None:
    """Ensure fsaverage6 is available in SUBJECTS_DIR.

    If fsaverage6 is not present, creates a symlink from
    $FREESURFER_HOME/subjects/fsaverage6.
    """
    fsaverage6_dir = subjects_dir / 'fsaverage6'
    if fsaverage6_dir.exists():
        logger.debug('fsaverage6 already in SUBJECTS_DIR')
        return

    fs_home = os.environ.get('FREESURFER_HOME')
    if not fs_home:
        raise EnvironmentError(
            'fsaverage6 not in SUBJECTS_DIR and FREESURFER_HOME not set. '
            'Load FreeSurfer module first.'
        )

    source = Path(fs_home) / 'subjects' / 'fsaverage6'
    if not source.exists():
        raise FileNotFoundError(
            f'fsaverage6 not found at {source}. Check FreeSurfer installation.'
        )

    fsaverage6_dir.symlink_to(source)
    logger.info('Symlinked fsaverage6: %s -> %s', fsaverage6_dir, source)


def create_lowres_reference(
    reference: Path,
    output_dir: Path,
    resolution: float = 2.0,
) -> Path:
    """Create a low-resolution version of the T1w reference for transforms.

    The fmriprep T1w can be sub-millimeter (e.g. 0.5mm), which makes the
    output 4D volume enormous and causes OOM kills. Resampling to 2mm
    keeps memory manageable while mri_vol2surf still samples at vertex
    locations regardless of voxel size.
    """
    stem = reference.name.replace('.nii.gz', '').replace('.nii', '')
    lowres_ref = output_dir / f'{stem}_res-2mm.nii.gz'
    if lowres_ref.exists():
        logger.debug('Low-res reference already exists: %s', lowres_ref.name)
        return lowres_ref

    cmd = [
        'ResampleImage', '3',
        str(reference), str(lowres_ref),
        f'{resolution}x{resolution}x{resolution}', '0', '0',
    ]
    logger.info('Creating 2mm T1w reference for transforms')
    logger.debug('Command: %s', ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f'ResampleImage failed (rc={result.returncode}): '
            f'{result.stderr or result.stdout}'
        )
    return lowres_ref


def apply_mni_to_t1w(
    input_vol: Path,
    output_vol: Path,
    transform: Path,
    reference: Path,
) -> None:
    """Warp 4D MNI volume to T1w space using antsApplyTransforms."""
    cmd = [
        'antsApplyTransforms',
        '-d', '3',
        '-e', '3',
        '-i', str(input_vol),
        '-r', str(reference),
        '-t', str(transform),
        '-o', str(output_vol),
    ]
    output_vol.parent.mkdir(parents=True, exist_ok=True)
    logger.info('antsApplyTransforms: %s -> T1w', input_vol.name)
    logger.debug('Command: %s', ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd,
            output=result.stdout, stderr=result.stderr,
        )


def surf2surf(
    input_surf: Path,
    output_path: Path,
    src_subject: str,
    trg_subject: str,
    hemi: str,
    subjects_dir: Path,
) -> None:
    """Resample or convert surface data using mri_surf2surf.

    When src_subject == trg_subject (e.g., both 'fsaverage6'), this performs
    an identity resample that converts GIFTI to NIfTI with FreeSurfer's
    dim=-1 convention needed by CBIG MSHBM MATLAB code.

    Args:
        input_surf: Input surface file (.func.gii or .nii.gz).
        output_path: Output surface file (.nii.gz) on target subject.
        src_subject: Source FreeSurfer subject (e.g., 'sub-s03' or 'fsaverage6').
        trg_subject: Target FreeSurfer subject (e.g., 'fsaverage6').
        hemi: Hemisphere ('lh' or 'rh').
        subjects_dir: FreeSurfer SUBJECTS_DIR.
    """
    cmd = [
        'mri_surf2surf',
        '--srcsubject', src_subject,
        '--trgsubject', trg_subject,
        '--hemi', hemi,
        '--sval', str(input_surf),
        '--tval', str(output_path),
    ]
    logger.debug(
        'mri_surf2surf (%s -> %s, %s): %s',
        src_subject, trg_subject, hemi, input_surf.name,
    )
    env = os.environ.copy()
    env['SUBJECTS_DIR'] = str(subjects_dir)
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    if result.stderr:
        logger.debug('mri_surf2surf stderr: %s', result.stderr.strip())


def vol2surf(
    input_vol: Path,
    output_path: Path,
    subject: str,
    hemi: str,
    subjects_dir: Path,
) -> None:
    """Project volume to fsaverage6 surface using mri_vol2surf.

    Args:
        input_vol: Input volume in subject T1w space.
        output_path: Output surface file (.nii.gz) on fsaverage6.
        subject: FreeSurfer subject name (e.g., sub-s03).
        hemi: Hemisphere ('lh' or 'rh').
        subjects_dir: FreeSurfer SUBJECTS_DIR.
    """
    cmd = [
        'mri_vol2surf',
        '--src', str(input_vol),
        '--out', str(output_path),
        '--regheader', subject,
        '--trgsubject', 'fsaverage6',
        '--hemi', hemi,
        '--projfrac', '0.5',
    ]
    logger.debug('mri_vol2surf (hemi=%s): %s', hemi, input_vol.name)
    env = os.environ.copy()
    env['SUBJECTS_DIR'] = str(subjects_dir)
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    if result.stderr:
        logger.debug('mri_vol2surf stderr: %s', result.stderr.strip())


# ---------------------------------------------------------------------------
# Output naming (MSHBM-compatible)
# ---------------------------------------------------------------------------


def make_output_name(input_path: Path, hemi: str) -> str:
    """Build MSHBM-compatible filename for a surface file.

    MSHBM wrapper globs: {lh,rh}*nat_resid_bpss_fsaverage6_sm*.nii.gz

    Input:  sub-s03_ses-02_task-cuedTS_run-1_task-regressed-residuals.nii.gz
        or: sub-s03_ses-02_task-cuedTS_run-1_hemi-L_task-regressed-residuals.func.gii
        or: sub-s03_ses-01_task-rest_run-1_hemi-L_space-fsaverage6_bold.func.gii
    Output: lh_ses-02_task-cuedTS_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz
    """
    entities = parse_bids_entities(input_path.name)
    parts = []
    if 'ses' in entities:
        parts.append(f'ses-{entities["ses"]}')
    if 'task' in entities:
        parts.append(f'task-{entities["task"]}')
    if 'run' in entities:
        parts.append(f'run-{entities["run"]}')
    suffix = '_'.join(parts)
    return f'{hemi}_{suffix}_nat_resid_bpss_fsaverage6_sm0.nii.gz'


# ---------------------------------------------------------------------------
# Subject processing
# ---------------------------------------------------------------------------


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
    glm_dir: Path,
    fmriprep_dir: Path,
    output_dir: Path,
    residuals_space: str = 'surface',
    rest_fmriprep_dir: Path | None = None,
    sessions: set[str] | None = None,
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

    errors = 0

    # --- Task residuals -> fsaverage6 ---
    if residuals_space == 'surface':
        # fsnative GIFTI -> fsaverage6 (mri_surf2surf)
        residual_files = discover_task_residuals_surface(glm_dir, subject)
        residual_files = filter_by_sessions(residual_files, sessions)
        errors += process_surface_residuals(
            residual_files, subject, subjects_dir, subj_output,
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
            residual_files, subject, subjects_dir, subj_output,
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Prepare fsaverage6 surface inputs for MSHBM',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Surface residuals + fsaverage6 rest from separate fmriprep
  %(prog)s --subj-id s03 \\
      --glm-dir /results/surface \\
      --fmriprep-dir /data/fmriprep \\
      --rest-fmriprep-dir /data/fmriprep_rest

  # MNI residuals + rest from same fmriprep
  %(prog)s --subj-id s03 \\
      --glm-dir /results/MNI \\
      --fmriprep-dir /data/fmriprep \\
      --residuals-space MNI""",
    )
    parser.add_argument(
        '--subj-id', type=str, required=True,
        help='Subject ID (e.g., s03)',
    )
    parser.add_argument(
        '--glm-dir', type=str, required=True,
        help='GLM results directory containing sub-s*/task-*/task_residuals/',
    )
    parser.add_argument(
        '--fmriprep-dir', type=str, required=True,
        help='Primary fMRIPrep derivatives directory (FreeSurfer subjects, anat)',
    )
    parser.add_argument(
        '--rest-fmriprep-dir', type=str, default=None,
        help='Separate fMRIPrep directory for rest BOLD '
        '(if different from --fmriprep-dir)',
    )
    parser.add_argument(
        '--output-dir', type=str,
        default='/scratch/users/logben/surface_inputs',
        help='Output base directory (default: /scratch/users/logben/surface_inputs)',
    )
    parser.add_argument(
        '--residuals-space', choices=['surface', 'MNI', 'T1w'], default='surface',
        help='Space of input task residuals. surface: fsnative GIFTI resampled '
        'via mri_surf2surf; MNI: warped to T1w then projected; T1w: projected '
        'directly (default: surface)',
    )
    parser.add_argument(
        '--sessions', nargs='+', default=None,
        help='Only process these sessions (e.g., --sessions 01 02). '
        'Default: all sessions.',
    )
    parser.add_argument(
        '--verbose', action='store_true', default=False,
        help='Enable debug logging',
    )
    return parser


def main() -> int:
    parser = get_parser()
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout,
    )

    subject = args.subj_id
    if not subject.startswith('sub-'):
        subject = f'sub-{subject}'

    sessions = set(args.sessions) if args.sessions else None
    rest_fmriprep_dir = (
        Path(args.rest_fmriprep_dir) if args.rest_fmriprep_dir else None
    )

    logger.info(
        'Preparing MSHBM inputs: %s (residuals: %s, rest fmriprep: %s, sessions: %s)',
        subject, args.residuals_space,
        rest_fmriprep_dir or 'same as --fmriprep-dir',
        ', '.join(sorted(sessions)) if sessions else 'all',
    )

    errors = process_subject(
        subject=subject,
        glm_dir=Path(args.glm_dir),
        fmriprep_dir=Path(args.fmriprep_dir),
        output_dir=Path(args.output_dir),
        residuals_space=args.residuals_space,
        rest_fmriprep_dir=rest_fmriprep_dir,
        sessions=sessions,
    )

    if errors > 0:
        logger.warning('Completed with %d errors', errors)
        return 1

    logger.info('Completed successfully')
    return 0


if __name__ == '__main__':
    sys.exit(main())
