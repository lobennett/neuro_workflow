"""Byte-equality gate for the compiled exclusions lockfile.

The committed lockfile (``data/exclusions/{dataset}_lock.json``) records the
provenance of a dataset's compiled exclusion set. This module asserts that a
fresh recompile reproduces that lockfile on every NON-VOLATILE field, so the
exclusion provenance is provably reproducible.

Volatile fields normalized out before comparison
-------------------------------------------------
- ``compiled_at``           — wall-clock timestamp, changes every run.
- ``compiled_at_code_sha``  — git SHA of the working tree (``+dirty`` suffix in a
  checkout with uncommitted changes; a clean SHA on a clean checkout).
- ``compiled_path``         — absolute path; differs per environment / scratch dir.
- ``sources[].ran_at``      — per-generator wall-clock timestamp.
- ``sources[].code_sha``    — per-generator git SHA.

Compared (reproducible) fields
------------------------------
- ``dataset``, ``n_total_entries``, ``n_overrides``.
- ``sources[].{generator, n_entries, args}`` (minus ``ran_at`` / ``code_sha``).
- optionally, the compiled exclusion ENTRY SET (the provenance-stripped 7-tuple
  keyset from :func:`neuro_workflow.testing.reproduce.canonical.compiled_to_keyset`).
"""

from __future__ import annotations

import json
from pathlib import Path

from neuro_workflow.testing.reproduce.canonical import compiled_to_keyset

# Top-level lockfile keys whose values change every run / per environment.
VOLATILE_TOP_FIELDS = frozenset({"compiled_at", "compiled_at_code_sha", "compiled_path"})
# Per-source _meta keys that change every run.
VOLATILE_SOURCE_FIELDS = frozenset({"ran_at", "code_sha"})


def load_lock(path: str | Path) -> dict:
    """Load a lockfile JSON from ``path``."""
    with open(path) as f:
        return json.load(f)


def normalize_lock(lock: dict) -> dict:
    """Return a canonical, volatile-field-stripped view of a lockfile dict.

    Two lockfiles compare equal under this normalization iff they encode the
    same reproducible provenance (same dataset, same entry/override counts, and
    the same per-generator source shape) regardless of when or on which commit
    they were compiled. ``sources`` is sorted by generator name so the compare
    is insensitive to on-disk source-file iteration order.
    """
    sources = [
        {k: v for k, v in src.items() if k not in VOLATILE_SOURCE_FIELDS}
        for src in lock.get("sources", [])
    ]
    sources.sort(key=lambda s: (s.get("generator") or ""))
    return {
        "dataset": lock.get("dataset"),
        "n_total_entries": lock.get("n_total_entries"),
        "n_overrides": lock.get("n_overrides"),
        "sources": sources,
    }


def diff_locks(recompiled: dict, committed: dict) -> list[str]:
    """Return a human-readable list of non-volatile differences (empty == match).

    Both inputs are raw lockfile dicts; they are normalized internally.
    """
    a = normalize_lock(recompiled)
    b = normalize_lock(committed)
    diffs: list[str] = []

    for field in ("dataset", "n_total_entries", "n_overrides"):
        if a[field] != b[field]:
            diffs.append(f"{field}: recompiled={a[field]!r} != committed={b[field]!r}")

    a_src = {s.get("generator"): s for s in a["sources"]}
    b_src = {s.get("generator"): s for s in b["sources"]}
    for gen in sorted(set(a_src) | set(b_src)):
        if gen not in a_src:
            diffs.append(f"sources: '{gen}' in committed but not recompiled")
        elif gen not in b_src:
            diffs.append(f"sources: '{gen}' in recompiled but not committed")
        elif a_src[gen] != b_src[gen]:
            diffs.append(f"sources['{gen}']: recompiled={a_src[gen]!r} != committed={b_src[gen]!r}")
    return diffs


def diff_entry_sets(recompiled: list[dict], committed: list[dict]) -> list[str]:
    """Return diffs between two compiled entry lists as provenance-stripped keysets.

    Uses :func:`compiled_to_keyset` (the 7-tuple
    ``subject, session, task, run, action, source, contrast``) so informational
    fields (reason, metrics) do not spuriously fail the compare.
    """
    a = compiled_to_keyset(recompiled)
    b = compiled_to_keyset(committed)
    diffs: list[str] = []
    only_recompiled = a - b
    only_committed = b - a
    for key in sorted(map(repr, only_recompiled)):
        diffs.append(f"entry only in recompiled: {key}")
    for key in sorted(map(repr, only_committed)):
        diffs.append(f"entry only in committed: {key}")
    return diffs


def assert_lockfile_reproducible(
    dataset: str,
    committed_lock_path: str | Path,
    *,
    bids_dir: str | Path | None = None,
    committed_compiled_path: str | Path | None = None,
) -> tuple[bool, list[str]]:
    """Recompile ``dataset`` and assert the fresh lockfile reproduces the committed one.

    Recompiles by calling :func:`neuro_workflow.core.exclusions.compile_exclusions`
    (which re-reads the already-saved ``sources/*.json``, re-applies overrides, and
    re-derives ``min_runs``), then compares the freshly-written lockfile against
    ``committed_lock_path`` on the non-volatile fields (see module docstring). When
    ``committed_compiled_path`` is given, also compares the compiled exclusion ENTRY
    SET against that committed ``compiled_exclusions.json`` snapshot.

    Returns ``(ok, diffs)`` — ``ok`` is ``True`` and ``diffs`` empty iff the
    recompile reproduces the committed lockfile (and, if provided, entry set).

    NOTE: this writes the lockfile to whatever ``exclusions.LOCKFILE_DIR`` currently
    points at. Callers that must not touch the committed tree redirect
    ``EXCLUSIONS_DIR`` / ``LOCKFILE_DIR`` first (the hermetic seam in
    ``scripts/reproduce_cohort.py``, or a monkeypatch in tests).
    """
    from neuro_workflow.core.exclusions import _lockfile_path, compile_exclusions

    compiled = compile_exclusions(dataset, bids_dir=str(bids_dir) if bids_dir is not None else None)
    recompiled_lock = load_lock(_lockfile_path(dataset))
    committed_lock = load_lock(committed_lock_path)

    diffs = diff_locks(recompiled_lock, committed_lock)

    if committed_compiled_path is not None:
        with open(committed_compiled_path) as f:
            committed_compiled = json.load(f)
        diffs.extend(diff_entry_sets(compiled, committed_compiled))

    return (not diffs, diffs)
