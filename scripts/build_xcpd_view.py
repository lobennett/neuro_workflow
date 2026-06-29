#!/usr/bin/env python3
"""Build the XCP-D input symlink view from the fMRIPrep *output* derivatives.

XCP-D consumes fMRIPrep outputs (not raw BIDS). This view lives at
``<bids>/derivatives/xcp_d_<ver>_input`` and mirrors ``fmriprep_<ver>/`` with:

  - top-level ``dataset_description.json``, ``.bidsignore``, ``sourcedata`` (whole-symlink)
  - per subject: ``anat/``, ``figures/``, ``log/`` (whole-dir symlinks — not scan-specific)
  - per subject/session: ``func/`` and ``fmap/`` as directories of PER-FILE symlinks,
    so that individual files belonging to a ``.bidsignore``'d scan are dropped.

The drop set is the cohort's excluded scan-keys, computed from the (de-annexed,
reconciled) raw-BIDS ``.bidsignore`` — identical keep-set logic to the rebuilt
``fmriprep_<ver>_input`` view, so the two views stay consistent. Field-map files
that carry no task/run scan-key are never dropped.

Idempotent: the view directory is rebuilt from scratch each run (it contains only
symlinks + empty dirs — targets are never touched).

Usage:
    uv run python scripts/build_xcpd_view.py discovery --fmriprep-version 25.2.4 --xcpd-version 26.0.2
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fmriprep_preflight import parse_bidsignore, path_matches_any  # noqa: E402
from scripts.reconcile_audit import scankey_from_name  # noqa: E402

# func/fmap are symlinked PER FILE so individual excluded scans can be dropped;
# every other directory (anat, log, figures, …) is scan-agnostic and is symlinked
# whole-dir. This mirrors the real fMRIPrep output layout where figures/ is
# subject-level while anat/, func/, fmap/, log/ live under each ses-*/ (and
# ses-multi-*/).
PER_FILE_SESSION = ("func", "fmap")
TOP_LEVEL = ("dataset_description.json", ".bidsignore", "sourcedata")


def excluded_scankeys(bids_dir: Path) -> set[str]:
    """Scan-keys of raw BOLD scans matched by the dataset's .bidsignore."""
    patterns = parse_bidsignore(bids_dir / ".bidsignore")
    excluded: set[str] = set()
    for f in bids_dir.glob("sub-*/ses-*/func/*_bold.nii.gz"):
        rel = f.relative_to(bids_dir).as_posix()
        if path_matches_any(rel, patterns):
            sk = scankey_from_name(f.name)
            if sk:
                excluded.add(sk)
    return excluded


def plan_links(fmriprep_out: Path, view_dir: Path, drop_keys: set[str]) -> dict[Path, Path]:
    """Return {view_path -> target} for the XCP-D view."""
    desired: dict[Path, Path] = {}

    for name in TOP_LEVEL:
        src = fmriprep_out / name
        if src.exists() or src.is_symlink():
            desired[view_dir / name] = src

    for sub_dir in sorted(fmriprep_out.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        sub = sub_dir.name
        for child in sorted(sub_dir.iterdir()):
            if not child.is_dir():
                continue
            name = child.name
            if name.startswith("ses-"):
                # session: func/fmap per-file (exclusion-filtered); rest whole-dir.
                for sub_child in sorted(child.iterdir()):
                    if not sub_child.is_dir():
                        continue
                    if sub_child.name in PER_FILE_SESSION:
                        for f in sorted(sub_child.iterdir()):
                            if not (f.is_file() or f.is_symlink()):
                                continue
                            sk = scankey_from_name(f.name)
                            if sk and sk in drop_keys:
                                continue  # excluded scan's derivative — drop it
                            rel = f.relative_to(fmriprep_out).as_posix()
                            desired[view_dir / rel] = f
                    else:  # anat, log, … — scan-agnostic, whole-dir
                        rel = sub_child.relative_to(fmriprep_out).as_posix()
                        desired[view_dir / rel] = sub_child
            elif name.startswith("sub-"):
                continue  # skip nested sub-* artifacts
            else:
                # subject-level scan-agnostic dir (e.g. figures/) — whole-dir
                desired[view_dir / sub / name] = child
    return desired


def build(bids_dir: Path, fmriprep_ver: str, xcpd_ver: str) -> dict:
    fmriprep_out = bids_dir / "derivatives" / f"fmriprep_{fmriprep_ver}"
    view_dir = bids_dir / "derivatives" / f"xcp_d_{xcpd_ver}_input"
    if not fmriprep_out.is_dir():
        raise SystemExit(f"ERROR: fMRIPrep output not found: {fmriprep_out}")

    drop_keys = excluded_scankeys(bids_dir)
    desired = plan_links(fmriprep_out, view_dir, drop_keys)

    # Rebuild from scratch (symlinks + empty dirs only; targets untouched).
    if view_dir.exists() or view_dir.is_symlink():
        shutil.rmtree(view_dir)
    view_dir.mkdir(parents=True)
    for view_path, target in desired.items():
        view_path.parent.mkdir(parents=True, exist_ok=True)
        view_path.symlink_to(target.resolve())

    n_func = sum(1 for p in desired if p.parent.name == "func")
    n_fmap = sum(1 for p in desired if p.parent.name == "fmap")
    return {
        "view_dir": str(view_dir),
        "n_dropped_scans": len(drop_keys),
        "n_links": len(desired),
        "n_func_files": n_func,
        "n_fmap_files": n_fmap,
        "n_subjects": len(list(view_dir.glob("sub-*"))),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("dataset")
    p.add_argument("--fmriprep-version", required=True)
    p.add_argument("--xcpd-version", required=True)
    p.add_argument(
        "--datasets-json",
        default=str(Path.home() / ".neuro_workflow" / "datasets.json"),
    )
    args = p.parse_args(argv)

    datasets = json.loads(Path(args.datasets_json).read_text())
    if args.dataset not in datasets:
        print(f"ERROR: dataset '{args.dataset}' not in {args.datasets_json}", file=sys.stderr)
        return 2
    bids_dir = Path(datasets[args.dataset]["bids_dir"])

    summary = build(bids_dir, args.fmriprep_version, args.xcpd_version)
    print(f"[{args.dataset}] xcp_d view rebuilt:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
