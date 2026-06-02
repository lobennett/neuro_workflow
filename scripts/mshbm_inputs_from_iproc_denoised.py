#!/usr/bin/env python3
"""Build DENOISING-MATCHED MSHBM fsaverage6 inputs from iProc surfaces.

The iProc multi-echo path applies tedana ME-ICA + bandpass only — it skips the
motion/WM/CSF/GSR nuisance regression that its own single-echo path (and the
fMRIPrep du2025 arm) run. For a fair iProc-vs-fMRIPrep contrast (Option A), this
driver adds that regression back:

    tedana-denoised surface (pre-bandpass)
      -> regress iProc's own 18P nuisance (6 motion + GSR + CSF + WM + 9 derivs;
         first 18 cols of iProc's nuis_36P.dat) -- structurally identical to the
         fMRIPrep du2025 set
      -> bandpass 0.01-0.1 Hz (matches iProc 3dBandpass and the fMRIPrep arm)
      -> (V,1,1,T) NIfTI for MSHBM   [sm0; 2mm smoothing applied separately]

Now both arms = [pipeline-specific denoise] + [identical 18P nuisance] + [identical
bandpass], so the only remaining difference is ME-tedana (iProc) vs single-echo
(fMRIPrep).

Usage:
    uv run python scripts/mshbm_inputs_from_iproc_denoised.py \\
        --iproc-dir /scratch/users/logben/discovery_bids/derivatives/iproc \\
        --subject s10 \\
        --output-dir /scratch/users/logben/mshbm_inputs_iproc_fs6_denoised
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from neuro_workflow.analysis.mshbm.from_iproc import discover_iproc_scans, make_mshbm_name
from neuro_workflow.analysis.mshbm.preproc import bandpass_filter, regress_confounds

logger = logging.getLogger(__name__)
N_18P = 18  # first 18 cols of iProc nuis_36P = 9 base (mot6+WB+CSF+WM) + 9 deriv


def _load_surface(path: Path) -> np.ndarray:
    """Load an iProc folded fsaverage6 NIfTI to (V, T) via column-major reshape."""
    a = np.asarray(nib.load(str(path)).dataobj, dtype=np.float32)
    V = int(np.prod(a.shape[:3]))
    T = a.shape[3] if a.ndim == 4 else 1
    return a.reshape(V, T, order="F")


def _nuis_path(iproc_dir: Path, subj: str, session: str, run: str, task: str) -> Path:
    cell = f"{task}_{run}"
    return (iproc_dir / "mri_data" / subj / "NAT111" / session / cell /
            f"{session}_bld{run}_reorient_skip_mc_unwarp_anat_nuis_36P.dat")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--iproc-dir", type=Path, required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--tr", type=float, default=1.49)
    p.add_argument("--lowcut", type=float, default=0.01)
    p.add_argument("--highcut", type=float, default=0.1)
    p.add_argument("--only", default=None, help="process only this cell, e.g. 01_REST_004")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    subj = args.subject[4:] if args.subject.startswith("sub-") else args.subject
    scans = discover_iproc_scans(args.iproc_dir / "mri_data" / subj)
    if not scans:
        logger.error("No iProc scans under %s", args.iproc_dir)
        return 1
    if args.only:
        scans = [s for s in scans if f"{s.session}_{s.task}_{s.run}" == args.only]
    logger.info("Denoising-matched build: %d scans for sub-%s "
                "(tedana -> 18P regress -> bandpass %.3g-%.3g)",
                len(scans), subj, args.lowcut, args.highcut)

    out_subj = args.output_dir / f"sub-{subj}"
    out_subj.mkdir(parents=True, exist_ok=True)

    n_written = 0
    for scan in scans:
        nuis_p = _nuis_path(args.iproc_dir, subj, scan.session, scan.run, scan.task)
        if not nuis_p.exists():
            logger.warning("  SKIP (no nuis): %s_%s_%s", scan.session, scan.task, scan.run)
            continue
        X = np.loadtxt(nuis_p)[:, :N_18P]            # (T, 18) -> matches du2025
        for hemi, bpss_path in (("lh", scan.lh_path), ("rh", scan.rh_path)):
            # pre-bandpass tedana surface = bpss path with _tedana_bpss_ -> _tedana_
            pre = Path(str(bpss_path).replace("_tedana_bpss_", "_tedana_"))
            if not pre.exists():
                logger.warning("  SKIP (no pre-bandpass surf): %s", pre.name)
                continue
            out_name = make_mshbm_name(hemi, scan.session, scan.run, task=scan.task.lower())
            out_path = out_subj / out_name
            if out_path.exists():
                logger.info("  SKIP (exists): %s", out_name); continue
            Y = _load_surface(pre)                    # (V, T)
            if Y.shape[1] != X.shape[0]:
                logger.warning("  T mismatch surf=%d nuis=%d for %s — skip",
                               Y.shape[1], X.shape[0], out_name)
                continue
            Yr = regress_confounds(Y, X)
            Yb = bandpass_filter(Yr, tr=args.tr, lowcut=args.lowcut, highcut=args.highcut)
            Yb = np.nan_to_num(Yb, nan=0.0).astype(np.float32)
            out4 = Yb.reshape(Yb.shape[0], 1, 1, Yb.shape[1])
            nib.save(nib.Nifti1Image(out4, affine=np.eye(4)), str(out_path))
            logger.info("  %s_%s_%s %s -> %s", scan.session, scan.task, scan.run, hemi, out_name)
            n_written += 1

    total = len(list(out_subj.glob("lh*fsaverage6_sm*.nii.gz")))
    logger.info("done sub-%s: wrote %d (%d lh scans total)", subj, n_written, total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
