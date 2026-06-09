#!/usr/bin/env python3
"""Build MSHBM fsaverage6 inputs for one subject from iProc surfaces.

iProc's ``filter_and_project`` stage already produces bandpass-filtered,
multi-echo-denoised time series projected to fsaverage6 for every task+rest
scan. This driver discovers them and canonicalises each to the ``(V, 1, 1, T)``
NIfTI layout the CBIG MSHBM MATLAB wrapper consumes, written under
``<output-dir>/sub-<subj>/`` with names the wrapper globs
(``{lh,rh}*fsaverage6_sm*.nii.gz``).

By default ALL task+rest scans are emitted (full timeseries, nothing
task-regressed — per J. Du, the whole BOLD is fed to MSHBM). Pass ``--rest-only``
to restrict to rest scans.

Usage:
    uv run python scripts/mshbm_inputs_from_iproc.py \\
        --iproc-dir /scratch/users/logben/discovery_bids/derivatives/iproc \\
        --subject s10 \\
        --output-dir /scratch/users/logben/surface_inputs_iproc
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from neuro_workflow.analysis.mshbm.from_iproc import (
    discover_iproc_rest,
    discover_iproc_scans,
    iproc_surf_to_mshbm_nifti,
    make_mshbm_name,
)

logger = logging.getLogger(__name__)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--iproc-dir", type=Path, required=True,
                   help="iProc derivatives root (contains mri_data/<subj>/FS6/...)")
    p.add_argument("--subject", required=True,
                   help="Subject label without sub- prefix (e.g. s10)")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="MSHBM input root (creates sub-<subj>/ inside)")
    p.add_argument("--rest-only", action="store_true",
                   help="Only rest scans (default: ALL task+rest scans)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    subj = args.subject[4:] if args.subject.startswith("sub-") else args.subject
    iproc_subj_root = args.iproc_dir / "mri_data" / subj
    if not iproc_subj_root.is_dir():
        logger.error("No iProc subject dir at %s", iproc_subj_root)
        return 1

    if args.rest_only:
        scans = discover_iproc_rest(iproc_subj_root)
        scope = "rest"
    else:
        scans = discover_iproc_scans(iproc_subj_root)
        scope = "task+rest"
    if not scans:
        logger.error("No iProc fsaverage6 surfaces under %s/FS6", iproc_subj_root)
        return 1
    logger.info("Found %d %s runs for sub-%s", len(scans), scope, subj)

    out_subj = args.output_dir / f"sub-{subj}"
    out_subj.mkdir(parents=True, exist_ok=True)

    n_written = 0
    for scan in scans:
        # rest-only scans (IprocRestScan) have no .task; default to "rest"
        task = getattr(scan, "task", "REST").lower()
        for hemi, src in (("lh", scan.lh_path), ("rh", scan.rh_path)):
            out_name = make_mshbm_name(hemi, scan.session, scan.run, task=task)
            out_path = out_subj / out_name
            if out_path.exists():
                logger.info("  SKIP (exists): %s", out_name)
                continue
            iproc_surf_to_mshbm_nifti(src, out_path)
            logger.info("  ses-%s %s -> %s", scan.session, hemi, out_name)
            n_written += 1

    total = len(list(out_subj.glob("lh*fsaverage6_sm*.nii.gz")))
    logger.info("done sub-%s: wrote %d files (%d lh sessions total in %s)",
                subj, n_written, total, out_subj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
