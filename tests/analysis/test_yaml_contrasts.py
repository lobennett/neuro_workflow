"""Verify each base task YAML's contrast formulas reference declared regressor names."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

TASK_CONFIG_DIR = (
    Path(__file__).resolve().parents[2] / "src/neuro_workflow/analysis/task_config/tasks"
)

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

_TOKEN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def _extract_tokens(formula: str) -> set[str]:
    """Identifiers in a contrast formula. Strips out numeric literals."""
    return {t for t in _TOKEN_RE.findall(formula)}


@pytest.mark.parametrize("task", BASE_TASKS)
def test_contrast_formulas_reference_declared_regressors(task: str) -> None:
    cfg = yaml.safe_load((TASK_CONFIG_DIR / f"{task}.yaml").read_text())
    regressors = cfg.get("regressors") or {}
    contrasts = cfg.get("contrasts") or {}
    declared = set(regressors.keys())

    failures: list[str] = []
    for name, formula in contrasts.items():
        tokens = _extract_tokens(formula)
        # Allow numeric literals and arithmetic; flag tokens that aren't declared regressors
        # or basic Python/math identifiers.
        candidates = {t for t in tokens if not t.replace(".", "").isdigit()}
        unknown = candidates - declared
        if unknown:
            failures.append(
                f"task={task} contrast={name!r}: references unknown identifiers {sorted(unknown)}"
            )

    assert not failures, "\n".join(failures)
