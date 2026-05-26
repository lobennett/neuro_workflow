"""Convert one subject's XCP-D denoised CIFTIs into MSHBM fsaverage6 inputs.

For each (session × task) cell, runs:
    wb_command -cifti-separate  (split L/R from CIFTI)
    wb_command -metric-resample (fsLR_32k → fsaverage6, BARYCENTRIC)
    wb_command -metric-smoothing (2mm FWHM on midthickness)
    python: wrap as (V, 1, 1, T) NIfTI for MSHBM

The fsaverage6 midthickness surfaces are pial+white averages, computed
once and cached at <output_dir>/.fsaverage6_midthickness_{L,R}.surf.gii.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from neuro_workflow.analysis.mshbm.from_xcpd import (
    Cell,
    discover_xcpd_cells,
    gifti_to_mshbm_nifti,
    templateflow_paths,
)

logger = logging.getLogger(__name__)

# 2mm FWHM → sigma = 2 / 2.355 ≈ 0.849
SMOOTHING_SIGMA_MM = 2.0 / 2.355


def _run(cmd: list[str]) -> None:
    logger.debug('+ %s', ' '.join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def _ensure_midthickness(out_dir: Path, paths: dict[str, dict[str, Path]]) -> dict[str, Path]:
    """Build (or cache) fsaverage6 midthickness per hemi."""
    midthk: dict[str, Path] = {}
    for hemi in ('L', 'R'):
        target = out_dir / f'.fsaverage6_midthickness_{hemi}.surf.gii'
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            _run([
                'wb_command', '-surface-average',
                str(target),
                '-surf', str(paths[hemi]['fsaverage6_pial']),
                '-surf', str(paths[hemi]['fsaverage6_white']),
            ])
        midthk[hemi] = target
    return midthk


def _process_cell(
    cell: Cell,
    subject: str,
    out_dir: Path,
    paths: dict[str, dict[str, Path]],
    midthk: dict[str, Path],
    work_dir: Path,
) -> None:
    """Run cifti-separate → metric-resample → metric-smoothing → nifti wrap
    for both hemispheres of one cell."""
    cifti_label = {'L': 'CORTEX_LEFT', 'R': 'CORTEX_RIGHT'}
    short = {'L': 'lh', 'R': 'rh'}

    # Step 1: split CIFTI → two per-hemi GIFTIs (fsLR_32k)
    sep_lh = work_dir / 'sep_lh.func.gii'
    sep_rh = work_dir / 'sep_rh.func.gii'
    _run([
        'wb_command', '-cifti-separate', str(cell.dtseries), 'COLUMN',
        '-metric', cifti_label['L'], str(sep_lh),
        '-metric', cifti_label['R'], str(sep_rh),
    ])

    for hemi, sep in (('L', sep_lh), ('R', sep_rh)):
        # Step 2: resample fsLR_32k → fsaverage6
        resampled = work_dir / f'resampled_{hemi}.func.gii'
        _run([
            'wb_command', '-metric-resample',
            str(sep),
            str(paths[hemi]['fsLR_sphere']),
            str(paths[hemi]['fsaverage6_sphere']),
            'BARYCENTRIC',
            str(resampled),
        ])

        # Step 3: smooth 2mm FWHM on fsaverage6 midthickness
        smoothed = work_dir / f'smoothed_{hemi}.func.gii'
        _run([
            'wb_command', '-metric-smoothing',
            str(midthk[hemi]),
            str(resampled),
            f'{SMOOTHING_SIGMA_MM:.6f}',
            str(smoothed),
        ])

        # Step 4: wrap as (V, 1, 1, T) NIfTI for MSHBM
        sub_dir = out_dir / f'sub-{subject}'
        out_path = sub_dir / f'{short[hemi]}_{cell.session}_task-{cell.task}_xcpd_fsaverage6_sm2.nii.gz'
        gifti_to_mshbm_nifti(smoothed, out_path)
        logger.info('  wrote %s', out_path.relative_to(out_dir))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xcpd-dir', type=Path, required=True,
                   help='XCP-D derivatives root (contains sub-{XXX}/...)')
    p.add_argument('--subject', required=True,
                   help='Subject label without sub- prefix (e.g. s10)')
    p.add_argument('--output-dir', type=Path, required=True,
                   help='MSHBM input root (will create sub-{XXX}/ inside)')
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if not shutil.which('wb_command'):
        logger.error('wb_command not on PATH — load the workbench module first')
        return 2

    subject_root = args.xcpd_dir / f'sub-{args.subject}'
    if not subject_root.is_dir():
        logger.error('No XCP-D output for sub-%s at %s', args.subject, subject_root)
        return 1

    cells = discover_xcpd_cells(subject_root)
    if not cells:
        logger.error('No desc-denoised CIFTIs found under %s', subject_root)
        return 1
    logger.info('Found %d cells for sub-%s', len(cells), args.subject)

    paths = templateflow_paths()
    midthk = _ensure_midthickness(args.output_dir, paths)

    with tempfile.TemporaryDirectory(prefix='mshbm_xcpd_') as work_dir_str:
        work_dir = Path(work_dir_str)
        for i, cell in enumerate(cells, 1):
            logger.info('[%d/%d] sub-%s %s task-%s', i, len(cells),
                        args.subject, cell.session, cell.task)
            _process_cell(cell, args.subject, args.output_dir, paths, midthk, work_dir)

    logger.info('done sub-%s', args.subject)
    return 0


if __name__ == '__main__':
    sys.exit(main())
