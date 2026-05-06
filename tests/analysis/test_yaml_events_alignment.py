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
TASK_CONFIG_DIR = Path(__file__).resolve().parents[2] / "src/neuro_workflow/analysis/task_config/tasks"

# Discovery: collect events.tsv per task across both cohorts.
EVENTS_RE = re.compile(r"^sub-\w+_ses-\w+_task-(?P<task>\w+)_run-\w+_events\.tsv$")

# Tasks in scope (8 base tasks)
BASE_TASKS = [
    "cuedTS", "directedForgetting", "flanker", "goNogo",
    "nBack", "shapeMatching", "spatialTS", "stopSignal",
]

# Token regex for column references in pandas queries — handles `name`, `name.method`, etc.
# This is a heuristic; refine if it produces false positives on real queries.
_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
# Match either single- or double-quoted string literals so we can strip them out
# before identifier extraction (otherwise tokens inside literals look like columns).
_STRING_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_PYTHON_KEYWORDS = {
    "and", "or", "not", "in", "is", "True", "False", "None",
    "if", "else", "for", "lambda",
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
                failures.append(f"{fp.name} regressor {reg_name!r}: missing columns {sorted(missing)}")

    assert not failures, "\n".join(failures[:20])


@pytest.mark.parametrize("task", BASE_TASKS)
def test_regressor_queries_return_rows(task: str) -> None:
    """Each regressor's subset query must return >=1 row in at least 80% of scans for that task."""
    cfg = _load_yaml(task)
    events_files = _events_for_task(task)
    if not events_files:
        pytest.skip(f"no events.tsv files for task {task}")

    regressors = cfg.get("regressors") or {}
    floor = 0.80

    failures: list[str] = []
    for reg_name, reg_cfg in regressors.items():
        subset = reg_cfg.get("subset")
        if subset is None:
            continue
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
                f"task={task} regressor={reg_name!r}: only "
                f"{n_with_rows}/{len(events_files)} ({coverage:.0%}) scans have ≥1 matching row "
                f"(floor={floor:.0%})"
            )

    assert not failures, "\n".join(failures)
