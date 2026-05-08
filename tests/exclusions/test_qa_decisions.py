"""Tests for src/neuro_workflow/exclusions/qa_decisions.py."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_qa_decisions_generator_importable():
    """The generator module imports and exposes QADecisionsGenerator."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    assert QADecisionsGenerator.name == "qa_decisions"


def _write_tsv(path: Path, rows: list[dict]) -> None:
    """Write a minimal qa decisions TSV (subject, session, task, run, action, reason)."""
    fieldnames = ["subject", "session", "task", "run", "action", "reason"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_args(tsv_path: Path) -> "object":
    """Minimal Namespace stand-in for args (only attributes the generator reads)."""
    from argparse import Namespace
    return Namespace(decisions_tsv=tsv_path)


def test_generator_has_cli_arg_for_decisions_tsv():
    """The generator declares --decisions-tsv on its parser."""
    from argparse import ArgumentParser
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator

    parser = ArgumentParser()
    QADecisionsGenerator().add_cli_args(parser)
    args = parser.parse_args(["--decisions-tsv", "/tmp/whatever.tsv"])
    assert str(args.decisions_tsv) == "/tmp/whatever.tsv"


def test_scan_level_exclude_emits_one_entry(tmp_path):
    """A single scan-level action=exclude row -> one entry, BIDS-prefixed."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "exclude", "reason": "noisy task data"},
    ])

    entries = QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))

    assert len(entries) == 1
    e = entries[0]
    assert e == {
        "subject": "sub-s03",
        "session": "ses-02",
        "task": "task-cuedTS",
        "run": "run-1",
        "source": "qa_decisions",
        "action": "exclude",
        "reason": "qa_decisions: noisy task data (scan-level)",
    }


def test_pass_and_review_rows_skipped(tmp_path, capsys):
    """Mixed actions: only `exclude` produces entries; summary line counts the others."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "exclude", "reason": "noisy"},
        {"subject": "sub-s10", "session": "ses-01", "task": "task-flanker",
         "run": "run-1", "action": "review", "reason": "borderline RT"},
        {"subject": "sub-s19", "session": "ses-03", "task": "task-goNogo",
         "run": "run-1", "action": "pass", "reason": "looks fine"},
    ])

    entries = QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))
    captured = capsys.readouterr()

    assert len(entries) == 1
    assert entries[0]["subject"] == "sub-s03"
    assert "1 excluded" in captured.out
    assert "1 review-skipped" in captured.out
    assert "1 pass-skipped" in captured.out
