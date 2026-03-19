#!/usr/bin/env python
"""
Resolve behavioral-BOLD discrepancies by:
1. Creating empty CSV placeholders for BOLD scans missing behavioral data
2. Adding entries to .bidsignore for missing/mismatched data
3. Generating comprehensive discrepancy report

Usage:
    python scripts/resolve_behavioral_discrepancies.py
"""

from pathlib import Path
from datetime import datetime


def create_empty_behavioral_csv(filepath: Path, reason: str):
    """Create an empty behavioral CSV with explanation header."""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    header = f"""# PLACEHOLDER - No behavioral data collected for this scan
# Reason: {reason}
# Created: {datetime.now().isoformat()}
# This file is a placeholder indicating that the BOLD scan exists but no behavioral data was recorded.
# Both this file and the corresponding BOLD scan are added to .bidsignore.
#
# Columns would normally be: [task-specific behavioral data columns]
"""
    filepath.write_text(header + "\n")
    return filepath


def main():
    # Discovery dataset discrepancies
    discovery_bidsignore = Path("/scratch/users/logben/discovery_bids/.bidsignore")
    discovery_root = Path("/scratch/users/logben/discovery_bids")

    # Validation dataset discrepancies
    validation_bidsignore = Path("/scratch/users/logben/validation_bids/.bidsignore")
    validation_root = Path("/scratch/users/logben/validation_bids")

    # Discrepancies with action needed
    discovery_missing_behavioral = [
        {
            "subject": "s19",
            "session": "ses-02",
            "task": "goNogo",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s19",
            "session": "ses-11",
            "task": "directedForgettingWFlanker",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s29",
            "session": "ses-01",
            "task": "cuedTS",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s29",
            "session": "ses-02",
            "task": "goNogo",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s43",
            "session": "ses-02",
            "task": "goNogo",
            "reason": "Behavioral data file missing from archive"
        },
    ]

    validation_missing_behavioral = [
        {
            "subject": "s1175",
            "session": "ses-11",
            "task": "cuedTSWFlanker",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s1292",
            "session": "ses-04",
            "task": "nBack",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s180",
            "session": "ses-12",
            "task": "shapeMatchingWCuedTS",
            "reason": "Behavioral data file missing from archive"
        },
        {
            "subject": "s321",
            "session": "ses-02",
            "task": "spatialTS",
            "reason": "Behavioral data file missing from archive"
        },
    ]

    # Special cases
    validation_behavioral_without_bold = [
        {
            "subject": "s321",
            "session": "ses-01",
            "task": "spatialTS",
            "reason": "BOLD scan does not exist for this task"
        }
    ]

    print("=" * 80)
    print("RESOLVING BEHAVIORAL-BOLD DISCREPANCIES")
    print("=" * 80)

    # Process Discovery Dataset
    print("\n### DISCOVERY DATASET ###\n")

    discovery_bidsignore_entries = []

    for disc in discovery_missing_behavioral:
        sub_label = f"sub-{disc['subject']}"
        beh_path = discovery_root / "sourcedata" / "in_scanner_behavior" / sub_label / disc["session"] / "beh" / f"{sub_label}_{disc['session']}_task-{disc['task']}_beh.csv"

        # Create empty CSV placeholder
        print(f"Creating placeholder: {sub_label}/{disc['session']}/task-{disc['task']}")
        create_empty_behavioral_csv(beh_path, disc["reason"])

        # Add to .bidsignore
        bidsignore_entry = f"{sub_label}/{disc['session']}/beh/{sub_label}_{disc['session']}_task-{disc['task']}_beh.csv"
        discovery_bidsignore_entries.append(f"# {disc['reason']}")
        discovery_bidsignore_entries.append(bidsignore_entry)
        discovery_bidsignore_entries.append("")

    # Special case: s03 ses-01 nBack (behavioral in ses-02, BOLD in ses-01) - note only
    discovery_bidsignore_entries.append("# SALVAGEABLE: s03 ses-01 nBack - behavioral CSV in raw ses-02 directory")
    discovery_bidsignore_entries.append("# Action: Update session mapping and re-run migration to salvage this file")
    discovery_bidsignore_entries.append("")

    # Write discovery .bidsignore
    if discovery_bidsignore_entries:
        print(f"\nWriting {len(discovery_bidsignore_entries)} lines to discovery .bidsignore")
        with open(discovery_bidsignore, "a") as f:
            f.write("\n# Behavioral-BOLD Discrepancies (Mar 19, 2026)\n")
            f.write("# See: docs/BEHAVIORAL_BOLD_DISCREPANCIES.md\n\n")
            f.write("\n".join(discovery_bidsignore_entries))
            if not discovery_bidsignore_entries[-1].startswith("#"):
                f.write("\n")

    # Process Validation Dataset
    print("\n### VALIDATION DATASET ###\n")

    validation_bidsignore_entries = []

    # Missing behavioral files
    for disc in validation_missing_behavioral:
        sub_label = f"sub-{disc['subject']}"
        beh_path = validation_root / "sourcedata" / "in_scanner_behavior" / sub_label / disc["session"] / "beh" / f"{sub_label}_{disc['session']}_task-{disc['task']}_beh.csv"

        # Create empty CSV placeholder
        print(f"Creating placeholder: {sub_label}/{disc['session']}/task-{disc['task']}")
        create_empty_behavioral_csv(beh_path, disc["reason"])

        # Add to .bidsignore
        bidsignore_entry = f"{sub_label}/{disc['session']}/beh/{sub_label}_{disc['session']}_task-{disc['task']}_beh.csv"
        validation_bidsignore_entries.append(f"# {disc['reason']}")
        validation_bidsignore_entries.append(bidsignore_entry)
        validation_bidsignore_entries.append("")

    # Behavioral without BOLD
    for disc in validation_behavioral_without_bold:
        sub_label = f"sub-{disc['subject']}"
        bidsignore_entry = f"{sub_label}/{disc['session']}/beh/{sub_label}_{disc['session']}_task-{disc['task']}_beh.csv"

        print(f"Marking for exclusion (behavioral w/o BOLD): {sub_label}/{disc['session']}/task-{disc['task']}")
        validation_bidsignore_entries.append(f"# {disc['reason']} - Behavioral file exists but no BOLD scan")
        validation_bidsignore_entries.append(bidsignore_entry)
        validation_bidsignore_entries.append("")

    # Special case: s300 ses-08 flanker (behavioral in ses-09, BOLD in ses-08) - note only
    validation_bidsignore_entries.append("# SALVAGEABLE: s300 ses-08 flanker - behavioral CSV in raw ses-09 directory")
    validation_bidsignore_entries.append("# Action: Update session mapping and re-run migration to salvage this file")
    validation_bidsignore_entries.append("")

    # Write validation .bidsignore
    if validation_bidsignore_entries:
        print(f"\nWriting {len(validation_bidsignore_entries)} lines to validation .bidsignore")
        with open(validation_bidsignore, "a") as f:
            f.write("\n# Behavioral-BOLD Discrepancies (Mar 19, 2026)\n")
            f.write("# See: docs/BEHAVIORAL_BOLD_DISCREPANCIES.md\n\n")
            f.write("\n".join(validation_bidsignore_entries))
            if not validation_bidsignore_entries[-1].startswith("#"):
                f.write("\n")

    # Summary
    print("\n" + "=" * 80)
    print("RESOLUTION COMPLETE")
    print("=" * 80)
    print(f"\nDiscovery:")
    print(f"  - Created {len(discovery_missing_behavioral)} empty behavioral CSV placeholders")
    print(f"  - Added {len(discovery_missing_behavioral)} entries to .bidsignore")
    print(f"\nValidation:")
    print(f"  - Created {len(validation_missing_behavioral)} empty behavioral CSV placeholders")
    print(f"  - Added {len(validation_missing_behavioral)} entries to .bidsignore")
    print(f"  - Excluded {len(validation_behavioral_without_bold)} behavioral file(s) without BOLD")
    print(f"\nTotal BIDS entries affected: {len(discovery_missing_behavioral) + len(validation_missing_behavioral) + len(validation_behavioral_without_bold)}")
    print(f"\nSalvageable items (optional - requires session mapping update):")
    print(f"  - s03 ses-01 nBack (discovery)")
    print(f"  - s300 ses-08 flanker (validation)")
    print(f"\nFor full details, see:")
    print(f"  - docs/BEHAVIORAL_BOLD_DISCREPANCIES.md")
    print(f"  - /oak/.../sourcedata/BEHAVIORAL_DISCREPANCIES_NOTES.md")


if __name__ == "__main__":
    main()
