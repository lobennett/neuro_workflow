"""Convert gephysio gear CSV outputs to BIDS physio format."""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

from neuro_workflow.bidsify.bids_writer import bids_filename

logger = logging.getLogger(__name__)

# Gephysio gear output file naming
_CHANNEL_CONFIG = {
    "cardiac": {
        "data_file": "PPG_FltData.csv",
        "trig_file": "PPG_FltTrig.csv",
        "sampling_frequency": 100,
        "description": "continuous pulse measurement, amplitude normalized by gephysio gear to range [0, 1]",
    },
    "respiratory": {
        "data_file": "RESP_FltData.csv",
        "trig_file": "RESP_FltTrig.csv",
        "sampling_frequency": 25,
        "description": "continuous measurements by respiration belt, amplitude normalized by gephysio gear to range [0, 1]",
    },
}


def parse_flt_data(csv_path: Path) -> tuple[list[int], list[float]]:
    """Parse a gephysio FltData CSV file.

    Format: ``timestamp_ms,amplitude`` per line (no header).

    Returns:
        (timestamps_ms, amplitudes) — parallel lists.
    """
    timestamps: list[int] = []
    amplitudes: list[float] = []
    text = csv_path.read_text().strip()
    if not text:
        return timestamps, amplitudes
    for line in text.split("\n"):
        if not line.strip():  # Skip blank lines
            continue
        parts = line.split(",")
        timestamps.append(int(parts[0]))
        amplitudes.append(float(parts[1]))
    return timestamps, amplitudes


def parse_flt_trig(trig_path: Path) -> list[int]:
    """Parse a gephysio FltTrig CSV file.

    Format: one timestamp_ms per line (no header).
    """
    text = trig_path.read_text().strip()
    if not text:
        return []
    return [int(line) for line in text.split("\n") if line.strip()]


def build_trigger_column(timestamps: list[int], trigger_times: list[int]) -> list[int]:
    """Build a binary trigger column: 1 at trigger timestamps, 0 elsewhere."""
    trigger_set = set(trigger_times)
    return [1 if ts in trigger_set else 0 for ts in timestamps]


def convert_physio_to_bids(
    input_dir: Path,
    output_dir: Path,
    subject: str,
    session: str,
    task: str,
    run: int,
    channel: str,
) -> bool:
    """Convert one channel of gephysio output to BIDS physio files.

    Args:
        input_dir: Directory containing gephysio CSV outputs.
        output_dir: BIDS func/ directory to write to.
        subject: Subject label (e.g. "s1175").
        session: Session label (e.g. "ses-02").
        task: Task name (e.g. "rest").
        run: Run number.
        channel: "cardiac" or "respiratory".

    Returns:
        True if files were written, False if source data was missing.
    """
    cfg = _CHANNEL_CONFIG[channel]
    data_path = input_dir / cfg["data_file"]
    trig_path = input_dir / cfg["trig_file"]

    if not data_path.exists():
        logger.debug("No %s data file at %s", channel, data_path)
        return False

    timestamps, amplitudes = parse_flt_data(data_path)
    if not timestamps:
        logger.warning("Empty %s data file: %s", channel, data_path)
        return False

    trigger_times = parse_flt_trig(trig_path) if trig_path.exists() else []
    triggers = build_trigger_column(timestamps, trigger_times)

    # Build BIDS filename
    stem = bids_filename(subject, session, task=task, run=run, recording=channel, suffix="physio")

    # Write gzipped TSV
    output_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = output_dir / f"{stem}.tsv.gz"
    with gzip.open(tsv_path, "wt") as f:
        f.write(f"{channel}\ttrigger\n")
        for amp, trig in zip(amplitudes, triggers):
            f.write(f"{amp}\t{trig}\n")

    # Write JSON sidecar
    json_path = output_dir / f"{stem}.json"
    sidecar = {
        "SamplingFrequency": cfg["sampling_frequency"],
        "StartTime": 0.0,
        "Columns": [channel, "trigger"],
        "Manufacturer": "BIOPAC",
        channel: {
            "Description": cfg["description"],
            "Units": "arbitrary",
        },
        "trigger": {
            "Description": "continuous measurement of the scanner trigger signal",
        },
    }
    json_path.write_text(json.dumps(sidecar, indent=2))

    return True
