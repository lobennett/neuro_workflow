"""Inspect recon-all logs for high-hole subjects to identify root cause.

For each subject above the hole threshold, scan recon-all.log + recon-all-status.log,
classify likely cause (skull-strip / motion / unknown), and emit a markdown report.
The classification drives the fix-vs-exclude decision for downstream steps.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CauseCategory = Literal['skull_strip', 'motion', 'unknown', 'log_missing']


@dataclass
class DiagnosisResult:
    subject: str
    fs_subject: str
    pre_fix_holes_mean: float
    cause: CauseCategory
    evidence: str


def diagnose_subject(
    subjects_dir: Path, fs_subject: str, pre_fix_holes_mean: float,
) -> DiagnosisResult:
    """Inspect recon-all logs for one subject; return diagnosis."""
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
