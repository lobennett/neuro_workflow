"""Behavioral exclusion generator — runs behavioral QC and produces exclusion entries.

Scoping note: the behavioral CSVs live in a SHARED sourcedata tree
(``in_scanner_behavior`` holds all cohorts' subjects), so this generator filters
its output to the dataset's canonical roster via ``load_dataset_subjects``,
exactly like ``qa_decisions`` / ``lev1_outlier``. (The earlier "dataset-scoped by
construction" assumption — that ``{bids_dir}/sourcedata`` holds only the cohort's
behavioral — does not hold for this layout and silently cross-contaminated
cohorts; this filter closes that.)
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator


class BehavioralGenerator:
    name = "behavioral"
    description = "Generate exclusions from behavioral QC (accuracy, RT, omission thresholds)"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--behavioral-dir",
            required=False,
            default=None,
            help="Path to sourcedata behavioral directory (default: {bids_dir}/sourcedata)",
        )

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        try:
            from neuro_workflow.events.qc import run_qc
        except ImportError:
            print(
                "Error: pandas required for behavioral generator. Install with: uv pip install -e '.[events]'"
            )
            return []

        bids_dir = Path(dataset_config["bids_dir"])
        behavioral_dir = (
            Path(args.behavioral_dir)
            if getattr(args, "behavioral_dir", None)
            else bids_dir / "sourcedata"
        )

        # Scope to the dataset roster: the shared behavioral tree holds all
        # cohorts' subjects, so restrict QC to this dataset's subjects (fail-loud
        # on an unknown dataset, via load_dataset_subjects).
        roster = load_dataset_subjects(dataset_name)
        exclusion_entries, trim_entries = run_qc(
            behavioral_dir=behavioral_dir,
            bids_dir=bids_dir,
            subjects=sorted(roster),
        )

        # Source field is set by the exclusions system when saving, but include for clarity
        for entry in exclusion_entries:
            entry["source"] = "behavioral-qc"

        print(
            f"Behavioral QC: {len(exclusion_entries)} exclusions, {len(trim_entries)} trim entries "
            f"(roster-scoped to {len(roster)} subjects of dataset '{dataset_name}')"
        )
        return exclusion_entries


register_generator(BehavioralGenerator())
