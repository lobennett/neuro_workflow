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
