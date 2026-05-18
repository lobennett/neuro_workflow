"""Surface visualisation of per-vertex Bayesian prevalence maps.

Renders a 4-panel figure (L + R hemispheres × lateral + medial views)
of the per-vertex MAP prevalence on the fsaverage6 inflated surface.
Optionally masks vertices whose 96%-HPDI lower bound falls below a
caller-supplied floor — those vertices become transparent, so the figure
shows only locations where the posterior puts most of its mass above
that floor (the standard "credibly elevated" filter from Ince 2021).

Also exposes an interactive HTML view (one hemisphere at a time) via
``nilearn.plotting.view_surf``.

The module is independent of MSHBM outputs — it consumes the prevalence
GIFTIs produced by :mod:`neuro_workflow.analysis.prevalence.run` and is
safe to call before any individual parcellation is available.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np

from neuro_workflow.analysis.prevalence.aggregate import load_gifti_data

logger = logging.getLogger(__name__)


_SUFFIX_FOR_KEY = {
    'map':     'prevalence-map',
    'hpdi_lo': 'prevalence-hpdiLo',
    'hpdi_hi': 'prevalence-hpdiHi',
    'k_count': 'prevalence-kCount',
}


# ---------------------------------------------------------------------------
# Filename derivation + loading
# ---------------------------------------------------------------------------


def derive_basenames(
    cohort: str,
    task: str,
    contrast: str,
    rtmodel: str = 'RTDur',
) -> dict[str, str]:
    """Return the per-hemisphere basename used by ``run.py`` output GIFTIs."""
    return {
        h: f'{cohort}_task-{task}_hemi-{h}_contrast-{contrast}_rtmodel-{rtmodel}'
        for h in ('L', 'R')
    }


def load_prevalence_outputs(
    prevalence_dir: Path,
    cohort: str,
    task: str,
    contrast: str,
    rtmodel: str = 'RTDur',
) -> dict[str, np.ndarray]:
    """Load all 8 prevalence GIFTIs (L/R × MAP + HPDI bounds + k-count).

    Returns a dict keyed by ``{stat}_{hemi}`` (e.g. ``map_L``, ``hpdi_lo_R``).

    Raises:
        FileNotFoundError: if any expected file is missing — the error
            message names which file so the caller can rerun the
            generation step that produces it.
    """
    prevalence_dir = Path(prevalence_dir)
    bases = derive_basenames(cohort, task, contrast, rtmodel)

    out: dict[str, np.ndarray] = {}
    for hemi, base in bases.items():
        for key, suffix in _SUFFIX_FOR_KEY.items():
            path = prevalence_dir / f'{base}_stat-{suffix}.func.gii'
            if not path.exists():
                raise FileNotFoundError(
                    f'Expected prevalence file not found: {path}.  '
                    f'Run neuro_workflow.analysis.prevalence.run first.'
                )
            out[f'{key}_{hemi}'] = load_gifti_data(path)
    return out


# ---------------------------------------------------------------------------
# HPDI-based thresholding
# ---------------------------------------------------------------------------


def apply_hpdi_mask(
    map_arr: np.ndarray,
    hpdi_lo: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Mask vertices with ``hpdi_lo <= threshold`` by setting them NaN.

    Args:
        map_arr: per-vertex MAP prevalence values.
        hpdi_lo: per-vertex HPDI lower bound (same shape as ``map_arr``).
        threshold: vertices with ``hpdi_lo <= threshold`` are blanked.

    Returns:
        A new array (same shape) with masked vertices set to NaN.  NaNs
        in the inputs are preserved.
    """
    if map_arr.shape != hpdi_lo.shape:
        raise ValueError(
            f'map_arr and hpdi_lo must have the same shape; '
            f'got {map_arr.shape} vs {hpdi_lo.shape}'
        )
    out = map_arr.astype(np.float64, copy=True)
    keep = np.isfinite(hpdi_lo) & (hpdi_lo > threshold)
    out[~keep] = np.nan
    return out


# ---------------------------------------------------------------------------
# 4-panel matplotlib figure
# ---------------------------------------------------------------------------


def _fetch_fsaverage6() -> Any:
    from nilearn import datasets
    return datasets.fetch_surf_fsaverage('fsaverage6')


def plot_prevalence_surface(
    map_left: np.ndarray,
    map_right: np.ndarray,
    output_path: Path,
    *,
    hpdi_lo_left: Optional[np.ndarray] = None,
    hpdi_lo_right: Optional[np.ndarray] = None,
    hpdi_threshold: Optional[float] = None,
    cmap: str = 'inferno',
    vmin: float = 0.0,
    vmax: Optional[float] = None,
    title: Optional[str] = None,
    surf_type: str = 'inflated',
    fsaverage: Optional[Any] = None,
    dpi: int = 150,
) -> Path:
    """Render a 4-panel surface figure of per-vertex MAP prevalence.

    Layout::

        ┌─────────────┬─────────────┐
        │  L lateral  │  R lateral  │
        ├─────────────┼─────────────┤
        │  L medial   │  R medial   │
        └─────────────┴─────────────┘

    Args:
        map_left, map_right: per-vertex MAP prevalence for each hemi
            (must match the fsaverage6 vertex count, 40962).
        output_path: where to write the PNG.
        hpdi_lo_left, hpdi_lo_right, hpdi_threshold: if all three are
            provided, vertices with HPDI lower bound ≤ threshold are
            blanked (NaN) before plotting — only "credibly elevated"
            vertices are coloured.
        cmap: matplotlib colormap.  Prevalence is positive-only so a
            sequential map ('inferno', 'magma', 'viridis', 'Reds') is
            more honest than the bipolar RdBu_r default.
        vmin, vmax: colormap clipping.  ``vmax=None`` → use 95th
            percentile of the (post-mask) data, ignoring NaN.
        title: figure title.
        surf_type: which fsaverage6 surface to render on
            ('inflated', 'pial', 'white').  Defaults to 'inflated'.
        fsaverage: pre-fetched fsaverage6 Bunch; if None, fetched on
            demand via ``nilearn.datasets.fetch_surf_fsaverage``.
        dpi: PNG resolution.

    Returns:
        ``output_path`` (for chaining).
    """
    import matplotlib.pyplot as plt
    from nilearn import plotting

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fsaverage is None:
        fsaverage = _fetch_fsaverage6()

    # Optional HPDI mask.
    if hpdi_threshold is not None:
        if hpdi_lo_left is None or hpdi_lo_right is None:
            raise ValueError(
                'hpdi_threshold given without both hpdi_lo arrays; '
                'pass hpdi_lo_left= and hpdi_lo_right= or drop the threshold.'
            )
        map_left = apply_hpdi_mask(map_left, hpdi_lo_left, hpdi_threshold)
        map_right = apply_hpdi_mask(map_right, hpdi_lo_right, hpdi_threshold)

    # Auto-vmax to 95th percentile of finite data (across both hemis) so
    # most of the dynamic range is allocated to the bulk of the
    # prevalence distribution rather than a few outlier vertices.
    if vmax is None:
        finite = np.concatenate([
            map_left[np.isfinite(map_left)],
            map_right[np.isfinite(map_right)],
        ])
        vmax = float(np.percentile(finite, 95)) if finite.size else 1.0
        vmax = max(vmax, vmin + 1e-6)  # guard against degenerate ranges

    fig, axes = plt.subplots(
        2, 2, figsize=(12, 8),
        subplot_kw={'projection': '3d'},
        gridspec_kw={'hspace': 0.0, 'wspace': 0.0},
    )

    panel_specs = [
        # (row, col, hemi, view, stat_map, mesh_key, bg_key)
        (0, 0, 'left',  'lateral', map_left,  f'{surf_type[:4]}_left',  'sulc_left'),
        (0, 1, 'right', 'lateral', map_right, f'{surf_type[:4]}_right', 'sulc_right'),
        (1, 0, 'left',  'medial',  map_left,  f'{surf_type[:4]}_left',  'sulc_left'),
        (1, 1, 'right', 'medial',  map_right, f'{surf_type[:4]}_right', 'sulc_right'),
    ]

    for row, col, hemi, view, stat_map, mesh_key, bg_key in panel_specs:
        plotting.plot_surf_stat_map(
            surf_mesh=fsaverage[mesh_key],
            stat_map=stat_map,
            bg_map=fsaverage[bg_key],
            hemi=hemi,
            view=view,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            colorbar=(col == 1 and row == 0),  # one colourbar, top-right
            symmetric_cbar=False,
            bg_on_data=True,
            axes=axes[row, col],
            figure=fig,
        )

    if title:
        fig.suptitle(title, fontsize=14, y=0.98)

    fig.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    logger.info('Wrote prevalence figure: %s', output_path)
    return output_path


# ---------------------------------------------------------------------------
# Interactive HTML view (one hemisphere at a time)
# ---------------------------------------------------------------------------


def interactive_view(
    map_data: np.ndarray,
    output_path: Path,
    *,
    hemi: str,
    title: Optional[str] = None,
    cmap: str = 'inferno',
    vmin: float = 0.0,
    vmax: Optional[float] = None,
    surf_type: str = 'inflated',
    fsaverage: Optional[Any] = None,
) -> Path:
    """Save a draggable / rotatable HTML widget for one hemisphere.

    The HTML can be opened locally in a browser; nilearn embeds plotly
    and the whole mesh inline, so the file is self-contained (no CDN).
    """
    from nilearn import plotting

    hemi = hemi.upper()
    if hemi not in ('L', 'R'):
        raise ValueError(f'hemi must be "L" or "R"; got {hemi!r}')

    if fsaverage is None:
        fsaverage = _fetch_fsaverage6()

    mesh_key = f'{surf_type[:4]}_{"left" if hemi == "L" else "right"}'
    bg_key = f'sulc_{"left" if hemi == "L" else "right"}'

    if vmax is None:
        finite = map_data[np.isfinite(map_data)]
        vmax = float(np.percentile(finite, 95)) if finite.size else 1.0
        vmax = max(vmax, vmin + 1e-6)

    view = plotting.view_surf(
        surf_mesh=fsaverage[mesh_key],
        surf_map=map_data,
        bg_map=fsaverage[bg_key],
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        symmetric_cmap=False,
        title=title,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    view.save_as_html(str(output_path))
    logger.info('Wrote interactive view: %s', output_path)
    return output_path
