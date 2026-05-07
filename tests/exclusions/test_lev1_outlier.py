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


def test_combined_rule_fires(tmp_path):
    """A row with vif>=combined_vif AND outlier_pct>=combined_outlier_pct fires combined."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s10", "session": "ses-02", "run": "1", "task": "cuedTS",
         "contrast": "response_time", "outlier_pct": "11.0", "vif": "11.0",
         "flagged_outliers": "1", "flagged_vif": "1"},
    ])
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    assert "combined" in entries[0]["reason"]
    assert "combined" in entries[0]["metrics"]["rules_fired"]


def test_strict_outliers_rule_fires(tmp_path):
    """A row with outlier_pct >= strict_outlier_pct fires strict_outliers."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s19", "session": "ses-03", "run": "1", "task": "flanker",
         "contrast": "incongruent-congruent", "outlier_pct": "18.0", "vif": "4.0",
         "flagged_outliers": "1", "flagged_vif": "0"},
    ])
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    assert "strict_outliers" in entries[0]["reason"]


def test_below_all_thresholds_emits_nothing(tmp_path):
    """A row that fails all three rules produces no entry."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s29", "session": "ses-04", "run": "1", "task": "goNogo",
         "contrast": "go", "outlier_pct": "8.0", "vif": "8.0",
         "flagged_outliers": "0", "flagged_vif": "0"},
    ])
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert entries == []


def test_per_scan_aggregation_collapses_multiple_contrasts(tmp_path):
    """Two flagged contrasts on the same (subject, session, task, run) -> one entry."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s03", "session": "ses-02", "run": "1", "task": "cuedTS",
         "contrast": "response_time", "outlier_pct": "2.0", "vif": "18.09",
         "flagged_outliers": "0", "flagged_vif": "1"},
        {"subject": "sub-s03", "session": "ses-02", "run": "1", "task": "cuedTS",
         "contrast": "cue_switch_cost", "outlier_pct": "12.3", "vif": "11.5",
         "flagged_outliers": "1", "flagged_vif": "1"},
        # An untouched contrast on the same scan — should NOT show in reason.
        {"subject": "sub-s03", "session": "ses-02", "run": "1", "task": "cuedTS",
         "contrast": "task-baseline", "outlier_pct": "1.0", "vif": "1.2",
         "flagged_outliers": "0", "flagged_vif": "0"},
    ])
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    e = entries[0]
    assert "response_time" in e["reason"]
    assert "cue_switch_cost" in e["reason"]
    assert "task-baseline" not in e["reason"]
    assert e["metrics"]["n_flagged_contrasts"] == 2
    assert set(e["metrics"]["rules_fired"]) == {"strict_vif", "combined"}
    assert e["metrics"]["max_vif"] == pytest.approx(18.09)
    assert e["metrics"]["max_outlier_pct"] == pytest.approx(12.3)


def test_threshold_configurability(tmp_path):
    """Bumping combined_vif to 20 makes a vif=11 row stop firing combined.

    The same row with strict_vif=12 still fires strict_vif. Demonstrates
    each threshold can be tuned independently.
    """
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s10", "session": "ses-02", "run": "1", "task": "cuedTS",
         "contrast": "response_time", "outlier_pct": "11.0", "vif": "11.0",
         "flagged_outliers": "1", "flagged_vif": "1"},
    ])

    # default thresholds: combined fires
    e_default = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert "combined" in e_default[0]["metrics"]["rules_fired"]

    # combined_vif bumped to 20: combined no longer fires; outlier_pct=11 < strict 15;
    # vif=11 < strict 15 -> nothing fires, no entry.
    args_loose = _make_args(csv_path, combined_vif=20.0)
    e_loose = Lev1OutlierGenerator().generate("discovery", {}, args_loose)
    assert e_loose == []

    # strict_vif bumped down to 10: strict_vif fires for vif=11 even though combined
    # still fires too. Just confirms independent threshold tuning works.
    args_tight = _make_args(csv_path, combined_vif=20.0, strict_vif=10.0)
    e_tight = Lev1OutlierGenerator().generate("discovery", {}, args_tight)
    assert len(e_tight) == 1
    assert "strict_vif" in e_tight[0]["metrics"]["rules_fired"]


def test_empty_outlier_pct_treated_as_zero(tmp_path):
    """Cohort-of-1 / degenerate case: outlier_pct is empty string. Must not fire rules."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        # outlier_pct empty (cohort QC couldn't compute) and vif=4 -> no rule fires.
        {"subject": "sub-s43", "session": "ses-01", "run": "1", "task": "nBack",
         "contrast": "twoBack-oneBack", "outlier_pct": "", "vif": "4.0",
         "flagged_outliers": "0", "flagged_vif": "0"},
    ])
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert entries == []


def test_missing_csv_raises_clear_error(tmp_path):
    """Missing input CSV -> FileNotFoundError with the path in the message."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    bogus = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match=str(bogus)):
        Lev1OutlierGenerator().generate("discovery", {}, _make_args(bogus))


def test_empty_csv_returns_empty_list(tmp_path):
    """CSV with only the header row returns []."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [])  # header only, no rows
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert entries == []


def test_generator_output_flows_through_compile(tmp_path, monkeypatch):
    """End-to-end through compile_exclusions: generator entries appear in compiled output."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    from neuro_workflow.core import exclusions as core_excl

    # Redirect EXCLUSIONS_DIR to a tmp path so compile_exclusions writes there.
    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

    # Generate entries from a small CSV
    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [
        {"subject": "sub-s03", "session": "ses-02", "run": "1", "task": "cuedTS",
         "contrast": "response_time", "outlier_pct": "2.0", "vif": "18.09",
         "flagged_outliers": "0", "flagged_vif": "1"},
    ])
    entries = Lev1OutlierGenerator().generate(
        "discovery", {}, _make_args(csv_path)
    )
    assert len(entries) == 1

    # Save to sources/<dataset>/lev1_outlier.json (matches what cmd_exclusions_generate does)
    core_excl.save_source_entries("discovery", "lev1_outlier", entries)

    # Run compile (load_overrides returns [] for missing file, so no overrides.json needed)
    compiled = core_excl.compile_exclusions("discovery")

    # Compiled output should contain our entry, with source preserved
    assert len(compiled) == 1
    assert compiled[0]["source"] == "lev1_outlier"
    assert compiled[0]["subject"] == "sub-s03"
    assert compiled[0]["task"] == "task-cuedTS"
    assert compiled[0]["action"] == "exclude"
