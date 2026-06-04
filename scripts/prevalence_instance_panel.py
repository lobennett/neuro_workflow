"""Panels conveying the per-instance prevalence trend.

Two complementary figures, both designed to show that the single-session
task signal is *weak across all session instances* rather than strong early
and washed out later:

1. ``instance_trend_lines.png`` — ROI-mean overall-prevalence vs session
   instance, one line per task/contrast, validation (solid) + discovery
   (dashed). Shared 0–1 prevalence y-axis so the reader sees absolute level,
   not just relative shape: most contrasts sit low and flat. An Ince-2021
   "credible" reference band (γ ≥ 0.5) is shaded.

2. ``{cohort}_instance_surface_grid.png`` — a contrast × instance grid of
   left-hemisphere lateral surfaces (overall prevalence MAP), all on a single
   fixed 0→1 colorbar. Weak cells render dark across every column; a row that
   were strong-then-washed-out would brighten on the left and darken to the
   right. Flat dark rows = uniformly weak.

Usage:
  uv run python scripts/prevalence_instance_panel.py \\
      --inst-root /scratch/users/logben/prevalence_by_instance \\
      --trend-tsv /scratch/users/logben/prevalence_by_instance/instance_trend_summary.tsv \\
      --out-dir   /scratch/users/logben/prevalence_by_instance/panels
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from neuro_workflow.analysis.prevalence.aggregate import MAIN_CELLS as CELLS
from neuro_workflow.analysis.prevalence.visualize import _fetch_fsaverage6

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

MAX_INSTANCE = 5  # instance-6 has n=2-3 subjects; excluded as unreliable.


# ---------------------------------------------------------------------------
# Figure 1: ROI-mean trend lines
# ---------------------------------------------------------------------------


def plot_trend_lines(trend_tsv: Path, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # cohort -> (task, contrast) -> {instance: roi_mean}
    data: dict[str, dict[tuple, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    ns: dict[str, dict[tuple, dict[int, int]]] = defaultdict(lambda: defaultdict(dict))
    with trend_tsv.open() as fh:
        for row in csv.DictReader(fh, delimiter='\t'):
            inst = int(row['instance'])
            if inst > MAX_INSTANCE:
                continue
            key = (row['task'], row['contrast'])
            data[row['cohort']][key][inst] = float(row['roi_mean_prevalence'])
            ns[row['cohort']][key][inst] = int(row['n_subjects'] or 0)

    cmap = plt.get_cmap('tab10')
    colors = {cell: cmap(i % 10) for i, cell in enumerate(CELLS)}

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, cohort in zip(axes, ('validation', 'discovery')):
        for cell in CELLS:
            pts = sorted(data[cohort].get(cell, {}).items())
            if not pts:
                continue
            xs = [i for i, _ in pts]
            ys = [v for _, v in pts]
            label = f'{cell[0]} {cell[1]}'
            ax.plot(xs, ys, marker='o', color=colors[cell], label=label, linewidth=1.8)
        # Ince credible band
        ax.axhspan(0.5, 1.0, color='green', alpha=0.06)
        ax.text(0.98, 0.52, 'γ ≥ 0.5 (majority-prevalent)', transform=ax.get_yaxis_transform(),
                ha='right', va='bottom', fontsize=8, color='green')
        ax.set_title(f'{cohort}  (ROI = top-decile of '
                     f'{"fixed-effects" if cohort == "validation" else "self"} prevalence)',
                     fontsize=11)
        ax.set_xlabel('session instance (1 = subject\'s first session of the task)')
        ax.set_xticks(range(1, MAX_INSTANCE + 1))
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel('mean overall-prevalence (MAP γ) in signal ROI')
    axes[1].legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8, frameon=False)
    fig.suptitle('Per-instance task-signal prevalence: low and flat across sessions '
                 '(no early-then-washed-out pattern)', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    logger.info('Wrote %s', out_path)
    return out_path


# ---------------------------------------------------------------------------
# Figure 2: contrast × instance surface grid
# ---------------------------------------------------------------------------


def _overall_map(inst_root: Path, cohort: str, task: str, contrast: str,
                 inst: int, hemi: str) -> np.ndarray | None:
    from neuro_workflow.analysis.prevalence.aggregate import load_gifti_data
    p = (inst_root / cohort /
         f'{cohort}_task-{task}_instance-{inst}_hemi-{hemi}_contrast-{contrast}'
         f'_rtmodel-RTDur_direction-overall_stat-prevalence-map.func.gii')
    return load_gifti_data(p) if p.exists() else None


def _n_subjects(inst_root: Path, cohort: str, task: str, contrast: str, inst: int):
    man = (inst_root / cohort /
           f'{cohort}_task-{task}_instance-{inst}_contrast-{contrast}_manifest.json')
    if not man.exists():
        return None
    d = json.loads(man.read_text())
    return d.get('L', d.get('R', {})).get('n_subjects')


def plot_surface_grid(inst_root: Path, cohort: str, out_path: Path,
                      hemi: str = 'L', views: tuple[str, ...] = ('lateral', 'medial')) -> Path:
    """Grid of L-hemi prevalence surfaces, contrast (rows) × instance (cols).

    Each contrast occupies ``len(views)`` adjacent sub-rows (lateral then
    medial by default) so medial-wall activation (medial frontal, precuneus,
    cingulate — relevant to nBack / cuedTS / spatialTS) is visible alongside
    lateral cortex. Fixed 0–1 colorbar; instances stay as columns so the
    across-session trend reads left-to-right within each sub-row.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    from nilearn import plotting

    fsav = _fetch_fsaverage6()
    mesh_key = f'infl_{"left" if hemi == "L" else "right"}'
    bg_key = f'sulc_{"left" if hemi == "L" else "right"}'
    nviews = len(views)

    nrows, ncols = len(CELLS) * nviews, MAX_INSTANCE
    fig, axes = plt.subplots(nrows, ncols, figsize=(2.6 * ncols, 2.2 * nrows),
                             subplot_kw={'projection': '3d'},
                             gridspec_kw={'hspace': 0.02, 'wspace': 0.0})
    vmin, vmax = 0.0, 1.0
    for ci, (task, contrast) in enumerate(CELLS):
        for vi, view in enumerate(views):
            r = ci * nviews + vi
            for c in range(ncols):
                inst = c + 1
                ax = axes[r, c]
                arr = _overall_map(inst_root, cohort, task, contrast, inst, hemi)
                if arr is None:
                    ax.set_axis_off()
                    continue
                plotting.plot_surf_stat_map(
                    surf_mesh=fsav[mesh_key], stat_map=arr, bg_map=fsav[bg_key],
                    hemi='left' if hemi == 'L' else 'right', view=view,
                    cmap='inferno', vmin=vmin, vmax=vmax, colorbar=False,
                    symmetric_cbar=False, bg_on_data=True, axes=ax, figure=fig,
                )
                if r == 0:
                    n = _n_subjects(inst_root, cohort, task, contrast, inst)
                    ax.set_title(f'instance {inst}\n(n={n})', fontsize=9)
            # contrast label on the first sub-row of the pair; view tag on each
            if vi == 0:
                axes[r, 0].text2D(-0.06, 0.0, f'{task}\n{contrast}',
                                  transform=axes[r, 0].transAxes,
                                  rotation=90, va='center', ha='right',
                                  fontsize=8, fontweight='bold')
            axes[r, 0].text2D(-0.01, 0.5, view[:3], transform=axes[r, 0].transAxes,
                              rotation=90, va='center', ha='right', fontsize=6.5,
                              color='#555')

    # Shared colorbar
    sm = ScalarMappable(norm=Normalize(vmin=vmin, vmax=vmax), cmap='inferno')
    cbar = fig.colorbar(sm, ax=axes, fraction=0.012, pad=0.01)
    cbar.set_label('overall prevalence (MAP γ)', fontsize=10)
    fig.suptitle(
        f'{cohort}: per-instance overall prevalence — {hemi} hemisphere, '
        f'{" + ".join(views)} views\n'
        f'(fixed 0–1 colorbar; dark across all instances = uniformly weak signal)',
        fontsize=13, y=0.995)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    logger.info('Wrote %s', out_path)
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inst-root', type=Path,
                    default=Path('/scratch/users/logben/prevalence_by_instance'))
    ap.add_argument('--trend-tsv', type=Path, default=None)
    ap.add_argument('--out-dir', type=Path, default=None)
    ap.add_argument('--cohorts', nargs='+', default=['validation', 'discovery'])
    ap.add_argument('--views', nargs='+', default=['lateral', 'medial'],
                    choices=['lateral', 'medial'],
                    help='Surface views stacked per contrast row (default: both).')
    ap.add_argument('--skip-trend-lines', action='store_true',
                    help='Skip re-rendering the (view-independent) line plot.')
    args = ap.parse_args(argv)

    out_dir = args.out_dir or (args.inst_root / 'panels')
    trend_tsv = args.trend_tsv or (args.inst_root / 'instance_trend_summary.tsv')

    if not args.skip_trend_lines:
        plot_trend_lines(trend_tsv, out_dir / 'instance_trend_lines.png')
    for cohort in args.cohorts:
        plot_surface_grid(args.inst_root, cohort,
                          out_dir / f'{cohort}_instance_surface_grid.png',
                          views=tuple(args.views))
    logger.info('Panels written to %s', out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
