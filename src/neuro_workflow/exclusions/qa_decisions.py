"""QA decisions exclusion generator.

Reads the qa_report decisions TSV (subject|session|task|run|action|reason) and
emits per-scan exclusion entries for action=exclude rows. Subject-level
decisions (session/task/run = '-') are expanded via the BIDS BOLD glob.
pass/review rows are counted in a stdout summary and skipped.
"""
from __future__ import annotations

import re
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


_BOLD_RE = re.compile(
    r"^(?P<subject>sub-[A-Za-z0-9]+)"
    r"_(?P<session>ses-[A-Za-z0-9]+)"
    r"_task-(?P<task>[A-Za-z0-9]+)"
    r"_run-(?P<run>[A-Za-z0-9]+)"
    # Tolerate any intervening BIDS entities (notably `_echo-N` on this
    # multi-echo dataset, also `_acq-`, `_dir-`, `_part-`, ...) before `_bold`.
    # Without this the regex matched no real BOLD file and subject-level
    # exclusions silently expanded to nothing.
    r"(?:_[A-Za-z0-9]+-[A-Za-z0-9]+)*"
    r"_bold\.nii\.gz$"
)


def _expand_subject_to_entries(
    subject: str, reason: str, bids_dir: Path,
) -> list[dict]:
    """Glob the dataset BIDS dir for `subject`'s BOLD files and emit one
    exclusion entry per scan. Multi-echo acquisitions yield one BOLD file per
    echo; we collapse them to a single (subject, session, task, run) entry."""
    sub = subject if subject.startswith("sub-") else f"sub-{subject}"
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict] = []
    for bold in (bids_dir / sub).glob("ses-*/func/*_bold.nii.gz"):
        m = _BOLD_RE.match(bold.name)
        if not m:
            continue
        key = (
            m.group("subject"),
            m.group("session"),
            f"task-{m.group('task')}",
            f"run-{m.group('run')}",
        )
        if key in seen:  # dedupe across echoes
            continue
        seen.add(key)
        out.append({
            "subject": key[0],
            "session": key[1],
            "task": key[2],
            "run": key[3],
            "source": "qa_decisions",
            "action": "exclude",
            "reason": f"qa_decisions: {reason} (subject-level)",
        })
    return out


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
        # Canonical roster from pipeline_config.json `samples` (fail-loud on an
        # unknown dataset). Cross-sample rows (e.g. validation subjects in a
        # discovery compile) are dropped here — the bug this fix closes.
        sample = load_dataset_subjects(dataset_name)

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
                if _norm_sub(key.subject) not in sample:
                    continue
                entries.append(_entry_from_scan_key(key, decision.reason))
                n_scan += 1
            else:
                # subject-level: key is a bare subject string.
                if _norm_sub(key) not in sample:
                    continue
                n_subj_rows += 1
                bids_dir = Path(dataset_config["bids_dir"])
                expanded = _expand_subject_to_entries(key, decision.reason, bids_dir)
                entries.extend(expanded)
                n_expanded += len(expanded)

        entries.sort(key=lambda e: (e["subject"], e["session"], e["task"], e["run"]))

        n_excluded = len(entries)
        print(
            f"qa_decisions: {n_excluded} excluded "
            f"({n_scan} scan-level, {n_expanded} expanded from {n_subj_rows} subject-level), "
            f"{n_review} review-skipped, {n_pass} pass-skipped"
        )
        return entries


register_generator(QADecisionsGenerator())
