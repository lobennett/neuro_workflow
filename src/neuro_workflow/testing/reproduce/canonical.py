"""Provenance-stripped canonical sets for reproduction diffs."""
from __future__ import annotations
from pathlib import Path
from typing import Iterable

_GATING_ACTIONS = {"exclude", "trim"}


def _bare_task(task: str) -> str:
    return task[5:] if task.startswith("task-") else task


def compiled_to_keyset(compiled: Iterable[dict]) -> set:
    """6-tuple gating set (subject, session, task[bare], run, action, source);
    reason intentionally excluded (informational)."""
    out = set()
    for e in compiled:
        if e.get("action") not in _GATING_ACTIONS:
            continue
        out.add((e["subject"], e["session"], _bare_task(e["task"]),
                 e["run"], e["action"], e.get("source")))
    return out


def bidsignore_lineset(text: str) -> set:
    return {ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def bids_fileset(bids_dir: Path) -> set:
    """All files under sub-*/ (bold, events, sidecars, anat), as posix relpaths.

    Physiological recordings (``*_physio.*``) are intentionally EXCLUDED: they are
    derived from a separate Flywheel gephysio processing step that the inventory
    snapshot + FakeFlywheel replay does not model, and they are not inputs to
    lev1/lev2. Reproducing physio is an accepted out-of-scope boundary (see the
    harness design doc "Out of scope"); leaving them in would make the filename
    diff spuriously FAIL on files the replay never claims to produce.
    """
    bids_dir = Path(bids_dir)
    out = set()
    for sub in sorted(bids_dir.glob("sub-*")):
        for f in sub.rglob("*"):
            if f.is_file() and "_physio." not in f.name:
                out.add(f.relative_to(bids_dir).as_posix())
    return out
