#!/usr/bin/env python
"""Generate QA HTML cohort dashboard from fmriprep derivatives.

Usage:
    uv run python scripts/qa_report.py \\
        --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \\
        [--output-dir PATH] \\
        [--subjects sub-s03 sub-s10 ...] \\
        [--decisions PATH] \\
        [--no-reliability-movies] \\
        [--euler-n-sigma 2.0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neuro_workflow.qa.report import build_reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fmriprep-dir", required=True, type=Path,
                        help="fmriprep derivatives directory "
                             "(e.g. <bids>/derivatives/fmriprep_25.2.4)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: <fmriprep-dir>/qa_html)")
    parser.add_argument("--subjects", nargs="+", default=None,
                        help="Restrict to these subjects (default: all)")
    parser.add_argument("--decisions", type=Path, default=None,
                        help="Path to qc_decisions.tsv (sidecar TSV with QC decisions)")
    parser.add_argument("--no-reliability-movies", action="store_true",
                        help="Skip brm reliability movie generation")
    parser.add_argument("--euler-n-sigma", type=float, default=2.0,
                        help="Cohort MAD multiplier for Euler outlier detection (default 2.0)")
    args = parser.parse_args()

    fmriprep_dir: Path = args.fmriprep_dir
    if not fmriprep_dir.is_dir():
        print(f"Error: fmriprep derivatives not found: {fmriprep_dir}", file=sys.stderr)
        return 1

    output_dir: Path = args.output_dir or (fmriprep_dir / "qa_html")

    build_reports(
        fmriprep_dir=fmriprep_dir,
        output_dir=output_dir,
        subjects=args.subjects,
        decisions_path=args.decisions,
        no_reliability_movies=args.no_reliability_movies,
        euler_n_sigma=args.euler_n_sigma,
    )
    print(f"Wrote QA HTML to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
