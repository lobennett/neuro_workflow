"""Drive per-instance prevalence over the 8 main task/contrast cells.

For each (cohort, task, contrast, instance_idx) cell, calls
``neuro_workflow.analysis.prevalence.run.main`` with ``--instance N``.
Subjects without an N-th session for the task drop out of that cell's
cohort silently. Each call writes a GIFTI bundle + manifest to
``{output_root}/{cohort}/``.

Usage:
  uv run python scripts/prevalence_by_instance_run.py \\
      --discovery-lev1 /scratch/users/logben/discovery_bids/derivatives/lev1_surface \\
      --validation-lev1 /scratch/users/logben/validation_bids/derivatives/lev1_surface \\
      --output-root /scratch/users/logben/prevalence_by_instance \\
      --max-instance 6
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from neuro_workflow.analysis.prevalence.run import main as run_prevalence_main

logger = logging.getLogger(__name__)


# (task, contrast) pairs matching the formal /derivatives/prevalence outputs.
MAIN_CELLS = [
    ('cuedTS',             'task_switch_cost'),
    ('directedForgetting', 'neg-con'),
    ('flanker',            'incongruent-congruent'),
    ('goNogo',             'nogo_success-go'),
    ('nBack',              'twoBack-oneBack'),
    ('shapeMatching',      'main_vars'),
    ('spatialTS',          'task_switch_cost'),
    ('stopSignal',         'stop_success-go'),
]


def run_one_cell(
    lev1_root: Path, cohort: str, task: str, contrast: str,
    instance_idx: int, output_dir: Path,
) -> int:
    argv = [
        '--lev1-root', str(lev1_root),
        '--task', task,
        '--contrast', contrast,
        '--output-dir', str(output_dir),
        '--cohort', cohort,
        '--instance', str(instance_idx),
        '--directional',
    ]
    logger.info(
        '── cell: cohort=%s task=%s contrast=%s instance=%d',
        cohort, task, contrast, instance_idx,
    )
    return run_prevalence_main(argv)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discovery-lev1', type=Path, default=None,
                   help='lev1_surface root for discovery (omit to skip).')
    p.add_argument('--validation-lev1', type=Path, default=None,
                   help='lev1_surface root for validation (omit to skip).')
    p.add_argument('--output-root', type=Path, required=True,
                   help='Output root; per-cohort subdirs will be created.')
    p.add_argument('--max-instance', type=int, default=6,
                   help='Highest instance index to attempt (default 6). '
                        'Cells with no subjects at instance N are skipped.')
    p.add_argument('--cells', nargs='*', default=None,
                   help='Optional subset of cells as TASK:CONTRAST tokens. '
                        'When omitted, runs the 8 main cells.')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.INFO,
    )

    if args.cells:
        cells = []
        for tok in args.cells:
            task, _, contrast = tok.partition(':')
            if not contrast:
                raise SystemExit(f'--cells token must be TASK:CONTRAST; got {tok!r}')
            cells.append((task, contrast))
    else:
        cells = MAIN_CELLS

    cohorts: list[tuple[str, Path]] = []
    if args.discovery_lev1 is not None:
        cohorts.append(('discovery', args.discovery_lev1))
    if args.validation_lev1 is not None:
        cohorts.append(('validation', args.validation_lev1))
    if not cohorts:
        raise SystemExit('Provide at least one of --discovery-lev1 / --validation-lev1.')

    total = 0
    skipped = 0
    for cohort, lev1_root in cohorts:
        out_dir = args.output_root / cohort
        out_dir.mkdir(parents=True, exist_ok=True)
        for task, contrast in cells:
            for inst in range(1, args.max_instance + 1):
                try:
                    rc = run_one_cell(lev1_root, cohort, task, contrast, inst, out_dir)
                except SystemExit as e:
                    # run_prevalence_main raises SystemExit when there are <2
                    # subjects (Bayesian prevalence undefined). Treat as skip.
                    logger.warning('  skipped (SystemExit %s)', e)
                    skipped += 1
                    continue
                except ValueError as e:
                    logger.warning('  skipped (ValueError: %s)', e)
                    skipped += 1
                    continue
                if rc != 0:
                    logger.warning('  cell returned rc=%s', rc)
                total += 1

    logger.info('Done: %d cells succeeded, %d skipped.', total, skipped)
    return 0


if __name__ == '__main__':
    sys.exit(main())
