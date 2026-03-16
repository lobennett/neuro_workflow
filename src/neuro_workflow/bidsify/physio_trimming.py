# File: src/neuro_workflow/bidsify/physio_trimming.py
"""Trim physiological data to match BOLD trimming (dummy scans and behavioral cutoff)."""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["trim_physio_data", "update_physio_json"]


def get_sampling_frequency(json_path: Path) -> int:
    """
    Extract sampling frequency from physio JSON sidecar.

    Args:
        json_path: Path to physio JSON sidecar

    Returns:
        Sampling frequency in Hz (default: 100 if not found)
    """
    with open(json_path) as f:
        data = json.load(f)
    return int(data.get("SamplingFrequency", 100))


def trim_physio_data(
    physio_tsv_gz: Path,
    physio_json: Path,
    dummy_scans: int = 7,
    tr: float = 1.49,
    behavioral_cutoff_ms: Optional[float] = None,
) -> bool:
    """
    Trim physio data to match BOLD trimming.

    Removes dummy scan samples and optionally trims at behavioral cutoff.
    Updates StartTime in JSON sidecar to reflect trimming.

    Args:
        physio_tsv_gz: Path to gzipped physio TSV file
        physio_json: Path to physio JSON sidecar
        dummy_scans: Number of dummy TRs to remove (default: 7)
        tr: Repetition time in seconds (default: 1.49)
        behavioral_cutoff_ms: Optional behavioral cutoff in milliseconds

    Returns:
        True if trimming was applied, False if file missing
    """
    if not physio_tsv_gz.exists():
        logger.warning(f"Physio file not found: {physio_tsv_gz}")
        return False

    if not physio_json.exists():
        logger.warning(f"Physio JSON not found: {physio_json}")
        return False

    # Calculate dummy offset in milliseconds
    dummy_offset_ms = dummy_scans * tr * 1000

    # Get sampling frequency to calculate sample count
    sampling_freq = get_sampling_frequency(physio_json)
    samples_per_ms = sampling_freq / 1000.0
    samples_to_skip = int(dummy_offset_ms * samples_per_ms)

    # Read original physio data
    with gzip.open(physio_tsv_gz, 'rt') as f:
        lines = f.readlines()

    if not lines:
        logger.warning(f"Empty physio file: {physio_tsv_gz}")
        return False

    header = lines[0]
    data_lines = lines[1:]

    # Skip dummy samples
    trimmed_lines = data_lines[samples_to_skip:]

    # Apply behavioral cutoff if specified
    applied_behavioral_cutoff = False
    if behavioral_cutoff_ms is not None:
        # Calculate how many samples to keep
        samples_to_keep = int(behavioral_cutoff_ms * samples_per_ms) - samples_to_skip
        if samples_to_keep <= 0:
            logger.warning(
                f"behavioral_cutoff_ms ({behavioral_cutoff_ms}ms) is less than "
                f"dummy_offset_ms ({dummy_offset_ms:.0f}ms), skipping behavioral cutoff"
            )
        else:
            trimmed_lines = trimmed_lines[:samples_to_keep]
            applied_behavioral_cutoff = True

    # Write trimmed data back
    with gzip.open(physio_tsv_gz, 'wt') as f:
        f.write(header)
        f.writelines(trimmed_lines)

    # Update JSON sidecar
    update_physio_json(
        physio_json,
        dummy_offset_ms=dummy_offset_ms,
        dummy_scans=dummy_scans,
        behavioral_cutoff_ms=behavioral_cutoff_ms if applied_behavioral_cutoff else None,
    )

    logger.info(
        f"Trimmed physio: removed {samples_to_skip} samples "
        f"({dummy_offset_ms:.0f} ms), kept {len(trimmed_lines)} samples"
    )

    return True


def update_physio_json(
    json_path: Path,
    dummy_offset_ms: float,
    dummy_scans: int = 7,
    behavioral_cutoff_ms: Optional[float] = None,
) -> None:
    """
    Update physio JSON sidecar with trimming metadata.

    Args:
        json_path: Path to physio JSON sidecar
        dummy_offset_ms: Dummy scan offset in milliseconds
        dummy_scans: Number of dummy scans removed (default: 7)
        behavioral_cutoff_ms: Optional behavioral cutoff in milliseconds
    """
    with open(json_path) as f:
        sidecar = json.load(f)

    # Store original StartTime
    original_start_time = sidecar.get("StartTime", 0.0)

    # Update with new StartTime (in seconds)
    sidecar["StartTime"] = dummy_offset_ms / 1000.0
    sidecar["OriginalStartTime"] = original_start_time
    sidecar["DummyScansRemoved"] = dummy_scans

    if behavioral_cutoff_ms is not None:
        sidecar["BehavioralTrimApplied"] = True
        sidecar["BehavioralTrimPointMs"] = behavioral_cutoff_ms

    with open(json_path, 'w') as f:
        json.dump(sidecar, f, indent=2)
