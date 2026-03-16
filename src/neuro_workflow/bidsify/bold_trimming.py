# File: src/neuro_workflow/bidsify/bold_trimming.py
"""Trim BOLD NIfTI files and events.tsv to remove dummies and behavioral cutoffs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import pandas as pd

logger = logging.getLogger(__name__)

__all__ = ["trim_bold_nifti", "trim_events_tsv"]


def trim_bold_nifti(
    bold_file: Path,
    dummy_scans: int = 7,
    behavioral_cutoff_trs: Optional[int] = None,
) -> bool:
    """
    Trim BOLD NIfTI file to remove dummy scans and optionally behavioral cutoff.

    Args:
        bold_file: Path to BOLD NIfTI file
        dummy_scans: Number of dummy volumes to remove from start
        behavioral_cutoff_trs: If provided, trim to this number of TRs

    Returns:
        True if trimming was applied, False if file missing
    """
    if not bold_file.exists():
        logger.warning(f"BOLD file not found: {bold_file}")
        return False

    # Load NIfTI
    img = nib.load(bold_file)
    data = img.get_fdata()

    if len(data.shape) != 4:
        logger.warning(f"BOLD file is not 4D: {bold_file}")
        return False

    num_volumes = data.shape[3]

    # Remove dummy scans
    start_idx = dummy_scans
    end_idx = num_volumes

    # Apply behavioral cutoff if specified
    if behavioral_cutoff_trs is not None:
        end_idx = dummy_scans + behavioral_cutoff_trs
        end_idx = min(end_idx, num_volumes)

    # Extract trimmed data
    trimmed_data = data[:, :, :, start_idx:end_idx]

    # Create new NIfTI with trimmed data
    trimmed_img = nib.Nifti1Image(trimmed_data, img.affine, img.header)

    # Save back to original file
    nib.save(trimmed_img, bold_file)

    logger.info(
        f"Trimmed BOLD: removed {dummy_scans} dummies, "
        f"kept {trimmed_data.shape[3]} volumes"
    )

    return True


def trim_events_tsv(
    events_file: Path,
    dummy_scans: int = 7,
    tr: float = 1.49,
    behavioral_cutoff_trs: Optional[int] = None,
) -> bool:
    """
    Trim events TSV file to match BOLD trimming.

    Adjusts onsets by -(dummy_scans * tr) and removes events with negative onsets.

    Args:
        events_file: Path to events TSV file
        dummy_scans: Number of dummy volumes removed from BOLD
        tr: Repetition time in seconds
        behavioral_cutoff_trs: If provided, filter to events before this TR

    Returns:
        True if trimming was applied, False if file missing
    """
    if not events_file.exists():
        logger.warning(f"Events file not found: {events_file}")
        return False

    # Load events
    events = pd.read_csv(events_file, sep='\t')

    # Adjust onsets for dummy removal
    dummy_offset = dummy_scans * tr
    events['onset'] -= dummy_offset

    # Remove events with negative onsets (occurred during dummies)
    initial_count = len(events)
    events = events[events['onset'] >= 0].reset_index(drop=True)
    dropped = initial_count - len(events)

    if dropped > 0:
        logger.info(f"Dropped {dropped} events occurring during dummy scans")

    # Apply behavioral cutoff if specified
    if behavioral_cutoff_trs is not None:
        behavioral_cutoff_s = behavioral_cutoff_trs * tr
        initial_count = len(events)
        events = events[events['onset'] < behavioral_cutoff_s].reset_index(drop=True)
        dropped = initial_count - len(events)

        if dropped > 0:
            logger.info(f"Dropped {dropped} events after behavioral cutoff")

    # Write back to file
    events.to_csv(events_file, sep='\t', index=False)

    logger.info(f"Trimmed events: {len(events)} events remain")

    return True
