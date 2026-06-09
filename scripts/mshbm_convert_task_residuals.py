"""Direct GIFTI → MSHBM-style NIfTI converter for fsaverage6 task residuals.

Bypasses ``mri_surf2surf`` for lev1's task-residual GIFTI files, which carry
``NIFTI_INTENT_NONE`` on DA[0] and consequently fail FreeSurfer's intent
check.  Since the data is already on fsaverage6 (no resampling needed), we
can skip mri_surf2surf entirely and convert directly via nibabel.

For each input *_task-regressed-residuals.func.gii (V vertices × T timepoints),
writes a NIfTI of shape (V, 1, 1, T) using the MSHBM filename convention:

  lh_ses-XX_task-XXX_run-Y_nat_resid_bpss_fsaverage6_sm0.nii.gz

This mirrors what ``process_surface_residuals`` in
``neuro_workflow.analysis.mshbm.run`` would have produced.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)

HEMI_MAP = {'L': 'lh', 'R': 'rh'}
_ENT = re.compile(
    r'sub-[^_]+_ses-(?P<ses>[^_]+)_task-(?P<task>[^_]+)'
    r'(?:_run-(?P<run>[^_]+))?_hemi-(?P<hemi>[LR])'
)


def gifti_to_nifti(gii_path: Path, out_path: Path) -> None:
    """Convert one fsaverage6 GIFTI time series → (V,1,1,T) NIfTI."""
    img = nib.load(str(gii_path))
    if not img.darrays:
        raise ValueError(f'GIFTI has no darrays: {gii_path}')
    stacked = np.stack([np.asarray(d.data, dtype=np.float32)
                        for d in img.darrays], axis=-1)
    V, T = stacked.shape
    arr = stacked.reshape(V, 1, 1, T)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nii = nib.Nifti1Image(arr, affine=np.eye(4))
    nii.to_filename(str(out_path))


def make_output_name(gii_name: str) -> str:
    """Mirror make_output_name() from analysis/mshbm/run.py."""
    m = _ENT.search(gii_name)
    if not m:
        raise ValueError(f'Cannot parse BIDS entities from: {gii_name}')
    hemi = HEMI_MAP[m.group('hemi')]
    run = m.group('run')
    ses = m.group('ses')
    task = m.group('task')
    if run is not None:
        suffix = f'ses-{ses}_task-{task}_run-{run}'
    else:
        suffix = f'ses-{ses}_task-{task}'
    return f'{hemi}_{suffix}_nat_resid_bpss_fsaverage6_sm0.nii.gz'


def find_task_residuals(lev1_root: Path, subject: str) -> list[Path]:
    """Glob all surface task-regressed-residuals GIFTIs for a subject."""
    subj_dir = lev1_root / f'sub-{subject}'
    files = list(subj_dir.glob(
        'task-*/task_residuals/*space-fsaverage6_task-regressed-residuals.func.gii'
    ))
    return sorted(files)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lev1-root', required=True, type=Path,
                   help='Path to lev1_surface derivative dir')
    p.add_argument('--output-dir', required=True, type=Path,
                   help='Subject MSHBM input dir (e.g. mshbm_inputs/sub-s03)')
    p.add_argument('--subject', required=True,
                   help='BIDS subject label without sub- prefix')
    p.add_argument('--skip-existing', action='store_true', default=True)
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    files = find_task_residuals(args.lev1_root, args.subject)
    logger.info('Found %d task-residual GIFTIs for sub-%s',
                len(files), args.subject)
    if not files:
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    n_converted = 0
    n_skipped = 0
    for gii in files:
        out_name = make_output_name(gii.name)
        out_path = args.output_dir / out_name
        if args.skip_existing and out_path.exists():
            n_skipped += 1
            continue
        try:
            gifti_to_nifti(gii, out_path)
            logger.info('  %s', out_name)
            n_converted += 1
        except Exception as e:
            logger.error('  FAILED %s: %s', gii.name, e)
            return 2

    logger.info('Converted %d files (%d skipped) → %s',
                n_converted, n_skipped, args.output_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
