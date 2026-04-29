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
