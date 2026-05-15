"""Triage subjects by pre-fix Euler hole count from a qa_report cohort.tsv.

Outputs a candidate-list of subjects with pre-fix holes above threshold.
Used as input to diagnose_high_hole_subjects.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def find_high_hole_subjects(cohort_tsv: Path, threshold: int) -> pd.DataFrame:
    """Read a cohort.tsv and return rows where mean pre-fix holes > threshold."""
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
