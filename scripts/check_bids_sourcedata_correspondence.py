#!/usr/bin/env python3
"""Check 1-1 correspondence between BIDS functional scans and sourcedata behavioral files."""

import json
from collections import defaultdict
from pathlib import Path

def extract_bids_tasks(bids_dir):
    """Extract all functional tasks from BIDS directory.

    Returns dict: {subject: {session: [task_list]}}
    """
    tasks = defaultdict(lambda: defaultdict(set))
    bids_path = Path(bids_dir)

    for func_file in bids_path.glob("sub-*/ses-*/func/*_bold.nii.gz"):
        # Extract subject, session, and task from path
        # Format: sub-XXX/ses-YY/func/sub-XXX_ses-YY_task-TASKNAME_bold.nii.gz
        parts = func_file.stem.split("_")
        subject = None
        session = None
        task = None

        for part in parts:
            if part.startswith("sub-"):
                subject = part
            elif part.startswith("ses-"):
                session = part
            elif part.startswith("task-"):
                task = part

        if subject and session and task:
            tasks[subject][session].add(task)

    return {s: {ses: sorted(list(tasks_set)) for ses, tasks_set in sessions.items()}
            for s, sessions in tasks.items()}

def extract_sourcedata_sessions(sourcedata_dir):
    """Extract all behavioral sessions from sourcedata.

    Returns dict: {subject: {session: [behavioral_files]}}
    """
    sessions = defaultdict(lambda: defaultdict(set))
    sourcedata_path = Path(sourcedata_dir)

    for beh_file in sourcedata_path.glob("sub-*/ses-*/beh/*.csv"):
        # Extract subject and session from path
        # Format: sub-XXX/ses-YY/beh/sub-XXX_ses-YY_task-TASKNAME.csv
        parts = beh_file.stem.split("_")
        subject = None
        session = None

        for part in parts:
            if part.startswith("sub-"):
                subject = part
            elif part.startswith("ses-"):
                session = part

        if subject and session:
            sessions[subject][session].add(beh_file.name)

    return {s: {ses: sorted(list(files_set)) for ses, files_set in sess.items()}
            for s, sess in sessions.items()}

def compare_datasets(bids_tasks, sourcedata_sessions):
    """Compare BIDS tasks with sourcedata behavioral files.

    Returns: (matches, missing_behavioral, orphaned_behavioral)
    """
    matches = []
    missing_behavioral = []
    orphaned_behavioral = []

    # Check each BIDS task has corresponding behavioral file
    for subject in sorted(bids_tasks.keys()):
        for session in sorted(bids_tasks[subject].keys()):
            for task in bids_tasks[subject][session]:
                # Look for corresponding behavioral file
                # Extract task name from "task-TASKNAME" format
                task_name = task.replace("task-", "")

                if subject in sourcedata_sessions and session in sourcedata_sessions[subject]:
                    # Look for matching behavioral file
                    found = False
                    for beh_file in sourcedata_sessions[subject][session]:
                        if f"task-{task_name}" in beh_file:
                            matches.append((subject, session, task, beh_file))
                            found = True
                            break

                    if not found:
                        missing_behavioral.append((subject, session, task))
                else:
                    missing_behavioral.append((subject, session, task))

    # Check for orphaned behavioral files
    for subject in sorted(sourcedata_sessions.keys()):
        for session in sorted(sourcedata_sessions[subject].keys()):
            for beh_file in sourcedata_sessions[subject][session]:
                # Extract task from behavioral filename
                if "task-" in beh_file:
                    task_name = beh_file.split("task-")[1].split(".")[0].split("_")[0]
                    task_full = f"task-{task_name}"

                    if subject not in bids_tasks or \
                       session not in bids_tasks[subject] or \
                       task_full not in bids_tasks[subject][session]:
                        orphaned_behavioral.append((subject, session, beh_file))

    return matches, missing_behavioral, orphaned_behavioral

def main():
    # Extract from all three datasets
    print("=" * 80)
    print("CHECKING BIDS <-> SOURCEDATA CORRESPONDENCE")
    print("=" * 80)
    print()

    datasets = {
        "discovery": {
            "bids": "/scratch/users/logben/discovery_bids",
            "sourcedata": "/oak/stanford/groups/russpold/data/network_grant/sourcedata",
            "excluded_sourcedata": None,
        },
        "validation": {
            "bids": "/scratch/users/logben/validation_bids",
            "sourcedata": "/oak/stanford/groups/russpold/data/network_grant/sourcedata",
            "excluded_sourcedata": "/oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata",
        },
        "excluded": {
            "bids": "/scratch/users/logben/excluded_bids",
            "sourcedata": None,
            "excluded_sourcedata": "/oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata",
        },
    }

    all_results = {}

    for sample_name, paths in datasets.items():
        print(f"\n### {sample_name.upper()} DATASET ###\n")

        if not Path(paths["bids"]).exists():
            print(f"BIDS directory not found: {paths['bids']}")
            continue

        # Extract BIDS tasks
        bids_tasks = extract_bids_tasks(paths["bids"])
        print(f"Found {sum(len(sessions) for sessions in bids_tasks.values())} BIDS sessions")

        # Extract sourcedata (include both regular and excluded)
        all_sourcedata = defaultdict(lambda: defaultdict(set))

        if paths["sourcedata"] and Path(paths["sourcedata"] / "behavioral_data").exists():
            sourcedata_regular = extract_sourcedata_sessions(paths["sourcedata"] / "behavioral_data")
            for subj, sessions in sourcedata_regular.items():
                for sess, files in sessions.items():
                    all_sourcedata[subj][sess].update(files)

        if paths["excluded_sourcedata"] and Path(paths["excluded_sourcedata"] / "behavioral_data").exists():
            sourcedata_excluded = extract_sourcedata_sessions(paths["excluded_sourcedata"] / "behavioral_data")
            for subj, sessions in sourcedata_excluded.items():
                for sess, files in sessions.items():
                    all_sourcedata[subj][sess].update(files)

        sourcedata_sessions = {s: {ses: sorted(list(files_set)) for ses, files_set in sess.items()}
                               for s, sess in all_sourcedata.items()}
        print(f"Found {sum(len(sessions) for sessions in sourcedata_sessions.values())} sourcedata sessions")

        # Compare
        matches, missing_beh, orphaned_beh = compare_datasets(bids_tasks, sourcedata_sessions)

        print(f"\nMatches (1-1 correspondence): {len(matches)}")
        print(f"BIDS tasks with missing behavioral: {len(missing_beh)}")
        print(f"Orphaned behavioral files: {len(orphaned_beh)}")

        if missing_beh:
            print(f"\n  Missing behavioral files:")
            for subject, session, task in missing_beh[:10]:  # Show first 10
                print(f"    {subject}/{session}/{task}")
            if len(missing_beh) > 10:
                print(f"    ... and {len(missing_beh) - 10} more")

        if orphaned_beh:
            print(f"\n  Orphaned behavioral files:")
            for subject, session, beh_file in orphaned_beh[:10]:  # Show first 10
                print(f"    {subject}/{session}/{beh_file}")
            if len(orphaned_beh) > 10:
                print(f"    ... and {len(orphaned_beh) - 10} more")

        all_results[sample_name] = {
            "bids_tasks": bids_tasks,
            "sourcedata_sessions": sourcedata_sessions,
            "matches": len(matches),
            "missing_behavioral": missing_beh,
            "orphaned_behavioral": orphaned_beh,
        }

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for sample_name, results in all_results.items():
        total_issues = len(results["missing_behavioral"]) + len(results["orphaned_behavioral"])
        status = "✓ PASS" if total_issues == 0 else f"✗ ISSUES ({total_issues})"
        print(f"{sample_name:15} | {results['matches']:4} matches | {status}")

if __name__ == "__main__":
    main()
