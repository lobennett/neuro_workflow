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


def audit_subject(
    canonical_label: str,
    bids_dir: Path,
    fw_sessions: list[dict[str, Any]],
    config_overrides: dict[str, dict],
) -> list[SessionAuditRow]:
    """Cross-reference FW sessions for a subject against BIDS contents."""
    raise NotImplementedError


def render_audit_md(canonical_label: str, rows: list[SessionAuditRow]) -> str:
    """Render audit rows as a markdown table."""
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
