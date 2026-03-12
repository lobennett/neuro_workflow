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

# Import utility functions from the rename script (these are still there)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rename_behavioral_to_sourcedata import (
    SKIP_DIRS,
    parse_csv_filename,
    zero_pad_session,
)


def build_bids_task_map(bids_dir: Path, subject: str) -> list[tuple[str, set[str]]]:
    """Scan BIDS func/ directories and return ordered (ses_label, task_set) pairs."""
    sub_label = subject if subject.startswith("sub-") else f"sub-{subject}"
    sub_dir = bids_dir / sub_label
    if not sub_dir.exists():
        return []

    sessions = []
    for ses_dir in sorted(sub_dir.glob("ses-*")):
        func_dir = ses_dir / "func"
        tasks = set()
        if func_dir.exists():
            for f in func_dir.iterdir():
                m = re.search(r"task-(\w+)_run", f.name)
                if m and m.group(1) != "rest":
                    tasks.add(m.group(1))
        sessions.append((ses_dir.name, tasks))
    return sessions


def build_raw_session_map(
    input_dir: Path, subject: str
) -> list[tuple[str, set[str], list[Path]]]:
    """Scan raw_cleaned sessions and return ordered (ses_label, task_set, csv_paths) triples."""
    subj_dir = input_dir / subject
    if not subj_dir.exists():
        return []

    sessions = []
    for ses_dir in sorted(subj_dir.glob("ses-*")):
        if ses_dir.name in SKIP_DIRS:
            continue
        tasks = set()
        csvs = []
        for csv_file in sorted(ses_dir.glob("*.csv")):
            if "practice" in str(csv_file).lower():
                continue
            task = parse_csv_filename(csv_file.name)
            if task:
                tasks.add(task)
            else:
                log.warning("Unrecognized file: %s", csv_file)
            csvs.append((csv_file, task))
        sessions.append((zero_pad_session(ses_dir.name), tasks, csvs))
    return sessions


def match_sessions(raw_sessions, bids_sessions):
    """Two-pass matching of behavioral sessions to BIDS sessions.

    Pass 1: greedy ordered matching (handles the common case where sessions
    are in the same order but offset).

    Pass 2: unmatched raw sessions are matched against skipped BIDS sessions
    (handles cases like s29 where later behavioral sessions correspond to
    earlier BIDS sessions that were skipped in pass 1).

    Returns:
        mappings: list of (raw_ses, bids_ses, tasks, csvs) for matched sessions
        skipped_bids: list of BIDS session labels with no behavioral match
        unmatched_raw: list of raw session labels with no BIDS match
    """
    mappings = []
    skipped_bids = []
    unmatched_raw_items = []  # (raw_ses, raw_tasks, csvs)
    bids_ptr = 0

    # Pass 1: greedy forward matching
    for raw_ses, raw_tasks, csvs in raw_sessions:
        if not raw_tasks:
            log.warning("Skipping %s: no recognized tasks", raw_ses)
            unmatched_raw_items.append((raw_ses, raw_tasks, csvs))
            continue

        matched = False
        while bids_ptr < len(bids_sessions):
            bids_ses, bids_tasks = bids_sessions[bids_ptr]
            if (raw_tasks & bids_tasks) and (
                raw_tasks <= bids_tasks or bids_tasks <= raw_tasks
            ):
                mappings.append((raw_ses, bids_ses, sorted(raw_tasks), csvs))
                bids_ptr += 1
                matched = True
                break
            else:
                skipped_bids.append(bids_ses)
                bids_ptr += 1

        if not matched:
            unmatched_raw_items.append((raw_ses, raw_tasks, csvs))

    # Any remaining BIDS sessions are also skipped
    while bids_ptr < len(bids_sessions):
        skipped_bids.append(bids_sessions[bids_ptr][0])
        bids_ptr += 1

    # Pass 2: match remaining raw sessions against skipped BIDS sessions
    if unmatched_raw_items and skipped_bids:
        bids_by_label = {ses: tasks for ses, tasks in bids_sessions}
        available_bids = [(ses, bids_by_label[ses]) for ses in skipped_bids]

        still_unmatched = []
        for raw_ses, raw_tasks, csvs in unmatched_raw_items:
            if not raw_tasks:
                still_unmatched.append((raw_ses, raw_tasks, csvs))
                continue
            matched = False
            for i, (bids_ses, bids_tasks) in enumerate(available_bids):
                if (raw_tasks & bids_tasks) and (
                    raw_tasks <= bids_tasks or bids_tasks <= raw_tasks
                ):
                    mappings.append((raw_ses, bids_ses, sorted(raw_tasks), csvs))
                    available_bids.pop(i)
                    log.info("Pass 2: matched %s -> %s", raw_ses, bids_ses)
                    matched = True
                    break
            if not matched:
                log.warning(
                    "No BIDS match for %s (tasks: %s)", raw_ses, sorted(raw_tasks)
                )
                still_unmatched.append((raw_ses, raw_tasks, csvs))

        skipped_bids = [ses for ses, _ in available_bids]
        unmatched_raw_items = still_unmatched
    else:
        for raw_ses, raw_tasks, csvs in unmatched_raw_items:
            log.warning(
                "No BIDS match for %s (tasks: %s)", raw_ses, sorted(raw_tasks)
            )

    unmatched_raw = [raw_ses for raw_ses, _, _ in unmatched_raw_items]
    return mappings, skipped_bids, unmatched_raw

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
