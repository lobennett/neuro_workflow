#!/usr/bin/env python3
"""Prepare fsaverage6 surface inputs for MSHBM (CLI entry point).

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

This module is the CLI only; the work is split across sibling modules:
- :mod:`.discover`   — BIDS entity parsing + input discovery + output naming
- :mod:`.transforms` — FreeSurfer / ANTs subprocess wrappers
- :mod:`.process`    — per-subject orchestration (``process_subject``)

Usage:
    uv run python -m neuro_workflow.analysis.mshbm.run \\
        --subj-id s03 \\
        --glm-dir /path/to/glm/results \\
        --fmriprep-dir /path/to/fmriprep \\
        --rest-fmriprep-dir /path/to/rest/fmriprep
"""

import argparse
import logging
import sys
from pathlib import Path

from neuro_workflow.analysis.mshbm.process import process_subject

logger = logging.getLogger(__name__)


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
        '--glm-dir', type=str, default=None,
        help='GLM results directory containing sub-s*/task-*/task_residuals/. '
             'Required unless --rest-only is set.',
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
        '--rest-only', action='store_true', default=False,
        help='Skip task-residual discovery + processing. Only rest BOLD '
             'is projected to fsaverage6. Mutually exclusive with --glm-dir.',
    )
    parser.add_argument(
        '--verbose', action='store_true', default=False,
        help='Enable debug logging',
    )
    return parser


def main() -> int:
    parser = get_parser()
    args = parser.parse_args()

    # Validation: exactly one of --rest-only / --glm-dir must be set.
    if args.rest_only and args.glm_dir:
        parser.error(
            "--rest-only and --glm-dir are mutually exclusive; pick one."
        )
    if not args.rest_only and not args.glm_dir:
        parser.error(
            "must supply either --rest-only or --glm-dir (one is required)."
        )

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
        glm_dir=Path(args.glm_dir) if args.glm_dir else None,
        fmriprep_dir=Path(args.fmriprep_dir),
        output_dir=Path(args.output_dir),
        residuals_space=args.residuals_space,
        rest_fmriprep_dir=rest_fmriprep_dir,
        sessions=sessions,
        rest_only=args.rest_only,
    )

    if errors > 0:
        logger.warning('Completed with %d errors', errors)
        return 1

    logger.info('Completed successfully')
    return 0


if __name__ == '__main__':
    sys.exit(main())
