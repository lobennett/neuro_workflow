from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa


def find_monotonic_point(onset_series) -> Optional[int]:
    """Find the index where the onset series becomes monotonically increasing.

    Returns None if no such point exists (requires at least 2 remaining elements).
    """
    for i in range(len(onset_series) - 1):
        if onset_series.iloc[i:].is_monotonic_increasing:
            return i
    return None


class NegEventsQa:
    name = "neg-events"
    description = "Report event files with non-monotonically increasing onsets"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass  # no extra args needed

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if pd is None:
            print("Error: 'pandas' required for 'neg-events'. Install with: uv pip install -e \".[qa]\"")
            return

        bids_dir = Path(dataset_config["bids_dir"])
        all_files = list(bids_dir.glob("sub-*/ses-*/func/*event*.tsv"))

        print(f"Found {len(all_files)} event files total")
        print("\nNon-monotonic event files and their trim points:")
        print("=" * 60)

        count = 0
        for file_path in sorted(all_files):
            try:
                df = pd.read_csv(file_path, sep="\t")
                if "onset" not in df.columns:
                    print(f"WARNING: {file_path.name} - no 'onset' column found")
                    continue
                if not df["onset"].is_monotonic_increasing:
                    monotonic_index = find_monotonic_point(df["onset"])
                    count += 1
                    print(f"{file_path.name}")
                    print(f"  Path: {file_path}")
                    print(f"  Trim index: {monotonic_index}")
                    print(f"  Total rows: {len(df)}")
                    if monotonic_index is not None:
                        print(f"  Rows to keep: {len(df) - monotonic_index}")
                    print()
            except Exception as e:
                print(f"ERROR reading {file_path.name}: {e}")

        print(f"\nSummary: {count} files with non-monotonic onsets")


register_qa(NegEventsQa())
