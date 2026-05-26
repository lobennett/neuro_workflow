"""Helpers for converting XCP-D denoised CIFTI outputs into MSHBM fsaverage6 NIfTIs.

Pure-Python utilities — wb_command orchestration lives in
``scripts/mshbm_from_xcpd.py`` to keep this module easy to test.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np


# Concatenated (combine-runs) filenames have no _run-N token.
# Per-run filenames have _run-N before _space.
_CELL_RE = re.compile(
    r'^sub-(?P<sub>[A-Za-z0-9]+)_'
    r'(?P<ses>ses-[A-Za-z0-9]+)_'
    r'task-(?P<task>[A-Za-z0-9]+)'
    r'(?:_run-(?P<run>\d+))?'
    r'_space-fsLR_den-91k_desc-denoised_bold\.dtseries\.nii$'
)


@dataclass(frozen=True)
class Cell:
    """One (session, task) cell for one subject.

    ``dtseries_paths`` is always a list. Length-1 means we found either the
    XCP-D --combine-runs concatenated file OR a single per-run file. Length>1
    means XCP-D emitted multiple ``_run-N`` files for this cell without a
    concatenated variant — the driver concatenates them via
    ``wb_command -cifti-merge`` before downstream processing.
    """
    session: str
    task: str
    dtseries_paths: tuple[Path, ...]


def gifti_to_mshbm_nifti(gifti_path: Path, out_path: Path) -> Path:
    """Load a per-vertex GIFTI time series and write (V, 1, 1, T) NIfTI.

    MSHBM's CBIG MATLAB wrapper consumes per-hemi time series shaped as
    a 4-D NIfTI with the time axis last and singleton y/z. This helper
    builds that volume from a GIFTI with one DataArray per TR.

    NaN values (introduced by wb_command -metric-resample at vertices
    that landed in resampling holes) are zeroed so MSHBM gets a single
    medial-wall sentinel (0) instead of a mixed zero/NaN convention.
    """
    gii = nib.load(str(gifti_path))
    cols = [da.data.astype(np.float32) for da in gii.darrays]
    if not cols:
        raise ValueError(f'No data arrays in {gifti_path}')
    arr = np.stack(cols, axis=-1)  # (V, T)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    arr_4d = arr.reshape(arr.shape[0], 1, 1, arr.shape[1])
    img = nib.Nifti1Image(arr_4d, affine=np.eye(4))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(out_path))
    return out_path


def discover_xcpd_cells(subject_root: Path) -> list[Cell]:
    """Find all `desc-denoised` CIFTIs for a subject, one per (session, task).

    XCP-D --combine-runs emits a no-run-suffix concatenated file ONLY when a
    (session, task) has >1 run. For single-run cells it leaves only the
    `_run-N` variant. This helper prefers the concatenated file when present,
    otherwise falls back to the unique per-run file. If a cell has multiple
    per-run files but no concatenation (anomalous), the lowest run number wins.
    """
    # Group all matches by (session, task)
    groups: dict[tuple[str, str], list[tuple[int | None, Path]]] = {}
    for path in Path(subject_root).rglob('*_desc-denoised_bold.dtseries.nii'):
        m = _CELL_RE.match(path.name)
        if not m:
            continue
        key = (m.group('ses'), m.group('task'))
        run = int(m.group('run')) if m.group('run') else None
        groups.setdefault(key, []).append((run, path))

    cells: list[Cell] = []
    for (session, task), entries in sorted(groups.items()):
        # Prefer the concatenated variant (run is None) — covers it standalone.
        concat = [p for r, p in entries if r is None]
        if concat:
            paths = (concat[0],)
        else:
            # No concatenation: return ALL per-run files (sorted by run number)
            # so the driver can wb_command -cifti-merge them.
            per_run = sorted([(r, p) for r, p in entries if r is not None])
            paths = tuple(p for _, p in per_run)
        cells.append(Cell(session=session, task=task, dtseries_paths=paths))
    return cells


def _templateflow_root() -> Path:
    """Resolve the templateflow cache root, honoring TEMPLATEFLOW_HOME."""
    root = os.environ.get('TEMPLATEFLOW_HOME')
    if root:
        return Path(root)
    return Path.home() / '.cache' / 'templateflow'


def templateflow_paths() -> dict[str, dict[str, Path]]:
    """Return the fsLR / fsaverage sphere + pial + white paths per hemi.

    Keys: 'L', 'R' → dict with keys 'fsLR_sphere' (32k registered to
    fsaverage), 'fsaverage6_sphere' (41k), 'fsaverage6_pial', 'fsaverage6_white'.
    """
    root = _templateflow_root()
    out: dict[str, dict[str, Path]] = {}
    for hemi in ('L', 'R'):
        out[hemi] = {
            'fsLR_sphere': root / 'tpl-fsLR' /
                f'tpl-fsLR_space-fsaverage_hemi-{hemi}_den-32k_sphere.surf.gii',
            'fsaverage6_sphere': root / 'tpl-fsaverage' /
                f'tpl-fsaverage_hemi-{hemi}_den-41k_sphere.surf.gii',
            'fsaverage6_pial': root / 'tpl-fsaverage' /
                f'tpl-fsaverage_hemi-{hemi}_den-41k_pial.surf.gii',
            'fsaverage6_white': root / 'tpl-fsaverage' /
                f'tpl-fsaverage_hemi-{hemi}_den-41k_white.surf.gii',
        }
    return out
