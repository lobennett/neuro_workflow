# File: src/neuro_workflow/bidsify/exclusions_manifest.py
"""
Generate and manage exclusions manifest.

Tracks all exclusions and trimming decisions in a single authoritative JSON file
for downstream analysis scripts to reference.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ExclusionsManifest:
    """Manage exclusions and trimming metadata in JSON manifest."""

    def __init__(self, output_file: Path):
        """
        Initialize manifest.

        Args:
            output_file: Path to save exclusions.json
        """
        self.output_file = Path(output_file)
        self.data = {
            "generated_date": datetime.now().isoformat(),
            "source": "BIDS trimming & audit pipeline",
            "categories": {
                "dummy_scans_removed": "7 dummy TRs removed from all scans",
                "behavioral_trim": "Scan terminated early - trimmed at behavioral cutoff",
                "behavioral_flag_no_trim": "Behavioral anomaly (fell asleep) - flagged but not trimmed",
                "irreconcilable": "BOLD exists but no behavioral data - events file cannot be created",
                "duplicate_anatomical": "Duplicate T1w/T2w from earlier session - lower quality",
            },
            "scans": [],
        }

    def add_dummy_removal(
        self,
        subject: str,
        session: str,
        task: str,
    ) -> None:
        """Record dummy scan removal for a scan."""
        entry = {
            "subject": subject,
            "session": session,
            "task": task,
            "category": "dummy_scans_removed",
            "dummy_scans": 7,
            "dummy_offset_ms": 10430,
            "dummy_offset_s": 10.43,
        }
        self.data["scans"].append(entry)

    def add_behavioral_trim(
        self,
        subject: str,
        session: str,
        task: str,
        original_trs: int,
        trimmed_trs: int,
        behavioral_cutoff_ms: float,
    ) -> None:
        """Record behavioral trimming for a cut-short scan."""
        entry = {
            "subject": subject,
            "session": session,
            "task": task,
            "category": "behavioral_trim",
            "reason": "Task terminated early",
            "source": "behavior_qc/behavior_cut_short",
            "original_trs": original_trs,
            "trimmed_trs": trimmed_trs,
            "behavioral_cutoff_ms": behavioral_cutoff_ms,
            "dummy_scans_removed": 7,
            "scans_affected": ["echo-1", "echo-2", "echo-3"],
            "bidsignore_patterns": [
                f"sub-{subject}/{session}/func/*{task}*_bold_timeTrimmed.nii.gz",
            ],
        }
        self.data["scans"].append(entry)

    def add_behavioral_flag_no_trim(
        self,
        subject: str,
        session: str,
        task: str,
        reason: str,
        analyst_notes: Optional[str] = None,
    ) -> None:
        """Record behavioral anomaly that is NOT trimmed."""
        entry = {
            "subject": subject,
            "session": session,
            "task": task,
            "category": "behavioral_flag_no_trim",
            "reason": reason,
            "action": "include_in_analysis_with_caution",
        }
        if analyst_notes:
            entry["analyst_notes"] = analyst_notes

        self.data["scans"].append(entry)

    def save(self) -> None:
        """Save manifest to JSON file."""
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w') as f:
            json.dump(self.data, f, indent=2)

        logger.info(f"Saved exclusions manifest to {self.output_file}")
