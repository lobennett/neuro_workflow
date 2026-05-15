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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subjects-dir', type=Path, required=True,
                        help='FreeSurfer SUBJECTS_DIR (e.g. <bids>/derivatives/fmriprep_*/sourcedata/freesurfer)')
    parser.add_argument('--cohort-tsv', type=Path, required=True,
                        help='qa_report cohort.tsv (provides per-subject hole counts)')
    parser.add_argument('--threshold', type=int, default=100,
                        help='Mean pre-fix holes threshold (default 100)')
    parser.add_argument('--output-md', type=Path, default=None,
                        help='Optional: write report to markdown file')
    args = parser.parse_args()

    import pandas as pd
    df = pd.read_csv(args.cohort_tsv, sep='\t')
    flagged = df.loc[df['fs_holes_mean'] > args.threshold]

    if len(flagged) == 0:
        print(f'No subjects exceed {args.threshold} mean pre-fix holes; nothing to diagnose.')
        return 0

    results = []
    for _, row in flagged.iterrows():
        candidates = sorted(args.subjects_dir.glob(f'{row["subject"]}_ses-*'))
        candidates = [c for c in candidates if c.is_dir()]
        if not candidates:
            results.append(DiagnosisResult(
                subject=row['subject'], fs_subject='(none)',
                pre_fix_holes_mean=row['fs_holes_mean'],
                cause='log_missing',
                evidence='No FreeSurfer subject dir found',
            ))
            continue
        fs_subj = candidates[0].name
        results.append(diagnose_subject(args.subjects_dir, fs_subj, row['fs_holes_mean']))

    lines = [
        '# Surface diagnosis — high-hole subjects',
        '',
        f'Threshold: mean pre-fix holes > {args.threshold}',
        '',
        '| Subject | FS subject | Mean holes | Cause | Evidence |',
        '|---|---|---|---|---|',
    ]
    for r in results:
        lines.append(f'| {r.subject} | {r.fs_subject} | {r.pre_fix_holes_mean:.1f} | {r.cause} | {r.evidence} |')

    md = '\n'.join(lines) + '\n'
    if args.output_md:
        args.output_md.write_text(md)
        print(f'Wrote {args.output_md}')
    else:
        print(md)

    n_fix = sum(1 for r in results if r.cause == 'skull_strip')
    n_excl = len(results) - n_fix
    print(f'\nFix attempts (skull_strip cause): {n_fix}', file=sys.stderr)
    print(f'Direct exclusions (other causes): {n_excl}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
