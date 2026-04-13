#!/usr/bin/env python3
"""Migrate out-of-scanner behavioral and survey data to BIDS sourcedata.

Out-of-scanner behavioral:
  Sources:
    - {raw_dir}/s{sub}/ses-{X}/practice/*.csv  (per-session practice runs)
    - {raw_dir}/s{sub}/pretouch/*.csv          (subject-level pretouch runs)
  Target: sourcedata/out_scanner_behavior/sub-{sub}/

Survey data:
  Sources:
    - {survey_root}/prescan_surveys/raw/s{sub}/*  (JSON + PDF)
    - {survey_root}/demographics_surveys/raw/s{sub}/*
  Target: sourcedata/survey_data/sub-{sub}/{category}/

Filters to subjects listed in one or more reconciliation manifests.
Files are copied with their original filenames to preserve provenance.

Usage:
    uv run python scripts/migrate_archive.py \\
        --raw-dir /oak/.../behavioral_data/raw_cleaned \\
        --survey-root /oak/.../network_grant/survey_data \\
        --output-dir /oak/.../sourcedata \\
        --manifests config/manifests/reconciliation_discovery.tsv config/manifests/reconciliation_validation.tsv
"""
import argparse
import csv
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def _load_subjects_from_manifests(manifest_paths):
    """Collect all subject labels appearing in the provided manifests."""
    subjects = set()
    for mp in manifest_paths:
        with open(mp, newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sub = row["subject"].replace("sub-", "")
                subjects.add(sub)
    return subjects


def migrate_out_scanner(raw_dir, output_dir, subjects):
    """Copy practice and pretouch files for each subject."""
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir) / "out_scanner_behavior"
    copied = 0

    for sub in sorted(subjects):
        sub_raw = raw_dir / sub
        if not sub_raw.exists():
            continue
        sub_out = output_dir / f"sub-{sub}"
        sub_out.mkdir(parents=True, exist_ok=True)

        # Session-level practice
        for ses_dir in sub_raw.glob("ses-*/practice"):
            ses_label = ses_dir.parent.name  # ses-02
            for csv_file in ses_dir.glob("*.csv"):
                dest = sub_out / f"{ses_label}_{csv_file.name}"
                shutil.copy2(csv_file, dest)
                copied += 1

        # Subject-level pretouch
        pretouch_dir = sub_raw / "pretouch"
        if pretouch_dir.exists():
            for csv_file in pretouch_dir.glob("*.csv"):
                dest = sub_out / f"pretouch_{csv_file.name}"
                shutil.copy2(csv_file, dest)
                copied += 1

    log.info("Out-of-scanner: copied %d files", copied)
    return copied


def migrate_survey(survey_root, output_dir, subjects):
    """Copy prescan_surveys and demographics_surveys raw files per subject."""
    survey_root = Path(survey_root)
    output_dir = Path(output_dir) / "survey_data"
    copied = 0

    for category in ("prescan_surveys", "demographics_surveys"):
        raw_cat = survey_root / category / "raw"
        if not raw_cat.exists():
            log.warning("Survey source missing: %s", raw_cat)
            continue
        for sub in sorted(subjects):
            sub_src = raw_cat / sub
            if not sub_src.exists():
                continue
            sub_dest = output_dir / f"sub-{sub}" / category
            sub_dest.mkdir(parents=True, exist_ok=True)
            for f in sub_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, sub_dest / f.name)
                    copied += 1

    log.info("Survey: copied %d files", copied)
    return copied


def main():
    parser = argparse.ArgumentParser(
        description="Migrate out-of-scanner behavioral and survey data to BIDS sourcedata"
    )
    parser.add_argument("--raw-dir", required=True, type=Path,
                        help="raw_cleaned behavioral archive")
    parser.add_argument("--survey-root", required=True, type=Path,
                        help="survey_data root containing prescan_surveys/ and demographics_surveys/")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="sourcedata output root")
    parser.add_argument("--manifests", nargs="+", required=True, type=Path,
                        help="Reconciliation manifests for subject filtering")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    subjects = _load_subjects_from_manifests(args.manifests)
    log.info("Migrating %d subjects", len(subjects))

    out_scanner_copied = migrate_out_scanner(args.raw_dir, args.output_dir, subjects)
    survey_copied = migrate_survey(args.survey_root, args.output_dir, subjects)

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "subjects": sorted(subjects),
        "out_scanner_files": out_scanner_copied,
        "survey_files": survey_copied,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "archive_migration_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Out-of-scanner: {out_scanner_copied} files")
    print(f"Survey: {survey_copied} files")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
