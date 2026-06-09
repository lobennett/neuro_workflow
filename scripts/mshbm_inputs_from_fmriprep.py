#!/usr/bin/env python3
"""Build MSHBM fsaverage6 inputs for one subject from fMRIPrep surface BOLD.

fMRIPrep arm of the pipeline comparison. Takes fMRIPrep's own fsaverage6 surface
BOLD (FS 7.3.2, via its sphere.reg) and applies the lab's mshbm.preproc:
du2025 confound regression + bandpass. The bandpass band defaults to 0.01-0.1 Hz
to MATCH iProc's `3dBandpass 0.01 0.1`, so the only pipeline difference vs the
iProc arm is the denoising (fMRIPrep confound-regression vs iProc ME-tedana) and
registration. No surface smoothing (sm0) — matching the iProc arms for this
comparison.

Output: `<output-dir>/sub-<subj>/{lh,rh}_ses-NN_task-T_run-R_nat_resid_bpss_fsaverage6_sm0.nii.gz`
as (V, 1, 1, T) NIfTIs the CBIG MSHBM wrapper consumes.

Usage:
    uv run python scripts/mshbm_inputs_from_fmriprep.py \\
        --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \\
        --subject s10 \\
        --output-dir /scratch/users/logben/mshbm_inputs_fmriprep_taskrest
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

from neuro_workflow.analysis.mshbm.from_fmriprep import (
    denoise_timeseries,
    discover_fmriprep_scans,
    make_mshbm_name,
)
from neuro_workflow.analysis.mshbm.surfsmooth import func_gii_to_array

logger = logging.getLogger(__name__)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fmriprep-dir", type=Path, required=True,
                   help="fMRIPrep derivatives root (contains sub-<subj>/ses-*/func/)")
    p.add_argument("--subject", required=True,
                   help="Subject label without sub- prefix (e.g. s10)")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="MSHBM input root (creates sub-<subj>/ inside)")
    p.add_argument("--lowcut", type=float, default=0.01,
                   help="Bandpass low cutoff Hz (default 0.01, matches iProc 3dBandpass)")
    p.add_argument("--highcut", type=float, default=0.1,
                   help="Bandpass high cutoff Hz (default 0.1, matches iProc 3dBandpass)")
    p.add_argument("--only", default=None,
                   help="Process only the scan whose prefix matches (e.g. ses-01_task-flanker_run-1)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    subj = args.subject[4:] if args.subject.startswith("sub-") else args.subject
    scans = discover_fmriprep_scans(args.fmriprep_dir, subj)
    if not scans:
        logger.error("No fMRIPrep fsaverage6 surface BOLD under %s/sub-%s",
                     args.fmriprep_dir, subj)
        return 1

    if args.only:
        scans = [s for s in scans
                 if f"ses-{s.session}_task-{s.task}_run-{s.run}" == args.only
                 or f"ses-{s.session}_task-{s.task}" == args.only]
    logger.info("Processing %d fMRIPrep task+rest scans for sub-%s "
                "(bandpass %.3g-%.3g Hz, sm0)", len(scans), subj, args.lowcut, args.highcut)

    out_subj = args.output_dir / f"sub-{subj}"
    out_subj.mkdir(parents=True, exist_ok=True)

    n_written = 0
    for scan in scans:
        try:
            conf = pd.read_csv(scan.confounds_tsv, sep="\t")
        except FileNotFoundError:
            logger.warning("  SKIP (no confounds): ses-%s task-%s run-%s",
                           scan.session, scan.task, scan.run)
            continue
        for hemi, src in (("lh", scan.lh_path), ("rh", scan.rh_path)):
            out_name = make_mshbm_name(hemi, scan.session, scan.run, scan.task)
            out_path = out_subj / out_name
            if out_path.exists():
                logger.info("  SKIP (exists): %s", out_name)
                continue
            Y = func_gii_to_array(src)                       # (V, T)
            Yd = denoise_timeseries(Y, conf, tr=scan.tr,
                                    lowcut=args.lowcut, highcut=args.highcut)
            out_4d = Yd.reshape(Yd.shape[0], 1, 1, Yd.shape[1]).astype(np.float32)
            nib.save(nib.Nifti1Image(out_4d, affine=np.eye(4)), str(out_path))
            logger.info("  ses-%s task-%s %s -> %s", scan.session, scan.task, hemi, out_name)
            n_written += 1

    total = len(list(out_subj.glob("lh*fsaverage6_sm*.nii.gz")))
    logger.info("done sub-%s: wrote %d files (%d lh scans total in %s)",
                subj, n_written, total, out_subj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
