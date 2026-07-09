"""Verify each base task YAML's regressor subset queries align with real events.tsv columns."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

BIDS_DIRS = [
    Path("/scratch/users/logben/discovery_bids"),
    Path("/scratch/users/logben/validation_bids"),
]
TASK_CONFIG_DIR = (
    Path(__file__).resolve().parents[2] / "src/neuro_workflow/analysis/task_config/tasks"
)

# Tasks in scope (8 base tasks)
BASE_TASKS = [
    "cuedTS",
    "directedForgetting",
    "flanker",
    "goNogo",
    "nBack",
    "shapeMatching",
    "spatialTS",
    "stopSignal",
]

# Dual tasks (11). Condition subsets validated against real events; nuisance/RT/break
# regressors are exempt from the "fires somewhere" check (three dual tasks legitimately
# have no break_with_performance_feedback events, and nuisance amplitudes are runtime-derived).
DUAL_TASKS = [
    "cuedTSWFlanker",
    "directedForgettingWCuedTS",
    "directedForgettingWFlanker",
    "flankerWShapeMatching",
    "nBackWShapeMatching",
    "nBackWSpatialTS",
    "shapeMatchingWCuedTS",
    "spatialTSWCuedTS",
    "spatialTSWShapeMatching",
    "stopSignalWDirectedForgetting",
    "stopSignalWFlanker",
]
_NON_CONDITION_REGRESSORS = {
    "omission",
    "commission",
    "rt_fast",
    "response_time",
    "break_with_performance_feedback",
}

# Token regex for column references in pandas queries — handles `name`, `name.method`, etc.
# This is a heuristic; refine if it produces false positives on real queries.
_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
# Match either single- or double-quoted string literals so we can strip them out
# before identifier extraction (otherwise tokens inside literals look like columns).
_STRING_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_PYTHON_KEYWORDS = {
    "and",
    "or",
    "not",
    "in",
    "is",
    "True",
    "False",
    "None",
    "if",
    "else",
    "for",
    "lambda",
}


def _extract_referenced_columns(query: str) -> set[str]:
    """Heuristic: identifiers in a pandas query that aren't keywords or numbers.

    Quoted string literals are stripped before tokenisation so values like
    'tstay_cstay' or "SSS" don't get misread as column names.
    """
    stripped = _STRING_LITERAL_RE.sub(" ", query)
    return {tok for tok in _IDENT_RE.findall(stripped) if tok not in _PYTHON_KEYWORDS}


def _events_for_task(task: str) -> list[Path]:
    out: list[Path] = []
    for bids_dir in BIDS_DIRS:
        for fp in bids_dir.rglob(f"*_task-{task}_*_events.tsv"):
            if "derivatives" in fp.parts or "sourcedata" in fp.parts:
                continue
            out.append(fp)
    return out


def _load_yaml(task: str) -> dict:
    return yaml.safe_load((TASK_CONFIG_DIR / f"{task}.yaml").read_text())


@pytest.mark.parametrize("task", BASE_TASKS)
def test_regressor_columns_exist_in_events(task: str) -> None:
    """Every column referenced by any regressor's subset query must exist in every events.tsv."""
    cfg = _load_yaml(task)
    events_files = _events_for_task(task)
    if not events_files:
        pytest.skip(f"no events.tsv files for task {task} (BIDS dirs not present)")

    regressors = cfg.get("regressors") or {}
    failures: list[str] = []
    for reg_name, reg_cfg in regressors.items():
        subset = reg_cfg.get("subset")
        if subset is None:
            continue  # parametric modulator, not a categorical filter
        referenced = _extract_referenced_columns(subset)
        for fp in events_files:
            df = pd.read_csv(fp, sep="\t")
            missing = referenced - set(df.columns)
            # filter out values that look like string literals or numbers
            missing = {c for c in missing if not c.replace(".", "").isdigit()}
            if missing:
                failures.append(
                    f"{fp.name} regressor {reg_name!r}: missing columns {sorted(missing)}"
                )

    assert not failures, "\n".join(failures[:20])


@pytest.mark.parametrize("task", BASE_TASKS)
def test_regressor_queries_return_rows(task: str) -> None:
    """Each regressor's subset query must:
    1. Return >=1 row in at least `events_query_min_coverage` of scans (default 0.8).
    2. Return >=1 row in at least one scan cohort-wide, regardless of the floor —
       this catches dead regressors that have a coverage override of 0.0 but never
       fire anywhere (e.g. queries built from copy-paste typos).
    """
    cfg = _load_yaml(task)
    events_files = _events_for_task(task)
    if not events_files:
        pytest.skip(f"no events.tsv files for task {task}")

    regressors = cfg.get("regressors") or {}
    default_floor = 0.80

    failures: list[str] = []
    for reg_name, reg_cfg in regressors.items():
        subset = reg_cfg.get("subset")
        if subset is None:
            continue
        floor = float(reg_cfg.get("events_query_min_coverage", default_floor))
        n_with_rows = 0
        for fp in events_files:
            df = pd.read_csv(fp, sep="\t")
            try:
                matched = df.query(subset)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{fp.name} {reg_name!r}: query raised {type(exc).__name__}: {exc}")
                continue
            if len(matched) > 0:
                n_with_rows += 1
        coverage = n_with_rows / len(events_files) if events_files else 0.0
        if coverage < floor:
            failures.append(
                f"task={task} regressor={reg_name!r}: per-scan coverage "
                f"{n_with_rows}/{len(events_files)} ({coverage:.0%}) below floor "
                f"events_query_min_coverage={floor:.0%}"
            )
        # Cohort-wide presence check: regressor must fire somewhere, even when floor=0.
        if n_with_rows < 1:
            failures.append(
                f"task={task} regressor={reg_name!r}: dead query — 0/{len(events_files)} "
                f"scans cohort-wide have any matching rows (subset={subset!r})"
            )

    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("task", DUAL_TASKS)
def test_dual_regressor_columns_exist_in_events(task: str) -> None:
    """Every column referenced by a dual-task regressor subset must exist in its events.tsv."""
    cfg = _load_yaml(task)
    events_files = _events_for_task(task)
    if not events_files:
        pytest.skip(f"no events.tsv files for task {task} (BIDS dirs not present)")

    regressors = cfg.get("regressors") or {}
    failures: list[str] = []
    for reg_name, reg_cfg in regressors.items():
        subset = reg_cfg.get("subset")
        if subset is None:
            continue
        referenced = _extract_referenced_columns(subset)
        for fp in events_files:
            df = pd.read_csv(fp, sep="\t")
            missing = referenced - set(df.columns)
            missing = {c for c in missing if not c.replace(".", "").isdigit()}
            if missing:
                failures.append(
                    f"{fp.name} regressor {reg_name!r}: missing columns {sorted(missing)}"
                )
    assert not failures, "\n".join(failures[:20])


@pytest.mark.parametrize("task", DUAL_TASKS)
def test_dual_condition_regressors_fire(task: str) -> None:
    """Each dual-task CONDITION regressor's subset must match >=1 real test_trial row
    somewhere in the cohort. Nuisance/RT/break regressors are exempt (runtime-derived
    amplitudes; three dual tasks have no break_with_performance_feedback events).
    Also verifies every contrast formula references only declared regressors.
    """
    cfg = _load_yaml(task)
    events_files = _events_for_task(task)
    if not events_files:
        pytest.skip(f"no events.tsv files for task {task}")

    regressors = cfg.get("regressors") or {}
    contrasts = cfg.get("contrasts") or {}

    # Contrast formulas reference only declared regressors.
    declared = set(regressors)
    contrast_failures: list[str] = []
    for cname, formula in contrasts.items():
        tokens = _extract_referenced_columns(formula)
        undeclared = {t for t in tokens if not t.replace(".", "").isdigit()} - declared
        if undeclared:
            contrast_failures.append(f"{task} contrast {cname!r}: undeclared {sorted(undeclared)}")
    assert not contrast_failures, "\n".join(contrast_failures)

    dfs = [pd.read_csv(fp, sep="\t") for fp in events_files]
    failures: list[str] = []
    for reg_name, reg_cfg in regressors.items():
        if reg_name in _NON_CONDITION_REGRESSORS:
            continue
        subset = reg_cfg.get("subset")
        if subset is None:
            continue
        n_with_rows = 0
        for df in dfs:
            try:
                if len(df.query(subset)) > 0:
                    n_with_rows += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{task} {reg_name!r}: query raised {type(exc).__name__}: {exc}")
        if n_with_rows < 1:
            failures.append(
                f"task={task} regressor={reg_name!r}: dead query — 0/{len(dfs)} scans "
                f"cohort-wide have matching rows (subset={subset!r})"
            )
    assert not failures, "\n".join(failures)
