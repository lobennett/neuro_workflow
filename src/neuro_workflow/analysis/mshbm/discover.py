"""BIDS entity parsing + input discovery for the MSHBM input-prep pipeline.

Pure path/filename helpers (no subprocess, no heavy deps): they locate the
task-residual and rest-BOLD files fmriprep/lev1 produced, filter them by
session, and derive MSHBM-compatible output names. Consumed by
:mod:`neuro_workflow.analysis.mshbm.process`.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


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
