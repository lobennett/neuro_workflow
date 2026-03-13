#!/usr/bin/env python
"""
Migrate behavioral data from archive to properly structured BIDS-format locations.

Usage:
    python scripts/migrate_archive_behavioral_data.py \\
        --archive-dir /oak/.../behavioral_data \\
        --sourcedata-dir /oak/.../sourcedata \\
        --mturk-dir /oak/.../mTurk \\
        --config config/behavioral_session_mapping.json
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime

from neuro_workflow.behavioral_archive.migrate import (
    migrate_mturk_data,
    migrate_out_of_scanner_data,
    migrate_survey_data,
    migrate_demographics_to_survey_data,
)
from neuro_workflow.behavioral_archive.sample_validation import load_samples_from_config


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Migrate behavioral archive data to BIDS-format sourcedata."
    )
    parser.add_argument(
        "--archive-dir",
        required=True,
        type=Path,
        help="Path to archive behavioral_data directory",
    )
    parser.add_argument(
        "--sourcedata-dir",
        required=True,
        type=Path,
        help="Path to output sourcedata directory",
    )
    parser.add_argument(
        "--mturk-dir",
        required=True,
        type=Path,
        help="Path to output mTurk directory",
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to behavioral_session_mapping.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without copying files",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Load samples
    logger.info("Loading sample configuration...")
    samples = load_samples_from_config(args.config)
    logger.info(
        f"Loaded samples: {len(samples['discovery'])} discovery, "
        f"{len(samples['validation'])} validation"
    )

    # Run migrations
    logger.info("=" * 60)
    logger.info("MTURK MIGRATION")
    logger.info("=" * 60)

    archive_mturk = args.archive_dir / "mTurk" / "all_data"
    mturk_stats = migrate_mturk_data(archive_mturk, args.mturk_dir, dry_run=args.dry_run)
    logger.info(f"mTurk: {mturk_stats['migrated']} migrated, {mturk_stats['errors']} errors")

    logger.info("=" * 60)
    logger.info("OUT-OF-SCANNER BEHAVIOR MIGRATION")
    logger.info("=" * 60)

    archive_out = args.archive_dir / "out_of_scanner"
    dest_out = args.sourcedata_dir / "out_scanner_behavior"
    out_stats = migrate_out_of_scanner_data(
        archive_out, dest_out, samples, dry_run=args.dry_run
    )
    logger.info(
        f"Out-of-scanner: {out_stats['migrated']} migrated, "
        f"{out_stats['skipped_not_in_sample']} skipped (not in sample), "
        f"{out_stats['errors']} errors"
    )

    logger.info("=" * 60)
    logger.info("SURVEY DATA MIGRATION")
    logger.info("=" * 60)

    archive_survey = args.archive_dir / "survey_data" / "prescan_surveys" / "raw"
    dest_survey = args.sourcedata_dir / "survey_data"
    survey_stats = migrate_survey_data(
        archive_survey, dest_survey, samples, dry_run=args.dry_run
    )
    logger.info(
        f"Survey: {survey_stats['migrated']} migrated, "
        f"{survey_stats['skipped_not_in_sample']} skipped (not in sample), "
        f"{survey_stats['errors']} errors"
    )

    logger.info("=" * 60)
    logger.info("DEMOGRAPHICS SURVEY MIGRATION")
    logger.info("=" * 60)

    archive_mturk = args.archive_dir / "mTurk" / "all_data"
    demographics_stats = migrate_demographics_to_survey_data(
        archive_mturk, dest_survey, samples, dry_run=args.dry_run
    )
    logger.info(
        f"Demographics: {demographics_stats['migrated']} migrated, "
        f"{demographics_stats['errors']} errors"
    )

    # Generate report
    report = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "mturk": mturk_stats,
        "out_of_scanner": out_stats,
        "survey": survey_stats,
        "demographics": demographics_stats,
        "total_migrated": mturk_stats["migrated"] + out_stats["migrated"] + survey_stats["migrated"] + demographics_stats["migrated"],
    }

    report_path = args.sourcedata_dir / "behavioral_migration_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
