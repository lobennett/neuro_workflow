#!/usr/bin/env python3
"""Pre-flight: build symlink view of fmriprep derivatives for XCP-D.

XCP-D 26.0.2 requires per subject either one anat session (one-to-all) or
one anat session per func session (one-to-one). fmriprep sometimes emits an
``anat/`` directory in a non-canonical session that contains only T2w files
(no T1w); XCP-D counts those as additional anatomical sessions and refuses
to run when neither mapping holds.

This script creates a symlink tree at
``<bids>/derivatives/xcp_d_<xcpd_version>_input/`` that mirrors the
fmriprep derivatives but omits T2w-only ``anat/`` directories.  Pass that
view path to xcpd via ``--fmriprep-dir-override``.

Usage:
    uv run python scripts/xcpd_preflight.py discovery_xcpd \\
        --fmriprep-version 25.2.4 --xcpd-version 26.0.2
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".neuro_workflow" / "datasets.json"


def load_dataset_config(dataset_name: str) -> dict:
    if not CONFIG_FILE.exists():
        sys.exit(f"Dataset registry not found at {CONFIG_FILE}")
    datasets = json.loads(CONFIG_FILE.read_text())
    if dataset_name not in datasets:
        sys.exit(f"Dataset '{dataset_name}' not registered. Available: {list(datasets)}")
    return datasets[dataset_name]


def load_subjects(subjects_file: Path) -> list[str]:
    return [s.strip() for s in subjects_file.read_text().splitlines() if s.strip() and not s.startswith("#")]


def anat_lacks_t1w(anat_dir: Path) -> bool:
    """Return True if anat_dir does not contain a T1w NIfTI.

    XCP-D's anat-session check counts any anat directory; sessions that
    contain only T2w or only xfm-files trigger spurious multi-anat errors
    even though XCP-D treats T2w as optional and doesn't use session-level
    xfm files (the T1w-space BOLD outputs already incorporate them).
    """
    return not any(anat_dir.glob("*T1w*.nii.gz"))


def link_session(session_src: Path, session_dst: Path) -> int:
    """Mirror a session directory by symlinking its subdirs.

    Skips ``anat/`` subdirs lacking T1w.  Returns 1 if an anat dir was
    symlinked (i.e., the session contributes anatomy to XCP-D), else 0.
    """
    session_dst.mkdir(parents=True, exist_ok=True)
    anat_count = 0
    for child in session_src.iterdir():
        dst = session_dst / child.name
        if dst.exists() or dst.is_symlink():
            continue
        if child.is_dir() and child.name == "anat":
            if anat_lacks_t1w(child):
                continue
            anat_count = 1
        dst.symlink_to(child)
    return anat_count


def link_subject(sub_src: Path, sub_dst: Path) -> int:
    """Mirror a subject directory.  Returns the count of anat sessions in view."""
    sub_dst.mkdir(parents=True, exist_ok=True)
    anat_sessions = 0
    for child in sub_src.iterdir():
        if child.is_dir() and child.name.startswith("ses-"):
            anat_sessions += link_session(child, sub_dst / child.name)
        else:
            dst = sub_dst / child.name
            if not dst.exists() and not dst.is_symlink():
                # Subject-level files (e.g., sub-X.html, sub-X_T1w.json) and
                # subject-level anat dir for non-longitudinal layouts.
                if child.is_dir() and child.name == "anat":
                    if anat_lacks_t1w(child):
                        continue
                    anat_sessions += 1
                dst.symlink_to(child)
    return anat_sessions


def link_top_level(fmriprep_root: Path, view_root: Path) -> None:
    """Symlink top-level entries (dataset_description.json, sourcedata/, etc.)."""
    view_root.mkdir(parents=True, exist_ok=True)
    for child in fmriprep_root.iterdir():
        if child.name.startswith("sub-"):
            continue
        if child.name == "logs":
            continue
        dst = view_root / child.name
        if not dst.exists() and not dst.is_symlink():
            dst.symlink_to(child)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", help="Dataset name registered with neuro-run (e.g. discovery_xcpd)")
    parser.add_argument("--fmriprep-version", required=True, help="Source fmriprep derivatives version (e.g. 25.2.4)")
    parser.add_argument("--xcpd-version", required=True, help="XCP-D version (used to name the view dir, e.g. 26.0.2)")
    parser.add_argument("--clean", action="store_true", help="Remove an existing view dir before building")
    args = parser.parse_args()

    config = load_dataset_config(args.dataset)
    bids_dir = Path(config["bids_dir"])
    subjects = load_subjects(Path(config["subjects_file"]))

    fmriprep_root = bids_dir / "derivatives" / f"fmriprep_{args.fmriprep_version}"
    view_root = bids_dir / "derivatives" / f"xcp_d_{args.xcpd_version}_input"

    if not fmriprep_root.is_dir():
        sys.exit(f"fmriprep derivatives not found: {fmriprep_root}")

    if args.clean and view_root.exists():
        print(f"Removing existing view: {view_root}")
        shutil.rmtree(view_root)

    link_top_level(fmriprep_root, view_root)

    issues: list[str] = []
    for sub_label in subjects:
        sub_src = fmriprep_root / f"sub-{sub_label}"
        sub_dst = view_root / f"sub-{sub_label}"
        if not sub_src.is_dir():
            issues.append(f"sub-{sub_label}: not present in fmriprep derivatives")
            continue
        n_anat = link_subject(sub_src, sub_dst)
        n_func = sum(1 for ses in sub_dst.iterdir() if ses.is_dir() and (ses / "func").exists())
        marker = "ok" if n_anat == 1 or n_anat == n_func else "WARN"
        print(f"  sub-{sub_label}: {n_anat} anat session(s), {n_func} func session(s) [{marker}]")
        if n_anat == 0:
            issues.append(f"sub-{sub_label}: no T1w-bearing anat session found")
        elif n_anat > 1 and n_anat != n_func:
            issues.append(f"sub-{sub_label}: {n_anat} anat sessions but {n_func} func sessions — neither 1-to-1 nor 1-to-all")

    print(f"\nView built at: {view_root}")
    if issues:
        print("\nWARNINGS:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
