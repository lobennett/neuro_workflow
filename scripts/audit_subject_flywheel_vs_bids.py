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
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
