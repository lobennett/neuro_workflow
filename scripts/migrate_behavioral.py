#!/usr/bin/env python3
"""Migrate behavioral data to BIDS sourcedata using a reviewed manifest.

Usage:
    uv run python scripts/migrate_behavioral.py \
        --manifest reconciliation_discovery.tsv \
        --raw-dir /oak/.../behavioral_data/raw_cleaned \
        --output-dir /oak/.../sourcedata \
        --sample discovery
"""

import argparse
import csv
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


def migrate_from_manifest(
    manifest_path: Path,
    output_dir: Path,
    strict: bool = False,
) -> dict:
    """Copy in-scanner behavioral files according to the reviewed manifest.

    Args:
        manifest_path: TSV manifest from reconcile_sessions.py
        output_dir: Sourcedata output root
        strict: If True, raise SystemExit if any rows are still 'pending'

    Returns:
        Report dict with counts.
    """
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)

    with open(manifest_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    report = {
        "copied": 0,
        "skipped_pending": 0,
        "skipped_irreconcilable": 0,
        "skipped_skip": 0,
        "skipped_no_raw_path": 0,
        "files": [],
    }

    pending_rows = [r for r in rows if r["action"] == "pending"]
    if strict and pending_rows:
        log.error(
            "%d rows still marked 'pending'. Resolve all discrepancies before migrating.",
            len(pending_rows),
        )
        sys.exit(1)

    for row in rows:
        action = row["action"]

        if action == "pending":
            report["skipped_pending"] += 1
            continue
        if action == "skip":
            report["skipped_skip"] += 1
            continue
        if action == "irreconcilable":
            report["skipped_irreconcilable"] += 1
            continue
        if action != "copy":
            log.warning(
                "Unknown action '%s' for %s %s %s, skipping",
                action,
                row["subject"],
                row["session"],
                row["task"],
            )
            continue

        raw_path = row.get("raw_path", "")
        if not raw_path or not Path(raw_path).exists():
            log.warning("Raw file not found: %s", raw_path)
            report["skipped_no_raw_path"] += 1
            continue

        subject = row["subject"]
        dest_session = row["dest_session"]
        task = row["task"]
        dest_run = row.get("dest_run", "").strip()

        sub_label = f"sub-{subject}" if not subject.startswith("sub-") else subject
        run_part = f"_run-{dest_run}" if dest_run else ""
        filename = f"{sub_label}_{dest_session}_task-{task}{run_part}_beh.csv"
        dest_path = output_dir / "in_scanner_behavior" / sub_label / dest_session / "beh" / filename

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_path, dest_path)

        report["copied"] += 1
        report["files"].append(
            {
                "src": raw_path,
                "dest": str(dest_path),
                "subject": subject,
                "session": dest_session,
                "task": task,
            }
        )

        log.info("Copied %s -> %s", Path(raw_path).name, dest_path)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Migrate behavioral data to BIDS sourcedata using reviewed manifest"
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Reviewed TSV manifest from reconcile_sessions.py",
    )
    parser.add_argument(
        "--raw-dir",
        required=True,
        type=Path,
        help="Path to raw_cleaned behavioral directory (for out-of-scanner, survey, mTurk)",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Sourcedata output root")
    parser.add_argument(
        "--sample",
        required=True,
        choices=["discovery", "validation"],
        help="Sample name (for filtering out-of-scanner/survey subjects)",
    )
    parser.add_argument(
        "--strict", action="store_true", help="Fail if any manifest rows are still 'pending'"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    report = migrate_from_manifest(args.manifest, args.output_dir, strict=args.strict)

    # Write migration report
    report_out = {
        "generated": datetime.now(UTC).isoformat(),
        "manifest": str(args.manifest),
        "sample": args.sample,
        **{k: v for k, v in report.items() if k != "files"},
        "files": report["files"],
    }
    report_path = args.output_dir / "migration_report.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_out, indent=2) + "\n")

    print(f"Copied: {report['copied']}")
    print(f"Skipped (pending): {report['skipped_pending']}")
    print(f"Skipped (irreconcilable): {report['skipped_irreconcilable']}")
    print(f"Skipped (skip): {report['skipped_skip']}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
