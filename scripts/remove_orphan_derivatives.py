#!/usr/bin/env python3
"""Remove fMRIPrep func-level derivatives for orphan scans (Stage 3 of the BIDS
reconciliation): scans that fMRIPrep processed but are now ``.bidsignore``'d.

fMRIPrep derivatives in these datasets are plain untracked files (not git/annex
tracked), so removal is a plain ``rm`` — there is nothing to ``git rm``. Only the
per-scan ``func/`` files (matched by scan-key) are removed; ``anat/`` and other
session content is scan-agnostic and untouched. The rebuilt XCP-D view already
drops these excluded scans, so no symlink is left dangling.

Reads the orphan list from ``reconcile_worklist_<cohort>.json`` (produced by
reconcile_audit.py). Dry-run by default; pass --execute to delete. Always writes a
manifest of exactly what was (or would be) removed.

Usage:
    uv run python scripts/remove_orphan_derivatives.py discovery --fmriprep-version 25.2.4
    uv run python scripts/remove_orphan_derivatives.py discovery --fmriprep-version 25.2.4 --execute
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRATCH = Path("/scratch/users/logben")
_SK = re.compile(r"(sub-[^_]+)_(ses-[^_]+)_task-([^_]+)_run-(\d+)")


# Confounds are the EVIDENCE a motion exclusion is derived from. If we delete an
# excluded scan's confounds, that motion exclusion can no longer be reproduced from
# the cleaned derivatives (it was a Stage-3 bug that broke validation reproducibility).
# So always PRESERVE the confounds timeseries (tiny) while removing heavy preproc.
_PRESERVE_SUFFIXES = ("_desc-confounds_timeseries.tsv", "_desc-confounds_timeseries.json")


def orphan_func_files(bids_dir: Path, fmriprep_ver: str, scankeys: list[str]) -> dict[str, list[Path]]:
    """Map each orphan scan-key -> the list of fMRIPrep func files to remove.

    Confounds timeseries (.tsv/.json) are preserved as the motion-exclusion evidence
    that keeps the exclusion reproducible after cleanup."""
    deriv = bids_dir / "derivatives" / f"fmriprep_{fmriprep_ver}"
    out: dict[str, list[Path]] = {}
    for sk in scankeys:
        m = _SK.match(sk)
        if not m:
            out[sk] = []
            continue
        sub, ses = m.group(1), m.group(2)
        func = deriv / sub / ses / "func"
        files = sorted(func.glob(f"{sk}_*")) + sorted(func.glob(f"{sk}.*")) if func.is_dir() else []
        out[sk] = [f for f in files if not f.name.endswith(_PRESERVE_SUFFIXES)]
    return out


def run(cohort: str, bids_dir: Path, fmriprep_ver: str, execute: bool) -> dict:
    worklist = json.loads((SCRATCH / f"reconcile_worklist_{cohort}.json").read_text())
    orphans = worklist["fmriprep_orphans"]
    mapping = orphan_func_files(bids_dir, fmriprep_ver, orphans)

    manifest = {"cohort": cohort, "fmriprep_version": fmriprep_ver,
                "executed": execute, "scans": {}}
    total = 0
    for sk, files in mapping.items():
        rels = [str(f.relative_to(bids_dir)) for f in files]
        manifest["scans"][sk] = {"n_files": len(files), "files": rels}
        total += len(files)
        for f in files:
            if execute:
                f.unlink()
    manifest["n_scans"] = len(orphans)
    manifest["n_files_total"] = total

    out_path = SCRATCH / f"orphan_removal_{cohort}.json"
    out_path.write_text(json.dumps(manifest, indent=2))
    verb = "REMOVED" if execute else "WOULD REMOVE (dry-run)"
    print(f"[{cohort}] {verb} {total} func files across {len(orphans)} orphan scans")
    for sk in orphans:
        print(f"  {sk}: {manifest['scans'][sk]['n_files']} files")
    print(f"manifest: {out_path}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("dataset")
    p.add_argument("--fmriprep-version", required=True)
    p.add_argument("--execute", action="store_true", help="actually delete (default: dry-run)")
    p.add_argument("--datasets-json",
                   default=str(Path.home() / ".neuro_workflow" / "datasets.json"))
    args = p.parse_args(argv)
    datasets = json.loads(Path(args.datasets_json).read_text())
    if args.dataset not in datasets:
        print(f"ERROR: dataset '{args.dataset}' not found", file=sys.stderr)
        return 2
    bids_dir = Path(datasets[args.dataset]["bids_dir"])
    run(args.dataset, bids_dir, args.fmriprep_version, args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
