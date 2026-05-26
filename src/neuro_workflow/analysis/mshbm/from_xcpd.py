"""Helpers for converting XCP-D denoised CIFTI outputs into MSHBM fsaverage6 NIfTIs.

Pure-Python utilities — wb_command orchestration lives in
``scripts/mshbm_from_xcpd.py`` to keep this module easy to test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_CELL_RE = re.compile(
    r'^sub-(?P<sub>[A-Za-z0-9]+)_'
    r'(?P<ses>ses-[A-Za-z0-9]+)_'
    r'task-(?P<task>[A-Za-z0-9]+)_'
    r'space-fsLR_den-91k_desc-denoised_bold\.dtseries\.nii$'
)


@dataclass(frozen=True)
class Cell:
    """One (session, task) cell for one subject."""
    session: str
    task: str
    dtseries: Path


def discover_xcpd_cells(subject_root: Path) -> list[Cell]:
    """Find all `desc-denoised` CIFTIs for a subject, per-task concatenated only.

    Skips per-run variants (filenames containing `_run-N_`) — XCP-D was run
    with --combine-runs, so the no-run-suffix file is the concatenation.
    """
    cells: list[Cell] = []
    for path in sorted(Path(subject_root).rglob('*_desc-denoised_bold.dtseries.nii')):
        m = _CELL_RE.match(path.name)
        if not m:
            continue
        cells.append(Cell(session=m.group('ses'), task=m.group('task'), dtseries=path))
    return cells
