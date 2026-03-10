#!/usr/bin/env python3
"""One-time migration: standardize raw behavioral CSV filenames to BIDS sourcedata layout.

Usage:
    python scripts/rename_behavioral_to_sourcedata.py \
        --input-dir /oak/.../behavioral_data/raw_cleaned \
        --output-dir /oak/.../behavioral_data/sourcedata \
        [--dry-run]
"""
import argparse
import logging
import re
import shutil
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
    ses_label = zero_pad_session(session)
    filename = f"{sub_label}_{ses_label}_task-{task_name}_beh.csv"
    return output_root / sub_label / ses_label / "beh" / filename


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


def main():
    parser = argparse.ArgumentParser(description="Rename behavioral CSVs to BIDS sourcedata layout")
    parser.add_argument("--input-dir", required=True, type=Path, help="raw_cleaned directory")
    parser.add_argument("--output-dir", required=True, type=Path, help="sourcedata output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print mapping without copying")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    copied = 0
    skipped = 0
    for csv_path, subject, session in discover_csvs(args.input_dir):
        task_name = parse_csv_filename(csv_path.name)
        if task_name is None:
            log.warning("Skipping unrecognized file: %s", csv_path)
            skipped += 1
            continue
        out_path = build_output_path(args.output_dir, subject, session, task_name)
        log.info("%s -> %s", csv_path, out_path)
        if not args.dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(csv_path, out_path)
        copied += 1

    log.info("Done: %d copied, %d skipped", copied, skipped)


if __name__ == "__main__":
    main()
