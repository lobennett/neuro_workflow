#!/usr/bin/env python3
"""Pre-flight: build symlink BIDS view that physically excludes .bidsignore'd files.

pybids does not honor .bidsignore, so fmriprep would otherwise process every file
in the BIDS tree. This script creates a parallel symlink directory under
<bids_dir>/derivatives/fmriprep_<version>_input/ where excluded files are simply
not linked, then sanity-checks that every subject still has a usable T1w.

Usage:
    uv run python scripts/fmriprep_preflight.py discovery
    uv run python scripts/fmriprep_preflight.py validation
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
from pathlib import Path


def parse_bidsignore(path: Path) -> list[str]:
    """Return non-comment, non-blank lines from a .bidsignore file."""
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def path_matches_any(rel_path: str, patterns: list[str]) -> bool:
    """Return True if `rel_path` matches any gitignore-style pattern.

    Implements gitignore semantics where `*` does not span `/` separators by
    splitting both path and pattern on `/` and matching segment-by-segment.

    Limitation: patterns without a `/` (e.g., ``*.bak``) only match top-level
    files, not files at arbitrary depth. All patterns in this project's
    .bidsignore files are fully-qualified, so this is acceptable for the
    current use case but should be revisited if bare patterns are added.
    """
    path_parts = rel_path.split("/")
    for pattern in patterns:
        pattern_parts = pattern.split("/")
        if len(path_parts) != len(pattern_parts):
            continue
        if all(fnmatch.fnmatchcase(p, pat) for p, pat in zip(path_parts, pattern_parts)):
            return True
    return False


TOP_LEVEL_METADATA = {
    "dataset_description.json",
    "README",
    "README.md",
    "README.txt",
    "participants.tsv",
    "participants.json",
    ".bidsignore",
    "CHANGES",
    "CITATION.cff",
}


def build_view(bids_dir: Path, view_dir: Path) -> dict:
    """Build a symlink view of `bids_dir` at `view_dir` excluding .bidsignore patterns.

    Top-level non-metadata directories (derivatives/, sourcedata/, code/, etc.) are
    skipped automatically because the algorithm only walks subject directories
    (matched via ``glob("sub-*")``) and a curated set of top-level metadata files.

    Returns a summary dict with files_linked, files_excluded.
    Idempotent: existing identical symlinks are left in place; missing ones are created;
    extras from a previous run are removed.
    """
    bids_dir = bids_dir.resolve()
    view_dir = Path(view_dir)
    patterns = parse_bidsignore(bids_dir / ".bidsignore")

    desired_links: dict[Path, Path] = {}  # view_path -> target

    # Top-level metadata files
    for child in bids_dir.iterdir():
        if child.is_file() and child.name in TOP_LEVEL_METADATA:
            desired_links[view_dir / child.name] = child

    # Subject directories
    for sub_dir in sorted(bids_dir.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        for fpath in sorted(sub_dir.rglob("*")):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(bids_dir).as_posix()
            if path_matches_any(rel, patterns):
                continue
            desired_links[view_dir / rel] = fpath

    # Apply: ensure view_dir exists, create symlinks, remove stale
    view_dir.mkdir(parents=True, exist_ok=True)
    _sync_symlinks(view_dir, desired_links)

    excluded_count = _count_excluded_files(bids_dir, patterns)
    return {
        "files_linked": len(desired_links),
        "files_excluded": excluded_count,
        "patterns": patterns,
    }


def _sync_symlinks(view_dir: Path, desired: dict[Path, Path]) -> None:
    """Create missing symlinks; replace mismatched ones; leave correct ones alone."""
    for view_path, target in desired.items():
        view_path.parent.mkdir(parents=True, exist_ok=True)
        if view_path.is_symlink():
            if Path(view_path.readlink()).resolve() == target.resolve():
                continue
            view_path.unlink()
        elif view_path.is_dir():
            shutil.rmtree(view_path)
        elif view_path.exists():
            view_path.unlink()
        view_path.symlink_to(target.resolve())

    # Sweep for stale symlinks under view_dir not in desired set
    desired_paths = set(desired.keys())
    for fpath in view_dir.rglob("*"):
        if fpath.is_symlink() and fpath not in desired_paths:
            fpath.unlink()

    _prune_empty_dirs(view_dir)


def _prune_empty_dirs(root: Path) -> None:
    """Remove empty directories under `root` (deepest first). Leaves `root` itself."""
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()


def verify_view(view_dir: Path, expected_multi_anat: dict[str, dict[str, int]]) -> list[str]:
    """Return a list of error strings; empty list means view is valid.

    Checks:
    1. Every subject directory in the view has ≥ 1 T1w file.  Subjects that are
       present in the source BIDS directory but have no files in the view (because
       all their files were .bidsignore'd) are also reported as missing T1w.
    2. For each subject in `expected_multi_anat`, the view contains exactly the
       expected number of T1w / T2w files. The dict shape is:
         {"s1351": {"T1w": 2}, "s1399": {"T2w": 2}}

    The source BIDS directory is discovered by resolving the dataset_description.json
    symlink that build_view links into the view (when present in the source BIDS dir).
    """
    errors: list[str] = []

    if not view_dir.is_dir():
        return [f"view_dir does not exist: {view_dir}"]

    # Discover source BIDS dir so we can detect subjects entirely excluded from the view.
    bids_dir: Path | None = None
    desc_link = view_dir / "dataset_description.json"
    if desc_link.is_symlink():
        bids_dir = desc_link.resolve().parent

    # Collect subjects present in the view
    view_subjects: dict[str, Path] = {}
    for sub_dir in sorted(view_dir.glob("sub-*")):
        if sub_dir.is_dir():
            view_subjects[sub_dir.name.removeprefix("sub-")] = sub_dir

    # Collect all subjects present in the source BIDS dir (if discoverable)
    all_subjects: set[str] = set(view_subjects.keys())
    if bids_dir is not None:
        for sub_dir in bids_dir.glob("sub-*"):
            if sub_dir.is_dir():
                all_subjects.add(sub_dir.name.removeprefix("sub-"))

    for sub in sorted(all_subjects):
        if sub not in view_subjects:
            errors.append(f"sub-{sub}: no T1w in view")
            continue
        sub_dir = view_subjects[sub]
        t1w_files = list(sub_dir.glob("ses-*/anat/*T1w.nii.gz"))
        t2w_files = list(sub_dir.glob("ses-*/anat/*T2w.nii.gz"))
        if not t1w_files:
            errors.append(f"sub-{sub}: no T1w in view")
            continue
        if sub in expected_multi_anat:
            for suffix, expected_count in expected_multi_anat[sub].items():
                actual = len(t1w_files) if suffix == "T1w" else len(t2w_files)
                if actual != expected_count:
                    errors.append(
                        f"sub-{sub}: expected {expected_count} {suffix} per EXCLUSIONS.md, "
                        f"view has {actual}"
                    )
    return errors


def _count_excluded_files(bids_dir: Path, patterns: list[str]) -> int:
    n = 0
    for sub_dir in bids_dir.glob("sub-*"):
        if not sub_dir.is_dir():
            continue
        for fpath in sub_dir.rglob("*"):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(bids_dir).as_posix()
            if path_matches_any(rel, patterns):
                n += 1
    return n
