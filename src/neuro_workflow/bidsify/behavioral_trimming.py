# File: src/neuro_workflow/bidsify/behavioral_trimming.py
"""Trim behavioral CSV files at time_elapsed cutoff."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

__all__ = ["trim_behavioral_csv"]


def trim_behavioral_csv(
    csv_file: Path,
    cutoff_time_ms: float,
) -> bool:
    """
    Trim behavioral CSV file at time_elapsed cutoff.

    Keeps all rows where time_elapsed <= cutoff_time_ms.

    Args:
        csv_file: Path to behavioral CSV file
        cutoff_time_ms: Cutoff time in milliseconds

    Returns:
        True if trimming was applied, False if file missing
    """
    if not csv_file.exists():
        logger.warning(f"Behavioral CSV not found: {csv_file}")
        return False

    # Load CSV
    df = pd.read_csv(csv_file)

    if 'time_elapsed' not in df.columns:
        logger.warning(f"No 'time_elapsed' column in {csv_file}")
        return False

    initial_count = len(df)

    # Trim at cutoff
    df = df[df['time_elapsed'] <= cutoff_time_ms].reset_index(drop=True)

    dropped = initial_count - len(df)

    # Write back to file
    df.to_csv(csv_file, index=False)

    logger.info(
        f"Trimmed behavioral CSV: removed {dropped} rows, "
        f"kept {len(df)} rows (cutoff: {cutoff_time_ms} ms)"
    )

    return True
