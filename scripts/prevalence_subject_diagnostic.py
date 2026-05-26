"""Diagnostic dashboard: per-subject z-maps + uncorrected prevalence.

For each of N target task-contrast cells, render:
  1. Uncorrected Bayesian prevalence map (single brain, 2-panel L+R lateral)
  2. Per-subject z-map montage (46 subjects in a grid, tiny brains)

Goal: visually inspect whether contrasts that fail FDR-corrected prevalence
have *any* across-subject consistency, or just no signal at all.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from multiprocessing import Pool
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np

from neuro_workflow.analysis.prevalence.aggregate import (
    find_subject_zmaps, load_gifti_data,
)
from neuro_workflow.analysis.prevalence.visualize import _fetch_fsaverage6

logger = logging.getLogger(__name__)


def _plot_4panel(map_l, map_r, out_path, *, cmap, vmin, vmax, title, fsaverage,
                 figsize=(8, 7), dpi=80, symmetric=False):
    """4-panel (L-lat, R-lat, L-med, R-med) brain figure with one colorbar."""
    from nilearn import plotting
    fig, axes = plt.subplots(
        2, 2, figsize=figsize,
        subplot_kw={'projection': '3d'},
        gridspec_kw={'wspace': 0.0, 'hspace': 0.0},
    )
    panels = (
        (axes[0, 0], 'left',  'lateral', map_l, 'infl_left',  'sulc_left',  False),
        (axes[0, 1], 'right', 'lateral', map_r, 'infl_right', 'sulc_right', False),
        (axes[1, 0], 'left',  'medial',  map_l, 'infl_left',  'sulc_left',  False),
        (axes[1, 1], 'right', 'medial',  map_r, 'infl_right', 'sulc_right', True),
    )
    for ax, hemi, view, stat_map, mesh_key, bg_key, show_cbar in panels:
        plotting.plot_surf_stat_map(
            surf_mesh=fsaverage[mesh_key], stat_map=stat_map,
            bg_map=fsaverage[bg_key], hemi=hemi, view=view,
            cmap=cmap, vmin=vmin, vmax=vmax,
            colorbar=show_cbar,
            symmetric_cbar=symmetric,
            bg_on_data=True, axes=ax, figure=fig,
        )
    if title:
        fig.suptitle(title, fontsize=9, y=0.97)
    fig.savefig(out_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out_path


def _render_interactive_viewer(stat_map, hemi, out_path, *, cmap, vmax,
                                symmetric, title, fsaverage):
    """Single-hemisphere rotatable WebGL viewer (nilearn view_surf)."""
    from nilearn import plotting
    mesh_key = f'infl_{hemi}'
    bg_key = f'sulc_{hemi}'
    view = plotting.view_surf(
        surf_mesh=fsaverage[mesh_key],
        surf_map=stat_map,
        bg_map=fsaverage[bg_key],
        cmap=cmap,
        symmetric_cmap=symmetric,
        threshold=None,
        vmax=vmax,
        title=title,
        black_bg=False,
    )
    view.save_as_html(str(out_path))
    return out_path


_SUBJECT_RE = re.compile(r'(sub-[a-zA-Z0-9]+)')


def _render_one_subject(args_tuple):
    """Top-level worker for multiprocessing.

    Emits the static 4-panel PNG AND two single-hemi WebGL viewers so the
    dashboard can open each subject's z-map in the modal overlay on click.
    """
    z_path_l, z_path_r, sub_id, out_path, vmax = args_tuple
    fsav = _fetch_fsaverage6()
    z_l = load_gifti_data(z_path_l)
    z_r = load_gifti_data(z_path_r)
    _plot_4panel(
        z_l, z_r, out_path,
        cmap='RdBu_r', vmin=-vmax, vmax=vmax,
        title=sub_id, fsaverage=fsav,
        figsize=(5, 4.5), dpi=150, symmetric=True,
    )
    for z_arr, hemi in ((z_l, 'left'), (z_r, 'right')):
        _render_interactive_viewer(
            z_arr, hemi,
            out_path.with_name(f'{out_path.stem}_{hemi[0].upper()}.html'),
            cmap='RdBu_r', vmax=vmax, symmetric=True,
            title=f'{sub_id} {hemi[0].upper()}',
            fsaverage=fsav,
        )
    return sub_id


def render_subject_montage(
    lev1_root: Path, task: str, contrast: str, output_dir: Path,
    n_jobs: int = 2,
) -> list[Path]:
    """Render one PNG per subject for a single task-contrast."""
    paths_l = find_subject_zmaps(lev1_root, task, contrast, 'L')
    paths_r = find_subject_zmaps(lev1_root, task, contrast, 'R')
    if len(paths_l) != len(paths_r):
        raise ValueError(f'L/R count mismatch for {task}/{contrast}')

    output_dir.mkdir(parents=True, exist_ok=True)
    # Compute global vmax (95th pctile across all subjects + both hemis)
    # for consistent color scale within a task-contrast.
    all_z = np.concatenate(
        [np.abs(load_gifti_data(p)) for p in paths_l + paths_r]
    )
    vmax = float(np.percentile(all_z[np.isfinite(all_z)], 95))
    logger.info('vmax for %s/%s = %.2f', task, contrast, vmax)

    work = []
    for p_l, p_r in zip(paths_l, paths_r):
        m = _SUBJECT_RE.search(p_l.name)
        sub_id = m.group(1)
        out_png = output_dir / f'{sub_id}_{task}_{contrast}.png'
        work.append((p_l, p_r, sub_id, out_png, vmax))

    logger.info('Rendering %d subject z-maps for %s/%s', len(work), task, contrast)
    with Pool(processes=n_jobs) as pool:
        for sub_id in pool.imap_unordered(_render_one_subject, work):
            logger.info('  done %s', sub_id)
    return [w[3] for w in work]


def render_prevalence_map(prev_dir: Path, task: str, contrast: str,
                          output_dir: Path, cohort: str = 'pooled46') -> Path:
    """Render uncorrected prevalence + directionality maps for one cell.

    Emits 4-panel static PNGs (lateral + medial, both hemis) AND four
    single-hemi WebGL viewers (prevalence L/R, directionality L/R) so the
    assemble step can lazy-load them as rotatable iframes.
    """
    fsav = _fetch_fsaverage6()
    base = f'{cohort}_task-{task}_hemi-X_contrast-{contrast}_rtmodel-RTDur'

    # ---- Overall prevalence ----
    map_l = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-L")}_direction-overall_stat-prevalence-map.func.gii')
    map_r = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-R")}_direction-overall_stat-prevalence-map.func.gii')
    prev_png = output_dir / f'{task}_{contrast}_prevalence_uncorrected.png'
    _plot_4panel(
        map_l, map_r, prev_png,
        cmap='inferno', vmin=0.0, vmax=None,
        title=f'{task} / {contrast} — UNCORRECTED prevalence (z>1.96)',
        fsaverage=fsav, figsize=(8, 7), dpi=100,
    )
    # Cell-specific vmax for interactive viewer (so it matches the static color scale)
    prev_concat = np.concatenate([map_l, map_r])
    prev_concat = prev_concat[np.isfinite(prev_concat)]
    prev_vmax = float(np.nanmax(prev_concat)) if prev_concat.size else 1.0
    for hemi_arr, hemi in ((map_l, 'left'), (map_r, 'right')):
        _render_interactive_viewer(
            hemi_arr, hemi,
            output_dir / f'{task}_{contrast}_prevalence_uncorrected_{hemi[0].upper()}.html',
            cmap='inferno', vmax=prev_vmax, symmetric=False,
            title=f'{hemi[0].upper()} hemi',
            fsaverage=fsav,
        )

    # ---- Directionality (signed) ----
    dir_l = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-L")}_stat-directionality.func.gii')
    dir_r = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-R")}_stat-directionality.func.gii')
    dir_path = output_dir / f'{task}_{contrast}_directionality_uncorrected.png'
    _plot_4panel(
        dir_l, dir_r, dir_path,
        cmap='RdBu_r', vmin=-1.0, vmax=1.0,
        title=f'{task} / {contrast} — directionality (signed, uncorrected)',
        fsaverage=fsav, figsize=(8, 7), dpi=100, symmetric=True,
    )
    for hemi_arr, hemi in ((dir_l, 'left'), (dir_r, 'right')):
        _render_interactive_viewer(
            hemi_arr, hemi,
            output_dir / f'{task}_{contrast}_directionality_uncorrected_{hemi[0].upper()}.html',
            cmap='RdBu_r', vmax=1.0, symmetric=True,
            title=f'{hemi[0].upper()} hemi',
            fsaverage=fsav,
        )

    return prev_png


_HTML_HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Diagnostic: uncorrected prevalence + per-subject z-maps</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; max-width: 1400px; }
  h1 { margin-top: 0; }
  h2 { border-bottom: 2px solid #888; padding-bottom: 6px; margin-top: 32px; }
  .prev-row { display: flex; gap: 16px; margin: 12px 0; flex-wrap: wrap; }
  .prev-row img { max-width: 640px; height: auto; border: 1px solid #ccc; }
  .subj-grid { display: grid; grid-template-columns: repeat(6, 1fr);
               gap: 6px; margin: 8px 0; }
  .subj-grid img { width: 100%; border: 1px solid #ddd; cursor: zoom-in; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.85);
              display: none; align-items: center; justify-content: center;
              z-index: 1000; cursor: zoom-out; }
  .modal-bg.show { display: flex; }
  .modal-bg img { max-width: 95vw; max-height: 95vh; }
  .meta { color: #666; font-size: 13px; margin-bottom: 16px; }
</style>
</head><body>
<h1>Diagnostic: per-subject + uncorrected-prevalence maps</h1>
<p class="meta">__META__</p>
__BODY__
<div id="modal" class="modal-bg" onclick="this.classList.remove('show')"><img id="modal-img"></div>
<script>
document.querySelectorAll('img').forEach(img => {
  img.addEventListener('click', () => {
    document.getElementById('modal-img').src = img.src;
    document.getElementById('modal').classList.add('show');
  });
});
</script>
</body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lev1-root', required=True, type=Path)
    p.add_argument('--prev-dir', required=True, type=Path,
                   help='Dir containing uncorrected prevalence outputs')
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--cells', nargs='+', required=True,
                   help='task:contrast pairs, e.g. flanker:incongruent-congruent')
    p.add_argument('--cohort', default='pooled46')
    p.add_argument('--n-jobs', type=int, default=2)
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    fig_dir = args.output_dir / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)
    _fetch_fsaverage6()  # warm cache

    sections = []
    for cell in args.cells:
        task, contrast = cell.split(':', 1)
        logger.info('=== %s / %s ===', task, contrast)
        # Prevalence maps (uncorrected overall + directionality)
        prev_png = render_prevalence_map(
            args.prev_dir, task, contrast, fig_dir, cohort=args.cohort,
        )
        dir_png = fig_dir / f'{task}_{contrast}_directionality_uncorrected.png'
        # Per-subject montage
        subj_pngs = render_subject_montage(
            args.lev1_root, task, contrast, fig_dir, n_jobs=args.n_jobs,
        )

        prev_rel = prev_png.relative_to(args.output_dir).as_posix()
        dir_rel = dir_png.relative_to(args.output_dir).as_posix()
        subj_rels = [p.relative_to(args.output_dir).as_posix() for p in subj_pngs]

        section_html = (
            f'<h2>{task} / {contrast}</h2>\n'
            f'<h3>Uncorrected prevalence (z>1.96) + directionality</h3>\n'
            f'<div class="prev-row">'
            f'<img src="{prev_rel}">'
            f'<img src="{dir_rel}">'
            f'</div>\n'
            f'<h3>Per-subject unthresholded z-maps (n=46, RdBu_r, symmetric)</h3>\n'
            '<div class="subj-grid">'
            + '\n'.join(f'<img src="{r}">' for r in subj_rels)
            + '</div>'
        )
        sections.append(section_html)

    meta = f'Source lev1: {args.lev1_root} • prevalence: {args.prev_dir} • cells: {len(args.cells)}'
    html = _HTML_HEAD.replace('__META__', meta).replace('__BODY__', '\n'.join(sections))
    out_html = args.output_dir / 'index.html'
    out_html.write_text(html)
    logger.info('Dashboard written: %s', out_html)
    return 0


if __name__ == '__main__':
    sys.exit(main())
