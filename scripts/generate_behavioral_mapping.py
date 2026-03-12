#!/usr/bin/env python3
"""Generate behavioral_session_mapping.json from BIDS + raw_cleaned data.

One-time script. Output is hand-reviewed and corrected before use.

Usage:
    uv run python scripts/generate_behavioral_mapping.py \
        --raw-dir /oak/.../behavioral_data/raw_cleaned \
        --discovery-bids /scratch/users/logben/discovery_bids \
        --validation-bids /scratch/users/logben/validation_bids \
        --output config/behavioral_session_mapping.json
"""
import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import matching functions from the existing rename script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rename_behavioral_to_sourcedata import (
    SKIP_DIRS,
    build_bids_task_map,
    build_raw_session_map,
    match_sessions,
)

log = logging.getLogger(__name__)

DISCOVERY_SUBJECTS = {"s03", "s10", "s19", "s29", "s43"}


def load_reconciliation_dates(bids_dir: Path) -> dict[str, dict[str, str]]:
    """Load reconciliation.json and return {subject: {bids_session: date_str}}."""
    rec_path = bids_dir / "sourcedata" / "reconciliation.json"
    if not rec_path.exists():
        log.warning("reconciliation.json not found at %s", rec_path)
        return {}

    with open(rec_path) as f:
        rec = json.load(f)

    dates: dict[str, dict[str, str]] = {}
    for sub, info in rec.get("subjects", {}).items():
        sub_dates: dict[str, str] = {}
        for sess in info.get("sessions", []):
            bids_ses = sess.get("bids_session")
            ts = sess.get("timestamp")
            if bids_ses and ts:
                # Extract YYYY-MM-DD from ISO timestamp
                sub_dates[bids_ses] = ts[:10]
        dates[sub] = sub_dates
    return dates


def check_offset_consistency(mappings: list[tuple]) -> list[str]:
    """Check if raw-to-bids session number offsets are consistent.

    Returns list of notes describing inconsistencies.
    """
    if len(mappings) < 2:
        return []

    offsets = []
    for raw_ses, bids_ses, *_ in mappings:
        raw_num = int(re.search(r"(\d+)", raw_ses).group(1))
        bids_num = int(re.search(r"(\d+)", bids_ses).group(1))
        offsets.append((raw_ses, bids_ses, bids_num - raw_num))

    unique_offsets = {o for _, _, o in offsets}
    if len(unique_offsets) > 1:
        details = ", ".join(f"{r}->{b} (offset={off})" for r, b, off in offsets)
        return [f"REVIEW: inconsistent offsets: {details}"]
    return []


def generate_subject_entry(
    subject: str,
    sample: str,
    raw_dir: Path,
    bids_dir: Path,
    dates: dict[str, str],
) -> dict | None:
    """Generate mapping entry for a single subject."""
    bids_sessions = build_bids_task_map(bids_dir, subject)
    if not bids_sessions:
        return None

    raw_sessions = build_raw_session_map(raw_dir, subject)
    if not raw_sessions:
        log.info("%s: no behavioral data in raw_cleaned", subject)
        return {
            "sample": sample,
            "excluded": False,
            "exclude_reason": None,
            "mappings": [],
            "skipped_bids": [s for s, _ in bids_sessions],
            "unmatched_raw": [],
            "irreconcilable_bids_runs": [],
            "notes": ["no behavioral data found in raw_cleaned"],
        }

    mappings, skipped_bids, unmatched_raw = match_sessions(raw_sessions, bids_sessions)

    # Build mapping entries with dates
    mapping_entries = []
    for raw_ses, bids_ses, tasks, _csvs in mappings:
        mapping_entries.append({
            "raw": raw_ses,
            "bids": bids_ses,
            "bids_date": dates.get(bids_ses),
            "tasks": tasks,
        })

    notes = check_offset_consistency(mappings)

    return {
        "sample": sample,
        "excluded": False,
        "exclude_reason": None,
        "mappings": mapping_entries,
        "skipped_bids": skipped_bids,
        "unmatched_raw": unmatched_raw,
        "irreconcilable_bids_runs": [],
        "notes": notes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate behavioral_session_mapping.json"
    )
    parser.add_argument(
        "--raw-dir", required=True, type=Path,
        help="Path to behavioral_data/raw_cleaned",
    )
    parser.add_argument(
        "--discovery-bids", required=True, type=Path,
        help="Path to discovery BIDS directory",
    )
    parser.add_argument(
        "--validation-bids", required=True, type=Path,
        help="Path to validation BIDS directory",
    )
    parser.add_argument(
        "--output", required=True, type=Path,
        help="Output path for JSON config",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Load reconciliation dates for both samples
    discovery_dates = load_reconciliation_dates(args.discovery_bids)
    validation_dates = load_reconciliation_dates(args.validation_bids)

    # Load excluded subjects from reconciliation_config.json
    config_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "neuro_workflow" / "bidsify" / "reconciliation_config.json"
    )
    with open(config_path) as f:
        recon_config = json.load(f)
    excluded_subjects = recon_config.get("excluded_validation_subjects", {})

    # Discover all raw_cleaned subjects
    raw_subjects = sorted(
        d.name for d in args.raw_dir.iterdir()
        if d.is_dir() and d.name not in SKIP_DIRS and d.name.startswith("s")
    )

    # Also find subjects that are in BIDS dirs but not in raw_cleaned
    discovery_bids_subjects = sorted(
        d.name.replace("sub-", "")
        for d in args.discovery_bids.iterdir()
        if d.is_dir() and d.name.startswith("sub-")
    )
    validation_bids_subjects = sorted(
        d.name.replace("sub-", "")
        for d in args.validation_bids.iterdir()
        if d.is_dir() and d.name.startswith("sub-")
    )

    all_subjects = sorted(
        set(raw_subjects) | set(discovery_bids_subjects) | set(validation_bids_subjects)
    )

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/generate_behavioral_mapping.py",
        "sources": {
            "bids_discovery": str(args.discovery_bids),
            "bids_validation": str(args.validation_bids),
            "behavioral_raw": str(args.raw_dir),
            "reconciliation_discovery": "sourcedata/reconciliation.json",
            "reconciliation_validation": "sourcedata/reconciliation.json",
            "scan_notes": "scan_notes/",
        },
        "subjects": {},
    }

    review_needed = []

    for subject in all_subjects:
        # Determine sample membership
        is_discovery = subject in DISCOVERY_SUBJECTS
        is_validation = subject in set(validation_bids_subjects)

        if is_discovery:
            sample = "discovery"
            bids_dir = args.discovery_bids
            dates = discovery_dates.get(subject, {})
        elif is_validation:
            sample = "validation"
            bids_dir = args.validation_bids
            dates = validation_dates.get(subject, {})
        else:
            # Subject only in raw_cleaned, not in any BIDS dir
            log.info("Skipping %s: not in any BIDS directory", subject)
            continue

        # Check if excluded
        if subject in excluded_subjects:
            output["subjects"][subject] = {
                "sample": sample,
                "excluded": True,
                "exclude_reason": excluded_subjects[subject],
                "mappings": [],
                "skipped_bids": [],
                "unmatched_raw": [],
                "irreconcilable_bids_runs": [],
                "notes": [],
            }
            log.info("%s: excluded (%s)", subject, excluded_subjects[subject])
            continue

        entry = generate_subject_entry(subject, sample, args.raw_dir, bids_dir, dates)
        if entry is None:
            log.info("Skipping %s: not found in %s BIDS directory", subject, sample)
            continue

        output["subjects"][subject] = entry

        # Report
        n_mapped = len(entry["mappings"])
        n_skipped = len(entry["skipped_bids"])
        n_unmatched = len(entry["unmatched_raw"])
        log.info(
            "%s (%s): %d mapped, %d skipped_bids, %d unmatched_raw",
            subject, sample, n_mapped, n_skipped, n_unmatched,
        )

        if entry["notes"]:
            review_needed.append(subject)
            for note in entry["notes"]:
                log.warning("  %s: %s", subject, note)

        if n_unmatched > 0:
            review_needed.append(subject)
            log.warning("  %s: unmatched raw sessions: %s", subject, entry["unmatched_raw"])

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    log.info("Wrote %s (%d subjects)", args.output, len(output["subjects"]))

    if review_needed:
        print("\n--- SUBJECTS NEEDING REVIEW ---")
        for s in sorted(set(review_needed)):
            entry = output["subjects"][s]
            print(f"  {s}: {entry.get('notes', [])} unmatched_raw={entry.get('unmatched_raw', [])}")


if __name__ == "__main__":
    main()
