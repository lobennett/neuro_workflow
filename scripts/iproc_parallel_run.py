"""Mirror an iProc subject directory to a parallel root and submit combine + filter.

Creates real directories with input files symlinked, so combine/filter outputs land in
the parallel root without touching the canonical tree. Launches on russpold's 32-CPU /
256 GB nodes for ~3-4x speedup over the canonical 8-CPU configuration.

Scientific equivalence:
  - Uses the exact iProc code + same per-scan args (we change nothing in iProc's
    invocation; only the BASEDIR cfg value moves outputs to a parallel root).
  - Inputs (BOLDs, mc.mat dirs, regressors_mc.dat, cross_session_maps templates,
    FreeSurfer recon-all) are symlinked from the canonical tree, so combine and
    filter read from the same canonical files the in-flight 8-CPU job would.
  - Outputs land in the parallel tree only, so no collision with the canonical run.

Usage:
  uv run python scripts/iproc_parallel_run.py \\
    --sub s10 \\
    --canonical-root /scratch/users/logben/discovery_bids/derivatives/iproc \\
    --parallel-root /scratch/users/logben/discovery_bids/derivatives/iproc_parallel
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def mirror_iproc_subject(canonical_root: Path, parallel_root: Path, sub: str) -> None:
    """Mirror the canonical iProc tree for one subject into a parallel root.

    - Top-level configs/ and fs/ are symlinked (immutable inputs, shared across runs).
    - mri_data/{sub}/cross_session_maps/ symlinked (templates from setup/unwarp/T1_warp).
    - mri_data/{sub}/NAT/{sess}/{TASK_BLD}/ are mkdir'd as real dirs with every existing
      file (and the mc.mat subdir) symlinked from canonical. This lets combine and
      filter write new outputs alongside the symlinked inputs, into the parallel root.
    - subject_lists/{sub}.cfg is rewritten in place with the new BASEDIR; scanlist is
      symlinked. logs/, Q/, rmfiles/, scratch/ start fresh.
    """
    canon = Path(canonical_root)
    para = Path(parallel_root)
    para.mkdir(parents=True, exist_ok=True)

    # Top-level: symlink configs/ and fs/ (read-only across runs), fresh scratch/.
    for d in ("configs", "fs"):
        src = canon / d
        dst = para / d
        if not dst.exists() and not dst.is_symlink():
            dst.symlink_to(src.resolve())
    (para / "scratch").mkdir(exist_ok=True)

    canon_sub = canon / "mri_data" / sub
    para_sub = para / "mri_data" / sub
    para_sub.mkdir(parents=True, exist_ok=True)

    # cross_session_maps: templates (mpr, _allscans_meanBOLD_to_T1, etc.) — all inputs.
    cm_dst = para_sub / "cross_session_maps"
    if not cm_dst.exists() and not cm_dst.is_symlink():
        cm_dst.symlink_to((canon_sub / "cross_session_maps").resolve())

    # Subject-level state dirs (logs/, Q/, rmfiles/): real dirs with EXISTING canonical
    # files symlinked. combine_and_apply_warp begins by loading
    # rmfiles/unwarp_motioncorrect_align.final (a state marker written when unwarp
    # completed); if absent, iProc raises IOError("Did you run the previous steps?").
    # We're skipping unwarp in the parallel run (its outputs are valid in canonical),
    # so we need to surface those state markers for combine to start.
    # logs/ and Q/ get the same treatment; parallel runs write NEW files (with new
    # SLURM job IDs / new step names) alongside the symlinked old ones — no collision.
    for d in ("logs", "Q", "rmfiles"):
        canon_d = canon_sub / d
        para_d = para_sub / d
        para_d.mkdir(exist_ok=True)
        if canon_d.is_dir():
            for entry in canon_d.iterdir():
                target = para_d / entry.name
                if target.exists() or target.is_symlink():
                    continue
                target.symlink_to(entry.resolve())

    # subject_lists/{sub}.cfg: copy with rewritten BASEDIR. Scanlist symlinked.
    sl_dst = para_sub / "subject_lists"
    sl_dst.mkdir(exist_ok=True)
    cfg_src = canon_sub / "subject_lists" / f"{sub}.cfg"
    cfg_dst = sl_dst / f"{sub}.cfg"
    canonical_basedir_line = f"BASEDIR={canon}"
    parallel_basedir_line = f"BASEDIR={para}"
    cfg_text = cfg_src.read_text()
    if canonical_basedir_line not in cfg_text:
        raise RuntimeError(
            f'Could not find "{canonical_basedir_line}" in {cfg_src} — '
            f"cfg uses a different basedir format than expected."
        )
    cfg_dst.write_text(cfg_text.replace(canonical_basedir_line, parallel_basedir_line))

    scanlist_src = canon_sub / "subject_lists" / f"scanlist_{sub}.csv"
    scanlist_dst = sl_dst / f"scanlist_{sub}.csv"
    if not scanlist_dst.exists() and not scanlist_dst.is_symlink():
        scanlist_dst.symlink_to(scanlist_src.resolve())

    # NAT/{sess}/{TASK_BLD}/: real dirs, symlink each input file (and the mc.mat
    # subdir) from canonical. combine/filter outputs (new filenames) land in the
    # real parallel dirs alongside the symlinked inputs.
    #
    # Filter out any stale combine/filter outputs that may exist in the canonical
    # tree (e.g., partial files from a prior crashed run). If we symlinked them,
    # the parallel run's --overwrite would write through the symlink and clobber
    # the canonical tree (colliding with any in-flight canonical job).
    output_substrings = (
        "_mc_unwarp_anat",  # combine T1/MNI/mean-warped BOLD
        "_T1_e",  # per-echo T1-space subdirs (e.g. 005_T1_e1)
        "_MNI_e",  # per-echo MNI-space subdirs
        "_resid",  # filter nuisance/wholebrain residuals (+ _resid_bpss)
        "tedana",  # tedana intermediates
    )

    def is_combine_filter_output(name: str) -> bool:
        return any(s in name for s in output_substrings)

    canon_nat = canon_sub / "NAT"
    para_nat = para_sub / "NAT"
    n_scans = 0
    n_links = 0
    n_skipped_outputs = 0
    for sess_dir in sorted(canon_nat.iterdir()):
        if not sess_dir.is_dir():
            continue
        para_sess = para_nat / sess_dir.name
        para_sess.mkdir(parents=True, exist_ok=True)
        for scan_dir in sorted(sess_dir.iterdir()):
            if not scan_dir.is_dir():
                continue
            para_scan = para_sess / scan_dir.name
            para_scan.mkdir(exist_ok=True)
            for entry in scan_dir.iterdir():
                if is_combine_filter_output(entry.name):
                    n_skipped_outputs += 1
                    continue
                para_entry = para_scan / entry.name
                if para_entry.exists() or para_entry.is_symlink():
                    continue
                # Symlink both files and the mc.mat subdir; combine/filter only
                # READ from these (write to the parent dir with new names).
                para_entry.symlink_to(entry.resolve())
                n_links += 1
            n_scans += 1
    logger.info(
        "Mirrored %d scan dirs (%d input symlinks, %d stale outputs skipped)",
        n_scans,
        n_links,
        n_skipped_outputs,
    )


def submit_iproc(
    parallel_root: Path,
    sub: str,
    code_dir: Path,
    sif: Path,
    stage: str,
    mem: str,
    cpus: int,
    time: str,
    bids_root: Path,
    dependency: str | None = None,
) -> str:
    sdir = Path(parallel_root) / "mri_data" / sub
    cfg = sdir / "subject_lists" / f"{sub}.cfg"
    logdir = sdir / "logs"

    bind = (
        "/oak:/oak,/scratch:/scratch,"
        f"{code_dir}/container/imagemagick-policy.xml:/etc/ImageMagick-6/policy.xml:ro,"
        f"{code_dir}/container/flirt_wrapper.sh:/opt/fsl-5.0.10/bin/flirt:ro,"
        f"{code_dir}/container/flirt.real:/opt/.fsl_orig/flirt:ro,"
        f"{code_dir}/container/convert_xfm_wrapper.sh:/opt/fsl-5.0.10/bin/convert_xfm:ro,"
        f"{code_dir}/container/convert_xfm.real:/opt/.fsl_orig/convert_xfm:ro"
    )
    inner = (
        "set -e && "
        "source /opt/iproc-venv/bin/activate && "
        "export FREESURFER_HOME=/opt/freesurfer-6.0.0 && "
        "source /opt/freesurfer-6.0.0/SetUpFreeSurfer.sh && "
        f"cd {code_dir} && "
        "pip install -e . 2>&1 | tail -1 && "
        f"python iProc.py -c {cfg} -s {stage} "
        f"--bids {bids_root}/sub-{sub} "
        "--executor local --overwrite"
    )
    wrap = f"apptainer exec --bind {bind} {sif} bash -c '{inner}'"

    sbatch_args = [
        "sbatch",
        "--parsable",
        "--job-name",
        f"iproc_par_{stage}_{sub}",
        "--partition",
        "russpold",
        "--time",
        time,
        "--mem",
        mem,
        "--cpus-per-task",
        str(cpus),
        "--output",
        str(logdir / f"slurm_{stage}_par_%j.log"),
        "--error",
        str(logdir / f"slurm_{stage}_par_%j.err"),
    ]
    if dependency is not None:
        sbatch_args.extend(["--dependency", f"afterok:{dependency}"])
    sbatch_args.extend(["--wrap", wrap])

    result = subprocess.run(sbatch_args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sub", required=True, help="Subject label (e.g., s10)")
    p.add_argument(
        "--canonical-root",
        type=Path,
        required=True,
        help="Canonical iProc deriv root (the one with the current outputs)",
    )
    p.add_argument(
        "--parallel-root",
        type=Path,
        required=True,
        help="New parallel root where mirrored tree + new outputs land",
    )
    p.add_argument("--code-dir", type=Path, default=Path("/scratch/users/logben/iProc"))
    p.add_argument(
        "--sif", type=Path, default=Path("/scratch/users/logben/iProc/container/iproc.sif")
    )
    p.add_argument("--bids-root", type=Path, default=Path("/scratch/users/logben/discovery_bids"))
    p.add_argument(
        "--cpus",
        type=int,
        default=32,
        help="CPUs per stage (russpold sh03-06* nodes have 32 CPU / 256 GB)",
    )
    p.add_argument("--mem", default="192G")
    p.add_argument("--combine-time", default="12:00:00")
    p.add_argument("--filter-time", default="08:00:00")
    p.add_argument(
        "--mirror-only", action="store_true", help="Set up the parallel tree but do not submit jobs"
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    logger.info("Mirroring %s -> %s for sub-%s", args.canonical_root, args.parallel_root, args.sub)
    mirror_iproc_subject(args.canonical_root, args.parallel_root, args.sub)
    logger.info("Mirror complete")

    if args.mirror_only:
        logger.info("--mirror-only set; skipping job submission")
        return 0

    logger.info("Submitting combine + filter on russpold (%d CPU, %s)", args.cpus, args.mem)
    j1 = submit_iproc(
        args.parallel_root,
        args.sub,
        args.code_dir,
        args.sif,
        stage="combine_and_apply_warp",
        mem=args.mem,
        cpus=args.cpus,
        time=args.combine_time,
        bids_root=args.bids_root,
    )
    logger.info("combine: %s", j1)
    j2 = submit_iproc(
        args.parallel_root,
        args.sub,
        args.code_dir,
        args.sif,
        stage="filter_and_project",
        mem=args.mem,
        cpus=args.cpus,
        time=args.filter_time,
        bids_root=args.bids_root,
        dependency=j1,
    )
    logger.info("filter_and_project: %s (afterok:%s)", j2, j1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
