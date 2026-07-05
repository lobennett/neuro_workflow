#!/usr/bin/env python3
"""Stage 0 divergence audit (read-only): enumerate divergences between the live
scratch BIDS datasets + their derivative chain and the recompiled exclusions, and
emit exact rerun worklists. Nothing is mutated.

Per cohort it computes:
  (a) symlink-view membership vs the new .bidsignore keep-set
      -> now_excluded_from_view / newly_included
  (b) fMRIPrep outputs vs keep-set -> orphans / missing
  (c) lev1 affected cells = events-changed scans + exclusion-changed (subject,task)

Outputs: /scratch/users/logben/reconcile_audit_<cohort>.md (report) and
         /scratch/users/logben/reconcile_worklist_<cohort>.json (worklist).

Usage:
    uv run python scripts/reconcile_audit.py discovery validation
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# repo root on path so `scripts.fmriprep_preflight` imports under sbatch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fmriprep_preflight import parse_bidsignore, path_matches_any  # noqa: E402

SCRATCH = Path("/scratch/users/logben")
FMRIPREP_VER = "25.2.4"
COHORTS = {
    "discovery": SCRATCH / "discovery_bids",
    "validation": SCRATCH / "validation_bids",
}
# (subject, session, bare-task) for scans whose events.tsv changed this cycle.
EVENTS_CHANGED = {
    ("sub-s10", "ses-02", "shapeMatching"),
    ("sub-s43", "ses-11", "stopSignalWFlanker"),
}

_SK = re.compile(r"(sub-[^_/]+)_(ses-[^_/]+)_task-([^_]+)_run-(\d+)")


def view_membership_diff(view_scans: set[str], keep_scans: set[str]) -> tuple[set, set]:
    """Return (now_excluded, newly_included) = (in view not in keep, in keep not in view)."""
    return view_scans - keep_scans, keep_scans - view_scans


def scankey_from_name(name: str) -> str | None:
    """Normalised scan key 'sub-X_ses-Y_task-T_run-Z' from a bold/confounds filename,
    or None if it doesn't carry the four entities (e.g. dataset_description.json)."""
    m = _SK.search(name)
    if not m:
        return None
    return f"{m.group(1)}_{m.group(2)}_task-{m.group(3)}_run-{m.group(4)}"


def _bare(task: str) -> str:
    return task[5:] if task.startswith("task-") else task


def _bold_scankeys(root: Path) -> set[str]:
    """Scan-keys of all *_bold.nii.gz under root (sub-*/ses-*/func/)."""
    out: set[str] = set()
    if not root.exists():
        return out
    for f in root.glob("sub-*/ses-*/func/*_bold.nii.gz"):
        sk = scankey_from_name(f.name)
        if sk:
            out.add(sk)
    return out


def audit(cohort: str) -> dict:
    bids = COHORTS[cohort]
    # Compare against the NEW rendered .bidsignore (the to-be-synced set), not the
    # current on-disk one — the audit runs in Stage 0, before the Stage 1 sync, so
    # it must PREDICT the post-sync divergence. Fall back to on-disk if absent.
    rendered = SCRATCH / f"recompile_{cohort}.bidsignore"
    patterns = parse_bidsignore(rendered if rendered.exists() else bids / ".bidsignore")

    # (a) keep-set = full BIDS bold scan-keys minus .bidsignore matches
    keep: set[str] = set()
    all_bold: set[str] = set()
    for f in bids.glob("sub-*/ses-*/func/*_bold.nii.gz"):
        rel = f.relative_to(bids).as_posix()
        sk = scankey_from_name(f.name)
        if not sk:
            continue
        all_bold.add(sk)
        if not path_matches_any(rel, patterns):
            keep.add(sk)
    view = _bold_scankeys(bids / "derivatives" / f"fmriprep_{FMRIPREP_VER}_input")
    now_excluded, newly_included = view_membership_diff(view, keep)

    # (b) fMRIPrep outputs (confounds) vs keep-set
    fmriprep: set[str] = set()
    deriv = bids / "derivatives" / f"fmriprep_{FMRIPREP_VER}"
    for c in deriv.glob("sub-*/ses-*/func/*_desc-confounds_timeseries.tsv"):
        sk = scankey_from_name(c.name)
        if sk:
            fmriprep.add(sk)
    orphans = sorted(fmriprep - keep)
    missing = sorted(keep - fmriprep)

    # (c) lev1 affected cells from compiled_exclusions.json
    compiled_path = (
        Path.home() / ".neuro_workflow" / "exclusions" / cohort / "compiled_exclusions.json"
    )
    compiled = json.loads(compiled_path.read_text()) if compiled_path.exists() else []
    excl_contrast_cells = sorted(
        {
            f"{e['subject']}|{_bare(e['task'])}"
            for e in compiled
            if e.get("action") == "exclude-contrast"
        }
    )
    behavioral_cells = sorted(
        {
            f"{e['subject']}|{_bare(e['task'])}"
            for e in compiled
            if e.get("action") == "exclude" and e.get("source") == "behavioral-qc"
        }
    )
    # events-changed cells restricted to this cohort's compiled subjects
    cohort_subjects = {e["subject"] for e in compiled}
    events_cells = sorted({f"{s}|{t}" for (s, _ses, t) in EVENTS_CHANGED if s in cohort_subjects})

    return {
        "cohort": cohort,
        "n_bold_total": len(all_bold),
        "n_keep": len(keep),
        "n_view": len(view),
        "n_fmriprep": len(fmriprep),
        "now_excluded_from_view": sorted(now_excluded),
        "newly_included": sorted(newly_included),
        "fmriprep_orphans": orphans,
        "fmriprep_missing": missing,
        "lev1_events_changed": events_cells,
        "lev1_exclusion_changed_cells": sorted(set(excl_contrast_cells) | set(behavioral_cells)),
        "_excl_contrast_cells": excl_contrast_cells,
        "_behavioral_cells": behavioral_cells,
    }


def _render_md(a: dict) -> str:
    L = [f"# Reconcile divergence audit — {a['cohort']}", ""]
    L.append(
        f"- BOLD scans total: {a['n_bold_total']} | keep-set (post-.bidsignore): {a['n_keep']}"
    )
    L.append(f"- symlink view scans: {a['n_view']} | fMRIPrep outputs: {a['n_fmriprep']}")
    L.append("")
    L.append("## Symlink view vs new .bidsignore")
    L.append(
        f"- now-excluded-from-view ({len(a['now_excluded_from_view'])}): {a['now_excluded_from_view']}"
    )
    L.append(
        f"- **newly-included ({len(a['newly_included'])})**: {a['newly_included']}  "
        f"<- MUST be empty for 0 fMRIPrep reruns"
    )
    L.append("")
    L.append("## fMRIPrep vs keep-set")
    L.append(
        f"- orphans (fMRIPrep exists, now excluded) ({len(a['fmriprep_orphans'])}): {a['fmriprep_orphans']}"
    )
    L.append(
        f"- **missing (keep-set, no fMRIPrep) ({len(a['fmriprep_missing'])})**: {a['fmriprep_missing']}  "
        f"<- MUST be empty"
    )
    L.append("")
    L.append("## lev1 rerun worklist")
    L.append(f"- events-changed cells: {a['lev1_events_changed']}")
    L.append(
        f"- exclusion-changed cells ({len(a['lev1_exclusion_changed_cells'])}): "
        f"{a['lev1_exclusion_changed_cells']}"
    )
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    cohorts = argv if argv else sys.argv[1:]
    if not cohorts:
        cohorts = ["discovery", "validation"]
    for cohort in cohorts:
        if cohort not in COHORTS:
            print(f"unknown cohort {cohort}; skipping")
            continue
        a = audit(cohort)
        (SCRATCH / f"reconcile_audit_{cohort}.md").write_text(_render_md(a))
        (SCRATCH / f"reconcile_worklist_{cohort}.json").write_text(json.dumps(a, indent=2))
        print(_render_md(a))
        flag = "OK" if not a["newly_included"] and not a["fmriprep_missing"] else "ATTENTION"
        print(
            f"[{cohort}] {flag}: newly_included={len(a['newly_included'])} "
            f"fmriprep_missing={len(a['fmriprep_missing'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
