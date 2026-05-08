"""QA decisions exclusion generator.

Reads the qa_report decisions TSV (subject|session|task|run|action|reason) and
emits per-scan exclusion entries for action=exclude rows. Subject-level
decisions (session/task/run = '-') are expanded via the BIDS BOLD glob.
pass/review rows are counted in a stdout summary and skipped.
"""
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator


class QADecisionsGenerator:
    name = "qa_decisions"
    description = (
        "Auto-exclude scans flagged action=exclude in the qa_report decisions TSV. "
        "Subject-level decisions are expanded to per-scan entries via BIDS glob."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        # Not argparse-required: every generator's args land on the same shared
        # subparser (lesson from PR #6). Runtime guard in generate() raises a
        # clear FileNotFoundError when this source is selected.
        parser.add_argument(
            "--decisions-tsv", type=Path,
            help="Path to qa_report decisions TSV "
                 "(required when source=qa_decisions).",
        )

    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        if args.decisions_tsv is None:
            raise FileNotFoundError(
                "qa_decisions generator requires --decisions-tsv"
            )
        return []


register_generator(QADecisionsGenerator())
