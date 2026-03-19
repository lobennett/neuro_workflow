#!/usr/bin/env python
"""
Check correspondence between behavioral data and fMRI BOLD data.

Validates that:
1. Behavioral CSV files have corresponding BOLD scans
2. BOLD scans have corresponding behavioral data
3. Reports discrepancies for .bidsignore addition

Only checks discovery subjects against discovery_bids and validation subjects against validation_bids.

Usage:
    python scripts/check_behavioral_bold_correspondence.py
"""

import re
import json
from pathlib import Path
from collections import defaultdict

from neuro_workflow.behavioral_archive.sample_validation import load_samples_from_config


def extract_beh_info(beh_file: Path) -> dict:
    """
    Extract subject, session, task from behavioral filename.

    Example: sub-s03_ses-01_task-goNogo_beh.csv
    """
    match = re.match(r"sub-(s\d+)_ses-(\d+)_task-([^_]+)_beh\.csv", beh_file.name)
    if match:
        return {
            "subject": match.group(1),
            "session": match.group(2),
            "task": match.group(3),
            "file": beh_file
        }
    return None


def extract_bold_info(bold_file: Path) -> dict:
    """
    Extract subject, session, task, run from BOLD filename.

    Example: sub-s03_ses-01_task-goNogo_run-1_echo-1_bold.nii.gz
    """
    match = re.match(r"sub-(s\d+)_ses-(\d+)_task-([^_]+)_run-(\d+)_echo-\d+_bold\.nii\.gz", bold_file.name)
    if match:
        return {
            "subject": match.group(1),
            "session": match.group(2),
            "task": match.group(3),
            "run": match.group(4),
            "file": bold_file
        }
    return None


def get_behavioral_data(beh_root: Path) -> dict:
    """Get all behavioral data indexed by (subject, session, task)."""
    behavioral = defaultdict(lambda: [])

    for beh_file in beh_root.rglob("*_beh.csv"):
        info = extract_beh_info(beh_file)
        if info:
            key = (info["subject"], info["session"], info["task"])
            behavioral[key].append(info["file"])

    return behavioral


def get_bold_data(bids_root: Path) -> dict:
    """Get all BOLD data indexed by (subject, session, task, run)."""
    bold = defaultdict(lambda: [])

    for bold_file in bids_root.rglob("*_bold.nii.gz"):
        info = extract_bold_info(bold_file)
        if info:
            key = (info["subject"], info["session"], info["task"], info["run"])
            bold[key].append(info["file"])

    return bold


def main():
    # Paths
    beh_root = Path("/oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior")
    discovery_bids = Path("/scratch/users/logben/discovery_bids")
    validation_bids = Path("/scratch/users/logben/validation_bids")

    # Load sample configuration to filter subjects
    config_path = Path("config/behavioral_session_mapping.json")
    samples = load_samples_from_config(config_path)

    discovery_subjects = set(samples.get("discovery", []))
    validation_subjects = set(samples.get("validation", []))

    print("=" * 80)
    print("BEHAVIORAL <-> BOLD CORRESPONDENCE CHECK")
    print("=" * 80)
    print(f"\nLoaded {len(discovery_subjects)} discovery subjects")
    print(f"Loaded {len(validation_subjects)} validation subjects\n")

    datasets = [
        ("discovery", discovery_bids, discovery_subjects),
        ("validation", validation_bids, validation_subjects),
    ]

    all_discrepancies = {
        "discovery": {
            "behavioral_without_bold": [],
            "bold_without_behavioral": [],
        },
        "validation": {
            "behavioral_without_bold": [],
            "bold_without_behavioral": [],
        },
    }

    for sample_name, bids_root, sample_subjects in datasets:
        print(f"\n### {sample_name.upper()} DATASET ###\n")

        # Get ALL behavioral data
        all_behavioral = get_behavioral_data(beh_root)

        # Filter to only this sample's subjects
        behavioral = {}
        for (subj, sess, task), beh_files in all_behavioral.items():
            if subj in sample_subjects:
                behavioral[(subj, sess, task)] = beh_files

        print(f"Found {len(behavioral)} behavioral (subject, session, task) groups for {sample_name}")

        # Get BOLD data
        bold = get_bold_data(bids_root)
        print(f"Found {len(bold)} BOLD (subject, session, task, run) files\n")

        behavioral_without_bold = []
        bold_without_behavioral = []

        # Check behavioral files have BOLD
        print("Checking behavioral → BOLD correspondence...")
        for (subj, sess, task), beh_files in sorted(behavioral.items()):
            # Look for BOLD files matching this (subject, session, task)
            matching_bold = []
            for (bold_subj, bold_sess, bold_task, run), bold_files in bold.items():
                if bold_subj == subj and bold_sess == sess and bold_task == task:
                    matching_bold.extend(bold_files)

            if not matching_bold:
                # This behavioral data has no corresponding BOLD
                behavioral_without_bold.append({
                    "subject": subj,
                    "session": sess,
                    "task": task,
                    "behavioral_files": [str(f.relative_to(beh_root)) for f in beh_files],
                })

        # Check BOLD files have behavioral
        print("Checking BOLD → behavioral correspondence...")
        for (bold_subj, bold_sess, bold_task, run), bold_files in sorted(bold.items()):
            # Skip rest tasks - they never have behavioral data
            if bold_task == "rest":
                continue

            # Look for behavioral matching this (subject, session, task)
            key = (bold_subj, bold_sess, bold_task)
            if key not in behavioral:
                # This BOLD scan has no corresponding behavioral
                bold_without_behavioral.append({
                    "subject": bold_subj,
                    "session": bold_sess,
                    "task": bold_task,
                    "run": run,
                    "bold_files": [str(f.relative_to(bids_root)) for f in bold_files],
                })

        all_discrepancies[sample_name]["behavioral_without_bold"] = behavioral_without_bold
        all_discrepancies[sample_name]["bold_without_behavioral"] = bold_without_behavioral

        # Print summary
        print(f"\n{'ISSUES FOUND:' if (behavioral_without_bold or bold_without_behavioral) else 'NO ISSUES'}\n")

        if behavioral_without_bold:
            print(f"Behavioral data without BOLD scans ({len(behavioral_without_bold)}):")
            for item in behavioral_without_bold[:10]:
                print(f"  sub-{item['subject']}/ses-{item['session']}/task-{item['task']}")
            if len(behavioral_without_bold) > 10:
                print(f"  ... and {len(behavioral_without_bold) - 10} more")

        if bold_without_behavioral:
            print(f"\nBOLD scans without behavioral data ({len(bold_without_behavioral)}):")
            for item in bold_without_behavioral[:10]:
                print(f"  sub-{item['subject']}/ses-{item['session']}/task-{item['task']}/run-{item['run']}")
            if len(bold_without_behavioral) > 10:
                print(f"  ... and {len(bold_without_behavioral) - 10} more")

    # Write detailed report
    report_path = Path("logs/bidsify_logs/behavioral_bold_correspondence_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(all_discrepancies, f, indent=2)

    print(f"\n{'=' * 80}")
    print(f"Detailed report saved to: {report_path}")
    print(f"{'=' * 80}\n")

    # Print .bidsignore entries needed
    print("\nTO ADD TO .bidsignore (for missing BOLD scans):\n")
    for sample_name in ["discovery", "validation"]:
        bidsignore_entries = []
        for item in all_discrepancies[sample_name]["behavioral_without_bold"]:
            bidsignore_entries.append(
                f"sub-{item['subject']}/ses-{item['session']}/beh/"
                f"sub-{item['subject']}_ses-{item['session']}_task-{item['task']}_beh.csv"
            )

        if bidsignore_entries:
            print(f"# {sample_name.upper()}")
            for entry in sorted(bidsignore_entries):
                print(entry)
            print()


if __name__ == "__main__":
    main()
