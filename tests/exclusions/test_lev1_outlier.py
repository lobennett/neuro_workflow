"""Tests for src/neuro_workflow/exclusions/lev1_outlier.py."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_lev1_outlier_generator_importable():
    """The generator module imports and exposes Lev1OutlierGenerator."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    assert Lev1OutlierGenerator.name == "lev1_outlier"


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write a minimal lev1_outliers.csv with the column set the generator expects."""
    fieldnames = [
        "subject", "session", "run", "task", "contrast",
        "outlier_pct", "vif", "flagged_outliers", "flagged_vif",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_args(csv_path: Path, **overrides) -> "object":
    """Minimal Namespace stand-in for args (only attributes the generator reads)."""
    from argparse import Namespace
    base = dict(
        lev1_outliers_csv=csv_path,
        combined_vif=10.0,
        combined_outlier_pct=10.0,
        strict_vif=15.0,
        strict_outlier_pct=15.0,
    )
    base.update(overrides)
    return Namespace(**base)


def test_strict_vif_rule_fires(tmp_path):
    """A scan-contrast with vif >= strict_vif emits an exclusion entry."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s03", "session": "ses-01", "run": "1", "task": "stopSignal",
         "contrast": "stop_success-go", "outlier_pct": "2.0", "vif": "18.0",
         "flagged_outliers": "0", "flagged_vif": "1"},
    ])

    entries = Lev1OutlierGenerator().generate(
        "discovery", {}, _make_args(csv_path)
    )
    assert len(entries) == 1
    e = entries[0]
    assert e["subject"] == "sub-s03"
    assert e["session"] == "ses-01"
    assert e["task"] == "task-stopSignal"
    assert e["run"] == "run-1"
    assert e["source"] == "lev1_outlier"
    assert e["action"] == "exclude"
    assert "strict_vif" in e["reason"]
    assert "stop_success-go" in e["reason"]
