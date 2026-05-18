"""CLI: derive per-subject FWER-corrected z-thresholds via sign-flip permutation.

For each subject, draws ``--n-permutations`` sign-flips of the run-level
β estimates, computes the FFX z-map under each permutation, and records
the max |z| across all valid vertices (both hemispheres pooled).  The
(1 - α) quantile of that null distribution is the subject's FWER-
corrected z-threshold at level α — the "strong control" requirement the
Ince et al. 2021 framework needs.

The output is a TSV with one row per subject:

    subject  n_runs  z_threshold  n_permutations  alpha  ...

Feed this TSV to ``prevalence.run`` via ``--subject-thresholds-tsv`` to
use per-subject thresholds when counting k per vertex.

Example
-------

  uv run python -m neuro_workflow.analysis.prevalence.permute_run \\
      --lev1-root /scratch/.../derivatives/lev1_surface \\
      --task flanker \\
      --contrast incongruent-congruent \\
      --output-tsv .../prevalence/validation_task-flanker_contrast-incongruent-congruent_subject-thresholds.tsv \\
      --n-permutations 1000 \\
      --alpha 0.05 \\
      --base-seed 0
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import zlib
from pathlib import Path
from typing import Optional

import numpy as np

from neuro_workflow.analysis.prevalence.permutation import (
    compute_subject_threshold,
)

logger = logging.getLogger(__name__)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            'Derive per-subject FWER-corrected z-thresholds for Bayesian '
            'prevalence via sign-flip permutation on run-level beta '
            'estimates (Ince et al. 2021 strong-control prescription).'
        ),
    )
    p.add_argument('--lev1-root', required=True, type=Path,
                   help='lev1_surface root — contains sub-*/task-*/indiv_contrasts/.')
    p.add_argument('--task', required=True,
                   help='Task name, no task- prefix (e.g. flanker).')
    p.add_argument('--contrast', required=True,
                   help='Contrast name as in filenames (e.g. incongruent-congruent).')
    p.add_argument('--rtmodel', default='RTDur',
                   help='RT-model tag (default: RTDur).')
    p.add_argument('--n-permutations', type=int, default=1000,
                   help='Number of sign-flip permutations per subject (default: 1000).')
    p.add_argument('--alpha', type=float, default=0.05,
                   help='Within-subject FPR level (default: 0.05).')
    p.add_argument('--output-tsv', required=True, type=Path,
                   help='Where to write the per-subject thresholds TSV.')
    p.add_argument('--subjects-file', type=Path, default=None,
                   help='Optional file listing sub-X ids (one per line); '
                        'default is to discover all subjects with matching files.')
    p.add_argument('--base-seed', type=int, default=0,
                   help='Base seed mixed with the subject id (via adler32) '
                        'to derive each subject\'s RNG seed deterministically '
                        '(default: 0).')
    p.add_argument('--verbose', action='store_true', default=False)
    return p.parse_args(argv)


def _load_subjects_file(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        out.append(line if line.startswith('sub-') else f'sub-{line}')
    return out


def _discover_subjects(
    lev1_root: Path, task: str, contrast: str, rtmodel: str,
) -> list[str]:
    """Find every subject under lev1_root that has a usable indiv_contrasts
    set for this (task, contrast)."""
    pattern = (
        f'sub-*/task-{task}/indiv_contrasts/'
        f'sub-*_ses-*_task-{task}_run-*_hemi-L_'
        f'contrast-{contrast}_rtmodel-{rtmodel}_stat-effect-size.func.gii'
    )
    paths = lev1_root.glob(pattern)
    subjects = sorted({p.parent.parent.parent.name for p in paths})
    return subjects


def _per_subject_seed(base_seed: int, subject: str) -> int:
    """Derive a deterministic per-subject seed via adler32 (cross-process
    stable; Python's str hash is randomised per-process).
    """
    return base_seed ^ zlib.adler32(subject.encode('utf-8'))


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if args.subjects_file is not None:
        subjects = _load_subjects_file(args.subjects_file)
        logger.info('Restricting to %d subjects from %s', len(subjects), args.subjects_file)
    else:
        subjects = _discover_subjects(
            args.lev1_root, args.task, args.contrast, args.rtmodel,
        )
        logger.info('Discovered %d subjects under %s', len(subjects), args.lev1_root)

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        'subject', 'n_runs',
        'n_vertices_L', 'n_vertices_R',
        'n_vertices_valid_L', 'n_vertices_valid_R',
        'z_threshold', 'n_permutations', 'alpha',
        'null_p50', 'null_p95', 'null_p99', 'null_max',
    ]

    rows: list[dict] = []
    for subj in subjects:
        seed = _per_subject_seed(args.base_seed, subj)
        try:
            result = compute_subject_threshold(
                lev1_root=args.lev1_root,
                subject=subj,
                task=args.task,
                contrast=args.contrast,
                n_permutations=args.n_permutations,
                alpha=args.alpha,
                rtmodel=args.rtmodel,
                rng=np.random.default_rng(seed),
            )
        except (FileNotFoundError, ValueError) as exc:
            logger.warning('Skipping %s: %s', subj, exc)
            continue
        logger.info(
            '%s: n_runs=%d z_threshold=%.3f (p95=%.3f, p99=%.3f)',
            subj, result['n_runs'], result['z_threshold'],
            result['null_p95'], result['null_p99'],
        )
        rows.append(result)

    with args.output_tsv.open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info('Wrote %d rows to %s', len(rows), args.output_tsv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
