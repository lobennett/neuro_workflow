import json
from pathlib import Path

import pytest

from neuro_workflow.core.exclusions import (
    EXCLUSIONS_DIR,
    validate_entry,
    save_source_entries,
    load_source_entries,
    save_overrides,
    load_overrides,
    compile_exclusions,
    load_compiled_exclusions,
    is_excluded,
    get_trim_info,
)


@pytest.fixture(autouse=True)
def _isolate_lockfile_dir(tmp_path, monkeypatch):
    """Redirect the committed-lockfile dir into tmp_path so compile_exclusions
    tests never write `<dataset>_lock.json` into the version-controlled
    data/exclusions/ tree (the source dir is already isolated per-test via the
    EXCLUSIONS_DIR monkeypatch)."""
    monkeypatch.setattr(
        "neuro_workflow.core.exclusions.LOCKFILE_DIR", tmp_path / "lock"
    )


def test_validate_entry_valid():
    entry = {
        "subject": "sub-s01",
        "session": "ses-01",
        "task": "task-rest",
        "run": "run-1",
        "source": "motion",
        "action": "exclude",
        "reason": "High FD",
    }
    assert validate_entry(entry) is True


def test_validate_entry_missing_field():
    entry = {"subject": "sub-s01", "session": "ses-01"}
    assert validate_entry(entry) is False


def test_validate_entry_bad_action():
    entry = {
        "subject": "sub-s01",
        "session": "ses-01",
        "task": "task-rest",
        "run": "run-1",
        "source": "motion",
        "action": "invalid",
        "reason": "test",
    }
    assert validate_entry(entry) is False


def test_save_and_load_source_entries(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)
    entries = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    save_source_entries("discovery", "motion", entries)
    loaded = load_source_entries("discovery", "motion")
    assert len(loaded) == 1
    assert loaded[0]["subject"] == "sub-s01"


def test_save_source_entries_rejects_invalid_entry(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)
    bad_entries = [
        {"subject": "sub-s01", "session": "ses-01"}  # missing task/run/action/reason
    ]
    with pytest.raises(ValueError):
        save_source_entries("discovery", "motion", bad_entries)


def test_save_and_load_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)
    overrides = [
        {
            "subject": "sub-s02",
            "session": "ses-05",
            "task": "task-rest",
            "run": "run-1",
            "action": "force-include",
            "reason": "Override",
        }
    ]
    save_overrides("discovery", overrides)
    loaded = load_overrides("discovery")
    assert len(loaded) == 1
    assert loaded[0]["action"] == "force-include"


def test_compile_merges_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    motion = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    neg = [
        {
            "subject": "sub-s02",
            "session": "ses-03",
            "task": "task-flanker",
            "run": "run-1",
            "source": "neg-events",
            "action": "trim",
            "reason": "Non-monotonic",
            "metrics": {"onset_trim_index": 50, "total_rows": 200, "rows_to_keep": 150},
        }
    ]
    save_source_entries("test", "motion", motion)
    save_source_entries("test", "neg_events", neg)
    save_overrides("test", [])

    compiled = compile_exclusions("test")
    assert len(compiled) == 2


def test_compile_force_include_removes(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    motion = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    overrides = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "action": "force-include",
            "reason": "Manual override",
        }
    ]
    save_source_entries("test", "motion", motion)
    save_overrides("test", overrides)

    compiled = compile_exclusions("test")
    assert len(compiled) == 0


def test_compile_force_exclude_adds(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    save_overrides("test", [
        {
            "subject": "sub-s99",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "action": "force-exclude",
            "reason": "Manual exclusion",
        }
    ])
    # No source files — just overrides
    compiled = compile_exclusions("test")
    assert len(compiled) == 1
    assert compiled[0]["action"] == "exclude"
    assert compiled[0]["source"] == "override"


def test_is_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    entries = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    save_source_entries("test", "motion", entries)
    save_overrides("test", [])
    compiled = compile_exclusions("test")

    assert is_excluded("sub-s01", "ses-01", "task-rest", "run-1", compiled) is True
    assert is_excluded("sub-s01", "ses-02", "task-rest", "run-1", compiled) is False


def test_get_trim_info(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    entries = [
        {
            "subject": "sub-s03",
            "session": "ses-11",
            "task": "task-stop",
            "run": "run-1",
            "source": "neg-events",
            "action": "trim",
            "reason": "Non-monotonic",
            "metrics": {"onset_trim_index": 161, "total_rows": 726, "rows_to_keep": 565},
        }
    ]
    save_source_entries("test", "neg_events", entries)
    save_overrides("test", [])
    compiled = compile_exclusions("test")

    info = get_trim_info("sub-s03", "ses-11", "task-stop", "run-1", compiled)
    assert info is not None
    assert info["onset_trim_index"] == 161
    assert info["rows_to_keep"] == 565

    assert get_trim_info("sub-s99", "ses-01", "task-rest", "run-1", compiled) is None
