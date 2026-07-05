#!/usr/bin/env python3
"""exclusion_gate.py — halt on undeliberate exclusion drift.

Diffs a NEWLY-compiled exclusion set against a frozen REFERENCE set (the current
validated compiled exclusions) using the provenance-stripped 7-tuple keyset.
Optionally scopes the diff to one ``source`` (motion, lev1_outlier, …) so a stage
that only just gained a source is compared like-for-like. Exit 0 = no drift;
exit 3 = drift (distinct from other scripts' exit codes). Every added/dropped
scan is printed with its evidence and written to a Markdown report.

Usage::

    uv run python scripts/exclusion_gate.py \
        --new  ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json \
        --reference data/exclusions/discovery_reference_compiled.json \
        --source motion \
        --report /scratch/users/logben/oak_reexec/gate_discovery_motion.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from neuro_workflow.testing.reproduce.canonical import compiled_to_keyset


def _load(path: Path) -> list[dict]:
    """Load a compiled-exclusions file (a bare list of entry dicts).

    Tolerates a ``{"exclusions": [...]}`` wrapper; anything else is a hard error
    rather than a silently-wrong fallback."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    entries = data.get("exclusions") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(
            f"{path}: expected a bare list or a dict with an 'exclusions' list, "
            f"got {type(data).__name__}")
    return entries


def _keyset(entries: list[dict], source: str | None) -> set:
    ks = compiled_to_keyset(entries)
    if source is not None:
        ks = {t for t in ks if t[5] == source}  # element 5 = source
    return ks


def _entries_for_keys(entries: list[dict], keys: set) -> list[dict]:
    """Return the full entry dicts (with evidence) matching a set of 7-tuples."""
    out = []
    for e in entries:
        # recompute this entry's tuple; keep if in keys
        for t in compiled_to_keyset([e]):
            if t in keys:
                out.append(e)
                break  # an entry maps to at most one gating tuple; guard duplicates
    return out


def diff_gate(*, new_path: Path, reference_path: Path,
              source: str | None = None) -> dict:
    """Return {ok, added, dropped} — added = in new not reference; dropped = reverse.

    A ``--source``-scoped run is an intentionally partial view: a scan that moved
    between sources will appear as a drop under its old source and an add under its
    new source; run unscoped (source=None) for the full picture."""
    new_entries = _load(new_path)
    ref_entries = _load(reference_path)
    new_ks = _keyset(new_entries, source)
    ref_ks = _keyset(ref_entries, source)
    added_keys = new_ks - ref_ks
    dropped_keys = ref_ks - new_ks
    return {
        "ok": not added_keys and not dropped_keys,
        "added": _entries_for_keys(new_entries, added_keys),
        "dropped": _entries_for_keys(ref_entries, dropped_keys),
        "source": source,
    }


def _render(result: dict) -> str:
    lines = [f"# Exclusion gate — {'PASS (no drift)' if result['ok'] else 'DRIFT DETECTED'}",
             f"source filter: {result['source'] or '(all)'}", ""]
    for label, key in (("ADDED (in new, not reference)", "added"),
                       ("DROPPED (in reference, not new)", "dropped")):
        lines.append(f"## {label}: {len(result[key])}")
        for e in result[key]:
            lines.append(
                f"- {e['subject']} {e['session']} {e['task']} {e['run']} "
                f"[{e.get('source')}] {e.get('action')} "
                f"contrast={e.get('contrast')} — {e.get('reason')}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--new", required=True, type=Path)
    p.add_argument("--reference", required=True, type=Path)
    p.add_argument("--source", default=None,
                   help="Scope the diff to one source (e.g. motion, lev1_outlier).")
    p.add_argument("--report", type=Path, default=None)
    a = p.parse_args(argv)
    result = diff_gate(new_path=a.new, reference_path=a.reference, source=a.source)
    report = _render(result)
    print(report)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(report)
        print(f"report: {a.report}")
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
