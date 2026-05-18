"""Tests for surface visualisation of per-vertex prevalence maps.

Covers:
- ``load_prevalence_outputs`` — discovery of the 8 GIFTIs (L/R × map +
  hpdi_lo + hpdi_hi + k_count) for a given (cohort, task, contrast)
  and round-trip values.
- ``apply_hpdi_mask`` — vertices with ``hpdi_lo <= threshold`` are set
  to NaN so the matplotlib surface plot renders them as transparent.
  NaNs in the input are preserved.
- ``plot_prevalence_surface`` — smoke test that the 4-panel PNG is
  written and is a non-empty PNG file.
- ``interactive_view`` — smoke test that an HTML widget is written and
  contains a recognisable nilearn signature (``surface_plot`` JS).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import nibabel as nib
import numpy as np
import pytest

# Use non-interactive backend for headless test environments.
matplotlib.use('Agg')

from neuro_workflow.analysis.prevalence.visualize import (
    apply_hpdi_mask,
    derive_basenames,
    interactive_view,
    load_prevalence_outputs,
    plot_prevalence_surface,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_gifti(path: Path, data: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    darray = nib.gifti.GiftiDataArray(
        data=data.astype(np.float32), intent='NIFTI_INTENT_NORMAL',
        datatype='NIFTI_TYPE_FLOAT32',
    )
    img = nib.gifti.GiftiImage()
    img.add_gifti_data_array(darray)
    img.to_filename(str(path))
    return path


def _write_full_prevalence_set(
    out_dir: Path,
    cohort: str,
    task: str,
    contrast: str,
    rtmodel: str,
    n_vertices: int,
    seed: int = 0,
) -> dict[str, Path]:
    """Write the 8 GIFTIs that load_prevalence_outputs expects."""
    rng = np.random.default_rng(seed)
    files: dict[str, Path] = {}
    for hemi in ('L', 'R'):
        base = (
            f'{cohort}_task-{task}_hemi-{hemi}'
            f'_contrast-{contrast}_rtmodel-{rtmodel}'
        )
        # MAP in [0, 0.8]; hpdi_lo in [0, MAP]; hpdi_hi in [MAP, 1]; k in [0, 40]
        map_arr = rng.uniform(0.0, 0.8, size=n_vertices)
        hpdi_lo = map_arr * rng.uniform(0.5, 1.0, size=n_vertices)
        hpdi_hi = map_arr + (1.0 - map_arr) * rng.uniform(0.0, 0.5, size=n_vertices)
        k_count = rng.integers(0, 41, size=n_vertices)
        files[f'map_{hemi}'] = _write_gifti(
            out_dir / f'{base}_stat-prevalence-map.func.gii', map_arr,
        )
        files[f'hpdi_lo_{hemi}'] = _write_gifti(
            out_dir / f'{base}_stat-prevalence-hpdiLo.func.gii', hpdi_lo,
        )
        files[f'hpdi_hi_{hemi}'] = _write_gifti(
            out_dir / f'{base}_stat-prevalence-hpdiHi.func.gii', hpdi_hi,
        )
        files[f'k_count_{hemi}'] = _write_gifti(
            out_dir / f'{base}_stat-prevalence-kCount.func.gii',
            k_count.astype(np.float32),
        )
    return files


# ---------------------------------------------------------------------------
# load_prevalence_outputs
# ---------------------------------------------------------------------------


def test_load_prevalence_outputs_returns_all_eight_arrays(tmp_path):
    n = 30
    _write_full_prevalence_set(
        tmp_path, 'discovery', 'flanker', 'incongruent-congruent', 'RTDur', n,
    )
    out = load_prevalence_outputs(
        tmp_path, cohort='discovery', task='flanker',
        contrast='incongruent-congruent',
    )
    for key in (
        'map_L', 'map_R', 'hpdi_lo_L', 'hpdi_lo_R',
        'hpdi_hi_L', 'hpdi_hi_R', 'k_count_L', 'k_count_R',
    ):
        assert key in out, f'Missing key: {key}'
        assert out[key].shape == (n,)


def test_load_prevalence_outputs_round_trips_values(tmp_path):
    """Values written into a known MAP GIFTI must come back unchanged."""
    map_L = np.linspace(0.0, 0.9, 25).astype(np.float32)
    map_R = np.linspace(0.9, 0.0, 25).astype(np.float32)
    base = 'cohortX_task-go_hemi-{hemi}_contrast-C_rtmodel-RTDur'
    _write_gifti(tmp_path / (base.format(hemi='L') + '_stat-prevalence-map.func.gii'), map_L)
    _write_gifti(tmp_path / (base.format(hemi='R') + '_stat-prevalence-map.func.gii'), map_R)
    # Fill the other six so the loader doesn't complain about missing files.
    for hemi in ('L', 'R'):
        zeros = np.zeros(25, dtype=np.float32)
        for suffix in ('prevalence-hpdiLo', 'prevalence-hpdiHi', 'prevalence-kCount'):
            _write_gifti(
                tmp_path / (base.format(hemi=hemi) + f'_stat-{suffix}.func.gii'),
                zeros,
            )
    out = load_prevalence_outputs(
        tmp_path, cohort='cohortX', task='go', contrast='C',
    )
    np.testing.assert_allclose(out['map_L'], map_L, rtol=1e-6)
    np.testing.assert_allclose(out['map_R'], map_R, rtol=1e-6)


def test_load_prevalence_outputs_raises_when_file_missing(tmp_path):
    """If even one of the 8 expected files is absent, raise with the
    missing filename in the error message."""
    n = 10
    files = _write_full_prevalence_set(
        tmp_path, 'discovery', 'flanker', 'incongruent-congruent', 'RTDur', n,
    )
    files['map_L'].unlink()
    with pytest.raises(FileNotFoundError, match='prevalence-map'):
        load_prevalence_outputs(
            tmp_path, cohort='discovery', task='flanker',
            contrast='incongruent-congruent',
        )


def test_load_prevalence_outputs_respects_custom_rtmodel(tmp_path):
    n = 10
    _write_full_prevalence_set(
        tmp_path, 'discovery', 'go', 'task-baseline', 'Const', n,
    )
    out = load_prevalence_outputs(
        tmp_path, cohort='discovery', task='go',
        contrast='task-baseline', rtmodel='Const',
    )
    assert out['map_L'].shape == (n,)


# ---------------------------------------------------------------------------
# apply_hpdi_mask
# ---------------------------------------------------------------------------


def test_apply_hpdi_mask_blanks_vertices_below_threshold():
    map_arr = np.array([0.1, 0.3, 0.5, 0.7])
    hpdi_lo = np.array([0.05, 0.2, 0.35, 0.5])
    out = apply_hpdi_mask(map_arr, hpdi_lo, threshold=0.3)
    # Vertices where hpdi_lo <= 0.3 should be NaN; others preserved.
    assert np.isnan(out[0])  # hpdi_lo 0.05 ≤ 0.3
    assert np.isnan(out[1])  # hpdi_lo 0.2 ≤ 0.3
    assert out[2] == pytest.approx(0.5, abs=1e-12)
    assert out[3] == pytest.approx(0.7, abs=1e-12)


def test_apply_hpdi_mask_preserves_nan_inputs():
    """NaN map values pass through; downstream plotting handles them."""
    map_arr = np.array([np.nan, 0.5])
    hpdi_lo = np.array([np.nan, 0.4])
    out = apply_hpdi_mask(map_arr, hpdi_lo, threshold=0.1)
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(0.5, abs=1e-12)


def test_apply_hpdi_mask_threshold_zero_keeps_all_positive_hpdi():
    """threshold=0 keeps every vertex with hpdi_lo > 0 unchanged."""
    map_arr = np.array([0.2, 0.4, 0.6])
    hpdi_lo = np.array([0.0, 0.1, 0.3])
    out = apply_hpdi_mask(map_arr, hpdi_lo, threshold=0.0)
    assert np.isnan(out[0])  # hpdi_lo = 0 is not strictly > 0
    assert out[1] == pytest.approx(0.4)
    assert out[2] == pytest.approx(0.6)


def test_apply_hpdi_mask_shape_mismatch_raises():
    with pytest.raises(ValueError, match='same shape'):
        apply_hpdi_mask(np.zeros(5), np.zeros(6), threshold=0.1)


# ---------------------------------------------------------------------------
# plot_prevalence_surface — smoke test
# ---------------------------------------------------------------------------


_FSAVERAGE6_VERTICES = 40962


@pytest.fixture(scope='module')
def fsaverage6():
    """Pre-fetch fsaverage6 once per module — avoids repeated downloads."""
    from nilearn import datasets
    return datasets.fetch_surf_fsaverage('fsaverage6')


def test_plot_prevalence_surface_writes_png(tmp_path, fsaverage6):
    """4-panel PNG produced by plot_prevalence_surface is non-empty."""
    rng = np.random.default_rng(0)
    map_L = rng.uniform(0.0, 0.5, _FSAVERAGE6_VERTICES).astype(np.float32)
    map_R = rng.uniform(0.0, 0.5, _FSAVERAGE6_VERTICES).astype(np.float32)
    out_path = tmp_path / 'prev.png'
    written = plot_prevalence_surface(
        map_left=map_L, map_right=map_R, output_path=out_path,
        fsaverage=fsaverage6, title='smoke',
    )
    assert written == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 1000  # a real PNG, not an empty stub
    # Sanity-check the PNG magic bytes.
    assert out_path.read_bytes()[:4] == b'\x89PNG'


def test_plot_prevalence_surface_with_threshold_writes_png(tmp_path, fsaverage6):
    """Threshold path also works end-to-end."""
    rng = np.random.default_rng(0)
    map_L = rng.uniform(0.0, 0.5, _FSAVERAGE6_VERTICES).astype(np.float32)
    map_R = rng.uniform(0.0, 0.5, _FSAVERAGE6_VERTICES).astype(np.float32)
    hpdi_lo_L = map_L * 0.6
    hpdi_lo_R = map_R * 0.6
    out_path = tmp_path / 'prev_thr.png'
    plot_prevalence_surface(
        map_left=map_L, map_right=map_R, output_path=out_path,
        hpdi_lo_left=hpdi_lo_L, hpdi_lo_right=hpdi_lo_R,
        hpdi_threshold=0.2, fsaverage=fsaverage6,
    )
    assert out_path.exists()
    assert out_path.read_bytes()[:4] == b'\x89PNG'


# ---------------------------------------------------------------------------
# interactive_view — smoke test
# ---------------------------------------------------------------------------


def test_interactive_view_writes_html(tmp_path, fsaverage6):
    rng = np.random.default_rng(0)
    map_L = rng.uniform(0.0, 0.5, _FSAVERAGE6_VERTICES).astype(np.float32)
    out_path = tmp_path / 'view_L.html'
    written = interactive_view(
        map_data=map_L, output_path=out_path, hemi='L', fsaverage=fsaverage6,
    )
    assert written == out_path
    assert out_path.exists()
    text = out_path.read_text()
    # nilearn embeds plotly + a script tag — quick fingerprint:
    assert '<html' in text.lower()
    assert len(text) > 10_000  # surface meshes are big — should be many kB


# ---------------------------------------------------------------------------
# derive_basenames
# ---------------------------------------------------------------------------


def test_derive_basenames_returns_expected_strings():
    bases = derive_basenames(
        cohort='validation', task='flanker',
        contrast='incongruent-congruent', rtmodel='RTDur',
    )
    assert bases['L'] == (
        'validation_task-flanker_hemi-L_'
        'contrast-incongruent-congruent_rtmodel-RTDur'
    )
    assert bases['R'].endswith('hemi-R_contrast-incongruent-congruent_rtmodel-RTDur')
