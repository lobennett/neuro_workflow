#!/usr/bin/env python3
"""One-time migration: standardize raw behavioral CSV filenames to BIDS sourcedata layout.

Matches behavioral sessions to BIDS sessions by task content using greedy
ordered matching, handling cases where Flywheel and raw_cleaned session
numbering diverge.

Usage:
    python scripts/rename_behavioral_to_sourcedata.py \
        --input-dir /oak/.../behavioral_data/raw_cleaned \
        --output-dir /oak/.../behavioral_data/sourcedata \
        --bids-dir /scratch/users/logben/discovery_BIDS \
        [--dry-run]
"""
import argparse
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Canonical mapping from raw long names to BIDS camelCase task names
LONG_NAME_TO_BIDS = {
    "stop_signal": "stopSignal",
    "flanker": "flanker",
    "go_nogo": "goNogo",
    "n_back": "nBack",
    "cued_task_switching": "cuedTS",
    "spatial_task_switching": "spatialTS",
    "directed_forgetting": "directedForgetting",
    "shape_matching": "shapeMatching",
    "stop_signal_with_flanker": "stopSignalWFlanker",
    "stop_signal_with_directed_forgetting": "stopSignalWDirectedForgetting",
    "directed_forgetting_with_flanker": "directedForgettingWFlanker",
    "directed_forgetting_with_cued_task_switching": "directedForgettingWCuedTS",
    "cued_task_switching_with_directed_forgetting": "directedForgettingWCuedTS",
    "spatial_task_switching_with_cued_task_switching": "spatialTSWCuedTS",
    "flanker_with_shape_matching": "flankerWShapeMatching",
    "flanker_with_cued_task_switching": "cuedTSWFlanker",
    "n_back_with_shape_matching": "nBackWShapeMatching",
    "n_back_with_spatial_task_switching": "nBackWSpatialTS",
    "shape_matching_with_cued_task_switching": "shapeMatchingWCuedTS",
    "shape_matching_with_spatial_task_switching": "spatialTSWShapeMatching",
}

# Reverse mapping for BIDS-style filenames (camelCase and dash-separated)
_BIDS_TASK_ALIASES = {
    "go-nogo": "goNogo",
    "stop-signal": "stopSignal",
    "shape-matching": "shapeMatching",
    "spatial-task-switching": "spatialTS",
    "cued-task-switching": "cuedTS",
    "directed-forgetting": "directedForgetting",
    "n-back": "nBack",
    "nBack": "nBack",
    "stopSignal": "stopSignal",
    "goNogo": "goNogo",
    "shapeMatching": "shapeMatching",
    "spatialTaskSwitching": "spatialTS",
    "cuedTaskSwitching": "cuedTS",
    "directedForgetting": "directedForgetting",
    "flanker": "flanker",
    # Dual tasks in BIDS-style
    "stop_signal_with_flanker": "stopSignalWFlanker",
    "stop_signal_with_directed_forgetting": "stopSignalWDirectedForgetting",
    "directed_forgetting_with_flanker": "directedForgettingWFlanker",
}


def parse_csv_filename(filename: str) -> str | None:
    """Extract canonical BIDS task name from any of the three naming patterns.

    Patterns:
    1. Descriptive: stop_signal_single_task_network__fmri_results (3).csv
    2. BIDS dash-separated: sub-s29_ses-01_task-stop-signal_desc-raw.csv
    3. BIDS camelCase: sub-s76_ses-01_task-stopSignal_desc-beh.csv

    Returns the camelCase BIDS task name, or None if not recognized.
    """
    # Pattern 1: descriptive style (with or without copy number)
    # Remove copy number like " (3)" and .csv extension
    base = re.sub(r"\s*\(\d+\)", "", filename)
    base = re.sub(r"\s*copy", "", base)
    base = base.replace(".csv", "")

    if "__fmri" in base:
        long_name = base.split("__fmri")[0]
        if "_single_task_network" in long_name:
            long_name = long_name.split("_single_task_network")[0]
        return LONG_NAME_TO_BIDS.get(long_name)

    # Pattern 2/3: BIDS-style with task- entity
    m = re.search(r"task-([^_]+)", base)
    if m:
        task_raw = m.group(1)
        # Check direct alias
        if task_raw in _BIDS_TASK_ALIASES:
            return _BIDS_TASK_ALIASES[task_raw]
        # Check if it's already a valid BIDS name
        if task_raw in LONG_NAME_TO_BIDS.values():
            return task_raw
        # Try converting dashes to underscores for dual task lookup
        task_underscore = task_raw.replace("-", "_")
        if task_underscore in LONG_NAME_TO_BIDS:
            return LONG_NAME_TO_BIDS[task_underscore]

    # Pattern for BIDS-style dual tasks with underscores in task field
    # e.g., sub-s29_ses_11_task-stop_signal_with_flanker_desc_raw.csv
    m2 = re.search(r"task-(.+?)_desc", base)
    if m2:
        task_raw = m2.group(1)
        task_underscore = task_raw.replace("-", "_")
        if task_underscore in LONG_NAME_TO_BIDS:
            return LONG_NAME_TO_BIDS[task_underscore]
        if task_raw in _BIDS_TASK_ALIASES:
            return _BIDS_TASK_ALIASES[task_raw]

    return None


def zero_pad_session(session: str) -> str:
    """Zero-pad session label: ses-1 -> ses-01, ses-01 stays ses-01."""
    m = re.match(r"ses-(\d+)", session)
    if m:
        return f"ses-{int(m.group(1)):02d}"
    return session


def build_output_path(
    output_root: Path, subject: str, session: str, task_name: str
) -> Path:
    """Build BIDS sourcedata output path."""
    sub_label = subject if subject.startswith("sub-") else f"sub-{subject}"
    filename = f"{sub_label}_{session}_task-{task_name}_beh.csv"
    return output_root / sub_label / session / "beh" / filename


SKIP_DIRS = {"dropped_subjects", "exclusions", "pretouch", "practice", "extra"}


def discover_csvs(input_dir: Path):
    """Yield (csv_path, subject_label, session_label) for all behavioral CSVs."""
    for subj_dir in sorted(input_dir.iterdir()):
        if not subj_dir.is_dir() or subj_dir.name in SKIP_DIRS:
            continue
        for ses_dir in sorted(subj_dir.iterdir()):
            if not ses_dir.is_dir() or ses_dir.name in SKIP_DIRS:
                continue
            if not ses_dir.name.startswith("ses-"):
                continue
            for csv_file in sorted(ses_dir.glob("*.csv")):
                # Skip practice files and extra directories
                if "practice" in str(csv_file).lower():
                    continue
                yield csv_file, subj_dir.name, ses_dir.name


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


def build_raw_session_map(input_dir: Path, subject: str) -> list[tuple[str, set[str], list[Path]]]:
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
    """Greedy ordered matching of behavioral sessions to BIDS sessions.

    Returns:
        mappings: list of (raw_ses, bids_ses, tasks) for matched sessions
        skipped_bids: list of BIDS session labels with no behavioral match
        unmatched_raw: list of raw session labels with no BIDS match
    """
    mappings = []
    skipped_bids = []
    unmatched_raw = []
    bids_ptr = 0

    for raw_ses, raw_tasks, csvs in raw_sessions:
        if not raw_tasks:
            log.warning("Skipping %s: no recognized tasks", raw_ses)
            unmatched_raw.append(raw_ses)
            continue

        matched = False
        while bids_ptr < len(bids_sessions):
            bids_ses, bids_tasks = bids_sessions[bids_ptr]
            if raw_tasks <= bids_tasks:  # subset or equal
                mappings.append((raw_ses, bids_ses, sorted(raw_tasks), csvs))
                bids_ptr += 1
                matched = True
                break
            else:
                skipped_bids.append(bids_ses)
                bids_ptr += 1

        if not matched:
            log.warning("No BIDS match for %s (tasks: %s)", raw_ses, sorted(raw_tasks))
            unmatched_raw.append(raw_ses)

    # Any remaining BIDS sessions are also skipped
    while bids_ptr < len(bids_sessions):
        skipped_bids.append(bids_sessions[bids_ptr][0])
        bids_ptr += 1

    return mappings, skipped_bids, unmatched_raw


def main():
    parser = argparse.ArgumentParser(description="Rename behavioral CSVs to BIDS sourcedata layout")
    parser.add_argument("--input-dir", required=True, type=Path, help="raw_cleaned directory")
    parser.add_argument("--output-dir", required=True, type=Path, help="sourcedata output directory")
    parser.add_argument("--bids-dir", required=True, type=Path, help="BIDS directory for session matching")
    parser.add_argument("--dry-run", action="store_true", help="Print mapping without copying")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session_mapping = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "bids_dir": str(args.bids_dir),
        "subjects": {},
    }

    total_copied = 0
    total_skipped = 0

    # Discover all subjects in raw_cleaned
    subjects = sorted(
        d.name for d in args.input_dir.iterdir()
        if d.is_dir() and d.name not in SKIP_DIRS
    )

    # Load timestamps from reconciliation.json if available
    reconciliation_path = args.bids_dir / "sourcedata" / "reconciliation.json"
    timestamps = {}
    if reconciliation_path.exists():
        with open(reconciliation_path) as f:
            rec = json.load(f)
        for sub, info in rec.get("subjects", {}).items():
            timestamps[sub] = {
                s["bids_session"]: s.get("timestamp")
                for s in info.get("sessions", [])
            }

    for subject in subjects:
        bids_sessions = build_bids_task_map(args.bids_dir, subject)
        if not bids_sessions:
            log.info("Skipping %s: not found in BIDS directory", subject)
            continue

        raw_sessions = build_raw_session_map(args.input_dir, subject)
        if not raw_sessions:
            log.warning("Skipping %s: no behavioral sessions found", subject)
            continue

        mappings, skipped_bids, unmatched_raw = match_sessions(raw_sessions, bids_sessions)

        # Record mapping for audit
        sub_timestamps = timestamps.get(subject, {})
        session_mapping["subjects"][subject] = {
            "mappings": [
                {
                    "raw_session": raw_ses,
                    "bids_session": bids_ses,
                    "timestamp": sub_timestamps.get(bids_ses),
                    "tasks": tasks,
                }
                for raw_ses, bids_ses, tasks, _ in mappings
            ],
            "skipped_bids_sessions": skipped_bids,
            "unmatched_raw_sessions": unmatched_raw,
        }

        # Print summary
        matched_count = len(mappings)
        raw_count = len(raw_sessions)
        remapped = [(r, b) for r, b, _, _ in mappings if r != b]

        log.info(
            "%s: %d/%d behavioral sessions matched", subject, matched_count, raw_count
        )
        if remapped:
            for raw_ses, bids_ses in remapped:
                log.info("  %s -> %s (remapped)", raw_ses, bids_ses)
        if skipped_bids:
            log.info("  skipped BIDS: %s", ", ".join(skipped_bids))
        if unmatched_raw:
            log.warning("  unmatched behavioral: %s", ", ".join(unmatched_raw))

        # Copy files
        for raw_ses, bids_ses, tasks, csvs in mappings:
            for csv_path, task_name in csvs:
                if task_name is None:
                    total_skipped += 1
                    continue
                out_path = build_output_path(args.output_dir, subject, bids_ses, task_name)
                if not args.dry_run:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(csv_path, out_path)
                total_copied += 1

    # Write session mapping JSON
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        mapping_path = args.output_dir / "session_mapping.json"
        mapping_path.write_text(json.dumps(session_mapping, indent=2))
        log.info("Wrote session mapping to %s", mapping_path)
    else:
        log.info("Dry run — session mapping (not written):")
        print(json.dumps(session_mapping, indent=2))

    log.info("Done: %d copied, %d skipped", total_copied, total_skipped)


if __name__ == "__main__":
    main()
