"""B2 regression: exclusion overrides live at the COMMITTED path
(LOCKFILE_DIR/<ds>_overrides.json), not the old machine-local
CONFIG_DIR/<ds>/overrides.json. compile_exclusions must load + apply them.

Each test writes the override file directly at the committed path/naming (as a
checked-in `data/exclusions/<ds>_overrides.json` would be), so it fails if
`_overrides_path` ever points back at the CONFIG_DIR location.
"""

import json

import neuro_workflow.core.exclusions as exc
from neuro_workflow.core.exclusions import save_source_entries, compile_exclusions


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(exc, "EXCLUSIONS_DIR", tmp_path / "cfg")
    monkeypatch.setattr(exc, "LOCKFILE_DIR", tmp_path / "lock")
    (tmp_path / "lock").mkdir()


def test_overrides_path_is_the_committed_lockfile_location(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert exc._overrides_path("validation") == (tmp_path / "lock" / "validation_overrides.json")


def test_committed_force_exclude_is_loaded_and_applied(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    save_source_entries(
        "testds",
        "motion",
        [
            {
                "subject": "sub-s1",
                "session": "ses-01",
                "task": "task-flanker",
                "run": "run-1",
                "action": "exclude",
                "source": "motion",
                "reason": "FD",
            }
        ],
    )
    (tmp_path / "lock" / "testds_overrides.json").write_text(
        json.dumps(
            [
                {
                    "subject": "sub-s2",
                    "session": "ses-02",
                    "task": "task-nBack",
                    "run": "run-1",
                    "action": "force-exclude",
                    "reason": "manual",
                }
            ]
        )
    )
    compiled = compile_exclusions("testds")
    keys = {(e["subject"], e["session"], e["task"], e["run"]) for e in compiled}
    assert ("sub-s2", "ses-02", "task-nBack", "run-1") in keys, compiled


def test_force_exclude_is_idempotent_against_source_entries(tmp_path, monkeypatch):
    """A force-exclude whose scan-key is already excluded by a source must NOT
    add a duplicate compiled entry (idempotent force-exclude); a force-exclude
    for a genuinely new scan is still added."""
    _isolate(tmp_path, monkeypatch)
    save_source_entries(
        "testds",
        "qa_decisions",
        [
            {
                "subject": "sub-s1",
                "session": "ses-01",
                "task": "task-nBack",
                "run": "run-1",
                "action": "exclude",
                "source": "qa_decisions",
                "reason": "junk-trial",
            }
        ],
    )
    (tmp_path / "lock" / "testds_overrides.json").write_text(
        json.dumps(
            [
                # duplicates the source-excluded scan -> must not double up
                {
                    "subject": "sub-s1",
                    "session": "ses-01",
                    "task": "task-nBack",
                    "run": "run-1",
                    "action": "force-exclude",
                    "reason": "Behavioral exclusion",
                },
                # a brand-new scan -> must be added
                {
                    "subject": "sub-s2",
                    "session": "ses-02",
                    "task": "task-flanker",
                    "run": "run-1",
                    "action": "force-exclude",
                    "reason": "Behavioral exclusion",
                },
            ]
        )
    )
    compiled = compile_exclusions("testds")
    keys = [(e["subject"], e["session"], e["task"], e["run"]) for e in compiled]
    # the overlapping scan appears exactly once (the source entry, not a duplicate)
    assert keys.count(("sub-s1", "ses-01", "task-nBack", "run-1")) == 1, compiled
    # the dedup keeps the source entry's provenance, not a second override entry
    dup = [
        e
        for e in compiled
        if (e["subject"], e["session"], e["task"], e["run"])
        == ("sub-s1", "ses-01", "task-nBack", "run-1")
    ]
    assert dup[0]["source"] == "qa_decisions", dup
    # the genuinely-new force-exclude is still added
    assert ("sub-s2", "ses-02", "task-flanker", "run-1") in keys, compiled
    assert len(compiled) == 2, compiled


def test_committed_force_include_removes_a_compiled_entry(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    save_source_entries(
        "testds",
        "motion",
        [
            {
                "subject": "sub-s1",
                "session": "ses-01",
                "task": "task-flanker",
                "run": "run-1",
                "action": "exclude",
                "source": "motion",
                "reason": "FD",
            }
        ],
    )
    (tmp_path / "lock" / "testds_overrides.json").write_text(
        json.dumps(
            [
                {
                    "subject": "sub-s1",
                    "session": "ses-01",
                    "task": "task-flanker",
                    "run": "run-1",
                    "action": "force-include",
                    "reason": "rescued",
                }
            ]
        )
    )
    compiled = compile_exclusions("testds")
    keys = {(e["subject"], e["session"], e["task"], e["run"]) for e in compiled}
    assert ("sub-s1", "ses-01", "task-flanker", "run-1") not in keys, compiled
