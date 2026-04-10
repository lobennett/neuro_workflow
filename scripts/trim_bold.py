#!/usr/bin/env python3
"""Trim 7 dummy volumes from BOLD NIfTIs and update sidecar JSONs.

Usage:
    uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
    uv run python scripts/trim_bold.py /scratch/users/logben/validation_bids
"""
import argparse
import json
import logging
from pathlib import Path

import nibabel as nib

log = logging.getLogger(__name__)

N_DUMMY = 7


def trim_bold_directory(bids_dir: Path) -> dict:
    """Trim dummy volumes from all BOLD NIfTIs in a BIDS directory.

    Returns summary dict with counts of trimmed, skipped_already_trimmed,
    skipped_too_short.
    """
    bids_dir = Path(bids_dir)
    summary = {"trimmed": 0, "skipped_already_trimmed": 0, "skipped_too_short": 0, "errors": 0}

    for nifti_path in sorted(bids_dir.glob("sub-*/ses-*/func/*_bold.nii.gz")):
        json_path = nifti_path.with_name(
            nifti_path.name.replace(".nii.gz", ".json")
        )

        # Idempotency check: skip if sidecar already records trimming
        if json_path.exists():
            sidecar = json.loads(json_path.read_text())
            if sidecar.get("NumberOfVolumesDiscardedByUser") == N_DUMMY:
                log.debug("Already trimmed: %s", nifti_path.name)
                summary["skipped_already_trimmed"] += 1
                continue
        else:
            sidecar = {}

        try:
            img = nib.load(str(nifti_path))
            n_vols = img.shape[3] if len(img.shape) > 3 else 1
        except Exception as e:
            log.error("Failed to load %s: %s", nifti_path.name, e)
            summary["errors"] += 1
            continue

        if n_vols <= N_DUMMY:
            log.warning("Too short to trim (dim4=%d): %s", n_vols, nifti_path.name)
            summary["skipped_too_short"] += 1
            continue

        # Trim first N_DUMMY volumes (write to temp file, then atomic rename)
        trimmed_data = img.slicer[:, :, :, N_DUMMY:]
        tmp_path = nifti_path.parent / nifti_path.name.replace("_bold.nii.gz", "_bold_tmp.nii.gz")
        nib.save(trimmed_data, str(tmp_path))
        tmp_path.rename(nifti_path)

        # Update sidecar
        sidecar["NumberOfVolumesDiscardedByUser"] = N_DUMMY
        if "NumVolumes" in sidecar:
            sidecar["NumVolumes"] = n_vols - N_DUMMY
        json_path.write_text(json.dumps(sidecar, indent=2) + "\n")

        log.info("Trimmed %d -> %d volumes: %s", n_vols, n_vols - N_DUMMY, nifti_path.name)
        summary["trimmed"] += 1

    return summary


def main():
    parser = argparse.ArgumentParser(description="Trim 7 dummy volumes from BOLD NIfTIs")
    parser.add_argument("bids_dir", type=Path, help="BIDS directory to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.bids_dir.exists():
        parser.error(f"Directory not found: {args.bids_dir}")

    summary = trim_bold_directory(args.bids_dir)
    print(f"Trimmed: {summary['trimmed']}")
    print(f"Skipped (already trimmed): {summary['skipped_already_trimmed']}")
    print(f"Skipped (too short): {summary['skipped_too_short']}")
    print(f"Errors: {summary['errors']}")


if __name__ == "__main__":
    main()
