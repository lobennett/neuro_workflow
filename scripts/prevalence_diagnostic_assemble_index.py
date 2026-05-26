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
  .subj-grid img { width: 100%; border: 1px solid #ddd; cursor: pointer; }
  .map-cell { display: flex; flex-direction: column; gap: 4px; }
  .rotate-btn { padding: 4px 10px; cursor: pointer; font-size: 12px;
                background: #06c; color: white; border: none;
                border-radius: 3px; align-self: flex-start; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.85);
              display: none; align-items: center; justify-content: center;
              z-index: 1000; }
  .modal-bg.show { display: flex; }
  #modal-content { display: flex; flex-direction: column; align-items: center; gap: 8px; }
  #modal-content img { max-width: 95vw; max-height: 95vh; }
  .modal-static-img { max-width: 1000px !important; max-height: 60vh !important;
                      background: white; padding: 4px; border-radius: 4px; }
  .modal-iframe-row { display: flex; gap: 12px; }
  .modal-surf-frame { width: 600px; height: 500px; border: 1px solid #888;
                      background: white; }
  .modal-close { position: fixed; top: 16px; right: 24px; font-size: 24px;
                 color: white; cursor: pointer; user-select: none;
                 padding: 4px 10px; background: rgba(0,0,0,0.5);
                 border-radius: 4px; }
  .modal-label { color: white; font-size: 14px;
                 font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
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
<div id="modal" class="modal-bg">
  <span class="modal-close" id="modal-close">&times;</span>
  <div id="modal-content"></div>
</div>
<script>
const modal = document.getElementById('modal');
const modalContent = document.getElementById('modal-content');

function clearModal() {
  while (modalContent.firstChild) modalContent.removeChild(modalContent.firstChild);
}
function closeModal() {
  modal.classList.remove('show');
  clearModal();
}
function openImgModal(src) {
  clearModal();
  const img = document.createElement('img');
  img.src = src;
  modalContent.appendChild(img);
  modal.classList.add('show');
}
function openIframeModal(urlL, urlR, label, staticSrc) {
  clearModal();
  if (label) {
    const lbl = document.createElement('div');
    lbl.className = 'modal-label';
    lbl.textContent = label;
    modalContent.appendChild(lbl);
  }
  if (staticSrc) {
    const img = document.createElement('img');
    img.src = staticSrc;
    img.className = 'modal-static-img';
    modalContent.appendChild(img);
  }
  const row = document.createElement('div');
  row.className = 'modal-iframe-row';
  for (const url of [urlL, urlR]) {
    const fr = document.createElement('iframe');
    fr.src = url;
    fr.className = 'modal-surf-frame';
    row.appendChild(fr);
  }
  modalContent.appendChild(row);
  modal.classList.add('show');
}

// Cohort PNGs → static image modal
document.querySelectorAll('.map-cell > img').forEach(img => {
  img.addEventListener('click', () => openImgModal(img.src));
});
// Subject tiles → static PNG + L+R iframes in modal
document.querySelectorAll('.subj-grid img').forEach(img => {
  img.addEventListener('click', () => {
    openIframeModal(img.dataset.l, img.dataset.r, img.dataset.label || '', img.src);
  });
});
// Cohort "View in 3D" buttons → interactive L+R iframes in modal
document.querySelectorAll('.rotate-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    openIframeModal(btn.dataset.l, btn.dataset.r, btn.dataset.label || '');
  });
});
// Modal close: X button, overlay click (not iframe), or Escape
document.getElementById('modal-close').addEventListener('click', closeModal);
modal.addEventListener('click', e => {
  if (e.target === modal) closeModal();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && modal.classList.contains('show')) closeModal();
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

        def _subj_tile(png_path):
            sub_id = png_path.stem.split('_', 1)[0]
            int_l = png_path.with_name(f'{png_path.stem}_L.html')
            int_r = png_path.with_name(f'{png_path.stem}_R.html')
            label = f'{sub_id} {task} / {contrast}'
            return (
                f'<img src="{_rel(png_path)}" '
                f'data-l="{_rel(int_l)}" data-r="{_rel(int_r)}" '
                f'data-label="{label}">'
            )

        section_html = (
            f'<h2 id="{anchor}">{task} / {contrast} '
            f'<small>(n_subj={len(subj_pngs)})</small></h2>\n'
            f'<h3>Uncorrected prevalence (z>1.96) + directionality</h3>\n'
            f'<div class="prev-row">'
            f'<div class="map-cell">'
            f'<img src="{_rel(prev_png)}">'
            f'<button class="rotate-btn" '
            f'data-l="{_rel(prev_int_l)}" data-r="{_rel(prev_int_r)}" '
            f'data-label="{task} / {contrast} — prevalence (unthresholded)">'
            f'View in 3D</button>'
            f'</div>'
            f'<div class="map-cell">'
            f'<img src="{_rel(dir_png)}">'
            f'<button class="rotate-btn" '
            f'data-l="{_rel(dir_int_l)}" data-r="{_rel(dir_int_r)}" '
            f'data-label="{task} / {contrast} — directionality (signed)">'
            f'View in 3D</button>'
            f'</div>'
            f'</div>\n'
            f'<h3>Per-subject unthresholded z-maps (click to view in 3D)</h3>\n'
            '<div class="subj-grid">'
            + '\n'.join(_subj_tile(p) for p in subj_pngs)
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
