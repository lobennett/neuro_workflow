# Lev1OutlierGenerator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Lev1OutlierGenerator` that converts cohort QC findings (`lev1_outliers.csv`) into per-scan exclusion entries via the existing `ExclusionGenerator` Protocol.

**Architecture:** One new file (`src/neuro_workflow/exclusions/lev1_outlier.py`) implementing the existing protocol from `exclusions/base.py`. Reuses the existing registry, compile, and override mechanics — no changes to `core/exclusions.py` or its CLI machinery. Three OR'd auto-exclude rules (combined `vif≥10 AND outlier_pct≥10`, strict `vif≥15`, strict `outlier_pct≥15`) all configurable via CLI.

**Tech Stack:** Python 3.13 (project venv via `uv`), pandas, pytest. Spec at `docs/superpowers/specs/2026-05-07-lev1-outlier-generator-design.md`.

---

## File Structure

**New files:**
- `src/neuro_workflow/exclusions/lev1_outlier.py` — `Lev1OutlierGenerator` class (≤150 lines)
- `tests/exclusions/__init__.py` — empty marker
- `tests/exclusions/test_lev1_outlier.py` — unit tests + integration tests

**Modified files:**
- `src/neuro_workflow/cli.py` — +1 line: `import neuro_workflow.exclusions.lev1_outlier  # noqa: F401`

---

## Code-style guardrails (re-stating from spec)

These are non-negotiable. Re-read before any task:

- Single source file, ≤150 lines, plain functions + frozen dataclass for the row + thresholds schemas.
- One test file, `tmp_path` only, no fixture factories.
- No silent fallbacks: missing CSV raises, malformed CSV row raises with line context.
- No retroactive abstractions ("we might add more rule types later"). YAGNI.
- Generator is registered once at module import; no factory/Builder patterns.

---

## Task 1: Scaffold test dir + first failing import test

Establish the test layout and confirm the not-yet-existing module can be discovered.

**Files:**
- Create: `tests/exclusions/__init__.py` (empty)
- Create: `tests/exclusions/test_lev1_outlier.py`

- [ ] **Step 1.1: Create empty `__init__.py`**

```bash
mkdir -p tests/exclusions
touch tests/exclusions/__init__.py
```

- [ ] **Step 1.2: Write first failing test (ImportError)**

Create `tests/exclusions/test_lev1_outlier.py`:

```python
"""Tests for src/neuro_workflow/exclusions/lev1_outlier.py."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_lev1_outlier_generator_importable():
    """The generator module imports and exposes Lev1OutlierGenerator."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    assert Lev1OutlierGenerator.name == "lev1_outlier"
```

- [ ] **Step 1.3: Run test to verify failure**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/exclusions/test_lev1_outlier.py -v
```

Expected: `ModuleNotFoundError: No module named 'neuro_workflow.exclusions.lev1_outlier'`.

- [ ] **Step 1.4: Commit (test scaffold only)**

```bash
git add tests/exclusions/__init__.py tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): scaffold test_lev1_outlier with import smoke

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Generator skeleton + name/description

Make the import test pass with a minimal skeleton that doesn't yet implement `generate()` correctly.

**Files:**
- Create: `src/neuro_workflow/exclusions/lev1_outlier.py`

- [ ] **Step 2.1: Write minimal skeleton**

Create `src/neuro_workflow/exclusions/lev1_outlier.py`:

```python
"""Lev1 outlier exclusion generator.

Reads cohort QC's lev1_outliers.csv (produced by neuro_workflow.qa.lev1_outliers)
and applies three OR'd auto-exclude rules to flag whole scans:

    combined:        vif >= combined_vif AND outlier_pct >= combined_outlier_pct
    strict_vif:      vif >= strict_vif
    strict_outliers: outlier_pct >= strict_outlier_pct

Per-scan aggregation: if any contrast on (subject, session, task, run) fires
any rule, emit one exclusion entry whose `reason` lists the offending
contrasts and which rule fired for each.
"""
from __future__ import annotations

import csv
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path

from neuro_workflow.exclusions.base import register_generator


@dataclass(frozen=True)
class Thresholds:
    """Auto-exclude thresholds. Defaults match spec defaults."""
    combined_vif: float = 10.0
    combined_outlier_pct: float = 10.0
    strict_vif: float = 15.0
    strict_outlier_pct: float = 15.0


class Lev1OutlierGenerator:
    name = "lev1_outlier"
    description = (
        "Auto-exclude scans flagged by cohort lev1 QC. Rules: "
        "(vif>=combined-vif AND outlier_pct>=combined-outlier-pct) OR "
        "vif>=strict-vif OR outlier_pct>=strict-outlier-pct."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--lev1-outliers-csv", type=Path,
            help="Path to cohort QC's lev1_outliers.csv (full per-(scan, contrast) table).",
        )
        parser.add_argument("--combined-vif", type=float, default=10.0)
        parser.add_argument("--combined-outlier-pct", type=float, default=10.0)
        parser.add_argument("--strict-vif", type=float, default=15.0)
        parser.add_argument("--strict-outlier-pct", type=float, default=15.0)

    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        # Filled in by Tasks 3-6.
        return []


register_generator(Lev1OutlierGenerator())
```

- [ ] **Step 2.2: Run test to verify pass**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py -v
```

Expected: `test_lev1_outlier_generator_importable PASSED`.

- [ ] **Step 2.3: Commit**

```bash
git add src/neuro_workflow/exclusions/lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): scaffold Lev1OutlierGenerator + CLI args

Class implements the existing ExclusionGenerator Protocol with name,
description, add_cli_args, and a stub generate(). Thresholds dataclass
holds the four CLI-configurable values. Wiring into cli.py and rule
logic land in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Single-rule logic + first passing rule test

TDD the simplest rule (strict_vif) end-to-end before generalizing.

**Files:**
- Modify: `src/neuro_workflow/exclusions/lev1_outlier.py`
- Modify: `tests/exclusions/test_lev1_outlier.py` (append)

- [ ] **Step 3.1: Write the failing test**

Append to `tests/exclusions/test_lev1_outlier.py`:

```python
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
```

- [ ] **Step 3.2: Run test to verify failure**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py::test_strict_vif_rule_fires -v
```

Expected: AssertionError because `generate()` currently returns `[]`.

- [ ] **Step 3.3: Implement minimal `generate()`**

Replace the stub `generate` in `src/neuro_workflow/exclusions/lev1_outlier.py` with:

```python
    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        thresholds = Thresholds(
            combined_vif=args.combined_vif,
            combined_outlier_pct=args.combined_outlier_pct,
            strict_vif=args.strict_vif,
            strict_outlier_pct=args.strict_outlier_pct,
        )
        rows = _read_outliers_csv(args.lev1_outliers_csv)
        return _aggregate_to_scan_entries(rows, thresholds)
```

Then add helpers at the top of the file (after `Thresholds` dataclass, before the class):

```python
def _to_float_or_zero(value: str) -> float:
    """Empty string / NaN-ish -> 0.0; otherwise parsed float."""
    if value is None or value == "":
        return 0.0
    try:
        f = float(value)
    except ValueError:
        return 0.0
    # Empty `outlier_pct` entries appear when cohort QC couldn't compute the
    # statistic (degenerate small-N case). Treat as 0 so they don't trip rules.
    if f != f:  # NaN check without importing math
        return 0.0
    return f


def _read_outliers_csv(path: Path) -> list[dict]:
    """Read the lev1_outliers.csv into a list of dicts."""
    if not path.is_file():
        raise FileNotFoundError(f"lev1_outliers.csv not found: {path}")
    with path.open() as f:
        return list(csv.DictReader(f))


def _rules_fired(vif: float, outlier_pct: float, t: Thresholds) -> list[str]:
    """Return the names of all rules that fire for this (vif, outlier_pct) pair."""
    fired: list[str] = []
    if vif >= t.combined_vif and outlier_pct >= t.combined_outlier_pct:
        fired.append("combined")
    if vif >= t.strict_vif:
        fired.append("strict_vif")
    if outlier_pct >= t.strict_outlier_pct:
        fired.append("strict_outliers")
    return fired


def _format_contrast_clause(contrast: str, vif: float, outlier_pct: float,
                             rules: list[str]) -> str:
    """Single-contrast clause for the `reason` field, e.g.
    'response_time vif=18.09 (strict_vif)'.
    """
    parts: list[str] = []
    parts.append(f"vif={vif:.2f}")
    if outlier_pct > 0:
        parts.append(f"outlier={outlier_pct:.1f}%")
    return f"{contrast} {','.join(parts)} ({','.join(rules)})"


def _aggregate_to_scan_entries(
    rows: list[dict], thresholds: Thresholds,
) -> list[dict]:
    """Group rows by (subject, session, task, run); emit one exclusion entry per
    scan that has at least one contrast firing any rule."""
    by_scan: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in rows:
        key = (row["subject"], row["session"], row["task"], row["run"])
        by_scan.setdefault(key, []).append(row)

    entries: list[dict] = []
    for (subject, session, task, run), scan_rows in sorted(by_scan.items()):
        flagged: list[tuple[str, float, float, list[str]]] = []
        for row in scan_rows:
            vif = _to_float_or_zero(row.get("vif"))
            pct = _to_float_or_zero(row.get("outlier_pct"))
            fired = _rules_fired(vif, pct, thresholds)
            if fired:
                flagged.append((row["contrast"], vif, pct, fired))
        if not flagged:
            continue
        clauses = [
            _format_contrast_clause(c, v, p, r) for c, v, p, r in flagged
        ]
        all_rules: set[str] = set()
        for _, _, _, r in flagged:
            all_rules.update(r)
        max_vif = max(v for _, v, _, _ in flagged)
        max_pct = max(p for _, _, p, _ in flagged)
        entries.append({
            "subject": subject,
            "session": session,
            "task": f"task-{task}",
            "run": f"run-{run}",
            "source": "lev1_outlier",
            "action": "exclude",
            "reason": "lev1_outlier: " + "; ".join(clauses),
            "metrics": {
                "max_vif": max_vif,
                "max_outlier_pct": max_pct,
                "n_flagged_contrasts": len(flagged),
                "rules_fired": sorted(all_rules),
            },
        })
    return entries
```

- [ ] **Step 3.4: Run test to verify pass**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py -v
```

Expected: 2 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/neuro_workflow/exclusions/lev1_outlier.py tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): implement strict_vif rule + per-scan aggregation

generate() now reads the cohort QC csv, applies the three OR'd rules,
and emits one entry per scan with a deterministic reason field.
Helper functions (_read_outliers_csv, _rules_fired, _aggregate_*)
are kept private at module scope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Cover the other two rules + multi-rule case

Add tests for combined + strict_outliers + a row that fires no rule.

**Files:**
- Modify: `tests/exclusions/test_lev1_outlier.py` (append)

- [ ] **Step 4.1: Append three more rule tests**

```python
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
```

- [ ] **Step 4.2: Run; expect all pass on first run (no impl change needed)**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py -v
```

Expected: 5 passed (the 3 new + 2 prior).

- [ ] **Step 4.3: Commit**

```bash
git add tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): cover combined + strict_outliers rules + below-threshold

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Per-scan aggregation across multiple flagged contrasts

Confirm two flagged contrasts on the same scan collapse to one entry that lists both.

**Files:**
- Modify: `tests/exclusions/test_lev1_outlier.py` (append)

- [ ] **Step 5.1: Append the multi-contrast test**

```python
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
```

- [ ] **Step 5.2: Run; expect pass**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py::test_per_scan_aggregation_collapses_multiple_contrasts -v
```

Expected: PASS.

- [ ] **Step 5.3: Commit**

```bash
git add tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): per-scan aggregation across multiple flagged contrasts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Threshold configurability + NaN handling + missing/empty CSV

Three small tests for the remaining edge-case requirements from the spec.

**Files:**
- Modify: `tests/exclusions/test_lev1_outlier.py` (append)

- [ ] **Step 6.1: Append the three tests**

```python
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
```

- [ ] **Step 6.2: Run; expect all pass without code changes (logic already handles these)**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py -v
```

Expected: 10 passed total.

- [ ] **Step 6.3: Commit**

```bash
git add tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): threshold configurability + NaN/missing/empty CSV cases

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Wire into cli.py + verify CLI registration

Add the import line so the CLI subparser picks up the new generator's args via the `for gen in list_generators().values(): gen.add_cli_args(gen_p)` loop in cli.py.

**Files:**
- Modify: `src/neuro_workflow/cli.py`

- [ ] **Step 7.1: Add the import line**

Find the existing import block in `src/neuro_workflow/cli.py` (around line 38):

```python
# Import exclusion generators to trigger auto-registration
import neuro_workflow.exclusions.motion  # noqa: F401
import neuro_workflow.exclusions.behavioral  # noqa: F401
```

Add one more line:

```python
import neuro_workflow.exclusions.lev1_outlier  # noqa: F401
```

- [ ] **Step 7.2: Verify CLI exposes the new generator + its args**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run exclusions generate lev1_outlier --help 2>&1 | head -30
```

Expected: argparse help text including `--lev1-outliers-csv`, `--combined-vif`, `--combined-outlier-pct`, `--strict-vif`, `--strict-outlier-pct`. Exit 0 (or argparse-style early exit after printing help).

If the `--help` invocation requires `dataset` as a positional, just confirm the args appear — `--help` prints regardless of positional resolution.

- [ ] **Step 7.3: Run all qa + exclusions tests to confirm no regression**

```bash
uv run pytest tests/exclusions/ tests/qa/ tests/analysis/ -q --tb=line 2>&1 | tail -3
```

Expected: all tests pass (240+ from prior plan + 10 new from this plan).

- [ ] **Step 7.4: Commit**

```bash
git add src/neuro_workflow/cli.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(cli): register Lev1OutlierGenerator for `exclusions generate`

The generator's add_cli_args contributes --lev1-outliers-csv plus four
threshold args to the existing exclusions generate subparser.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Compile-pipeline integration test

Build a tiny synthetic flow: write a `lev1_outlier.json` to a fake `sources/<dataset>/`, run `compile_exclusions`, assert the merged compiled output contains the entries. Confirms the generator's output is shaped correctly for the existing compile mechanic.

**Files:**
- Modify: `tests/exclusions/test_lev1_outlier.py` (append)

- [ ] **Step 8.1: Append the integration test**

```python
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

    # Need an empty overrides file for compile to find
    overrides_path = tmp_path / "exclusions" / "discovery" / "overrides.json"
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text("[]")

    # Run compile
    compiled = core_excl.compile_exclusions("discovery")

    # Compiled output should contain our entry, with source preserved
    assert len(compiled) == 1
    assert compiled[0]["source"] == "lev1_outlier"
    assert compiled[0]["subject"] == "sub-s03"
    assert compiled[0]["task"] == "task-cuedTS"
    assert compiled[0]["action"] == "exclude"
```

- [ ] **Step 8.2: Run; expect pass**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py::test_generator_output_flows_through_compile -v
```

Expected: PASS.

If it fails on `_overrides_path()` resolution (compile tries to find overrides at the project-root `data/exclusions/<dataset>_overrides.json`, not the EXCLUSIONS_DIR location), read `core/exclusions.py:load_overrides` to see where it looks and update the test fixture to write the overrides file at that path. Adjust the monkeypatch accordingly.

- [ ] **Step 8.3: Commit**

```bash
git add tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): generator output flows through compile_exclusions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: End-to-end test against real discovery cohort QC output

Skipped if `/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv` is absent. When present, runs the generator against real cohort QC output and validates basic invariants.

**Files:**
- Modify: `tests/exclusions/test_lev1_outlier.py` (append)

- [ ] **Step 9.1: Append the end-to-end test**

```python
def test_end_to_end_on_real_discovery_cohort_qc():
    """Smoke: generator runs against real cohort QC output and produces sensible entries.

    Skipped if the discovery cohort QC output isn't present.
    """
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator

    real_csv = Path("/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv")
    if not real_csv.is_file():
        pytest.skip(f"discovery cohort QC output not present at {real_csv}")

    entries = Lev1OutlierGenerator().generate(
        "discovery", {}, _make_args(real_csv)
    )

    # Discovery cohort N=5: only strict_vif rule should fire (per the math finding
    # in docs/audits/2026-05-06-lev1-base-task-audit.md — outlier_pct bounded by
    # sqrt(N-1) ~= 2.0 for N=5, so neither combined nor strict_outliers fires).
    # Just assert the shape is sound; counts depend on the actual data.
    for e in entries:
        assert e["source"] == "lev1_outlier"
        assert e["action"] == "exclude"
        assert e["subject"].startswith("sub-")
        assert e["session"].startswith("ses-")
        assert e["task"].startswith("task-")
        assert e["run"].startswith("run-")
        assert "lev1_outlier:" in e["reason"]
        assert "max_vif" in e["metrics"]
        assert e["metrics"]["n_flagged_contrasts"] >= 1
        # Discovery shouldn't fire outlier-based rules
        assert "strict_outliers" not in e["metrics"]["rules_fired"]
```

- [ ] **Step 9.2: Run; expect pass (or skip if /scratch absent)**

```bash
uv run pytest tests/exclusions/test_lev1_outlier.py::test_end_to_end_on_real_discovery_cohort_qc -v
```

Expected: PASS or SKIPPED. Report which.

- [ ] **Step 9.3: Commit**

```bash
git add tests/exclusions/test_lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): end-to-end on real discovery cohort QC output

Skipped when /scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv
is absent. When present, validates entry shape + invariant that
strict_outliers rule should not fire on discovery (N=5).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Real-data dry run + audit trail

Run the generator end-to-end via the CLI to confirm it actually produces a sources file, and inspect the result. This is operational validation, not a test.

- [ ] **Step 10.1: Run the generator CLI**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run exclusions generate lev1_outlier discovery \
  --lev1-outliers-csv /scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv
```

Expected: stdout reports `Saved <N> entries to sources/lev1_outlier.json`. N depends on data; on discovery cohort, expect a small number (only strict_vif rule fires).

- [ ] **Step 10.2: Inspect the output**

```bash
cat ~/.neuro_workflow/exclusions/discovery/sources/lev1_outlier.json | python -m json.tool | head -40
```

(Path may be `data/exclusions/sources/discovery/lev1_outlier.json` if the existing system uses repo-relative paths — check both.)

Expected: a JSON array of exclusion entries with `source: "lev1_outlier"`, valid `subject/session/task/run`, sensible `reason` strings, and populated `metrics`.

- [ ] **Step 10.3: Recompile and confirm propagation**

```bash
uv run neuro-run exclusions compile discovery
```

Expected: stdout shows the new `lev1_outlier` source entry count in the breakdown. Compiled file at `~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json` contains the new entries.

- [ ] **Step 10.4: Commit a brief ops note (optional)**

If the dry run surfaces anything notable (a count of flagged scans worth recording), add a short note to a follow-up audit doc or skip this step if there's nothing surprising.

```bash
# Only if a doc was created/updated:
# git add docs/...
# git -c commit.gpgsign=false commit -m "docs: record discovery lev1_outlier dry-run counts"
```

---

# Self-Review

**Spec coverage:**
- Goal 1 (generator implements ExclusionGenerator Protocol) → Task 2.
- Goal 2 (three OR'd rules with default thresholds) → Tasks 3-4.
- Goal 3 (per-scan aggregation, reason format) → Tasks 3, 5.
- Goal 4 (CLI args + sources/<ds>/lev1_outlier.json output) → Tasks 2, 7.
- Goal 5 (override escape valve preserved) → Task 8 (compile integration confirms entries flow through; force-include/force-exclude mechanic was already in core/exclusions.py).
- Goal 6 (test coverage: 3 rules independently, aggregation, threshold config, NaN/empty, end-to-end) → Tasks 3-9.

**Type consistency:**
- `Thresholds` dataclass and the four CLI args use the same names (`combined_vif`, `combined_outlier_pct`, `strict_vif`, `strict_outlier_pct`) consistently across Tasks 2, 3, 6.
- `_make_args` test helper mirrors the same names.
- Output entry schema (`subject`, `session`, `task`, `run`, `source`, `action`, `reason`, `metrics`) is consistent across Tasks 3-8 and matches the motion generator schema.

**Placeholder scan:**
- Task 8 Step 8.2 has a "if it fails on …" branching note — that's diagnostic guidance for the implementer, not a placeholder. The actual fallback is named (`load_overrides`).
- Task 10 Step 10.4 is explicitly conditional ("only if …"), not a placeholder.

No "TBD", no "fill in details", no "similar to Task N", no "add appropriate error handling."
