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


_SKULL_STRIP_PATTERNS = [
    re.compile(r'brainmask.+(too aggressive|failed|removed brain)', re.I),
    re.compile(r'skull.?strip.+(may have|might have|aggressive)', re.I),
    re.compile(r'mri_watershed.+(error|warn)', re.I),
]

_MOTION_PATTERNS = [
    re.compile(r'motion artifact', re.I),
    re.compile(r'image.+severely motion.?corrupted', re.I),
]


def diagnose_subject(
    subjects_dir: Path, fs_subject: str, pre_fix_holes_mean: float,
) -> DiagnosisResult:
    """Inspect recon-all logs for one subject; return diagnosis."""
    subject = fs_subject.split('_ses-')[0]
    log_path = subjects_dir / fs_subject / 'scripts' / 'recon-all.log'
    if not log_path.exists():
        return DiagnosisResult(
            subject=subject, fs_subject=fs_subject,
            pre_fix_holes_mean=pre_fix_holes_mean,
            cause='log_missing',
            evidence=f'recon-all.log not found at {log_path}',
        )

    text = log_path.read_text(errors='replace')
    skull_hits = [p.search(text) for p in _SKULL_STRIP_PATTERNS]
    skull_hits = [m for m in skull_hits if m]
    motion_hits = [p.search(text) for p in _MOTION_PATTERNS]
    motion_hits = [m for m in motion_hits if m]

    defects_match = re.search(r'Topology fixer found (\d+) defects?', text)
    defects_str = f'{defects_match.group(1)} defects' if defects_match else ''

    if skull_hits:
        evidence = '; '.join([m.group(0)[:80] for m in skull_hits])
        if defects_str:
            evidence = f'{evidence}; {defects_str}'
        return DiagnosisResult(subject, fs_subject, pre_fix_holes_mean,
                               cause='skull_strip', evidence=evidence)
    if motion_hits:
        evidence = '; '.join([m.group(0)[:80] for m in motion_hits])
        return DiagnosisResult(subject, fs_subject, pre_fix_holes_mean,
                               cause='motion', evidence=evidence)
    return DiagnosisResult(subject, fs_subject, pre_fix_holes_mean,
                           cause='unknown',
                           evidence=f'no diagnostic pattern matched; {defects_str or "no defect line"}')


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
