#!/usr/bin/env python
"""Run cohort outlier QC on lev1 outputs.

Usage:
    uv run python scripts/lev1_outliers.py \\
        --lev1-dir /scratch/.../lev1_discovery \\
        --output-dir /scratch/.../qa_lev1 \\
        [--exclusions-file data/exclusions/discovery_compiled.json] \\
        [--n-std 3.0] [--vif-threshold 5.0] [--outlier-pct-threshold 10.0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neuro_workflow.analysis.core.utils import load_exclusions
from neuro_workflow.qa.lev1_outliers import detect_lev1_outliers


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lev1-dir", type=Path, action="append", required=True,
                   help="lev1 subject-output dir (repeatable)")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--exclusions-file", type=Path, default=None,
                   help="Compiled exclusions JSON (e.g. data/exclusions/"
                        "discovery_compiled.json). Scans with action 'exclude'/"
                        "'trim' are dropped before cohort outlier statistics.")
    p.add_argument("--n-std", type=float, default=3.0,
                   help="SD threshold for outlier voxels (default 3.0)")
    p.add_argument("--vif-threshold", type=float, default=5.0)
    p.add_argument("--outlier-pct-threshold", type=float, default=10.0)
    p.add_argument("--contrast-glob", type=str,
                   default="sub-s*/task-*/indiv_contrasts/*stat-effect-size.nii.gz")
    p.add_argument("--vif-glob", type=str,
                   default="sub-s*/task-*/quality_control/*_desc-contrastVIFs.csv")
    args = p.parse_args()

    for d in args.lev1_dir:
        if not d.is_dir():
            print(f"Error: lev1 dir not found: {d}", file=sys.stderr)
            return 1

    exclusions = None
    if args.exclusions_file is not None:
        if not args.exclusions_file.is_file():
            print(f"Error: exclusions file not found: {args.exclusions_file}",
                  file=sys.stderr)
            return 1
        exclusions = load_exclusions(args.exclusions_file)
        print(f"Loaded {len(exclusions)} exclusion keys from "
              f"{args.exclusions_file}")

    detect_lev1_outliers(
        lev1_dirs=args.lev1_dir,
        output_dir=args.output_dir,
        n_std=args.n_std,
        vif_threshold=args.vif_threshold,
        outlier_pct_threshold=args.outlier_pct_threshold,
        contrast_glob=args.contrast_glob,
        vif_glob=args.vif_glob,
        exclusions=exclusions,
    )
    print(f"Wrote lev1 outlier report to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
