# Prevalence Diagnostic Dashboard — Medial Views + Interactive Rotation

**Date:** 2026-05-25
**Status:** Approved (design); pending implementation plan
**Scope:** Extend `scripts/prevalence_subject_diagnostic.py` and `scripts/prevalence_diagnostic_assemble_index.py` so the dashboard at `/scratch/users/logben/prevalence_diagnostic_all44/` shows medial surface views and supports interactive (rotatable) cohort maps.

## Motivation

The current dashboard renders 2-panel lateral-only PNGs for every map (cohort prevalence + directionality + 46 per-subject z-maps). FDR-corrected Bayesian prevalence killed signal in several conflict-style contrasts (cuedTS, spatialTS, directedForgetting, flanker). The user is investigating whether real signal exists in those cells before FDR — particularly on medial cortex (anterior cingulate, pre-SMA, mPFC, PCC) which is not visible in the lateral-only views.

Two additions:
1. Medial views — all maps become 4-panel (L-lat / L-med / R-lat / R-med).
2. Interactive rotation — cohort-level maps additionally get rotatable WebGL viewers (one per hemisphere) that load on demand, so the user can spin to any angle (inferior, posterior, etc.) without re-rendering.

Per-subject z-map tiles stay static (4-panel only) because there are 2,024 of them and the diagnostic value of rotating each tile is low compared to the cost.

## Approach Overview

**Approach A — Extend the existing renderer + restart the SLURM array.** Both diagnostic scripts are modified to produce 4-panel static PNGs + `nilearn.plotting.view_surf` HTML viewers. The in-flight 44-task array (job 25922227) is killed, the previous 2-panel output is snapshotted to `$GROUP_SCRATCH`, and the array is re-submitted with the new code. End state: one uniform 4-panel + interactive dashboard.

Rejected alternatives:
- Two-phase add-on — adds medial PNGs + viewers in a second script after the lateral array finishes. Zero wasted compute but maintains two code paths and the disk layout grows messier.
- Refactor into shared `surface_renderer` module — best long-term architecture but the abstraction isn't justified yet (only two callers).

## Architecture

### Files touched

| File | Change |
|---|---|
| `scripts/prevalence_subject_diagnostic.py` | Replace `_plot_2panel` with `_plot_4panel`. Add `_render_interactive_viewer` emitting `view_surf` HTML per (map, hemi). |
| `scripts/prevalence_diagnostic_assemble_index.py` | Add rotate toggle button next to each cohort map; embed lazy iframe-injection JS in `_HTML_HEAD`. Update CSS for `.map-cell`, `.rotate-btn`, `.iframe-holder`, `.surf-frame`. |
| `/scratch/groups/russpold/logben/prevalence_diagnostic_array.sbatch` | No change (same script, new code). |
| `/scratch/groups/russpold/logben/prevalence_diagnostic_assemble.sbatch` | No change. |

### Disk layout (under `figures/` in dashboard dir)

```
{task}_{contrast}_prevalence_uncorrected.png             4-panel static
{task}_{contrast}_directionality_uncorrected.png         4-panel static
{task}_{contrast}_prevalence_uncorrected_L.html          NEW — interactive L hemi
{task}_{contrast}_prevalence_uncorrected_R.html          NEW — interactive R hemi
{task}_{contrast}_directionality_uncorrected_L.html      NEW
{task}_{contrast}_directionality_uncorrected_R.html      NEW
sub-{XXX}_{task}_{contrast}.png                          4-panel static (per subject)
```

Per-cell adds 4 HTML files. 44 cells → 176 new HTML files. Each `view_surf` HTML is ~300KB–1MB (embeds mesh + map + plotly JS). Estimated total addition: ~50–180MB. Total dashboard size remains well under 1GB.

## Rendering Details

### Static 4-panel PNGs

`_plot_4panel(map_l, map_r, out_path, ...)` draws a 2×2 grid:

```
+----------+----------+
| L-lat    | R-lat    |
+----------+----------+
| L-med    | R-med    |
+----------+----------+
```

Each panel: `nilearn.plotting.plot_surf_stat_map(surf_mesh=infl_{hemi}, stat_map=map_{hemi}, bg_map=sulc_{hemi}, hemi=hemi, view='lateral'|'medial', cmap, vmin, vmax, symmetric_cbar, bg_on_data=True, ...)`. Single colorbar attached to the lower-right panel.

| Parameter | Cohort prevalence | Cohort directionality | Per-subject z-map |
|---|---|---|---|
| Figure size (in) | 8 × 7 | 8 × 7 | 5 × 4.5 |
| DPI | 100 | 100 | 50 |
| Colormap | `inferno` | `RdBu_r` | `RdBu_r` |
| vmin / vmax | 0 / auto | −1.0 / 1.0 | ±vmax_pctile95 (cohort-wide for this cell) |
| `symmetric_cbar` | False | True | True |
| `bg_on_data` | True | True | True |

`vmax_pctile95` is computed once per task-contrast cell as the 95th percentile of |z| across all 46 subjects × both hemispheres (already in current code).

### Interactive viewers

```python
view = nilearn.plotting.view_surf(
    surf_mesh=fsaverage[f'infl_{hemi}'],
    surf_map=stat_map,
    bg_map=fsaverage[f'sulc_{hemi}'],
    cmap='inferno' if prevalence else 'RdBu_r',
    symmetric_cmap=False if prevalence else True,
    threshold=None,                  # unthresholded per spec
    vmax=cell_specific_vmax,
    title=f'{task} / {contrast} — {hemi} hemi',
    black_bg=False,
)
view.save_as_html(out_path)
```

Self-contained: embeds mesh, map, and plotly WebGL JS inline. Hover reveals vertex index + value. Drag rotates. Scroll zooms. No threshold slider — `view_surf` does not expose one and adding it is out of scope.

Per-hemi (not bilateral combined) viewers. Each interactive map produces one HTML per hemisphere (L + R). They rotate independently. A combined bilateral mesh would require custom plotly trimesh code; deferred unless explicitly requested.

### Per-cell render budget (8 workers per array task)

| Step | Time |
|---|---|
| Cohort 4-panel PNGs (2 maps) | ~12 sec |
| Interactive HTMLs (4 files) | ~20 sec |
| 46 subject 4-panel tiles | ~17 sec wall (8-way parallel) |
| Total per cell | ~50 sec |

Array wall time is 1h per task — comfortable.

## Dashboard HTML / JS Behavior

### Per-cell section markup (assemble script)

```html
<h2 id="{anchor}">{task} / {contrast} <small>(n_subj=46)</small></h2>
<h3>Uncorrected prevalence (z>1.96) + directionality</h3>

<div class="prev-row">
  <div class="map-cell">
    <img src="figures/{task}_{contrast}_prevalence_uncorrected.png">
    <button class="rotate-btn"
            data-l="figures/{task}_{contrast}_prevalence_uncorrected_L.html"
            data-r="figures/{task}_{contrast}_prevalence_uncorrected_R.html">
      rotate
    </button>
    <div class="iframe-holder" hidden></div>
  </div>
  <div class="map-cell">
    <img src="figures/{task}_{contrast}_directionality_uncorrected.png">
    <button class="rotate-btn"
            data-l="figures/{task}_{contrast}_directionality_uncorrected_L.html"
            data-r="figures/{task}_{contrast}_directionality_uncorrected_R.html">
      rotate
    </button>
    <div class="iframe-holder" hidden></div>
  </div>
</div>

<h3>Per-subject unthresholded z-maps</h3>
<div class="subj-grid">...46 static 4-panel PNGs...</div>
```

### Toggle JS (inlined in `_HTML_HEAD`)

Use `createElement` / `appendChild` for the iframe injection (no `innerHTML`, no string interpolation into HTML). Source URLs come from `data-l` / `data-r` attributes set by the Python assemble script — but using DOM APIs is the safer pattern regardless.

```javascript
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
```

### CSS additions

```css
.map-cell    { display: flex; flex-direction: column; gap: 4px; }
.rotate-btn  { padding: 4px 10px; cursor: pointer; font-size: 12px;
               background: #06c; color: white; border: none;
               border-radius: 3px; align-self: flex-start; }
.iframe-holder { display: flex; gap: 8px; margin-top: 8px; }
.surf-frame  { width: 480px; height: 380px; border: 1px solid #ccc; }
```

### Lifecycle guarantees

- Page load: 0 iframes alive — only static PNGs render. Existing img-click modal-zoom behavior preserved.
- Open: 2 iframes spawn for that map (L + R). Plotly loads inside each (~300KB JS, browser-cached after first viewer).
- Close: iframes removed from DOM; plotly instances garbage-collected. Memory bounded by *open* viewers, not by cell count.
- Multiple cells may be opened simultaneously for side-by-side comparison.

## Testing & Rollout

### Pre-launch smoke test

Run on one cell (`flanker:incongruent-congruent` — clear known signal):

```bash
sbatch --wait \
  --partition=russpold --time=00:20:00 --mem=12G --cpus-per-task=8 \
  --wrap="module load uv && uv --directory /home/users/logben/neuro_workflow run python \
    scripts/prevalence_subject_diagnostic.py \
    --lev1-root /scratch/users/logben/lev1_surface_pooled_46 \
    --prev-dir /scratch/users/logben/prevalence_uncorrected_n46 \
    --output-dir /scratch/users/logben/prevalence_diagnostic_smoke \
    --cells flanker:incongruent-congruent --n-jobs 8"
```

Verify visually:
- 4-panel cohort PNG laid out 2×2 with single colorbar
- 4 interactive HTMLs render in a browser (drag rotates, hover shows values)
- 46 subject tiles all 4-panel
- After assemble run, toggle button appears next to each cohort map; opens iframes on click; closes and tears down on second click
- Flanker incongruent-congruent shows expected medial-frontal signal (anterior cingulate / pre-SMA)

### Snapshot before re-launch

```bash
cp -r /scratch/users/logben/prevalence_diagnostic_all44 \
      /scratch/groups/russpold/logben/prevalence_diagnostic_all44_2panel_snapshot
```

### Re-launch

```bash
scancel 25922227 25922253                  # kill in-flight array + assemble dep
sbatch /scratch/groups/russpold/logben/prevalence_diagnostic_array.sbatch
sbatch --dependency=afterok:<new_array_id> \
  /scratch/groups/russpold/logben/prevalence_diagnostic_assemble.sbatch
```

### No unit tests added

Dashboard rendering is visual output. Smoke test + visual inspection of the smoke output is the validation. No assertable logic worth covering.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Interactive vmax mismatches static thresholded scale | Both use the same cell-specific `vmax_pctile95`. Static applies threshold, interactive shows full range. |
| Iframe `src` paths break | Use `figures/{name}.html` (relative to index.html), same pattern as existing `<img src>`. |
| `view_surf` wraps content in full-page styling that overflows iframe | Confirmed during smoke test; if it does, tighten `.surf-frame` height/width or post-process the HTML. |
| 4-panel render bloats array wall time past 1h | Budget says ~50 sec/cell. If a cell overruns, the array task simply fails for that cell — re-render via `--cells task:contrast` later. |
| Disk usage from 176 HTMLs | ~50–180MB. Acceptable. |

## Out of Scope

- Synchronized L+R rotation (independent rotation per hemi is acceptable).
- Threshold sliders inside the interactive viewer.
- Per-subject interactive tiles (46 × 44 = 2,024 viewers is too many).
- Dorsal/ventral panels (only L-lat, L-med, R-lat, R-med).
- Refactor into a shared `surface_renderer` library module.
- Threshold tuning UI on the dashboard.
- Re-rendering the existing FDR-corrected `prevalence_dashboard.py` output (separate dashboard, separate decision).

## Success Criteria

1. `/scratch/users/logben/prevalence_diagnostic_all44/index.html` renders all 44 cells with 4-panel cohort PNGs + 4-panel per-subject tiles.
2. Each cohort map has a working rotate toggle that loads and tears down L + R interactive viewers.
3. Page load (without any toggles opened) is under 5 seconds on a typical laptop.
4. The 2-panel snapshot at `$GROUP_SCRATCH` is preserved for rollback.
5. The user can spin medial cortex on the flanker / cuedTS / spatialTS / directedForgetting contrasts and form an opinion on whether real signal exists pre-FDR.
