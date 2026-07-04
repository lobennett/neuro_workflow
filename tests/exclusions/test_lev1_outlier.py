"""Tests for src/neuro_workflow/exclusions/lev1_outlier.py (per-contrast emission)."""

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
        "subject",
        "session",
        "run",
        "task",
        "contrast",
        "outlier_pct",
        "vif",
        "flagged_outliers",
        "flagged_vif",
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


def test_strict_vif_rule_fires_per_contrast(tmp_path):
    """A non-exempt contrast with vif >= strict_vif emits one exclude-contrast entry."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s03",
                "session": "ses-01",
                "run": "1",
                "task": "stopSignal",
                "contrast": "stop_success-go",
                "outlier_pct": "2.0",
                "vif": "18.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
        ],
    )

    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    e = entries[0]
    assert e["subject"] == "sub-s03"
    assert e["session"] == "ses-01"
    assert e["task"] == "task-stopSignal"
    assert e["run"] == "run-1"
    assert e["contrast"] == "stop_success-go"
    assert e["source"] == "lev1_outlier"
    assert e["action"] == "exclude-contrast"
    assert "strict_vif" in e["reason"] and "stop_success-go" in e["reason"]
    assert e["metrics"]["vif"] == pytest.approx(18.0)
    assert e["metrics"]["rules_fired"] == ["strict_vif"]


def test_exempt_contrast_skips_vif_rules(tmp_path):
    """task-baseline / response_time with huge VIF do NOT fire the VIF rules."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s10",
                "session": "ses-02",
                "run": "1",
                "task": "shapeMatching",
                "contrast": "task-baseline",
                "outlier_pct": "2.0",
                "vif": "129.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
            {
                "subject": "sub-s10",
                "session": "ses-02",
                "run": "1",
                "task": "shapeMatching",
                "contrast": "response_time",
                "outlier_pct": "1.0",
                "vif": "40.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert entries == []  # both exempt from VIF rules; neither has high outlier_pct


def test_exempt_contrast_still_fires_outlier_rule(tmp_path):
    """An exempt contrast is still excluded if it trips the outlier-only rule."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s10",
                "session": "ses-02",
                "run": "1",
                "task": "shapeMatching",
                "contrast": "task-baseline",
                "outlier_pct": "20.0",
                "vif": "129.0",
                "flagged_outliers": "1",
                "flagged_vif": "1",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    assert entries[0]["contrast"] == "task-baseline"
    assert entries[0]["metrics"]["rules_fired"] == ["strict_outliers"]


def test_combined_rule_fires_non_exempt(tmp_path):
    """A non-exempt row with vif>=combined_vif AND outlier_pct>=combined_outlier_pct."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s10",
                "session": "ses-02",
                "run": "1",
                "task": "cuedTS",
                "contrast": "cue_switch_cost",
                "outlier_pct": "11.0",
                "vif": "11.0",
                "flagged_outliers": "1",
                "flagged_vif": "1",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    assert "combined" in entries[0]["metrics"]["rules_fired"]
    assert entries[0]["action"] == "exclude-contrast"


def test_strict_outliers_rule_fires(tmp_path):
    """A row with outlier_pct >= strict_outlier_pct fires strict_outliers."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s19",
                "session": "ses-03",
                "run": "1",
                "task": "flanker",
                "contrast": "incongruent-congruent",
                "outlier_pct": "18.0",
                "vif": "4.0",
                "flagged_outliers": "1",
                "flagged_vif": "0",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    assert "strict_outliers" in entries[0]["reason"]
    assert entries[0]["contrast"] == "incongruent-congruent"


def test_below_all_thresholds_emits_nothing(tmp_path):
    """A row that fails all three rules produces no entry."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s29",
                "session": "ses-04",
                "run": "1",
                "task": "goNogo",
                "contrast": "go",
                "outlier_pct": "8.0",
                "vif": "8.0",
                "flagged_outliers": "0",
                "flagged_vif": "0",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert entries == []


def test_multiple_contrasts_emit_separate_entries(tmp_path):
    """Two flagged contrasts on one scan -> two entries; an exempt high-VIF row -> none."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s03",
                "session": "ses-02",
                "run": "1",
                "task": "cuedTS",
                "contrast": "cue_switch_cost",
                "outlier_pct": "2.0",
                "vif": "18.09",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
            {
                "subject": "sub-s03",
                "session": "ses-02",
                "run": "1",
                "task": "cuedTS",
                "contrast": "task_switch_cost",
                "outlier_pct": "12.3",
                "vif": "11.5",
                "flagged_outliers": "1",
                "flagged_vif": "1",
            },
            # exempt contrast with huge VIF — must NOT emit
            {
                "subject": "sub-s03",
                "session": "ses-02",
                "run": "1",
                "task": "cuedTS",
                "contrast": "task-baseline",
                "outlier_pct": "1.0",
                "vif": "90.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 2
    contrasts = {e["contrast"] for e in entries}
    assert contrasts == {"cue_switch_cost", "task_switch_cost"}
    assert all(e["action"] == "exclude-contrast" for e in entries)
    assert all(e["run"] == "run-1" and e["task"] == "task-cuedTS" for e in entries)


def test_threshold_configurability(tmp_path):
    """Independent threshold tuning on a NON-exempt contrast."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s10",
                "session": "ses-02",
                "run": "1",
                "task": "cuedTS",
                "contrast": "cue_switch_cost",
                "outlier_pct": "11.0",
                "vif": "11.0",
                "flagged_outliers": "1",
                "flagged_vif": "1",
            },
        ],
    )
    e_default = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert "combined" in e_default[0]["metrics"]["rules_fired"]

    args_loose = _make_args(csv_path, combined_vif=20.0)
    assert Lev1OutlierGenerator().generate("discovery", {}, args_loose) == []

    args_tight = _make_args(csv_path, combined_vif=20.0, strict_vif=10.0)
    e_tight = Lev1OutlierGenerator().generate("discovery", {}, args_tight)
    assert len(e_tight) == 1
    assert "strict_vif" in e_tight[0]["metrics"]["rules_fired"]


def test_empty_outlier_pct_treated_as_zero(tmp_path):
    """outlier_pct empty string -> 0.0; with low vif, no rule fires."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s43",
                "session": "ses-01",
                "run": "1",
                "task": "nBack",
                "contrast": "twoBack-oneBack",
                "outlier_pct": "",
                "vif": "4.0",
                "flagged_outliers": "0",
                "flagged_vif": "0",
            },
        ],
    )
    assert Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path)) == []


def test_missing_csv_raises_clear_error(tmp_path):
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    bogus = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match=str(bogus)):
        Lev1OutlierGenerator().generate("discovery", {}, _make_args(bogus))


def test_empty_csv_returns_empty_list(tmp_path):
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(csv_path, [])
    assert Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path)) == []


def test_generator_output_flows_through_compile(tmp_path, monkeypatch):
    """End-to-end: per-contrast entries validate, save, and survive compile."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s03",
                "session": "ses-02",
                "run": "1",
                "task": "cuedTS",
                "contrast": "cue_switch_cost",
                "outlier_pct": "2.0",
                "vif": "18.09",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1

    core_excl.save_source_entries("discovery", "lev1_outlier", entries)
    compiled = core_excl.compile_exclusions("discovery")

    assert len(compiled) == 1
    assert compiled[0]["source"] == "lev1_outlier"
    assert compiled[0]["action"] == "exclude-contrast"
    assert compiled[0]["contrast"] == "cue_switch_cost"
    # contrast-level exclusion must NOT mark the scan excluded (run still runs in lev1)
    assert not core_excl.is_excluded("sub-s03", "ses-02", "task-cuedTS", "run-1", compiled)


def test_exclude_contrast_not_rendered_to_bidsignore():
    """A contrast-level entry produces no .bidsignore glob (it's not a BOLD removal)."""
    from neuro_workflow.core.exclusions_render import _entry_to_bidsignore_glob

    entry = {
        "subject": "sub-s10",
        "session": "ses-02",
        "task": "shapeMatching",
        "run": "run-1",
        "contrast": "DDS",
        "action": "exclude-contrast",
        "source": "lev1_outlier",
        "reason": "lev1_outlier: DDS vif=18 (strict_vif)",
    }
    assert _entry_to_bidsignore_glob(entry) is None


def test_end_to_end_on_real_discovery_cohort_qc():
    """Smoke: generator runs against real cohort QC output; per-contrast shape sound."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    real_csv = Path("/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv")
    if not real_csv.is_file():
        pytest.skip(f"discovery cohort QC output not present at {real_csv}")

    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(real_csv))
    for e in entries:
        assert e["source"] == "lev1_outlier"
        assert e["action"] == "exclude-contrast"
        assert e["subject"].startswith("sub-")
        assert e["contrast"]  # non-empty
        # exempt contrasts must never appear via a VIF rule
        if e["contrast"] in {"task-baseline", "response_time"}:
            assert "strict_outliers" in e["metrics"]["rules_fired"]
            assert "strict_vif" not in e["metrics"]["rules_fired"]
            assert "combined" not in e["metrics"]["rules_fired"]


def test_dataset_filter_drops_non_member_subjects(tmp_path):
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s03",
                "session": "ses-01",
                "run": "1",
                "task": "stopSignal",
                "contrast": "go-stop",
                "outlier_pct": "1.0",
                "vif": "18.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
            {
                "subject": "sub-s1035",
                "session": "ses-02",
                "run": "1",
                "task": "flanker",
                "contrast": "incongruent-congruent",
                "outlier_pct": "1.0",
                "vif": "20.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
        ],
    )
    entries = Lev1OutlierGenerator().generate("discovery", {}, _make_args(csv_path))
    assert len(entries) == 1
    assert entries[0]["subject"] == "sub-s03"


def test_unknown_dataset_fails_loud(tmp_path):
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    csv_path = tmp_path / "lev1_outliers.csv"
    _write_csv(
        csv_path,
        [
            {
                "subject": "sub-s03",
                "session": "ses-01",
                "run": "1",
                "task": "stopSignal",
                "contrast": "go-stop",
                "outlier_pct": "1.0",
                "vif": "18.0",
                "flagged_outliers": "0",
                "flagged_vif": "1",
            },
        ],
    )
    with pytest.raises(ValueError, match="anything"):
        Lev1OutlierGenerator().generate("anything", {}, _make_args(csv_path))
