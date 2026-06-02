"""Common-scan-set intersection across MSHBM arms.

A (session, task, run) cell enters MSHBM only if present in EVERY arm, so all
arms feed byte-identical data. Cells dropped by any arm are reported per-arm.
"""
from __future__ import annotations

Cell = tuple[str, str, str]   # (session, task, run)


def common_scan_set(arm_cells: dict[str, set[Cell]]):
    """Return (common, dropped). common = cells present in ALL arms; dropped =
    per-arm cells not in the common set. Empty input -> (set(), {})."""
    if not arm_cells:
        return set(), {}
    common = set.intersection(*arm_cells.values())
    dropped = {arm: (cells - common) for arm, cells in arm_cells.items()}
    return common, dropped
