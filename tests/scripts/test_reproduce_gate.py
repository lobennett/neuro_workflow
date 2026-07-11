"""Dual-aware reproduce gate: byte-equality of the recompiled exclusions lockfile.

Asserts that regenerating a dataset's pre-lev1 exclusion sources and
``compile_exclusions`` is DETERMINISTIC (two recompiles produce lockfiles that
are byte-identical on every non-volatile field) and REPRODUCES a committed
snapshot lockfile (fixture). This is the provenance-reproducibility gate: if the
exclusion machinery drifts, the recompiled lockfile stops matching the committed
one and this test fails.

The synthetic cohort is built so the compiled set exercises all three
exclusion mechanisms the provenance refactor added / relies on:

- ``junk_qc``  — a base task (flanker) and a DUAL task (cuedTSWFlanker) each with
  a >30%-junk run, so the runtime ``percent_junk > 0.30`` QA-fail is lifted to a
  first-class compiled exclusion.
- derived ``min_runs`` — flanker has 3 runs, 2 flagged by junk_qc, leaving 1
  surviving run < the base-task fixed-effects floor (2), so compile derives a
  ``belowMinRuns`` exclusion.
- dual-task — the ``cuedTSWFlanker`` junk exclusion proves the gate is dual-aware
  (the dual battery is discovered/handled, not silently dropped).
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

nib = pytest.importorskip("nibabel")

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reproduce_gate"


# ---------------------------------------------------------------------------
# Synthetic cohort builder
# ---------------------------------------------------------------------------


def _write_bold(func: Path, sub: str, ses: str, task: str, run: str, n_scans: int = 200) -> None:
    func.mkdir(parents=True, exist_ok=True)
    img = nib.Nifti1Image(np.zeros((2, 2, 2, n_scans), dtype=np.float32), np.eye(4))
    nib.save(img, func / f"{sub}_{ses}_task-{task}_run-{run}_echo-1_bold.nii.gz")


def _write_events(func: Path, sub: str, ses: str, task: str, run: str, n_good: int, n_om: int) -> None:
    func.mkdir(parents=True, exist_ok=True)
    rows = []
    onset = 0.0
    for _ in range(n_good):
        rows.append(
            {"onset": onset, "duration": 1.0, "trial_id": "test_trial", "trial_type": "test",
             "key_press": 1, "correct_response": 1, "response_time": 0.5}
        )
        onset += 2.0
    for _ in range(n_om):
        rows.append(
            {"onset": onset, "duration": 1.0, "trial_id": "test_trial", "trial_type": "test",
             "key_press": -1, "correct_response": 1, "response_time": "n/a"}
        )
        onset += 2.0
    pd.DataFrame(rows).to_csv(func / f"{sub}_{ses}_task-{task}_run-{run}_events.tsv", sep="\t",
                              index=False)


def _build_synthetic_cohort(tmp_path: Path) -> Path:
    """Build the junk_qc + min_runs + dual synthetic BIDS tree (sub-s10, discovery)."""
    bids = tmp_path / "bids"
    sub = "sub-s10"  # in the discovery roster

    # flanker (base, floor 2): 3 runs; run-1 & run-2 >30% junk, run-3 clean.
    f1 = bids / sub / "ses-01" / "func"
    for run, (good, om) in {"1": (6, 4), "2": (6, 4), "3": (10, 0)}.items():
        _write_bold(f1, sub, "ses-01", "flanker", run)
        _write_events(f1, sub, "ses-01", "flanker", run, good, om)

    # cuedTSWFlanker (DUAL, floor 1): single >30%-junk run.
    f2 = bids / sub / "ses-02" / "func"
    _write_bold(f2, sub, "ses-02", "cuedTSWFlanker", "1")
    _write_events(f2, sub, "ses-02", "cuedTSWFlanker", "1", 6, 4)

    return bids


def _regenerate_and_compile(dataset: str, bids: Path):
    """Run junk_qc (like the harness) + compile_exclusions; return compiled entries.

    Sources are saved with ``args=None`` exactly as ``scripts/reproduce_cohort.py``
    does, so the lockfile's ``sources[].args`` is reproducible.
    """
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.exclusions.junk_qc import JunkQCGenerator

    entries = JunkQCGenerator().generate(dataset, {"bids_dir": str(bids)}, Namespace())
    core_excl.save_source_entries(dataset, "junk_qc", entries)
    return core_excl.compile_exclusions(dataset, bids_dir=str(bids))


def _patch_hermetic(monkeypatch, tmp_path: Path):
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_recompile_is_deterministic(tmp_path, monkeypatch):
    """Two recompiles produce lockfiles identical on every non-volatile field."""
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.testing.reproduce.canonical import compiled_to_keyset
    from neuro_workflow.testing.reproduce.lockfile import load_lock, normalize_lock

    _patch_hermetic(monkeypatch, tmp_path)
    bids = _build_synthetic_cohort(tmp_path)

    compiled_1 = _regenerate_and_compile("discovery", bids)
    lock_1 = load_lock(core_excl._lockfile_path("discovery"))

    compiled_2 = _regenerate_and_compile("discovery", bids)
    lock_2 = load_lock(core_excl._lockfile_path("discovery"))

    # Byte-identical on the non-volatile view (compiled_at / code_sha / paths /
    # ran_at stripped). Raw compiled_at DOES differ run-to-run:
    assert normalize_lock(lock_1) == normalize_lock(lock_2)
    # ... and the compiled entry SET is identical.
    assert compiled_to_keyset(compiled_1) == compiled_to_keyset(compiled_2)


def test_dual_junk_and_minruns_are_represented(tmp_path, monkeypatch):
    """The compiled set + lockfile carry junk_qc, derived min_runs, and a dual task."""
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.testing.reproduce.lockfile import load_lock

    _patch_hermetic(monkeypatch, tmp_path)
    bids = _build_synthetic_cohort(tmp_path)
    compiled = _regenerate_and_compile("discovery", bids)

    sources = {e.get("source") for e in compiled}
    assert "junk_qc" in sources
    assert "min_runs" in sources  # derived in compile, not a saved source file

    # dual task present (cuedTSWFlanker) and flagged by junk_qc.
    dual = [e for e in compiled if e["task"].endswith("cuedTSWFlanker")]
    assert dual and dual[0]["source"] == "junk_qc"

    # min_runs targets the base flanker task (3 runs, 2 junk -> 1 surviving < 2).
    minruns = [e for e in compiled if e.get("source") == "min_runs"]
    assert len(minruns) == 1
    assert minruns[0]["task"].endswith("flanker")
    assert minruns[0]["metrics"]["surviving_runs"] == 1
    assert minruns[0]["metrics"]["floor"] == 2

    # lockfile records junk_qc as a source with 3 entries; n_total counts the
    # derived min_runs too (3 junk_qc + 1 min_runs = 4).
    lock = load_lock(core_excl._lockfile_path("discovery"))
    gens = {s["generator"]: s for s in lock["sources"]}
    assert gens["junk_qc"]["n_entries"] == 3
    assert lock["n_total_entries"] == 4


def test_recompile_matches_committed_snapshot(tmp_path, monkeypatch):
    """assert_lockfile_reproducible PASSES against the committed fixture snapshot."""
    from neuro_workflow.testing.reproduce.lockfile import assert_lockfile_reproducible

    _patch_hermetic(monkeypatch, tmp_path)
    bids = _build_synthetic_cohort(tmp_path)
    # Pre-save the sources so the gate's recompile has something to read.
    _regenerate_and_compile("discovery", bids)

    ok, diffs = assert_lockfile_reproducible(
        "discovery",
        _FIXTURES / "discovery_lock.json",
        bids_dir=bids,
        committed_compiled_path=_FIXTURES / "discovery_compiled.json",
    )
    assert ok, "recompile diverged from committed snapshot:\n" + "\n".join(diffs)
    assert diffs == []


def test_gate_fails_on_tampered_lockfile(tmp_path, monkeypatch):
    """A committed lockfile with a wrong count is reported as a diff (not a pass)."""
    import json

    from neuro_workflow.testing.reproduce.lockfile import assert_lockfile_reproducible

    _patch_hermetic(monkeypatch, tmp_path)
    bids = _build_synthetic_cohort(tmp_path)
    _regenerate_and_compile("discovery", bids)

    tampered = json.loads((_FIXTURES / "discovery_lock.json").read_text())
    tampered["n_total_entries"] = 999
    tampered_path = tmp_path / "tampered_lock.json"
    tampered_path.write_text(json.dumps(tampered))

    ok, diffs = assert_lockfile_reproducible("discovery", tampered_path, bids_dir=bids)
    assert not ok
    assert any("n_total_entries" in d for d in diffs)


def test_cli_exposes_check_lockfile_mode():
    """scripts/reproduce_cohort.py parses --check-lockfile and defines the handler."""
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "reproduce_cohort.py"
    spec = importlib.util.spec_from_file_location("reproduce_cohort_cli", script)
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)

    assert hasattr(rc, "check_lockfile")
    args = rc._parse_args(["discovery", "--check-lockfile"])
    assert args.check_lockfile is True
    assert rc._parse_args(["discovery"]).check_lockfile is False
