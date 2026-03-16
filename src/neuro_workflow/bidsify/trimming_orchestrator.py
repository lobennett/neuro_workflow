"""
Orchestrate trimming of all BIDS and sourcedata files.

Coordinates BOLD NIfTI, events TSV, physio, and behavioral CSV trimming
to ensure consistency across all data types for a given scan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from neuro_workflow.bidsify.bold_trimming import trim_bold_nifti, trim_events_tsv
from neuro_workflow.bidsify.behavioral_trimming import trim_behavioral_csv
from neuro_workflow.bidsify.physio_trimming import trim_physio_data

logger = logging.getLogger(__name__)


@dataclass
class TrimContext:
    """Context for a single trimming operation."""

    subject: str
    session: str
    task: str
    dummy_scans: int = 7
    tr: float = 1.49
    behavioral_cutoff_ms: Optional[float] = None

    @property
    def dummy_offset_ms(self) -> float:
        """Calculate dummy offset in milliseconds."""
        return self.dummy_scans * self.tr * 1000

    @property
    def dummy_offset_s(self) -> float:
        """Calculate dummy offset in seconds."""
        return self.dummy_offset_ms / 1000.0

    @property
    def behavioral_cutoff_trs(self) -> Optional[int]:
        """Calculate behavioral cutoff in TRs."""
        if self.behavioral_cutoff_ms is None:
            return None
        return int(self.behavioral_cutoff_ms / (self.tr * 1000))


class TrimOrchestrator:
    """Orchestrate trimming of all associated BIDS/sourcedata files for a scan."""

    def __init__(self, bids_dir: Path, sourcedata_behavioral_dir: Path):
        """
        Initialize orchestrator.

        Args:
            bids_dir: Root BIDS directory
            sourcedata_behavioral_dir: Path to sourcedata/behavioral_data
        """
        self.bids_dir = Path(bids_dir)
        self.sourcedata_behavioral_dir = Path(sourcedata_behavioral_dir)

    def trim_scan(self, context: TrimContext) -> dict:
        """
        Trim all files associated with a single scan.

        Args:
            context: TrimContext with scan details

        Returns:
            Dictionary with trimming results
        """
        results = {
            "subject": context.subject,
            "session": context.session,
            "task": context.task,
            "trimmed": [],
            "failed": [],
        }

        # Find BOLD files (all echoes)
        func_dir = (
            self.bids_dir / f"sub-{context.subject}" / context.session / "func"
        )
        if not func_dir.exists():
            logger.warning(f"No func directory for {context.subject} {context.session}")
            return results

        # Trim BOLD files (all echoes)
        bold_pattern = f"sub-{context.subject}_{context.session}_*task-{context.task}*_bold.nii.gz"
        for bold_file in func_dir.glob(bold_pattern):
            try:
                trim_bold_nifti(
                    bold_file,
                    dummy_scans=context.dummy_scans,
                    behavioral_cutoff_trs=context.behavioral_cutoff_trs,
                )
                results["trimmed"].append(f"BOLD: {bold_file.name}")
            except Exception as e:
                results["failed"].append(f"BOLD: {bold_file.name} - {str(e)}")
                logger.error(f"Failed to trim BOLD {bold_file.name}: {e}")

        # Trim events TSV
        events_pattern = f"sub-{context.subject}_{context.session}_*task-{context.task}*_events.tsv"
        for events_file in func_dir.glob(events_pattern):
            try:
                trim_events_tsv(
                    events_file,
                    dummy_scans=context.dummy_scans,
                    tr=context.tr,
                    behavioral_cutoff_trs=context.behavioral_cutoff_trs,
                )
                results["trimmed"].append(f"Events: {events_file.name}")
            except Exception as e:
                results["failed"].append(f"Events: {events_file.name} - {str(e)}")
                logger.error(f"Failed to trim events {events_file.name}: {e}")

        # Trim physio files (cardiac and respiratory)
        for recording in ["cardiac", "respiratory"]:
            physio_pattern = f"sub-{context.subject}_{context.session}_*task-{context.task}*_recording-{recording}_physio.tsv.gz"
            for physio_file in func_dir.glob(physio_pattern):
                physio_json = physio_file.with_suffix("").with_suffix(".json")
                try:
                    trim_physio_data(
                        physio_file,
                        physio_json,
                        dummy_scans=context.dummy_scans,
                        tr=context.tr,
                        behavioral_cutoff_ms=context.behavioral_cutoff_ms,
                    )
                    results["trimmed"].append(f"Physio ({recording}): {physio_file.name}")
                except Exception as e:
                    results["failed"].append(
                        f"Physio ({recording}): {physio_file.name} - {str(e)}"
                    )
                    logger.error(f"Failed to trim physio {physio_file.name}: {e}")

        # Trim behavioral CSV if found
        beh_dir = (
            self.sourcedata_behavioral_dir
            / f"sub-{context.subject}"
            / context.session
            / "beh"
        )
        if beh_dir.exists() and context.behavioral_cutoff_ms is not None:
            beh_pattern = f"*task-{context.task}*.csv"
            for beh_file in beh_dir.glob(beh_pattern):
                try:
                    trim_behavioral_csv(
                        beh_file,
                        cutoff_time_ms=context.behavioral_cutoff_ms,
                    )
                    results["trimmed"].append(f"Behavioral CSV: {beh_file.name}")
                except Exception as e:
                    results["failed"].append(
                        f"Behavioral CSV: {beh_file.name} - {str(e)}"
                    )
                    logger.error(f"Failed to trim behavioral {beh_file.name}: {e}")

        return results
