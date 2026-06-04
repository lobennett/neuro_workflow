"""Render a browseable dashboard for direction-resolved prevalence outputs.

For each (task, contrast) cell in a directional prevalence directory
(output of ``neuro_workflow.analysis.prevalence.run --directional``):

- Render four 4-panel PNGs (L-lateral, R-lateral, L-medial, R-medial,
  with a colorbar) per cell — one each for the overall, positive,
  negative, and consistency maps.
- Aggregate everything into ``index.html`` — a single filterable
  DataTables-style table with embedded PNG thumbnails linking through
  to full-size views.

Usage:
    uv run python scripts/prevalence_dashboard.py \\
        --prevalence-dir /scratch/.../prevalence_fdr_q05_directional_n46 \\
        --output-dir /scratch/.../prevalence_fdr_q05_directional_n46/dashboard
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from neuro_workflow.analysis.prevalence.aggregate import load_gifti_data
from neuro_workflow.analysis.prevalence.visualize import _fetch_fsaverage6


def _plot_compact_2panel(
    map_left: np.ndarray,
    map_right: np.ndarray,
    output_path: Path,
    *,
    cmap: str,
    vmin: float,
    vmax: Optional[float],
    title: Optional[str],
    fsaverage,
    dpi: int = 80,
) -> Path:
    """Render a 2-panel (L lateral, R lateral) PNG with one colorbar.

    Substantially faster than the 4-panel ``plot_prevalence_surface`` —
    each call to ``plot_surf_stat_map`` is the bottleneck, so cutting
    medial views halves the wall time.  Dashboard thumbnails don't need
    medial; users can drill through to the raw GIFTI for that.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from nilearn import plotting

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if vmax is None:
        finite = np.concatenate([
            map_left[np.isfinite(map_left)],
            map_right[np.isfinite(map_right)],
        ])
        vmax = float(np.percentile(finite, 95)) if finite.size else 1.0
        vmax = max(vmax, vmin + 1e-6)

    fig, axes = plt.subplots(
        1, 2, figsize=(8, 3.5),
        subplot_kw={'projection': '3d'},
        gridspec_kw={'wspace': 0.0},
    )
    for ax, hemi, stat_map, mesh_key, bg_key in (
        (axes[0], 'left',  map_left,  'infl_left',  'sulc_left'),
        (axes[1], 'right', map_right, 'infl_right', 'sulc_right'),
    ):
        plotting.plot_surf_stat_map(
            surf_mesh=fsaverage[mesh_key],
            stat_map=stat_map,
            bg_map=fsaverage[bg_key],
            hemi=hemi, view='lateral',
            cmap=cmap, vmin=vmin, vmax=vmax,
            colorbar=(hemi == 'right'),
            symmetric_cbar=(cmap == 'RdBu_r'),
            bg_on_data=True, axes=ax, figure=fig,
        )
    if title:
        fig.suptitle(title, fontsize=10, y=0.95)
    fig.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return output_path


plot_prevalence_surface = _plot_compact_2panel  # alias for the rest of the file

logger = logging.getLogger(__name__)


_MANIFEST_RE = re.compile(
    r'(?P<cohort>[^_]+)_task-(?P<task>[^_]+)_contrast-(?P<contrast>.+)_manifest\.json$'
)


def discover_cells(prevalence_dir: Path) -> list[dict]:
    """Find all (cohort, task, contrast) cells via manifest filenames."""
    cells = []
    for manifest in sorted(prevalence_dir.glob('*_manifest.json')):
        m = _MANIFEST_RE.match(manifest.name)
        if not m:
            continue
        with manifest.open() as fh:
            meta = json.load(fh)
        cells.append({
            'cohort':   m.group('cohort'),
            'task':     m.group('task'),
            'contrast': m.group('contrast'),
            'manifest': manifest,
            'meta':     meta,
        })
    return cells


def _load_hemi_pair(prev_dir: Path, base_tag: str, stat: str) -> tuple[np.ndarray, np.ndarray]:
    """Load L + R GIFTIs for a given (base_tag, stat) and return arrays."""
    paths = {
        h: prev_dir / f'{base_tag.replace("hemi-X", f"hemi-{h}")}_stat-{stat}.func.gii'
        for h in ('L', 'R')
    }
    return load_gifti_data(paths['L']), load_gifti_data(paths['R'])


def render_cell_pngs(
    prev_dir: Path,
    out_dir: Path,
    cell: dict,
    fsaverage,
    dpi: int = 80,
) -> dict[str, Path]:
    """Render PNGs for one cell.  ``dpi=80`` keeps thumbnails web-light.

    Returns dict mapping {direction_or_stat: png_path}.
    """
    cohort, task, contrast = cell['cohort'], cell['task'], cell['contrast']
    out_dir.mkdir(parents=True, exist_ok=True)
    pngs: dict[str, Path] = {}

    # Direction-resolved prevalence maps
    for direction in ('overall', 'pos', 'neg'):
        base_tag = (
            f'{cohort}_task-{task}_hemi-X_contrast-{contrast}'
            f'_rtmodel-RTDur_direction-{direction}'
        )
        map_l, map_r = _load_hemi_pair(prev_dir, base_tag, 'prevalence-map')
        png = out_dir / f'{cohort}_task-{task}_contrast-{contrast}_direction-{direction}.png'
        plot_prevalence_surface(
            map_left=map_l, map_right=map_r, output_path=png,
            cmap=('inferno' if direction != 'neg' else 'Blues'),
            vmin=0.0, vmax=None,
            title=f'{task} / {contrast} — direction={direction}',
            fsaverage=fsaverage, dpi=dpi,
        )
        pngs[direction] = png

    # Consistency map disabled in the dashboard (directionality below is
    # a strict superset — it conveys both magnitude AND sign of agreement).
    # Uncomment to restore.
    # base_tag = f'{cohort}_task-{task}_hemi-X_contrast-{contrast}_rtmodel-RTDur'
    # cons_l, cons_r = _load_hemi_pair(prev_dir, base_tag, 'consistency')
    # png = out_dir / f'{cohort}_task-{task}_contrast-{contrast}_consistency.png'
    # plot_prevalence_surface(
    #     map_left=cons_l, map_right=cons_r, output_path=png,
    #     cmap='viridis', vmin=0.5, vmax=1.0,
    #     title=f'{task} / {contrast} — directional consistency',
    #     fsaverage=fsaverage, dpi=dpi,
    # )
    # pngs['consistency'] = png

    # Directionality (signed proportion): +1 all positive, -1 all negative
    base_tag = f'{cohort}_task-{task}_hemi-X_contrast-{contrast}_rtmodel-RTDur'
    dir_l, dir_r = _load_hemi_pair(prev_dir, base_tag, 'directionality')
    png = out_dir / f'{cohort}_task-{task}_contrast-{contrast}_directionality.png'
    plot_prevalence_surface(
        map_left=dir_l, map_right=dir_r, output_path=png,
        cmap='RdBu_r', vmin=-1.0, vmax=1.0,
        title=f'{task} / {contrast} — directionality (+1 all pos, −1 all neg)',
        fsaverage=fsaverage, dpi=dpi,
    )
    pngs['directionality'] = png
    return pngs


_HTML_HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Directional prevalence dashboard</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         margin: 20px; }
  h1 { margin-top: 0; }
  .meta { color: #666; font-size: 13px; margin-bottom: 16px; }
  table.dataTable { border-collapse: collapse; }
  table.dataTable td { vertical-align: top; padding: 6px 8px; }
  img.thumb { width: 280px; height: auto; border: 1px solid #ddd;
              cursor: zoom-in; display: block; }
  img.thumb:hover { border-color: #555; }
  .cell-name { font-weight: 600; min-width: 220px; }
  .stat-summary { font-size: 12px; color: #555; max-width: 260px; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.85);
              display: none; align-items: center; justify-content: center;
              z-index: 1000; cursor: zoom-out; }
  .modal-bg.show { display: flex; }
  .modal-bg img { max-width: 95vw; max-height: 95vh; }
</style>
</head><body>
<h1>Directional prevalence dashboard</h1>
<div class="meta">__META__</div>
<table id="cells" class="display compact">
<thead>
<tr>
  <th>task</th><th>contrast</th>
  <th>overall (any direction)</th>
  <th>positive (z &gt; 0)</th>
  <th>negative (z &lt; 0)</th>
  <th>directionality (signed)</th>
  <th>stats</th>
</tr>
</thead>
<tbody>
__ROWS__
</tbody>
</table>
<div id="modal" class="modal-bg" onclick="this.classList.remove('show')"><img id="modal-img"></div>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<script>
$(document).ready(function(){
  $('#cells').DataTable({ paging: false, info: false, order: [[0,'asc'], [1,'asc']] });
  $('img.thumb').on('click', function(){
    $('#modal-img').attr('src', $(this).attr('src'));
    $('#modal').addClass('show');
  });
});
</script>
</body></html>"""


def _stat_summary(cell: dict) -> str:
    """Short text summary per cell from the manifest."""
    meta = cell['meta']
    if not meta:
        return ''
    h = next(iter(meta.values()))  # first hemi (L or R)
    return (
        f"n={h.get('n_subjects','?')}, "
        f"α={h.get('alpha','?')}, "
        f"q={h.get('fdr_q','?')}, "
        f"invalid={h.get('n_vertices_invalid','?')}"
    )


def build_index_html(
    cells: list[dict],
    pngs_by_cell: dict[tuple[str, str], dict[str, Path]],
    output_dir: Path,
    meta_line: str,
) -> Path:
    """Write the single index.html dashboard referencing all rendered PNGs."""
    rows = []
    for cell in cells:
        key = (cell['task'], cell['contrast'])
        pngs = pngs_by_cell.get(key, {})
        if not pngs:
            continue

        def img_cell(direction: str) -> str:
            png = pngs.get(direction)
            if png is None:
                return '<em>(missing)</em>'
            rel = png.relative_to(output_dir).as_posix()
            return f'<a href="{rel}" target="_blank"><img class="thumb" src="{rel}"></a>'

        rows.append(
            '<tr>'
            f'<td>{cell["task"]}</td>'
            f'<td class="cell-name">{cell["contrast"]}</td>'
            f'<td>{img_cell("overall")}</td>'
            f'<td>{img_cell("pos")}</td>'
            f'<td>{img_cell("neg")}</td>'
            f'<td>{img_cell("directionality")}</td>'
            f'<td class="stat-summary">{_stat_summary(cell)}</td>'
            '</tr>'
        )

    html = _HTML_HEAD.replace('__META__', meta_line).replace('__ROWS__', '\n'.join(rows))
    out = output_dir / 'index.html'
    out.write_text(html)
    return out


def _render_one_cell(args_tuple):
    """Top-level worker (must be picklable for multiprocessing.Pool)."""
    prev_dir, fig_dir, cell, dpi = args_tuple
    # Each worker fetches its own cached fsaverage6 (cheap; nilearn caches
    # to ~/nilearn_data so it's a hash check, not a re-download).
    fsav = _fetch_fsaverage6()
    try:
        pngs = render_cell_pngs(prev_dir=prev_dir, out_dir=fig_dir,
                                cell=cell, fsaverage=fsav, dpi=dpi)
        return (cell['task'], cell['contrast']), pngs, None
    except FileNotFoundError as e:
        return (cell['task'], cell['contrast']), {}, str(e)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prevalence-dir', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--n-jobs', type=int, default=2,
                   help='Parallel workers for PNG rendering (default 8).')
    p.add_argument('--dpi', type=int, default=80,
                   help='PNG resolution (default 80; thumbnails are web-light).')
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    cells = discover_cells(args.prevalence_dir)
    if not cells:
        logger.error('No prevalence cells found in %s', args.prevalence_dir)
        return 1
    logger.info('Found %d cells in %s (rendering with %d workers, dpi=%d)',
                len(cells), args.prevalence_dir, args.n_jobs, args.dpi)

    figures_dir = args.output_dir / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Pre-warm fsaverage6 cache in the main process so workers don't race
    # to download/cache it concurrently.
    _ = _fetch_fsaverage6()

    work = [
        (args.prevalence_dir, figures_dir, cell, args.dpi)
        for cell in cells
    ]
    pngs_by_cell: dict[tuple[str, str], dict[str, Path]] = {}
    from multiprocessing import Pool
    with Pool(processes=args.n_jobs) as pool:
        for i, (key, pngs, err) in enumerate(
            pool.imap_unordered(_render_one_cell, work, chunksize=1), 1,
        ):
            if err:
                logger.warning('[%d/%d] %s / %s — SKIPPED (%s)',
                               i, len(cells), key[0], key[1], err)
            else:
                logger.info('[%d/%d] %s / %s — %d PNGs',
                            i, len(cells), key[0], key[1], len(pngs))
                pngs_by_cell[key] = pngs

    meta_line = (
        f'Source: {args.prevalence_dir} • '
        f'Cells rendered: {len(pngs_by_cell)} / {len(cells)} • '
        f'Per cell: overall / positive / negative / consistency'
    )
    html_path = build_index_html(cells, pngs_by_cell, args.output_dir, meta_line)
    logger.info('Dashboard written: %s', html_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
