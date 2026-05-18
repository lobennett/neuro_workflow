"""CLI: render prevalence GIFTIs to PNG + interactive HTML.

Usage example
-------------

  uv run python -m neuro_workflow.analysis.prevalence.viz_run \\
      --prevalence-dir /scratch/.../derivatives/prevalence \\
      --cohort validation \\
      --task flanker \\
      --contrast incongruent-congruent \\
      --output-dir /scratch/.../derivatives/prevalence/figures \\
      --hpdi-threshold 0.2 \\
      --interactive

Produces (in ``--output-dir``)::

    <cohort>_task-<task>_contrast-<contrast>_map.png
    <cohort>_task-<task>_contrast-<contrast>_thresholded-hpdiLo-<thr>.png  (if --hpdi-threshold)
    <cohort>_task-<task>_contrast-<contrast>_hemi-L_interactive.html       (if --interactive)
    <cohort>_task-<task>_contrast-<contrast>_hemi-R_interactive.html       (if --interactive)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from neuro_workflow.analysis.prevalence.visualize import (
    interactive_view,
    load_prevalence_outputs,
    plot_prevalence_surface,
)

logger = logging.getLogger(__name__)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            'Render per-vertex Bayesian prevalence maps onto the '
            'fsaverage6 inflated surface (4-panel PNG; optional '
            'interactive HTML).'
        ),
    )
    p.add_argument('--prevalence-dir', required=True, type=Path,
                   help='Directory containing the prevalence GIFTIs '
                        '(output of neuro_workflow.analysis.prevalence.run).')
    p.add_argument('--cohort', required=True,
                   help='Cohort tag used in the GIFTI filenames.')
    p.add_argument('--task', required=True, help='Task name (no task- prefix).')
    p.add_argument('--contrast', required=True,
                   help='Contrast name as it appears in filenames, e.g. incongruent-congruent.')
    p.add_argument('--rtmodel', default='RTDur',
                   help='RT model tag (default: RTDur).')
    p.add_argument('--output-dir', required=True, type=Path,
                   help='Where to write the PNG / HTML outputs.')
    p.add_argument('--hpdi-threshold', type=float, default=None,
                   help='If given, also produce a thresholded PNG where '
                        'vertices with HPDI_lo <= threshold are blanked.')
    p.add_argument('--cmap', default='inferno',
                   help='Matplotlib colormap (default: inferno).')
    p.add_argument('--vmax', type=float, default=None,
                   help='Colormap max (default: 95th percentile of finite data).')
    p.add_argument('--surf-type', default='inflated',
                   choices=('inflated', 'pial', 'white'),
                   help='Surface type (default: inflated).')
    p.add_argument('--interactive', action='store_true', default=False,
                   help='Also write one HTML view per hemisphere.')
    p.add_argument('--dpi', type=int, default=150,
                   help='PNG resolution (default: 150).')
    p.add_argument('--verbose', action='store_true', default=False)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        'Loading prevalence outputs from %s (cohort=%s task=%s contrast=%s)',
        args.prevalence_dir, args.cohort, args.task, args.contrast,
    )
    arrays = load_prevalence_outputs(
        prevalence_dir=args.prevalence_dir,
        cohort=args.cohort, task=args.task,
        contrast=args.contrast, rtmodel=args.rtmodel,
    )

    n_L, n_R = arrays['map_L'].shape[0], arrays['map_R'].shape[0]
    logger.info('Loaded %d / %d vertices for L / R hemispheres', n_L, n_R)

    title_base = (
        f'Prevalence MAP — {args.cohort} — task-{args.task} '
        f'contrast-{args.contrast}'
    )

    # Always: unthresholded MAP.
    out_map = args.output_dir / (
        f'{args.cohort}_task-{args.task}_contrast-{args.contrast}_map.png'
    )
    plot_prevalence_surface(
        map_left=arrays['map_L'],
        map_right=arrays['map_R'],
        output_path=out_map,
        cmap=args.cmap,
        vmax=args.vmax,
        surf_type=args.surf_type,
        title=title_base,
        dpi=args.dpi,
    )

    # Optional: threshold by HPDI lower bound.
    if args.hpdi_threshold is not None:
        out_thr = args.output_dir / (
            f'{args.cohort}_task-{args.task}_contrast-{args.contrast}'
            f'_thresholded-hpdiLo-{args.hpdi_threshold:.2f}.png'
        )
        plot_prevalence_surface(
            map_left=arrays['map_L'],
            map_right=arrays['map_R'],
            output_path=out_thr,
            hpdi_lo_left=arrays['hpdi_lo_L'],
            hpdi_lo_right=arrays['hpdi_lo_R'],
            hpdi_threshold=args.hpdi_threshold,
            cmap=args.cmap,
            vmax=args.vmax,
            surf_type=args.surf_type,
            title=f'{title_base}  (HPDI_lo > {args.hpdi_threshold:.2f})',
            dpi=args.dpi,
        )

    # Optional: interactive HTML widgets.
    if args.interactive:
        for hemi in ('L', 'R'):
            out_html = args.output_dir / (
                f'{args.cohort}_task-{args.task}_contrast-{args.contrast}'
                f'_hemi-{hemi}_interactive.html'
            )
            interactive_view(
                map_data=arrays[f'map_{hemi}'],
                output_path=out_html,
                hemi=hemi,
                cmap=args.cmap,
                vmax=args.vmax,
                surf_type=args.surf_type,
                title=f'{title_base}  hemi-{hemi}',
            )

    logger.info('Done. Outputs in %s', args.output_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
