# Prevalence Diagnostic Dashboard — Medial Views + Interactive Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the diagnostic dashboard at `/scratch/users/logben/prevalence_diagnostic_all44/` to render 4-panel (L-lat/L-med/R-lat/R-med) static PNGs and add lazy-loaded WebGL interactive rotation viewers for cohort-level prevalence + directionality maps.

**Architecture:** Modify two existing standalone Python scripts (`scripts/prevalence_subject_diagnostic.py` and `scripts/prevalence_diagnostic_assemble_index.py`). Re-use the existing 44-task SLURM array after the in-flight run is cancelled. Snapshot the previous 2-panel dashboard to `$GROUP_SCRATCH` before re-launching.

**Tech Stack:** Python 3, `nilearn.plotting.plot_surf_stat_map` (static), `nilearn.plotting.view_surf` (interactive WebGL via plotly), fsaverage6 inflated meshes, vanilla HTML/CSS/JS.

**Reference spec:** `docs/superpowers/specs/2026-05-25-prevalence-dashboard-medial-interactive-design.md`

---

## Pre-flight notes

The two diagnostic scripts are currently untracked in git (see `git status`). Task 1 commits them as a clean baseline so the medial+interactive changes show up as focused, reviewable diffs.

There is no unit-test scaffolding for these scripts — they're standalone visualization scripts. Validation is via manual visual inspection of the smoke-test output (Task 9) and the final regenerated dashboard (Task 12).

Active SLURM jobs to be aware of (do not touch until Task 11):
- `25922227` — `prev_diag_render` 44-task array (in flight, must be cancelled before re-launch)
- `25922253` — `prev_diag_assemble` (dependent on the array; will be re-submitted after)

---

### Task 1: Commit existing diagnostic scripts as baseline

**Files:**
- Modify (git index only): `scripts/prevalence_subject_diagnostic.py`
- Modify (git index only): `scripts/prevalence_diagnostic_assemble_index.py`

- [ ] **Step 1: Confirm both scripts are currently untracked**

Run: `git status --short scripts/prevalence_subject_diagnostic.py scripts/prevalence_diagnostic_assemble_index.py`
Expected: both prefixed with `??` (untracked).

- [ ] **Step 2: Stage the two scripts (only these two)**

```bash
git add scripts/prevalence_subject_diagnostic.py \
        scripts/prevalence_diagnostic_assemble_index.py
git status --short scripts/prevalence_subject_diagnostic.py \
                   scripts/prevalence_diagnostic_assemble_index.py
```
Expected: both prefixed with `A` (added to index).

- [ ] **Step 3: Commit as baseline**

```bash
git commit -m "$(cat <<'EOF'
feat(prevalence): per-subject + uncorrected prevalence diagnostic dashboard scripts

Adds the two scripts that build the per-cell diagnostic dashboard at
/scratch/users/logben/prevalence_diagnostic_all44/: a renderer that draws
per-subject z-map montages + the uncorrected Bayesian prevalence + directionality
maps for one or more task-contrast cells, and an assemble step that scans the
figures/ dir and writes a master index.html.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify clean working tree for the scripts**

Run: `git status --short scripts/prevalence_subject_diagnostic.py scripts/prevalence_diagnostic_assemble_index.py`
Expected: empty output (nothing to commit for these two files).

---

### Task 2: Replace `_plot_2panel` with `_plot_4panel` in subject_diagnostic

**Files:**
- Modify: `scripts/prevalence_subject_diagnostic.py:33-58` (replace `_plot_2panel` definition)

- [ ] **Step 1: Replace the function definition**

In `scripts/prevalence_subject_diagnostic.py`, replace the existing `_plot_2panel` (lines 33-58) with `_plot_4panel`:

```python
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
```

- [ ] **Step 2: Update `_render_one_subject` to call `_plot_4panel` with subject-tile sizing**

Replace lines 64-76 (the `_render_one_subject` worker) with:

```python
def _render_one_subject(args_tuple):
    """Top-level worker for multiprocessing."""
    z_path_l, z_path_r, sub_id, out_path, vmax = args_tuple
    fsav = _fetch_fsaverage6()
    z_l = load_gifti_data(z_path_l)
    z_r = load_gifti_data(z_path_r)
    _plot_4panel(
        z_l, z_r, out_path,
        cmap='RdBu_r', vmin=-vmax, vmax=vmax,
        title=sub_id, fsaverage=fsav,
        figsize=(5, 4.5), dpi=50, symmetric=True,
    )
    return sub_id
```

- [ ] **Step 3: Update `render_prevalence_map` call sites to use `_plot_4panel`**

In `render_prevalence_map` (currently lines 120-135), change both `_plot_2panel(...)` calls to `_plot_4panel(...)`. The full updated body of `render_prevalence_map` (replacing lines 112-136):

```python
def render_prevalence_map(prev_dir: Path, task: str, contrast: str,
                          output_dir: Path, cohort: str = 'pooled46') -> Path:
    """Render the uncorrected directional prevalence map for one cell."""
    fsav = _fetch_fsaverage6()
    base = f'{cohort}_task-{task}_hemi-X_contrast-{contrast}_rtmodel-RTDur'
    map_l = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-L")}_direction-overall_stat-prevalence-map.func.gii')
    map_r = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-R")}_direction-overall_stat-prevalence-map.func.gii')
    out_path = output_dir / f'{task}_{contrast}_prevalence_uncorrected.png'
    _plot_4panel(
        map_l, map_r, out_path,
        cmap='inferno', vmin=0.0, vmax=None,
        title=f'{task} / {contrast} — UNCORRECTED prevalence (z>1.96)',
        fsaverage=fsav, figsize=(8, 7), dpi=100,
    )
    # Directionality map (signed)
    dir_l = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-L")}_stat-directionality.func.gii')
    dir_r = load_gifti_data(prev_dir / f'{base.replace("hemi-X","hemi-R")}_stat-directionality.func.gii')
    dir_path = output_dir / f'{task}_{contrast}_directionality_uncorrected.png'
    _plot_4panel(
        dir_l, dir_r, dir_path,
        cmap='RdBu_r', vmin=-1.0, vmax=1.0,
        title=f'{task} / {contrast} — directionality (signed, uncorrected)',
        fsaverage=fsav, figsize=(8, 7), dpi=100, symmetric=True,
    )
    return out_path
```

- [ ] **Step 4: Manual smoke check — render one subject tile to verify the new layout**

Run:
```bash
sbatch --wait \
  --partition=russpold --time=00:10:00 --mem=8G --cpus-per-task=4 \
  --output=/tmp/medial_smoke.out --error=/tmp/medial_smoke.err \
  --wrap="module load uv && uv --directory /home/users/logben/neuro_workflow run python -c '
from pathlib import Path
import sys
sys.path.insert(0, \"/home/users/logben/neuro_workflow/scripts\")
from prevalence_subject_diagnostic import render_subject_montage
out_dir = Path(\"/tmp/medial_smoke_figs\")
render_subject_montage(
    lev1_root=Path(\"/scratch/users/logben/lev1_surface_pooled_46\"),
    task=\"flanker\", contrast=\"incongruent-congruent\",
    output_dir=out_dir, n_jobs=4,
)
print(\"Wrote\", len(list(out_dir.glob(\"*.png\"))), \"tiles\")
'"
```

Open one of the output PNGs (e.g., `/tmp/medial_smoke_figs/sub-s03_flanker_incongruent-congruent.png`) and confirm:
- 2×2 grid: L-lat top-left, R-lat top-right, L-med bottom-left, R-med bottom-right
- Single colorbar attached to bottom-right panel
- Aspect ratio roughly square (~5×4.5 in)

- [ ] **Step 5: Commit**

```bash
git add scripts/prevalence_subject_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(prevalence): 4-panel (L-lat/L-med/R-lat/R-med) layout for diagnostic figures

Replace _plot_2panel with _plot_4panel in prevalence_subject_diagnostic.py.
Cohort prevalence + directionality maps and all 46 per-subject z-map tiles
now show both lateral and medial surfaces. Cohort maps render at (8, 7) in
@ 100 dpi; per-subject tiles at (5, 4.5) in @ 50 dpi.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add `_render_interactive_viewer` helper

**Files:**
- Modify: `scripts/prevalence_subject_diagnostic.py` (add new function above `_SUBJECT_RE` declaration)

- [ ] **Step 1: Add the helper function**

In `scripts/prevalence_subject_diagnostic.py`, insert the following function definition immediately after `_plot_4panel` (i.e., before the `_SUBJECT_RE = re.compile(...)` line):

```python
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
```

`hemi` must be the string `'left'` or `'right'` (matching the fsaverage dict keys `infl_left`, `infl_right`, `sulc_left`, `sulc_right`).

- [ ] **Step 2: Standalone smoke test — render one HTML and open it**

Run:
```bash
sbatch --wait \
  --partition=russpold --time=00:10:00 --mem=8G --cpus-per-task=2 \
  --output=/tmp/viewer_smoke.out --error=/tmp/viewer_smoke.err \
  --wrap="module load uv && uv --directory /home/users/logben/neuro_workflow run python -c '
from pathlib import Path
import sys
sys.path.insert(0, \"/home/users/logben/neuro_workflow/scripts\")
from prevalence_subject_diagnostic import _render_interactive_viewer
from neuro_workflow.analysis.prevalence.aggregate import load_gifti_data
from neuro_workflow.analysis.prevalence.visualize import _fetch_fsaverage6

fsav = _fetch_fsaverage6()
prev_dir = Path(\"/scratch/users/logben/prevalence_uncorrected_n46\")
base = \"pooled46_task-flanker_hemi-L_contrast-incongruent-congruent_rtmodel-RTDur_direction-overall_stat-prevalence-map.func.gii\"
arr = load_gifti_data(prev_dir / base)
out = Path(\"/tmp/viewer_smoke.html\")
_render_interactive_viewer(arr, \"left\", out, cmap=\"inferno\", vmax=0.5,
                            symmetric=False, title=\"flanker L smoke\", fsaverage=fsav)
print(\"Wrote\", out, out.stat().st_size, \"bytes\")
'"
```

Confirm the file is ~300KB–1MB. Copy it to your laptop with scp (`scp sherlock:/tmp/viewer_smoke.html ~/Desktop/`) and open in a browser; drag to rotate, hover to see vertex values. Confirm cmap is `inferno`, no threshold applied.

- [ ] **Step 3: Commit**

```bash
git add scripts/prevalence_subject_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(prevalence): _render_interactive_viewer helper (nilearn view_surf)

Wraps nilearn.plotting.view_surf to emit a standalone HTML containing a
rotatable WebGL surface viewer for a single hemisphere. Used for cohort-level
prevalence + directionality maps in the diagnostic dashboard. Unthresholded,
hover-enabled, cell-specific vmax for color-scale parity with the static
4-panel PNG.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire interactive viewers into `render_prevalence_map`

**Files:**
- Modify: `scripts/prevalence_subject_diagnostic.py` (expand `render_prevalence_map` to also emit 4 HTMLs per cell)

- [ ] **Step 1: Replace the `render_prevalence_map` body**

Replace the *entire* `render_prevalence_map` function (just updated in Task 2) with the following expanded version:

```python
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
            title=f'{task} / {contrast} — {hemi} prevalence (unthresholded)',
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
            title=f'{task} / {contrast} — {hemi} directionality (signed)',
            fsaverage=fsav,
        )

    return prev_png
```

Note the file-naming convention: interactive HTMLs use `_L.html` / `_R.html` suffix (single capital letter), so the assemble script can construct paths deterministically.

- [ ] **Step 2: Smoke test — render one full cell and verify 6 figures land on disk**

Run:
```bash
sbatch --wait \
  --partition=russpold --time=00:20:00 --mem=12G --cpus-per-task=8 \
  --output=/tmp/cell_smoke.out --error=/tmp/cell_smoke.err \
  --wrap="module load uv && rm -rf /scratch/users/logben/prevalence_diagnostic_smoke && \
    uv --directory /home/users/logben/neuro_workflow run python \
    /home/users/logben/neuro_workflow/scripts/prevalence_subject_diagnostic.py \
    --lev1-root /scratch/users/logben/lev1_surface_pooled_46 \
    --prev-dir /scratch/users/logben/prevalence_uncorrected_n46 \
    --output-dir /scratch/users/logben/prevalence_diagnostic_smoke \
    --cells flanker:incongruent-congruent --n-jobs 8 --verbose"
ls -la /scratch/users/logben/prevalence_diagnostic_smoke/figures/ | head -20
```

Expected files in `figures/`:
- `flanker_incongruent-congruent_prevalence_uncorrected.png`
- `flanker_incongruent-congruent_prevalence_uncorrected_L.html`
- `flanker_incongruent-congruent_prevalence_uncorrected_R.html`
- `flanker_incongruent-congruent_directionality_uncorrected.png`
- `flanker_incongruent-congruent_directionality_uncorrected_L.html`
- `flanker_incongruent-congruent_directionality_uncorrected_R.html`
- 46× `sub-*_flanker_incongruent-congruent.png`

- [ ] **Step 3: Commit**

```bash
git add scripts/prevalence_subject_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(prevalence): emit interactive view_surf HTMLs alongside static 4-panel PNGs

render_prevalence_map now writes four extra HTMLs per cell (prevalence L/R,
directionality L/R) using _render_interactive_viewer. Interactive vmax matches
each cell's static color scale so the rotatable and the thresholded views are
visually comparable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update assemble-script HTML markup for rotate-toggle buttons

**Files:**
- Modify: `scripts/prevalence_diagnostic_assemble_index.py:104-128` (the per-cell section_html construction)

- [ ] **Step 1: Replace the per-cell section_html construction**

In `scripts/prevalence_diagnostic_assemble_index.py`, replace the `for task, contrast in cells:` block (currently lines 104-130) with the following:

```python
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
```

- [ ] **Step 2: Run assemble against the smoke dashboard from Task 4 and grep the markup**

Run:
```bash
uv --directory /home/users/logben/neuro_workflow run python \
  /home/users/logben/neuro_workflow/scripts/prevalence_diagnostic_assemble_index.py \
  --dashboard-dir /scratch/users/logben/prevalence_diagnostic_smoke
grep -A2 'map-cell' /scratch/users/logben/prevalence_diagnostic_smoke/index.html | head -30
```

Expected: see `<div class="map-cell">` wrapping each `<img>`, with `<button class="rotate-btn" data-l="figures/...html" data-r="figures/...html">` and `<div class="iframe-holder" hidden></div>` following.

Note: this step runs the script directly because the assemble step doesn't need GPU/large mem; it's pure HTML generation.

- [ ] **Step 3: Commit**

```bash
git add scripts/prevalence_diagnostic_assemble_index.py
git commit -m "$(cat <<'EOF'
feat(prevalence): rotate-toggle markup in diagnostic dashboard assemble step

Each cohort map (prevalence + directionality) is now wrapped in a .map-cell
container with a rotate-btn carrying data-l/data-r attrs pointing to the
single-hemi interactive HTML viewers, plus a hidden .iframe-holder that the
toggle JS (next commit) populates lazily on click.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add CSS for `.map-cell`, `.rotate-btn`, `.iframe-holder`, `.surf-frame`

**Files:**
- Modify: `scripts/prevalence_diagnostic_assemble_index.py:29-48` (the `<style>` block inside `_HTML_HEAD`)

- [ ] **Step 1: Add the new selectors inside the `<style>` block**

In the existing `_HTML_HEAD` string (lines 25-67 of the assemble script), update the `<style>` block to include the four new selectors. Replace the `<style>` block (between `<style>` and `</style>`) with:

```css
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
```

- [ ] **Step 2: Regenerate the smoke dashboard and verify the styles land in `<head>`**

Run:
```bash
uv --directory /home/users/logben/neuro_workflow run python \
  /home/users/logben/neuro_workflow/scripts/prevalence_diagnostic_assemble_index.py \
  --dashboard-dir /scratch/users/logben/prevalence_diagnostic_smoke
grep -E '\.(map-cell|rotate-btn|iframe-holder|surf-frame)' \
  /scratch/users/logben/prevalence_diagnostic_smoke/index.html
```

Expected: all four selectors appear in grep output.

- [ ] **Step 3: Commit**

```bash
git add scripts/prevalence_diagnostic_assemble_index.py
git commit -m "$(cat <<'EOF'
style(prevalence): CSS for rotate-toggle button + lazy iframe holder

Adds .map-cell column layout, .rotate-btn pill, .iframe-holder flex container,
and .surf-frame iframe sizing (480x380, 1px border) for the diagnostic
dashboard. Existing modal-zoom and subject-grid styling preserved.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add toggle JS using `createElement` / `appendChild`

**Files:**
- Modify: `scripts/prevalence_diagnostic_assemble_index.py:58-66` (the `<script>` block inside `_HTML_HEAD`)

- [ ] **Step 1: Replace the existing `<script>` block**

In `_HTML_HEAD`, replace the existing `<script>...</script>` block (currently lines 58-66) with:

```html
<script>
// Modal zoom for static images (subject tiles + cohort PNGs)
document.querySelectorAll('.subj-grid img, .map-cell > img').forEach(img => {
  img.addEventListener('click', () => {
    document.getElementById('modal-img').src = img.src;
    document.getElementById('modal').classList.add('show');
  });
});
// Rotate toggle: lazy-spawn L+R iframes on click, tear down on second click
document.querySelectorAll('.rotate-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const holder = btn.nextElementSibling;
    const open = !holder.hidden;
    if (open) {
      while (holder.firstChild) holder.removeChild(holder.firstChild);
      holder.hidden = true;
      btn.textContent = 'rotate';
    } else {
      for (const url of [btn.dataset.l, btn.dataset.r]) {
        const fr = document.createElement('iframe');
        fr.src = url;
        fr.className = 'surf-frame';
        holder.appendChild(fr);
      }
      holder.hidden = false;
      btn.textContent = 'close';
    }
  });
});
</script>
```

The selector `.subj-grid img, .map-cell > img` is critical: it limits the modal-zoom binding to *direct child* `<img>` of `.map-cell` (the static PNG) AND to subject-grid tiles. It deliberately excludes any `<img>` that the interactive iframe might inject (those live inside the iframe document, but the `>` selector makes the rule unambiguous regardless).

- [ ] **Step 2: Regenerate the smoke dashboard, copy to local, manually test**

Regenerate:
```bash
uv --directory /home/users/logben/neuro_workflow run python \
  /home/users/logben/neuro_workflow/scripts/prevalence_diagnostic_assemble_index.py \
  --dashboard-dir /scratch/users/logben/prevalence_diagnostic_smoke
```

Then copy the dashboard to local (run on local machine, not Sherlock):
```bash
mkdir -p ~/Desktop/prev_smoke && \
  rsync -avz --info=progress2 \
    sherlock:/scratch/users/logben/prevalence_diagnostic_smoke/ \
    ~/Desktop/prev_smoke/
open ~/Desktop/prev_smoke/index.html
```

Visual checklist:
- Page renders with the flanker cell; cohort 4-panel PNG visible (L-lat/R-lat top, L-med/R-med bottom)
- Each cohort PNG has a blue "rotate" button below it
- Click rotate → two iframes (L hemi + R hemi) appear side by side; drag to rotate; hover shows values
- Click "close" → iframes disappear; DOM is empty inside `.iframe-holder`
- Click a per-subject tile → existing modal zoom still works
- Click static PNG (e.g., the cohort prevalence PNG) → modal zoom still works (`.map-cell > img` selector covers it)

- [ ] **Step 3: Commit**

```bash
git add scripts/prevalence_diagnostic_assemble_index.py
git commit -m "$(cat <<'EOF'
feat(prevalence): lazy iframe-injection JS for rotate toggle

Toggle handler creates iframes via document.createElement (no innerHTML) and
tears them down on close so memory is bounded by the number of *open* viewers,
not by cell count. Modal-zoom rule scoped via .subj-grid img, .map-cell > img
so iframe contents are not intercepted.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: End-to-end smoke test — one cell, full dashboard render + visual sign-off

**Files:** none (verification only)

- [ ] **Step 1: Wipe and re-run the smoke directory from scratch**

```bash
rm -rf /scratch/users/logben/prevalence_diagnostic_smoke
sbatch --wait \
  --partition=russpold --time=00:30:00 --mem=12G --cpus-per-task=8 \
  --output=/tmp/e2e_smoke.out --error=/tmp/e2e_smoke.err \
  --wrap="module load uv && \
    uv --directory /home/users/logben/neuro_workflow run python \
      /home/users/logben/neuro_workflow/scripts/prevalence_subject_diagnostic.py \
      --lev1-root /scratch/users/logben/lev1_surface_pooled_46 \
      --prev-dir /scratch/users/logben/prevalence_uncorrected_n46 \
      --output-dir /scratch/users/logben/prevalence_diagnostic_smoke \
      --cells flanker:incongruent-congruent --n-jobs 8 --verbose && \
    uv --directory /home/users/logben/neuro_workflow run python \
      /home/users/logben/neuro_workflow/scripts/prevalence_diagnostic_assemble_index.py \
      --dashboard-dir /scratch/users/logben/prevalence_diagnostic_smoke"
```

- [ ] **Step 2: Confirm file inventory**

```bash
ls /scratch/users/logben/prevalence_diagnostic_smoke/figures/ | sort | uniq -c | awk '{print $2}' | sed 's/_sub-.*$//' | sort -u
ls /scratch/users/logben/prevalence_diagnostic_smoke/figures/ | wc -l
ls /scratch/users/logben/prevalence_diagnostic_smoke/figures/*.html | wc -l
```

Expected:
- Total file count: 2 (cohort PNGs) + 4 (interactive HTMLs) + 46 (subject tiles) = 52
- HTML file count: 4

- [ ] **Step 3: Local visual inspection**

On your local machine:
```bash
rsync -avz sherlock:/scratch/users/logben/prevalence_diagnostic_smoke/ \
           ~/Desktop/prev_smoke/
open ~/Desktop/prev_smoke/index.html
```

Verify:
- Cohort 4-panel PNGs render correctly (medial visible)
- Toggle opens iframes; closes cleanly
- Per-subject tile grid shows all 46 in 4-panel
- Flanker incongruent-congruent shows medial-frontal signal (anterior cingulate / pre-SMA) — sanity check that the medial view actually exposes new neural signal

- [ ] **Step 4: Get user sign-off**

This is a hard checkpoint. **Do not proceed to Task 9 until the user has confirmed the smoke dashboard looks correct.** Tell the user the smoke output path and ask them to open it.

---

### Task 9: Snapshot existing 2-panel dashboard to `$GROUP_SCRATCH`

**Files:** none (filesystem operation only)

- [ ] **Step 1: Confirm the existing dashboard exists at the expected path**

```bash
ls -la /scratch/users/logben/prevalence_diagnostic_all44/
ls /scratch/users/logben/prevalence_diagnostic_all44/figures/ | wc -l
```

Expected: `index.html` present, `figures/` with ~2 cohort PNGs × 44 + 46 × 44 = ~2,112 PNGs (give or take, depending on how much of the array completed).

- [ ] **Step 2: Copy to `$GROUP_SCRATCH` for rollback safety**

```bash
sbatch --wait \
  --partition=normal --time=00:30:00 --mem=4G --cpus-per-task=2 \
  --output=/tmp/snapshot.out --error=/tmp/snapshot.err \
  --wrap="cp -r /scratch/users/logben/prevalence_diagnostic_all44 \
                /scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot && \
          du -sh /scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot"
```

Expected: snapshot completes, du reports something on the order of 1–2 GB.

- [ ] **Step 3: Verify snapshot is intact**

```bash
test -f /scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot/index.html && echo OK
ls /scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot/figures/ | wc -l
```

Expected: `OK`, and figure count matches the source within a small margin.

---

### Task 10: Cancel in-flight array + re-launch with new code

**Files:**
- Sbatch wrappers (already in place, no modification): `/scratch/groups/russpold/logben/prevalence_diagnostic_array.sbatch`, `/scratch/groups/russpold/logben/prevalence_diagnostic_assemble.sbatch`

- [ ] **Step 1: Confirm what's running**

```bash
squeue -u $USER --format='%.18i %.20j %.8T %.10M %.6D' | grep -E 'prev_diag|JOBID'
```

Expected: see `prev_diag_render` (array) and possibly `prev_diag_assemble` in PD or R state.

- [ ] **Step 2: Cancel both**

```bash
scancel --name=prev_diag_render --name=prev_diag_assemble
sleep 5
squeue -u $USER --format='%.18i %.20j %.8T' | grep -E 'prev_diag' || echo "all cancelled"
```

Expected: `all cancelled`.

- [ ] **Step 3: Wipe the in-progress dashboard tree (cohort PNGs + interactives will overlap with stale lateral-only PNGs otherwise)**

```bash
rm -rf /scratch/users/logben/prevalence_diagnostic_all44
mkdir -p /scratch/users/logben/prevalence_diagnostic_all44/logs
mkdir -p /scratch/users/logben/prevalence_diagnostic_all44/figures
```

The snapshot from Task 9 is the rollback. If you skipped Task 9, **STOP** and complete it before this step.

- [ ] **Step 4: Submit the new array**

```bash
ARRAY_ID=$(sbatch --parsable /scratch/groups/russpold/logben/prevalence_diagnostic_array.sbatch)
echo "Array ID: $ARRAY_ID"
sbatch --dependency=afterok:$ARRAY_ID \
       /scratch/groups/russpold/logben/prevalence_diagnostic_assemble.sbatch
squeue -u $USER --format='%.18i %.20j %.8T %.10M %.6D' | head
```

- [ ] **Step 5: Monitor and wait for completion**

```bash
# Poll status every few minutes (do NOT sleep; just rerun this when checking)
squeue -u $USER --format='%.18i %.20j %.8T %.10M %.6D' | grep prev_diag
# Once empty, peek at one task's stderr
tail /scratch/users/logben/prevalence_diagnostic_all44/logs/render-${ARRAY_ID}-1.err
```

Expected: ~5–15 min for the full array (per-cell budget ~50 sec, 44 array tasks in parallel limited by partition queue depth).

---

### Task 11: Final verification on the full regenerated dashboard

**Files:** none (verification only)

- [ ] **Step 1: Check file inventory matches expectations**

```bash
ls /scratch/users/logben/prevalence_diagnostic_all44/figures/*.html | wc -l
ls /scratch/users/logben/prevalence_diagnostic_all44/figures/*_prevalence_uncorrected.png | wc -l
ls /scratch/users/logben/prevalence_diagnostic_all44/figures/*_directionality_uncorrected.png | wc -l
ls /scratch/users/logben/prevalence_diagnostic_all44/figures/sub-*.png | wc -l
```

Expected counts:
- HTML files: 44 × 4 = **176**
- Prevalence cohort PNGs: **44**
- Directionality cohort PNGs: **44**
- Subject tile PNGs: 44 × 46 = **2024**

If any count is short, identify failed array tasks via `sacct -j $ARRAY_ID --format=JobID,State,ExitCode | grep -v COMPLETED` and rerun those cells with `--cells task:contrast` directly.

- [ ] **Step 2: Confirm assemble step ran**

```bash
ls -la /scratch/users/logben/prevalence_diagnostic_all44/index.html
grep -c 'rotate-btn' /scratch/users/logben/prevalence_diagnostic_all44/index.html
```

Expected: index.html exists; rotate-btn count = 88 (2 per cell × 44 cells).

- [ ] **Step 3: Pull dashboard local + visual inspection on 3 cells**

On local machine:
```bash
rsync -avz --info=progress2 \
  sherlock:/scratch/users/logben/prevalence_diagnostic_all44/ \
  ~/Desktop/prev_diag_all44/
open ~/Desktop/prev_diag_all44/index.html
```

Click through the TOC to spot-check three cells (the target cells of this investigation):
- `flanker / incongruent-congruent` — expect medial-frontal signal
- `cuedTS / cue_switch_cost` — the cell FDR was killing; check whether medial cortex shows pre-FDR consistency
- `goNogo / nogo_success-go` — strong-signal positive control

For each, open the rotate toggle on both prevalence and directionality maps, verify rotation works, then close to confirm DOM cleanup.

- [ ] **Step 4: Report back to user**

Summarize for the user:
1. Dashboard is at `/scratch/users/logben/prevalence_diagnostic_all44/index.html`
2. Snapshot of the prior 2-panel state is at `/scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot/`
3. Which cells (if any) failed to render and need manual `--cells` reruns
4. Any visual surprises noticed during spot-check

---

## Rollback procedure

If at any point after Task 10 the new dashboard is broken or unusable:

```bash
rm -rf /scratch/users/logben/prevalence_diagnostic_all44
cp -r /scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot \
      /scratch/users/logben/prevalence_diagnostic_all44
```

To revert the code changes:
```bash
git log --oneline -12 scripts/prevalence_subject_diagnostic.py scripts/prevalence_diagnostic_assemble_index.py
git revert <medial-interactive-commit-shas>
```

---

## Spec coverage cross-check

| Spec section | Implementation task(s) |
|---|---|
| 4-panel static PNGs (cohort + subject) | Task 2 (`_plot_4panel`) |
| Interactive viewer per (map, hemi) | Tasks 3, 4 (`_render_interactive_viewer`, wired into `render_prevalence_map`) |
| `cell-specific vmax` for color-scale parity | Task 4 (computes `prev_vmax` from L+R concat; directionality uses fixed ±1.0) |
| Unthresholded interactive (`threshold=None`) | Task 3 |
| Disk layout (`_L.html`, `_R.html` suffixes) | Task 4 (writes); Task 5 (reads) |
| HTML markup (`map-cell`, `rotate-btn`, `iframe-holder`) | Task 5 |
| CSS (`.map-cell`, `.rotate-btn`, `.iframe-holder`, `.surf-frame`) | Task 6 |
| Toggle JS (createElement/appendChild lazy load) | Task 7 |
| Smoke test on `flanker:incongruent-congruent` | Task 8 |
| Snapshot before re-launch | Task 9 |
| Cancel in-flight array + re-submit | Task 10 |
| Spot-check final dashboard | Task 11 |
| No unit tests (visual output) | Reflected in plan — Tasks 2/3/4/7/8 use manual smoke checks instead |
