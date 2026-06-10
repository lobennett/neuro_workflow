"""Single source for study-level analysis thresholds (config-as-code).

Loads ``config/thresholds.yaml`` (repo root) once at import. The public
threshold constants in :mod:`neuro_workflow.events.qc_globals` and the argparse
defaults in the motion / lev1_outlier exclusion generators are bound from these
values, so externalizing them is behavior-preserving.

This module also exposes :func:`config_version`, a short stable hash over the
canonical config files (``thresholds.yaml`` + the task ``battery.yaml``),
consumed by the provenance work in PR4.

Fail-loud policy: a missing or empty config file raises immediately. There is
no silent fallback to baked-in defaults — the YAML is the source of truth.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# config/thresholds.yaml lives at the repo root, next to pipeline_config.json.
# qc_globals.py is at src/neuro_workflow/events/qc_globals.py; this module is at
# src/neuro_workflow/core/thresholds.py. Both resolve to the same repo root via
# parents[3]: core -> neuro_workflow -> src -> <repo root>.
_REPO_ROOT = Path(__file__).resolve().parents[3]
THRESHOLDS_PATH = _REPO_ROOT / "config" / "thresholds.yaml"

# Task battery config (de-hardcoded in PR3b). Folded into config_version so the
# provenance hash also tracks the canonical task list.
_BATTERY_PATH = (
    Path(__file__).resolve().parents[1]
    / "analysis"
    / "task_config"
    / "battery.yaml"
)


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    """Load and parse the thresholds YAML.

    Args:
        path: Optional override (used by tests). Defaults to ``THRESHOLDS_PATH``.

    Returns:
        The parsed config as a dict.

    Raises:
        FileNotFoundError: if the config file does not exist.
        ValueError: if the file is empty or does not parse to a non-empty dict.
    """
    cfg_path = THRESHOLDS_PATH if path is None else path
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"thresholds config not found: {cfg_path}. "
            "config/thresholds.yaml is the single source of truth for analysis "
            "thresholds; it must exist (no silent fallback)."
        )
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or not data:
        raise ValueError(
            f"thresholds config is empty or not a mapping: {cfg_path}"
        )
    return data


@lru_cache(maxsize=1)
def _cached_thresholds() -> dict[str, Any]:
    """Process-wide cached load of the canonical thresholds file."""
    return load_thresholds()


def behavioral_qc() -> dict[str, Any]:
    """Behavioral-QC threshold section."""
    return _cached_thresholds()["behavioral_qc"]


def motion() -> dict[str, Any]:
    """Motion-exclusion threshold section."""
    return _cached_thresholds()["motion"]


def lev1_outlier() -> dict[str, Any]:
    """Lev1-outlier (VIF) threshold section."""
    return _cached_thresholds()["lev1_outlier"]


@lru_cache(maxsize=1)
def config_version() -> str:
    """Return a short, stable hash of the canonical config files.

    Hashes the raw bytes of ``thresholds.yaml`` and ``battery.yaml`` (in a fixed
    order) so that any edit to a study-level config produces a new version
    string. Consumed by the provenance work (PR4).
    """
    h = hashlib.sha256()
    for p in (THRESHOLDS_PATH, _BATTERY_PATH):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]
