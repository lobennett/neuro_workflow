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
    df = pd.read_csv(cohort_tsv, sep='\t')
    df['mean_holes'] = (df['lh_holes'] + df['rh_holes']) / 2
    return df.loc[df['mean_holes'] > threshold].reset_index(drop=True)


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
