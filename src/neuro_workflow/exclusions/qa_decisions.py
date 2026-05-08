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
from neuro_workflow.qa.decisions import ScanKey, load_decisions


def _norm_sub(s: str) -> str:
    return s if s.startswith("sub-") else f"sub-{s}"


def _norm_ent(value: str, prefix: str) -> str:
    """Normalize a BIDS entity to the `<prefix>-<value>` form."""
    return value if value.startswith(f"{prefix}-") else f"{prefix}-{value}"


def _entry_from_scan_key(key: ScanKey, reason: str) -> dict:
    return {
        "subject": _norm_sub(key.subject),
        "session": _norm_ent(key.session, "ses"),
        "task": _norm_ent(key.task, "task"),
        "run": _norm_ent(key.run, "run"),
        "source": "qa_decisions",
        "action": "exclude",
        "reason": f"qa_decisions: {reason} (scan-level)",
    }


class QADecisionsGenerator:
    name = "qa_decisions"
    description = (
        "Auto-exclude scans flagged action=exclude in the qa_report decisions TSV. "
        "Subject-level decisions are expanded to per-scan entries via BIDS glob."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        # Not argparse-required (shared subparser).
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
        if not args.decisions_tsv.is_file():
            raise FileNotFoundError(
                f"qa_decisions: TSV not found: {args.decisions_tsv}"
            )

        decisions = load_decisions(args.decisions_tsv)
        sample = load_dataset_subjects(dataset_config)

        entries: list[dict] = []
        n_scan = n_expanded = n_subj_rows = n_review = n_pass = 0

        for key, decision in decisions.items():
            if decision.action == "review":
                n_review += 1
                continue
            if decision.action == "pass":
                n_pass += 1
                continue
            # decision.action == "exclude"
            if isinstance(key, ScanKey):
                if sample is not None and _norm_sub(key.subject) not in sample:
                    continue
                entries.append(_entry_from_scan_key(key, decision.reason))
                n_scan += 1
            # subject-level expansion follows in Task 6

        entries.sort(key=lambda e: (e["subject"], e["session"], e["task"], e["run"]))

        n_excluded = len(entries)
        print(
            f"qa_decisions: {n_excluded} excluded "
            f"({n_scan} scan-level, {n_expanded} expanded from {n_subj_rows} subject-level), "
            f"{n_review} review-skipped, {n_pass} pass-skipped"
        )
        return entries


register_generator(QADecisionsGenerator())
