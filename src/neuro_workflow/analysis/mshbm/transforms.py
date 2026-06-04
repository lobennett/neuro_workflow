"""External surface/volume transform wrappers for the MSHBM input-prep pipeline.

Thin subprocess wrappers around FreeSurfer (``mri_surf2surf``,
``mri_vol2surf``), ANTs (``antsApplyTransforms``, ``ResampleImage``), plus the
FreeSurfer SUBJECTS_DIR bookkeeping (``resolve_fs_subject``,
``ensure_fsaverage6``). Consumed by
:mod:`neuro_workflow.analysis.mshbm.process`.
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_fs_subject(subjects_dir: Path, subject: str) -> str:
    """Resolve the actual FreeSurfer subject directory name for a BIDS subject.

    fmriprep names FS subject dirs as either ``<subject>`` (cross-session
    anatomical) or ``<subject>_ses-<N>`` (longitudinal with a single anat
    session). This helper checks for ``surf/lh.sphere.reg.gii`` to identify
    the right dir, since the BIDS subject id alone is ambiguous.

    Args:
        subjects_dir: FreeSurfer SUBJECTS_DIR.
        subject: BIDS subject id including the ``sub-`` prefix (e.g. ``sub-s03``).

    Returns:
        Actual directory name to pass as ``--srcsubject`` to ``mri_surf2surf``.

    Raises:
        FileNotFoundError: when no matching FS subject dir is found.
        ValueError: when multiple session-suffixed dirs match — caller must
            resolve which session to use.
    """
    # FreeSurfer's spherical-registration file is normally the bare
    # ``lh.sphere.reg`` (no extension); newer versions also accept a
    # ``.gii`` variant.  Either is sufficient to identify a complete dir.
    def has_sphere_reg(dir_: Path) -> bool:
        surf = dir_ / "surf"
        return (surf / "lh.sphere.reg").is_file() or (surf / "lh.sphere.reg.gii").is_file()

    bare = subjects_dir / subject
    if has_sphere_reg(bare):
        return subject

    candidates = sorted(p for p in subjects_dir.glob(f"{subject}_ses-*")
                        if has_sphere_reg(p))
    if len(candidates) == 1:
        return candidates[0].name
    if len(candidates) > 1:
        names = [p.name for p in candidates]
        raise ValueError(
            f"Multiple FS subject dirs for {subject}: {names}. "
            "Disambiguate via single-anat-session policy upstream."
        )
    raise FileNotFoundError(
        f"No FreeSurfer subject dir found for {subject} under {subjects_dir}. "
        f"Expected '{subject}/' or '{subject}_ses-*/' with surf/lh.sphere.reg."
    )


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
