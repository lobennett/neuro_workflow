"""Neg-events exclusion generator: detects non-monotonic event file onsets."""
from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

from neuro_workflow.exclusions.base import register_generator


def _find_monotonic_point(onset_series) -> Optional[int]:
    """Find the index where onsets become monotonically increasing."""
    for i in range(len(onset_series)):
        if onset_series.iloc[i:].is_monotonic_increasing:
            return i
    return None


def _parse_event_filename(filename: str) -> dict | None:
    """Extract BIDS entities from an event filename."""
    sub = re.search(r'(sub-\w+)', filename)
    ses = re.search(r'(ses-\w+)', filename)
    task = re.search(r'task-(\w+)', filename)
    run = re.search(r'run-(\w+)', filename)
    if not sub or not ses or not task:
        return None
    return {
        "subject": sub.group(1),
        "session": ses.group(1),
        "task": f"task-{task.group(1)}",
        "run": f"run-{run.group(1)}" if run else "run-1",
    }


class NegEventsGenerator:
    name = "neg-events"
    description = "Detect non-monotonic event file onsets and generate trim/exclude entries"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass  # no extra args

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        if pd is None:
            print("Error: 'pandas' required for neg-events generator. Install with: uv pip install -e \".[qa]\"")
            return []

        bids_dir = Path(dataset_config["bids_dir"])
        event_files = sorted(bids_dir.glob("sub-*/ses-*/func/*event*.tsv"))
        if not event_files:
            print(f"No event files found in {bids_dir}")
            return []

        entries = []
        for fp in event_files:
            try:
                df = pd.read_csv(fp, sep="\t")
                if "onset" not in df.columns:
                    continue
                if df["onset"].is_monotonic_increasing:
                    continue

                parsed = _parse_event_filename(fp.name)
                if not parsed:
                    continue

                trim_idx = _find_monotonic_point(df["onset"])
                total_rows = len(df)

                if trim_idx is not None:
                    rows_to_keep = total_rows - trim_idx
                    salvage_ratio = rows_to_keep / total_rows
                    action = "trim" if salvage_ratio > 0.5 else "exclude"
                else:
                    rows_to_keep = 0
                    trim_idx = total_rows
                    action = "exclude"

                entries.append({
                    "subject": parsed["subject"],
                    "session": parsed["session"],
                    "task": parsed["task"],
                    "run": parsed["run"],
                    "source": "neg-events",
                    "action": action,
                    "reason": f"Non-monotonic onsets, {rows_to_keep / total_rows * 100:.1f}% salvageable",
                    "metrics": {
                        "onset_trim_index": trim_idx,
                        "total_rows": total_rows,
                        "rows_to_keep": rows_to_keep,
                    },
                })
            except Exception as e:
                print(f"Error reading {fp.name}: {e}")

        print(f"Neg-events generator: {len(entries)} entries from {len(event_files)} event files")
        return entries


register_generator(NegEventsGenerator())
