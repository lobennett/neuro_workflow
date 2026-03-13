"""Core migration logic for each data type."""

import csv
import json
import logging
from pathlib import Path
from typing import Dict, Any

from .copy_utils import copy_file_with_retries
from .normalize_filenames import (
    normalize_mturk_filename,
    normalize_out_of_scanner_filename,
    normalize_survey_filename,
    normalize_demographics_filename,
)
from .sample_validation import is_subject_in_sample

logger = logging.getLogger(__name__)


def convert_json_survey_to_csv(json_path: Path) -> str:
    """
    Convert JSON survey (prescan or demographics) to CSV format preserving metadata.

    Format: First row has metadata (worker_id, experiment_id, battery_name, finishtime)
    Then: question_id,question_text,response,required,options_json

    Options are stored as JSON string to preserve multi-choice structure.

    Args:
        json_path: Path to JSON survey file

    Returns:
        CSV content as string
    """
    import io

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Error reading JSON {json_path}: {e}")
        raise

    output = io.StringIO()
    writer = csv.writer(output)

    # Write metadata row
    writer.writerow([
        "metadata",
        data.get("worker_id", ""),
        data.get("experiment_id", ""),
        data.get("battery_name", ""),
        data.get("finishtime", ""),
        str(data.get("completed", False)),
    ])

    # Write header row
    writer.writerow(["question_id", "question_text", "response", "required", "options_json"])

    # Write data rows
    for question_id, question_data in data.get("data", {}).items():
        options = json.dumps(question_data.get("options", []))
        writer.writerow([
            question_id,
            question_data.get("text", ""),
            question_data.get("response", ""),
            question_data.get("required", 0),
            options if options != "[]" else "",
        ])

    return output.getvalue()


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
        samples: Sample dict from load_samples_from_config (includes 'excluded' key)
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped_not_in_sample', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped": 0, "skipped_not_in_sample": 0, "errors": 0}
    excluded = samples.get("excluded", {})

    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        # Skip hidden directories (.svn, .DS_Store, etc.)
        if subject_dir.name.startswith("."):
            continue

        subject = subject_dir.name

        # Check if excluded
        if subject in excluded:
            logger.info(f"Subject {subject} excluded ({excluded[subject]}), skipping")
            # Count all files in this subject (excluding hidden files)
            stats["skipped_not_in_sample"] += len([f for f in subject_dir.iterdir() if f.is_file() and not f.name.startswith(".")])
            continue

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
    Migrate prescan survey data files (sample-filtered).

    - JSON files: Convert to CSV while preserving all metadata
    - PDF files: Copy with BIDS-normalized naming
    - Other formats: Skip

    Args:
        archive_dir: Path to archive/survey_data/prescan_surveys/raw
        dest_dir: Path to output sourcedata/survey_data
        samples: Sample dict from load_samples_from_config (includes 'excluded' key)
        dry_run: If True, don't actually write files

    Returns:
        Stats dict with 'migrated', 'skipped_not_in_sample', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped": 0, "skipped_not_in_sample": 0, "errors": 0}
    excluded = samples.get("excluded", {})

    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        # Skip hidden directories (.svn, .DS_Store, etc.)
        if subject_dir.name.startswith("."):
            continue

        subject = subject_dir.name

        # Check if excluded
        if subject in excluded:
            logger.info(f"Subject {subject} excluded ({excluded[subject]}), skipping")
            # Count all files in this subject (excluding hidden files)
            stats["skipped_not_in_sample"] += len([f for f in subject_dir.iterdir() if f.is_file() and not f.name.startswith(".")])
            continue

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

            # Handle JSON files (convert to CSV)
            if src_file.suffix == ".json":
                try:
                    normalized_name = normalize_survey_filename(src_file.name, subject=subject)
                    # Change extension from .json to .csv
                    normalized_name = normalized_name.replace(".json", ".csv")
                except ValueError as e:
                    logger.debug(f"Skipped non-standard survey file {src_file.name}: {e}")
                    stats["skipped"] += 1
                    continue

                dest_file = dest_subject / normalized_name

                if not dry_run:
                    try:
                        # Convert JSON to CSV
                        csv_content = convert_json_survey_to_csv(src_file)

                        # Create destination directory
                        dest_file.parent.mkdir(parents=True, exist_ok=True)

                        # Write CSV file
                        with open(dest_file, "w", encoding="utf-8") as f:
                            f.write(csv_content)

                        logger.debug(f"Converted {src_file.name} to {dest_file.name}")
                        stats["migrated"] += 1
                    except Exception as e:
                        logger.error(f"Failed to convert {src_file}: {e}")
                        stats["errors"] += 1
                else:
                    stats["migrated"] += 1

            # Handle PDF files (rename and copy)
            elif src_file.suffix == ".pdf":
                try:
                    normalized_name = normalize_survey_filename(src_file.name, subject=subject)
                    # Keep .pdf extension
                    normalized_name = normalized_name.replace(".json", ".pdf")
                except ValueError as e:
                    logger.debug(f"Skipped non-standard survey PDF {src_file.name}: {e}")
                    stats["skipped"] += 1
                    continue

                dest_file = dest_subject / normalized_name

                if not dry_run:
                    try:
                        copy_file_with_retries(src_file, dest_file, skip_existing=True)
                        logger.debug(f"Copied PDF {src_file.name} to {dest_file.name}")
                        stats["migrated"] += 1
                    except Exception as e:
                        logger.error(f"Failed to copy PDF {src_file}: {e}")
                        stats["errors"] += 1
                else:
                    stats["migrated"] += 1

            else:
                # Skip other file types
                logger.debug(f"Skipped non-JSON/PDF file {src_file.name}")
                stats["skipped"] += 1

    return stats

def migrate_demographics_to_survey_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    samples: Dict[str, list],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate demographics survey CSV files to survey_data directory (keep as CSV).

    Includes ALL demographics files regardless of sample membership.

    Args:
        archive_dir: Path to archive/mTurk/all_data (contains demographics_survey CSVs)
        dest_dir: Path to output sourcedata/survey_data
        samples: Sample dict from load_samples_from_config (unused, kept for API compatibility)
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'errors'
    """
    import re as re_module

    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "errors": 0}

    # Find all demographics_survey CSV files in mTurk directory
    try:
        for src_file in sorted(archive_dir.rglob("demographics_survey*.csv")):
            if not src_file.is_file():
                continue

            # Skip hidden files
            if src_file.name.startswith("."):
                continue

            # Extract subject from filename
            try:
                match = re_module.search(r"(s\d+)", src_file.name)
                if not match:
                    logger.debug(f"Could not extract subject from {src_file.name}")
                    stats["errors"] += 1
                    continue
                subject = match.group(1)
            except Exception as e:
                logger.error(f"Error extracting subject from {src_file.name}: {e}")
                stats["errors"] += 1
                continue


            dest_subject = dest_dir / f"sub-{subject}"

            # Normalize filename
            try:
                normalized_name = normalize_demographics_filename(src_file.name, subject=subject)
            except ValueError as e:
                logger.debug(f"Skipped non-standard demographics file {src_file.name}: {e}")
                stats["errors"] += 1
                continue

            # Keep .csv extension (change from .json if normalized)
            dest_file = dest_subject / normalized_name.replace(".json", ".csv")

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    logger.debug(f"Copied {src_file.name} to {dest_file.name}")
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1
    except Exception as e:
        logger.error(f"Error during demographics migration: {e}")

    return stats
