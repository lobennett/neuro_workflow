"""Tests for src/neuro_workflow/core/thresholds.py (config-as-code).

These guard the behavior-preserving externalization of analysis thresholds
into config/thresholds.yaml. Every value loaded from the config MUST equal the
pre-refactor literal, and a missing/empty config MUST fail loud.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Loader + path resolution
# ---------------------------------------------------------------------------
def test_thresholds_yaml_resolves_and_loads():
    """config/thresholds.yaml resolves package-relative and parses to a dict."""
    from neuro_workflow.core.thresholds import THRESHOLDS_PATH, load_thresholds

    assert THRESHOLDS_PATH.is_file(), f"thresholds.yaml not found at {THRESHOLDS_PATH}"
    data = load_thresholds()
    assert isinstance(data, dict)
    assert "behavioral_qc" in data
    assert "motion" in data
    assert "lev1_outlier" in data


def test_missing_config_fails_loud(tmp_path, monkeypatch):
    """A missing config path raises FileNotFoundError (no silent fallback)."""
    from neuro_workflow.core import thresholds as t

    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError):
        t.load_thresholds(missing)


def test_empty_config_fails_loud(tmp_path):
    """An empty config file raises a clear error (no silent empty-dict)."""
    from neuro_workflow.core import thresholds as t

    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError):
        t.load_thresholds(empty)


# ---------------------------------------------------------------------------
# Behavioral QC constants — byte-identical to pre-refactor literals
# ---------------------------------------------------------------------------
def test_behavioral_qc_constants_byte_identical():
    from neuro_workflow.events import qc_globals as q

    assert q.STOP_SUCCESS_ACC_LOW_THRESHOLD == 0.25
    assert q.STOP_SUCCESS_ACC_HIGH_THRESHOLD == 0.75
    assert q.GO_RT_THRESHOLD_FMRI == 1000
    assert q.GO_RT_THRESHOLD_FMRI_DUAL_TASK == 1050

    assert q.GONOGO_GO_ACC_THRESHOLD_1 == 0.75
    assert q.GONOGO_NOGO_ACC_THRESHOLD_1 == 0.2
    assert q.GONOGO_GO_ACC_THRESHOLD_2 == 0.5
    assert q.GONOGO_NOGO_ACC_THRESHOLD_2 == 0.5

    assert q.NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1 == 0.2
    assert q.NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 == 0.75
    assert q.NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_2 == 0.5
    assert q.NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2 == 0.5
    assert q.NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_1 == 0.2
    assert q.NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 == 0.75
    assert q.NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_2 == 0.5
    assert q.NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2 == 0.5

    assert q.ACC_THRESHOLD == 0.55
    assert q.OMISSION_RATE_THRESHOLD == 0.25

    assert q.LAST_N_TEST_TRIALS == 10
    assert q.SUMMARY_ROWS == 4


# ---------------------------------------------------------------------------
# Motion + lev1 VIF defaults — byte-identical to pre-refactor literals
# ---------------------------------------------------------------------------
def test_motion_thresholds_byte_identical():
    from neuro_workflow.core.thresholds import load_thresholds

    motion = load_thresholds()["motion"]
    assert motion["fd_threshold"] == 0.2
    assert motion["proportion_fd_threshold"] == 0.2
    assert motion["proportion_dvars_threshold"] == 0.2


def test_motion_generator_cli_defaults_from_config():
    """The MotionGenerator argparse defaults come from the config values."""
    from argparse import ArgumentParser

    from neuro_workflow.exclusions.motion import MotionGenerator

    parser = ArgumentParser()
    MotionGenerator().add_cli_args(parser)
    ns = parser.parse_args([])
    assert ns.fd_threshold == 0.2
    assert ns.proportion_fd_threshold == 0.2
    assert ns.proportion_dvars_threshold == 0.2


def test_lev1_outlier_thresholds_byte_identical():
    from neuro_workflow.core.thresholds import load_thresholds

    lev1 = load_thresholds()["lev1_outlier"]
    assert lev1["combined_vif"] == 10.0
    assert lev1["combined_outlier_pct"] == 10.0
    assert lev1["strict_vif"] == 15.0
    assert lev1["strict_outlier_pct"] == 15.0


def test_lev1_outlier_dataclass_defaults_from_config():
    """The Thresholds dataclass + CLI defaults come from the config values."""
    from argparse import ArgumentParser

    from neuro_workflow.exclusions.lev1_outlier import (
        Lev1OutlierGenerator,
        Thresholds,
    )

    t = Thresholds()
    assert t.combined_vif == 10.0
    assert t.combined_outlier_pct == 10.0
    assert t.strict_vif == 15.0
    assert t.strict_outlier_pct == 15.0

    parser = ArgumentParser()
    Lev1OutlierGenerator().add_cli_args(parser)
    ns = parser.parse_args(["--lev1-outliers-csv", "/tmp/x.csv"])
    assert ns.combined_vif == 10.0
    assert ns.combined_outlier_pct == 10.0
    assert ns.strict_vif == 15.0
    assert ns.strict_outlier_pct == 15.0


# ---------------------------------------------------------------------------
# config_version() helper (consumed by PR4 provenance)
# ---------------------------------------------------------------------------
def test_config_version_stable_and_short():
    from neuro_workflow.core.thresholds import config_version

    v1 = config_version()
    v2 = config_version()
    assert isinstance(v1, str)
    assert v1 == v2  # stable across calls
    assert 0 < len(v1) <= 16  # short hash
    assert all(c in "0123456789abcdef" for c in v1)


def test_config_version_returns_unknown_when_file_missing(tmp_path, monkeypatch):
    """A missing config file must yield the literal 'unknown', not an opaque
    FileNotFoundError that would crash provenance recording."""
    from neuro_workflow.core import thresholds as t

    monkeypatch.setattr(t, "THRESHOLDS_PATH", tmp_path / "nope.yaml")
    # Bypass the module-level lru_cache so the patched path is actually read.
    assert t.config_version.__wrapped__() == "unknown"


# ---------------------------------------------------------------------------
# Cache-isolation: section getters must return fresh copies
# ---------------------------------------------------------------------------
def test_section_getters_return_copies_not_cached_refs():
    """behavioral_qc()/motion()/lev1_outlier() must hand back a fresh dict each
    call: mutating a returned dict must NOT poison the process-wide lru_cache
    (which would corrupt every later caller, including qc_globals)."""
    from neuro_workflow.core import thresholds as t

    for getter in (t.behavioral_qc, t.motion, t.lev1_outlier):
        first = getter()
        first["__poison__"] = 999  # mutate the returned dict
        first[next(iter(first))] = -12345  # also clobber a real key
        second = getter()
        assert "__poison__" not in second, f"{getter.__name__} leaked a cached ref"
        assert second != first


def test_raw_yaml_config_returns_deepcopy():
    """get_raw_yaml_config must return a deep copy: mutating a nested value must
    not bleed into a later call (the underlying parse is lru_cache'd)."""
    from neuro_workflow.analysis.task_config.loader import get_raw_yaml_config

    cfg = get_raw_yaml_config("flanker")
    cfg["__poison__"] = 999
    # Mutate a nested container if present, to prove deep (not shallow) copy.
    for v in cfg.values():
        if isinstance(v, dict):
            v["__nested_poison__"] = 1
            break
    again = get_raw_yaml_config("flanker")
    assert "__poison__" not in again
    assert not any(
        isinstance(v, dict) and "__nested_poison__" in v for v in again.values()
    )
