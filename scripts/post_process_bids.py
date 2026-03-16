#!/usr/bin/env python3
"""
Post-process BIDS directories to trim dummy scans and behavioral cutoffs.

Usage:
    uv run python scripts/post_process_bids.py \
        --bids-dir /path/to/bids \
        --sourcedata-beh /path/to/sourcedata/behavioral_data \
        --output-manifest sourcedata/exclusions.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from neuro_workflow.bidsify.exclusions_manifest import ExclusionsManifest
from neuro_workflow.bidsify.trimming_orchestrator import TrimContext, TrimOrchestrator

logger = logging.getLogger(__name__)

# Trimming manifest from behavior_qc
TRIMMING_MANIFEST = {
    "discovery_bids": [
        {"subject": "s19", "session": "ses-07", "task": "stopSignal", "behavioral_cutoff_ms": 342700},
        {"subject": "s19", "session": "ses-09", "task": "flanker", "behavioral_cutoff_ms": 281610},
        {"subject": "s19", "session": "ses-09", "task": "stopSignal", "behavioral_cutoff_ms": 552790},
        {"subject": "s19", "session": "ses-09", "task": "cuedTS", "behavioral_cutoff_ms": 378460},
        {"subject": "s43", "session": "ses-11", "task": "stopSignalWDirectedForgetting", "behavioral_cutoff_ms": 780760},
    ],
    "validation_bids": [
        {"subject": "s76", "session": "ses-01", "task": "stopSignal", "behavioral_cutoff_ms": 470840},
        {"subject": "s1057", "session": "ses-12", "task": "stopSignalWFlanker", "behavioral_cutoff_ms": 284590},
        {"subject": "s1058", "session": "ses-02", "task": "directedForgetting", "behavioral_cutoff_ms": 302470},
        {"subject": "s1175", "session": "ses-06", "task": "spatialTS", "behavioral_cutoff_ms": 385910},
        {"subject": "s1314", "session": "ses-05", "task": "goNogo", "behavioral_cutoff_ms": 400810},
        {"subject": "s247", "session": "ses-11", "task": "stopSignalWDirectedForgetting", "behavioral_cutoff_ms": 524480},
        # s394 - fell asleep, NO trim
        {"subject": "s599", "session": "ses-10", "task": "nBack", "behavioral_cutoff_ms": 648150},
        {"subject": "s874", "session": "ses-06", "task": "cuedTS", "behavioral_cutoff_ms": 433590},
        {"subject": "s956", "session": "ses-04", "task": "cuedTS", "behavioral_cutoff_ms": 241380},
    ],
}

FELL_ASLEEP = [
    {"subject": "s394", "session": "ses-07", "task": "goNogo", "reason": "subject fell asleep"},
]


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
    )


def process_bids_directory(
    bids_dir: Path,
    sourcedata_beh: Path,
    manifest: ExclusionsManifest,
    trim_list: list[dict],
    fell_asleep_list: list[dict],
) -> dict:
    """
    Process a single BIDS directory.

    Args:
        bids_dir: Path to BIDS directory
        sourcedata_beh: Path to sourcedata/behavioral_data
        manifest: ExclusionsManifest instance
        trim_list: List of scans to trim
        fell_asleep_list: List of fell-asleep scans

    Returns:
        Dictionary with processing results
    """
    orchestrator = TrimOrchestrator(bids_dir, sourcedata_beh)
    results = {
        "bids_dir": str(bids_dir),
        "scans_processed": 0,
        "scans_trimmed": 0,
        "scans_flagged": 0,
        "details": [],
    }

    # Process behavioral trim scans
    for scan_spec in trim_list:
        context = TrimContext(
            subject=scan_spec["subject"],
            session=scan_spec["session"],
            task=scan_spec["task"],
            behavioral_cutoff_ms=scan_spec.get("behavioral_cutoff_ms"),
        )

        trim_result = orchestrator.trim_scan(context)
        results["scans_processed"] += 1
        results["scans_trimmed"] += 1
        results["details"].append(trim_result)

        # Record in manifest
        manifest.add_behavioral_trim(
            subject=context.subject,
            session=context.session,
            task=context.task,
            original_trs=0,  # TODO: extract from BOLD JSON
            trimmed_trs=0,   # TODO: calculate after trim
            behavioral_cutoff_ms=context.behavioral_cutoff_ms,
        )

    # Process fell-asleep scans
    for scan_spec in fell_asleep_list:
        context = TrimContext(
            subject=scan_spec["subject"],
            session=scan_spec["session"],
            task=scan_spec["task"],
            behavioral_cutoff_ms=None,  # No behavioral trim
        )

        trim_result = orchestrator.trim_scan(context)
        results["scans_processed"] += 1
        results["scans_flagged"] += 1
        results["details"].append(trim_result)

        # Record in manifest
        manifest.add_behavioral_flag_no_trim(
            subject=context.subject,
            session=context.session,
            task=context.task,
            reason=scan_spec.get("reason", "behavioral anomaly"),
            analyst_notes="Include in analysis with caution",
        )

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Post-process BIDS directories to trim dummies and behavioral cutoffs"
    )
    parser.add_argument(
        "--bids-dirs",
        type=str,
        nargs="+",
        required=True,
        help="Paths to BIDS directories",
    )
    parser.add_argument(
        "--sourcedata-beh",
        type=str,
        required=True,
        help="Path to sourcedata/behavioral_data",
    )
    parser.add_argument(
        "--output-manifest",
        type=str,
        default="sourcedata/exclusions.json",
        help="Output path for exclusions manifest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be trimmed without making changes",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Initialize manifest
    manifest = ExclusionsManifest(Path(args.output_manifest))

    # Determine which dataset is being processed
    for bids_dir in args.bids_dirs:
        bids_path = Path(bids_dir)

        # Determine which trim list to use
        if "discovery" in bids_dir:
            trim_list = TRIMMING_MANIFEST["discovery_bids"]
            fell_asleep_list = []
        elif "validation" in bids_dir:
            trim_list = TRIMMING_MANIFEST["validation_bids"]
            fell_asleep_list = FELL_ASLEEP
        elif "excluded" in bids_dir:
            trim_list = []
            fell_asleep_list = []
        else:
            logger.warning(f"Cannot determine dataset type for {bids_dir}, skipping")
            continue

        logger.info(f"Processing {bids_path.name}...")

        if args.dry_run:
            logger.info(f"DRY RUN: Would trim {len(trim_list)} scans")
            logger.info(f"DRY RUN: Would flag {len(fell_asleep_list)} scans")
            continue

        result = process_bids_directory(
            bids_path,
            Path(args.sourcedata_beh),
            manifest,
            trim_list,
            fell_asleep_list,
        )

        logger.info(f"Completed {bids_path.name}: {result['scans_processed']} scans processed")

    # Save manifest
    manifest.save()
    logger.info(f"Saved manifest to {args.output_manifest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
