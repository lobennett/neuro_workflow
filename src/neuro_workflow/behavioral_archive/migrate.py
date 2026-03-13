"""Core migration logic for each data type."""

import logging
from pathlib import Path
from typing import Dict, Any

from .copy_utils import copy_file_with_retries
from .normalize_filenames import (
    normalize_mturk_filename,
    normalize_out_of_scanner_filename,
    normalize_survey_filename,
)
from .sample_validation import is_subject_in_sample

logger = logging.getLogger(__name__)


def migrate_mturk_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate all mTurk files (no sample filtering).

    Args:
        archive_dir: Path to archive/mTurk/all_data
        dest_dir: Path to output mTurk directory
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped": 0, "errors": 0}

    # Iterate subject directories
    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        # Skip hidden directories (.svn, .DS_Store, etc.)
        if subject_dir.name.startswith("."):
            continue

        subject = subject_dir.name
        dest_subject = dest_dir / f"sub-{subject}"

        # Copy all files from this subject
        for src_file in subject_dir.iterdir():
            if not src_file.is_file():
                continue

            # Skip hidden/system files
            if src_file.name.startswith("."):
                continue

            # Normalize filename
            try:
                normalized_name = normalize_mturk_filename(src_file.name)
            except ValueError as e:
                logger.debug(f"Skipped non-behavioral file {src_file.name}: {e}")
                stats["skipped"] += 1
                continue

            dest_file = dest_subject / normalized_name

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1

    return stats


def migrate_out_of_scanner_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    samples: Dict[str, list],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate out_of_scanner files (sample-filtered).

    Args:
        archive_dir: Path to archive/out_of_scanner
        dest_dir: Path to output sourcedata/out_scanner_behavior
        samples: Sample dict from load_samples_from_config
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped_not_in_sample', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped": 0, "skipped_not_in_sample": 0, "errors": 0}

    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        # Skip hidden directories (.svn, .DS_Store, etc.)
        if subject_dir.name.startswith("."):
            continue

        subject = subject_dir.name

        # Check if in sample
        if not is_subject_in_sample(subject, samples):
            logger.info(f"Subject {subject} not in discovery/validation sample, skipping")
            # Count all files in this subject (excluding hidden files)
            stats["skipped_not_in_sample"] += len([f for f in subject_dir.iterdir() if f.is_file() and not f.name.startswith(".")])
            continue

        dest_subject = dest_dir / f"sub-{subject}"

        for src_file in subject_dir.iterdir():
            if not src_file.is_file():
                continue

            # Skip hidden/system files
            if src_file.name.startswith("."):
                continue

            try:
                normalized_name = normalize_out_of_scanner_filename(src_file.name)
            except ValueError as e:
                logger.debug(f"Skipped non-behavioral file {src_file.name}: {e}")
                stats["skipped"] += 1
                continue

            dest_file = dest_subject / normalized_name

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1

    return stats


def migrate_survey_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    samples: Dict[str, list],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate survey data files (sample-filtered).

    Args:
        archive_dir: Path to archive/survey_data/prescan_surveys/raw
        dest_dir: Path to output sourcedata/survey_data
        samples: Sample dict from load_samples_from_config
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped_not_in_sample', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped": 0, "skipped_not_in_sample": 0, "errors": 0}

    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        # Skip hidden directories (.svn, .DS_Store, etc.)
        if subject_dir.name.startswith("."):
            continue

        subject = subject_dir.name

        if not is_subject_in_sample(subject, samples):
            logger.info(f"Subject {subject} not in discovery/validation sample, skipping")
            # Count all files in this subject (excluding hidden files)
            stats["skipped_not_in_sample"] += len([f for f in subject_dir.iterdir() if f.is_file() and not f.name.startswith(".")])
            continue

        dest_subject = dest_dir / f"sub-{subject}"

        for src_file in subject_dir.iterdir():
            if not src_file.is_file():
                continue

            # Skip hidden/system files
            if src_file.name.startswith("."):
                continue

            try:
                normalized_name = normalize_survey_filename(src_file.name, subject=subject)
            except ValueError as e:
                logger.debug(f"Skipped non-standard survey file {src_file.name}: {e}")
                stats["skipped"] += 1
                continue

            dest_file = dest_subject / normalized_name

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1

    return stats
