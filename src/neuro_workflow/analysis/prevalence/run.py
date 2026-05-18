"""CLI: compute Bayesian prevalence maps from cohort fixed-effects z-maps.

Usage example
-------------

  uv run python -m neuro_workflow.analysis.prevalence.run \\
      --lev1-root /scratch/users/logben/discovery_bids/derivatives/lev1_surface \\
      --task flanker \\
      --contrast incongruent-congruent \\
      --output-dir /scratch/users/logben/discovery_bids/derivatives/prevalence \\
      --cohort discovery

Produces (per hemisphere)::

    <cohort>_task-<task>_hemi-<L|R>_contrast-<contrast>_stat-prevalence-{map,hpdiLo,hpdiHi,kCount}.func.gii

with ``alpha=0.05``, ``z_threshold≈1.96`` two-sided, and ``HPDI level=0.96``
matching the Ince et al. 2021 defaults.

Each output file embeds the parameters (cohort size, alpha, z-threshold,
HPDI level, number of invalid vertices) in its metadata for downstream
provenance.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from neuro_workflow.analysis.prevalence.aggregate import (
    compute_prevalence,
    find_subject_zmaps,
    save_prevalence_gifti,
    stack_subject_zmaps,
)

logger = logging.getLogger(__name__)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Compute Bayesian prevalence maps from cohort fixed-effects z-maps '
        '(Ince et al. 2021, PMC8494477).',
    )
    p.add_argument('--lev1-root', required=True, type=Path,
                   help='lev1 surface output root (contains sub-X/task-X/fixed_effects/)')
    p.add_argument('--task', required=True,
                   help='Task name, e.g. flanker (no task- prefix)')
    p.add_argument('--contrast', required=True,
                   help='Contrast name as it appears in the output filename, e.g. incongruent-congruent')
    p.add_argument('--output-dir', required=True, type=Path,
                   help='Directory to write prevalence GIFTIs into')
    p.add_argument('--cohort', required=True,
                   help='Cohort tag used in output filenames (discovery, validation, …)')
    p.add_argument('--space', default='fsaverage6',
                   help='Surface space tag (default: fsaverage6)')
    p.add_argument('--alpha', type=float, default=0.05,
                   help='Within-subject NHST false-positive rate (default: 0.05)')
    p.add_argument('--z-threshold', type=float, default=None,
                   help='Optional explicit z critical value; overrides --alpha→z conversion. '
                        'Use to pass a FWER-corrected threshold from a permutation test.')
    p.add_argument('--two-sided', action=argparse.BooleanOptionalAction, default=True,
                   help='Use two-sided |z| > z_α test (default: True)')
    p.add_argument('--level', type=float, default=0.96,
                   help='HPDI mass level (default: 0.96)')
    p.add_argument('--subjects-file', type=Path, default=None,
                   help='Optional file listing sub-X ids to include (one per line). '
                        'When omitted, every subject in lev1-root with a matching contrast file is used.')
    p.add_argument('--subject-thresholds-tsv', type=Path, default=None,
                   help='Optional TSV from neuro_workflow.analysis.prevalence.permute_run '
                        'with one row per subject and a z_threshold column.  When '
                        'supplied, each subject\'s row is thresholded at its own '
                        'permutation-derived FWER-corrected z (Ince 2021 strong-control). '
                        'Overrides --alpha and --z-threshold.')
    p.add_argument('--hemispheres', nargs='+', default=['L', 'R'],
                   help='Which hemispheres to process (default: L R)')
    p.add_argument('--verbose', action='store_true', default=False,
                   help='Enable debug logging')
    return p.parse_args(argv)


def _load_subjects(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        out.append(line if line.startswith('sub-') else f'sub-{line}')
    return out


def _load_subject_thresholds(path: Path) -> dict[str, float]:
    """Read subject → z_threshold from a TSV produced by permute_run.py."""
    import csv
    out: dict[str, float] = {}
    with path.open() as fh:
        reader = csv.DictReader(fh, delimiter='\t')
        for row in reader:
            out[row['subject']] = float(row['z_threshold'])
    return out


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    subjects = _load_subjects(args.subjects_file)
    if subjects is not None:
        logger.info('Restricting to %d subjects from %s', len(subjects), args.subjects_file)

    subject_thresholds: dict[str, float] | None = None
    if args.subject_thresholds_tsv is not None:
        subject_thresholds = _load_subject_thresholds(args.subject_thresholds_tsv)
        logger.info(
            'Per-subject thresholds loaded for %d subjects from %s '
            '(min=%.3f median=%.3f max=%.3f)',
            len(subject_thresholds), args.subject_thresholds_tsv,
            min(subject_thresholds.values()),
            sorted(subject_thresholds.values())[len(subject_thresholds) // 2],
            max(subject_thresholds.values()),
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary_per_hemi: dict[str, dict] = {}

    for hemi in args.hemispheres:
        logger.info('Hemisphere %s', hemi)
        paths = find_subject_zmaps(
            lev1_root=args.lev1_root, task=args.task, contrast=args.contrast,
            hemisphere=hemi, space=args.space, subjects=subjects,
        )
        if not paths:
            logger.warning('No subject z-maps for hemi=%s task=%s contrast=%s. '
                           'Skipping.', hemi, args.task, args.contrast)
            continue
        logger.info('Found %d subject z-maps', len(paths))
        zmaps, subj_ids = stack_subject_zmaps(paths)
        logger.info('Stacked %d subjects × %d vertices', *zmaps.shape)

        # Per-subject threshold path: build a (n_subjects,) z_threshold
        # array from the TSV, in the same order as the stacked subjects.
        z_thr_arg: float | list[float] | None
        if subject_thresholds is not None:
            missing = [s for s in subj_ids if s not in subject_thresholds]
            if missing:
                raise SystemExit(
                    f'Subject thresholds TSV is missing rows for '
                    f'{len(missing)} subjects in the lev1 input: {missing[:5]}...'
                )
            z_thr_arg = [subject_thresholds[s] for s in subj_ids]
        else:
            z_thr_arg = args.z_threshold

        result = compute_prevalence(
            zmaps,
            alpha=args.alpha,
            z_threshold=z_thr_arg,
            two_sided=args.two_sided,
            level=args.level,
        )
        logger.info(
            'MAP prevalence min/median/max = %.3f / %.3f / %.3f; '
            'invalid vertices = %d',
            float(min(result.map[~_isnan(result.map)], default=0.0)),
            float(median_safe(result.map)),
            float(max(result.map[~_isnan(result.map)], default=0.0)),
            result.n_vertices_invalid,
        )

        base = (
            f'{args.cohort}_task-{args.task}_hemi-{hemi}'
            f'_contrast-{args.contrast}_rtmodel-RTDur'
        )
        files = save_prevalence_gifti(result, args.output_dir, base)
        for kind, path in files.items():
            logger.info('  %s → %s', kind, path)

        summary_per_hemi[hemi] = {
            'n_subjects': result.n_subjects,
            'alpha': result.alpha,
            'z_threshold': result.z_threshold,
            'level': result.level,
            'n_vertices_invalid': result.n_vertices_invalid,
            'subjects': subj_ids,
            'files': {k: str(v) for k, v in files.items()},
        }

    # Drop a manifest so downstream consumers (e.g. parcel-level summaries
    # against MSHBM dlabels) can find the maps + know exactly which
    # subjects contributed.
    manifest_path = args.output_dir / f'{args.cohort}_task-{args.task}_contrast-{args.contrast}_manifest.json'
    manifest_path.write_text(json.dumps(summary_per_hemi, indent=2))
    logger.info('Manifest written: %s', manifest_path)

    return 0


# ---------------------------------------------------------------------------
# Small NaN-safe helpers — keep dependencies minimal.
# ---------------------------------------------------------------------------


def _isnan(arr):
    import numpy as np
    return np.isnan(arr)


def median_safe(arr):
    import numpy as np
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return 0.0
    return float(np.median(finite))


if __name__ == '__main__':
    sys.exit(main())
