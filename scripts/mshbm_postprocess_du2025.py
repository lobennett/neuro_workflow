"""Apply Du et al. 2025-style post-processing to prep-mshbm NIfTI outputs.

The prep-mshbm pipeline (with --rest-only=False) produces NIfTI files in
fsaverage6 surface space, one per (subject, session, task, run, hemisphere):

    lh_ses-XX_task-XXX_run-Y_nat_resid_bpss_fsaverage6_sm0.nii.gz

These are bare format-converted outputs — no confound regression, no
bandpass, no smoothing has been applied.  This script post-processes
them to match the Du et al. (2025, Neuron) MSHBM preprocessing recipe:

  * REST files (filename contains "_task-rest_"): Du-style 18-regressor
    nuisance regression (6 motion + GSR + ventricular + deep WM + their
    derivatives) + bandpass 0.01-0.10 Hz + 2 mm FWHM surface smoothing
  * TASK-RESIDUAL files (every other task-... file): bandpass only +
    2 mm FWHM surface smoothing.  Lev1 GLM already regressed motion +
    aCompCor + drift, so we do NOT re-regress.

Inputs are read from the prep-mshbm output dir and overwritten in place.
A backup *.preproc-input.nii.gz is left alongside each file for safety
unless --no-backup is set.

For the rest path, this script also needs the matching fmriprep
confounds.tsv (located via --fmriprep-dir).  TR is read from the BIDS
JSON sidecar.
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

from neuro_workflow.analysis.mshbm.preproc import (
    bandpass_filter,
    build_regressor_matrix_du2025,
    regress_confounds,
)

logger = logging.getLogger(__name__)


_REST_RE = re.compile(r'_task-rest_')
_BIDS_RE = re.compile(
    r'_ses-(?P<ses>[^_]+)_task-(?P<task>[^_]+)(?:_run-(?P<run>[^_]+))?_'
)


def find_confounds_tsv(fmriprep_dir: Path, subject: str, ses: str, task: str,
                       run: str | None) -> Path:
    """Find fmriprep's *_desc-confounds_timeseries.tsv for a given run."""
    fp = fmriprep_dir / f'sub-{subject}' / f'ses-{ses}' / 'func'
    if run is not None:
        pattern = f'sub-{subject}_ses-{ses}_task-{task}_run-{run}_desc-confounds_timeseries.tsv'
    else:
        pattern = f'sub-{subject}_ses-{ses}_task-{task}_desc-confounds_timeseries.tsv'
    matches = list(fp.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f'No confounds.tsv match for sub-{subject} ses-{ses} task-{task} '
            f'run-{run} in {fp}'
        )
    return matches[0]


def read_tr_seconds(fmriprep_dir: Path, subject: str, ses: str, task: str,
                    run: str | None) -> float:
    """Read RepetitionTime (s) from the BOLD JSON sidecar."""
    import json
    fp = fmriprep_dir / f'sub-{subject}' / f'ses-{ses}' / 'func'
    if run is not None:
        pattern = f'sub-{subject}_ses-{ses}_task-{task}_run-{run}_desc-preproc_bold.json'
    else:
        pattern = f'sub-{subject}_ses-{ses}_task-{task}_desc-preproc_bold.json'
    matches = list(fp.glob(pattern))
    if not matches:
        raise FileNotFoundError(f'No BOLD JSON sidecar for sub-{subject} ses-{ses}')
    with matches[0].open() as fh:
        meta = json.load(fh)
    return float(meta['RepetitionTime'])


def parse_bids_from_filename(name: str) -> dict[str, str | None]:
    """Pull ses/task/run entities from a prep-mshbm NIfTI filename."""
    m = _BIDS_RE.search(name)
    if not m:
        raise ValueError(f'Cannot parse BIDS entities from: {name}')
    out = m.groupdict()
    return {k: v for k, v in out.items()}


def load_nifti_vt(path: Path) -> tuple[np.ndarray, nib.Nifti1Image]:
    """Load a (V, T) array from the CBIG/freesurfer convention NIfTI.

    These NIfTIs store one vertex per voxel along the first spatial dim,
    with T volumes along the fourth dim.  Shape is typically (40962, 1, 1, T).
    Returns ``(V, T) array, original_image``.
    """
    img = nib.load(str(path))
    data = np.asanyarray(img.dataobj)  # could be (V,1,1,T) or similar
    # Reshape to (V, T): the CBIG convention is the first 3 dims hold V
    # (as e.g. V x 1 x 1) and the last dim is T.
    if data.ndim != 4:
        raise ValueError(f'Expected 4D NIfTI, got shape {data.shape}: {path}')
    V = int(np.prod(data.shape[:3]))
    T = data.shape[3]
    return data.reshape(V, T).astype(np.float32, copy=False), img


def save_nifti_vt(arr_vt: np.ndarray, ref_img: nib.Nifti1Image, out_path: Path) -> None:
    """Save a (V, T) array back to a 4-D NIfTI matching the reference."""
    V, T = arr_vt.shape
    spatial = ref_img.shape[:3]
    if int(np.prod(spatial)) != V:
        raise ValueError(f'Vertex count mismatch: ref {spatial} vs data {V}')
    new_data = arr_vt.reshape(*spatial, T)
    out_img = nib.Nifti1Image(new_data, ref_img.affine, ref_img.header)
    out_img.to_filename(str(out_path))


def smooth_surface_2mm(in_path: Path, out_path: Path, fwhm: float,
                       subjects_dir: Path, hemi: str) -> None:
    """Apply mri_surf2surf surface smoothing on fsaverage6."""
    cmd = [
        'mri_surf2surf',
        '--srcsubject', 'fsaverage6',
        '--trgsubject', 'fsaverage6',
        '--sval', str(in_path),
        '--tval', str(out_path),
        '--hemi', hemi,
        '--fwhm-trg', str(fwhm),
    ]
    env = {'SUBJECTS_DIR': str(subjects_dir)}
    import os
    env = {**os.environ, **env}
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f'mri_surf2surf failed for {in_path}: {res.stderr[-500:]}'
        )


def process_one(
    nifti_path: Path,
    fmriprep_dir: Path,
    subject: str,
    subjects_dir: Path,
    fwhm_mm: float,
    lowcut_hz: float,
    highcut_hz: float,
    backup: bool,
) -> None:
    """Apply Du-style preproc to one prep-mshbm NIfTI file in place."""
    name = nifti_path.name
    is_rest = bool(_REST_RE.search(name))
    is_lh = name.startswith('lh_')
    hemi = 'lh' if is_lh else 'rh'
    entities = parse_bids_from_filename(name)
    ses, task, run = entities['ses'], entities['task'], entities.get('run')

    logger.info(
        '[%s] %s — rest=%s ses=%s task=%s run=%s hemi=%s',
        subject, name, is_rest, ses, task, run, hemi,
    )

    Y, ref_img = load_nifti_vt(nifti_path)
    V, T = Y.shape
    logger.info('  shape: V=%d T=%d', V, T)

    if backup:
        backup_path = nifti_path.with_suffix('.preproc-input.nii.gz')
        if not backup_path.exists():
            shutil.copy2(nifti_path, backup_path)
            logger.info('  backup → %s', backup_path.name)

    # Step 1: confound regression — REST ONLY
    if is_rest:
        confounds_path = find_confounds_tsv(fmriprep_dir, subject, ses, task, run)
        confounds_df = pd.read_csv(confounds_path, sep='\t')
        X = build_regressor_matrix_du2025(confounds_df)
        if X.shape[0] != T:
            raise ValueError(
                f'confounds rows={X.shape[0]} != T={T} for {nifti_path.name}'
            )
        Y = regress_confounds(Y, X)
        logger.info('  Du-style confound regression applied (18 regressors)')
    else:
        logger.info('  task-residual file — skipping further nuisance regression '
                    '(lev1 already regressed motion + aCompCor + drift)')

    # Step 2: bandpass — both rest and task residuals
    tr_s = read_tr_seconds(fmriprep_dir, subject, ses, task, run)
    Y = bandpass_filter(Y, tr=tr_s, lowcut=lowcut_hz, highcut=highcut_hz)
    logger.info('  bandpass %.3f-%.3f Hz (TR=%.3fs)', lowcut_hz, highcut_hz, tr_s)

    # Step 3: write pre-smoothing intermediate, then smooth via mri_surf2surf
    with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        save_nifti_vt(Y, ref_img, tmp_path)
        smooth_surface_2mm(tmp_path, nifti_path, fwhm_mm, subjects_dir, hemi)
        logger.info('  smoothed %.1f mm FWHM (mri_surf2surf) → %s', fwhm_mm, nifti_path.name)
    finally:
        tmp_path.unlink(missing_ok=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mshbm-input-dir', required=True, type=Path,
                   help='Subject dir from prep-mshbm (e.g. .../sub-s03)')
    p.add_argument('--fmriprep-dir', required=True, type=Path)
    p.add_argument('--subjects-dir', required=True, type=Path,
                   help='FreeSurfer SUBJECTS_DIR (must contain fsaverage6 subject)')
    p.add_argument('--subject', required=True,
                   help='BIDS subject label, no sub- prefix, e.g. s03')
    p.add_argument('--fwhm-mm', type=float, default=2.0)
    p.add_argument('--lowcut-hz', type=float, default=0.01)
    p.add_argument('--highcut-hz', type=float, default=0.10)
    p.add_argument('--no-backup', action='store_true')
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    files = sorted(args.mshbm_input_dir.glob('*_nat_resid_bpss_fsaverage6_sm0.nii.gz'))
    if not files:
        logger.error('No NIfTIs in %s', args.mshbm_input_dir)
        return 1
    logger.info('Found %d files in %s', len(files), args.mshbm_input_dir)

    for f in files:
        try:
            process_one(
                nifti_path=f,
                fmriprep_dir=args.fmriprep_dir,
                subject=args.subject,
                subjects_dir=args.subjects_dir,
                fwhm_mm=args.fwhm_mm,
                lowcut_hz=args.lowcut_hz,
                highcut_hz=args.highcut_hz,
                backup=(not args.no_backup),
            )
        except Exception as e:
            logger.error('FAILED: %s — %s', f.name, e)
            return 2

    logger.info('All files processed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
