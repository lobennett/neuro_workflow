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
