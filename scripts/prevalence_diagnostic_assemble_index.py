"""Assemble a single dashboard index.html from per-cell figures in figures/.

Reads the cell list from the figures directory by scanning for the
``<cohort>_<task>_<contrast>_prevalence_uncorrected.png`` filenames written
by ``prevalence_subject_diagnostic.py`` and rebuilds the master HTML that
references all of them.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


_PREV_RE = re.compile(
    r'^(?P<task>[A-Za-z0-9]+)_(?P<contrast>.+)_prevalence_uncorrected\.png$'
)
_SUBJ_RE = re.compile(
    r'^(?P<sub>sub-[A-Za-z0-9]+)_(?P<task>[A-Za-z0-9]+)_(?P<contrast>.+)\.png$'
)


_HTML_HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Diagnostic: uncorrected prevalence + per-subject z-maps (all 44)</title>
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
  .map-cell { display: flex; flex-direction: column; gap: 4px; }
  .rotate-btn { padding: 4px 10px; cursor: pointer; font-size: 12px;
                background: #06c; color: white; border: none;
                border-radius: 3px; align-self: flex-start; }
  .iframe-holder { display: flex; gap: 8px; margin-top: 8px; }
  .surf-frame { width: 480px; height: 380px; border: 1px solid #ccc; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.85);
              display: none; align-items: center; justify-content: center;
              z-index: 1000; cursor: zoom-out; }
  .modal-bg.show { display: flex; }
  .modal-bg img { max-width: 95vw; max-height: 95vh; }
  .meta { color: #666; font-size: 13px; margin-bottom: 16px; }
  .toc { columns: 4; -webkit-columns: 4; -moz-columns: 4; gap: 12px;
         padding: 12px; background: #f4f4f4; border-radius: 6px; }
  .toc a { display: block; font-size: 12px; padding: 1px 0; color: #06c; text-decoration: none; }
</style>
</head><body>
<h1>Diagnostic: per-subject + uncorrected-prevalence maps (all 44 cells)</h1>
<p class="meta">__META__</p>
<details><summary>Table of contents</summary>
<div class="toc">
__TOC__
</div>
</details>
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
    p.add_argument('--dashboard-dir', required=True, type=Path,
                   help='Dir containing figures/ subdir')
    args = p.parse_args(argv)

    fig_dir = args.dashboard_dir / 'figures'
    if not fig_dir.is_dir():
        print(f'No figures/ dir at {fig_dir}', file=sys.stderr)
        return 1

    # Find all cells via prevalence_uncorrected.png filenames
    cells = []
    for png in sorted(fig_dir.glob('*_prevalence_uncorrected.png')):
        m = _PREV_RE.match(png.name)
        if not m:
            continue
        cells.append((m.group('task'), m.group('contrast')))
    if not cells:
        print('No cells found via *_prevalence_uncorrected.png', file=sys.stderr)
        return 1

    print(f'Assembling index for {len(cells)} cells')

    # Per-cell subject map: cells → list of subject PNG paths
    subj_pngs_by_cell: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for png in sorted(fig_dir.glob('sub-*.png')):
        m = _SUBJ_RE.match(png.name)
        if not m:
            continue
        subj_pngs_by_cell[(m.group('task'), m.group('contrast'))].append(png)

    toc_items = []
    sections = []
    for task, contrast in cells:
        anchor = f'{task}__{contrast}'.replace('-', '_').replace(':', '_')
        prev_png = fig_dir / f'{task}_{contrast}_prevalence_uncorrected.png'
        dir_png = fig_dir / f'{task}_{contrast}_directionality_uncorrected.png'
        prev_int_l = fig_dir / f'{task}_{contrast}_prevalence_uncorrected_L.html'
        prev_int_r = fig_dir / f'{task}_{contrast}_prevalence_uncorrected_R.html'
        dir_int_l = fig_dir / f'{task}_{contrast}_directionality_uncorrected_L.html'
        dir_int_r = fig_dir / f'{task}_{contrast}_directionality_uncorrected_R.html'
        subj_pngs = sorted(subj_pngs_by_cell.get((task, contrast), []))

        def _rel(p):
            return p.relative_to(args.dashboard_dir).as_posix()

        section_html = (
            f'<h2 id="{anchor}">{task} / {contrast} '
            f'<small>(n_subj={len(subj_pngs)})</small></h2>\n'
            f'<h3>Uncorrected prevalence (z>1.96) + directionality</h3>\n'
            f'<div class="prev-row">'
            f'<div class="map-cell">'
            f'<img src="{_rel(prev_png)}">'
            f'<button class="rotate-btn" '
            f'data-l="{_rel(prev_int_l)}" data-r="{_rel(prev_int_r)}">'
            f'rotate</button>'
            f'<div class="iframe-holder" hidden></div>'
            f'</div>'
            f'<div class="map-cell">'
            f'<img src="{_rel(dir_png)}">'
            f'<button class="rotate-btn" '
            f'data-l="{_rel(dir_int_l)}" data-r="{_rel(dir_int_r)}">'
            f'rotate</button>'
            f'<div class="iframe-holder" hidden></div>'
            f'</div>'
            f'</div>\n'
            f'<h3>Per-subject unthresholded z-maps</h3>\n'
            '<div class="subj-grid">'
            + '\n'.join(
                f'<img src="{_rel(p)}">'
                for p in subj_pngs
            )
            + '</div>'
        )
        sections.append(section_html)
        toc_items.append(f'<a href="#{anchor}">{task} / {contrast}</a>')

    meta = (
        f'Cells: {len(cells)} (each shown with uncorrected Bayesian γ, '
        f'directionality, and per-subject z-map grid)'
    )
    html = (_HTML_HEAD
            .replace('__META__', meta)
            .replace('__TOC__', '\n'.join(toc_items))
            .replace('__BODY__', '\n'.join(sections)))
    out_html = args.dashboard_dir / 'index.html'
    out_html.write_text(html)
    print(f'Wrote: {out_html} ({out_html.stat().st_size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
