"""Tests for the derived `min_runs` (belowMinRuns) exclusion step in compile.

`compile_exclusions` inspects the BIDS run inventory and the already-merged
scan-level exclusions to record, as a first-class DERIVED exclusion, any
(subject, task) whose surviving-run count falls below the fixed-effects floor
(`min_runs_floor`). This mirrors the implicit `_desc-belowMinRuns` filename tag
that lev1 applies and lev2 filters on: a fixed-effects map is tagged (and thus
dropped at lev2) exactly when `0 < surviving_runs < floor` -- a subject×task
with 0 surviving runs produces no map at all, so there is nothing to tag.
"""

from __future__ import annotations

from pathlib import Path


def _make_fake_bids(tmp_path: Path, subject: str, scans: list[tuple[str, str, str]]) -> Path:
    """Build a minimal multi-echo BIDS tree with empty BOLD files.

    Each scan tuple is (session, task, run), e.g. ('ses-01', 'flanker', '1').
    Writes 3 echoes per scan so the inventory glob/regex is exercised against
    production-shaped multi-echo filenames (deduped to one scan per run).
    """
    bids = tmp_path / "bids"
    for session, task, run in scans:
        func = bids / subject / session / "func"
        func.mkdir(parents=True, exist_ok=True)
        for echo in (1, 2, 3):
            fname = f"{subject}_{session}_task-{task}_run-{run}_echo-{echo}_bold.nii.gz"
            (func / fname).write_bytes(b"")
    return bids


def _scan_exclude(subject: str, session: str, task: str, run: str) -> dict:
    return {
        "subject": subject,
        "session": session,
        "task": task,
        "run": run,
        "source": "qa_decisions",
        "action": "exclude",
        "reason": "qa_decisions: noisy (scan-level)",
    }


def test_below_floor_base_task_records_derived_min_runs(tmp_path, monkeypatch):
    """Base task with 3 runs, 2 scan-level excluded -> surviving 1 < floor 2.

    Exactly one derived `min_runs` entry, with metrics recording surviving=1,
    floor=2, total=3, is_dual=False. The dual task (surviving 1 == floor 1)
    gets NO derived entry, and a fully-excluded task (surviving 0) gets none.
    """
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    bids_dir = _make_fake_bids(
        tmp_path,
        "sub-s03",
        [
            # base task flanker: 3 runs
            ("ses-01", "flanker", "1"),
            ("ses-01", "flanker", "2"),
            ("ses-01", "flanker", "3"),
            # dual task cuedTSWFlanker: 1 run
            ("ses-02", "cuedTSWFlanker", "1"),
            # goNogo (base): 1 run, will be fully excluded -> surviving 0
            ("ses-03", "goNogo", "1"),
            # rest: must be ignored entirely
            ("ses-01", "rest", "1"),
        ],
    )

    # Scan-level exclusions: 2 of 3 flanker runs, and the single goNogo run.
    scan_excludes = [
        _scan_exclude("sub-s03", "ses-01", "task-flanker", "run-1"),
        _scan_exclude("sub-s03", "ses-01", "task-flanker", "run-2"),
        _scan_exclude("sub-s03", "ses-03", "task-goNogo", "run-1"),
    ]
    core_excl.save_source_entries("discovery", "qa_decisions", scan_excludes)

    compiled = core_excl.compile_exclusions("discovery", bids_dir=str(bids_dir))

    min_runs_entries = [e for e in compiled if e.get("source") == "min_runs"]

    # Exactly one derived record: the base flanker task (surviving 1 < floor 2).
    assert len(min_runs_entries) == 1, min_runs_entries
    e = min_runs_entries[0]
    assert e["subject"] == "sub-s03"
    assert e["task"].endswith("flanker")
    assert e["action"] == "exclude"
    assert e["metrics"]["surviving_runs"] == 1
    assert e["metrics"]["floor"] == 2
    assert e["metrics"]["total_runs"] == 3
    assert e["metrics"]["is_dual"] is False
    assert "belowMinRuns" in e["reason"]

    # No derived entry for the dual task (surviving 1 == floor 1) or for the
    # fully-excluded goNogo (surviving 0), or for rest.
    tasks_flagged = {ee["task"] for ee in min_runs_entries}
    assert not any("cuedTSWFlanker" in t for t in tasks_flagged)
    assert not any("goNogo" in t for t in tasks_flagged)
    assert not any("rest" in t for t in tasks_flagged)


def test_derived_min_runs_is_idempotent(tmp_path, monkeypatch):
    """Recompiling twice does not duplicate the derived min_runs entry."""
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    bids_dir = _make_fake_bids(
        tmp_path,
        "sub-s03",
        [
            ("ses-01", "flanker", "1"),
            ("ses-01", "flanker", "2"),
        ],
    )
    core_excl.save_source_entries(
        "discovery",
        "qa_decisions",
        [_scan_exclude("sub-s03", "ses-01", "task-flanker", "run-1")],
    )

    core_excl.compile_exclusions("discovery", bids_dir=str(bids_dir))
    compiled = core_excl.compile_exclusions("discovery", bids_dir=str(bids_dir))

    min_runs_entries = [e for e in compiled if e.get("source") == "min_runs"]
    assert len(min_runs_entries) == 1, min_runs_entries


def test_no_bids_dir_skips_derivation(tmp_path, monkeypatch):
    """Without a bids_dir the run inventory is unknown -> no derived entries."""
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    core_excl.save_source_entries(
        "discovery",
        "qa_decisions",
        [_scan_exclude("sub-s03", "ses-01", "task-flanker", "run-1")],
    )

    compiled = core_excl.compile_exclusions("discovery")
    assert [e for e in compiled if e.get("source") == "min_runs"] == []
