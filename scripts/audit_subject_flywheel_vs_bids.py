"""Audit a single subject's Flywheel sessions vs current BIDS contents.

Outputs a markdown report mapping each Flywheel session to its BIDS session
number (or EXCLUDED / MISSING). Used to surface misclassified sessions before
fixing them in pipeline_config.json + re-running bidsify.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionAuditRow:
    fw_session_label: str
    fw_timestamp: str
    bids_session: str  # "ses-NN", "EXCLUDED", "MISSING", "REASSIGNED"
    n_t1w: int
    n_t2w: int
    n_bold: int
    n_fmap: int
    notes: str


def _classify_acquisition(label: str) -> str:
    """Classify a Flywheel acquisition label into a BIDS scan-type bucket."""
    L = label.lower()
    if 't1w' in L or 'mprage' in L:
        return 't1w'
    if 't2w' in L or ('t2' in L and 't2*' not in L and 't2star' not in L):
        return 't2w'
    if 'bold' in L or 'task' in L or 'rest' in L:
        return 'bold'
    if 'fmap' in L or 'fieldmap' in L or 'epi' in L:
        return 'fmap'
    return 'other'


def _count_acquisitions(acquisitions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {'t1w': 0, 't2w': 0, 'bold': 0, 'fmap': 0}
    for acq in acquisitions:
        bucket = _classify_acquisition(acq.get('label', ''))
        if bucket in counts:
            counts[bucket] += 1
    return counts


def audit_subject(
    canonical_label: str,
    bids_dir: Path,
    fw_sessions: list[dict[str, Any]],
    config_overrides: dict[str, dict],
) -> list[SessionAuditRow]:
    """Cross-reference FW sessions for a subject against BIDS contents."""
    # Sort FW sessions chronologically (skipping excluded/reassigned for the
    # ses-NN numbering, since bidsify also skips them).
    sorted_sessions = sorted(fw_sessions, key=lambda s: s.get('timestamp', ''))

    bids_subj_dir = bids_dir / f'sub-{canonical_label}'
    bids_session_counter = 0

    rows: list[SessionAuditRow] = []
    for sess in sorted_sessions:
        label = sess['fw_session_label']
        override = config_overrides.get(label, {})
        counts = _count_acquisitions(sess.get('acquisitions', []))

        if override.get('exclude'):
            bids_label = 'EXCLUDED'
            notes = override.get('reason', '')
        elif override.get('reassign_to'):
            bids_label = 'REASSIGNED'
            notes = f"reassigned to {override['reassign_to']}: {override.get('reason', '')}"
        else:
            bids_session_counter += 1
            candidate = f'ses-{bids_session_counter:02d}'
            if (bids_subj_dir / candidate).is_dir():
                bids_label = candidate
                notes = ''
            else:
                bids_label = 'MISSING'
                notes = f'FW session present but no {candidate} dir in BIDS'

        rows.append(SessionAuditRow(
            fw_session_label=label,
            fw_timestamp=sess.get('timestamp', ''),
            bids_session=bids_label,
            n_t1w=counts['t1w'],
            n_t2w=counts['t2w'],
            n_bold=counts['bold'],
            n_fmap=counts['fmap'],
            notes=notes,
        ))
    return rows


def render_audit_md(canonical_label: str, rows: list[SessionAuditRow]) -> str:
    """Render audit rows as a markdown table."""
    lines = [
        f'# Audit — sub-{canonical_label}',
        '',
        '| FW Session | Timestamp | BIDS Session | T1w | T2w | BOLD | Fmap | Notes |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for r in rows:
        lines.append(
            f'| {r.fw_session_label} | {r.fw_timestamp} | {r.bids_session} | '
            f'{r.n_t1w} | {r.n_t2w} | {r.n_bold} | {r.n_fmap} | {r.notes} |'
        )
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True,
                        help='Canonical subject label (e.g., s03)')
    parser.add_argument('--bids-dir', type=Path, required=True,
                        help='BIDS root (e.g., /scratch/users/logben/discovery_bids)')
    parser.add_argument('--config', type=Path,
                        default=Path('config/pipeline_config.json'),
                        help='Path to pipeline_config.json')
    parser.add_argument('--output-md', type=Path, default=None,
                        help='Write report to this path (else print to stdout)')
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    fw_cfg = config['flywheel']
    aliases = fw_cfg.get('subject_aliases', {})
    overrides_all = fw_cfg.get('session_overrides', {})
    subject_overrides = overrides_all.get(args.subject, {})

    # Use the existing bidsify FW query infrastructure
    import flywheel
    from neuro_workflow.bidsify.flywheel_query import (
        collect_subject_sessions, query_project_subjects,
    )
    fw = flywheel.Client()
    all_subjects, _project = query_project_subjects(fw, fw_cfg['project'])
    session_infos = collect_subject_sessions(
        canonical_label=args.subject,
        all_subjects=all_subjects,
        aliases=aliases,
        session_overrides=overrides_all,
    )

    # Adapt session_infos to the audit_subject input shape
    fw_sessions = []
    for info in session_infos:
        acqs = []
        for a in info['fw_session'].acquisitions():
            acqs.append({'label': a.label})
        fw_sessions.append({
            'fw_session_label': info['fw_session'].label,
            'timestamp': info['timestamp'].isoformat() if info['timestamp'] else '',
            'acquisitions': acqs,
        })

    rows = audit_subject(args.subject, args.bids_dir, fw_sessions, subject_overrides)
    md = render_audit_md(args.subject, rows)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md)
        print(f'Wrote {args.output_md}')
    else:
        print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
