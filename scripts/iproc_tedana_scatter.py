"""Scatter the multi-echo tedana denoising stage (run_tedana.py): one SLURM job per
scan per space.

WHY THIS EXISTS: iProc registers only three stages (unwarp / combine_and_apply_warp /
filter_and_project) but ships tedana as STANDALONE drivers (run_tedana.py,
tedana_loop.py). tedana sits BETWEEN combine and filter: combine produces the three
spatially-normalised echoes (MNI111 + NAT111), tedana ICA-denoises them into
tedana/{ses}_bld{run}_desc-denoised_bold.nii.gz, and bandpass_ME (filter stage)
consumes that. The combine->filter scatter therefore skipped a required stage; this
driver fills the gap.

ZERO SCIENTIFIC DIVERGENCE: the UNMODIFIED run_tedana.py runs inside each job. This
driver only chooses which (scan, space) a job handles and submits idempotently. Each
run_tedana invocation reads only its own scan's echoes + JSON echo-times and writes
only its own tedana/ dir, so jobs are per-(scan,space) disjoint and race-free.

CALIBRATION (s10 ses-01 FLANKER 009, MNI, 1mm pilot job 26893565): 1h25m wall,
110 GB peak RSS. --mem 120G packs two jobs on a 256 GB russpold node; --time 4:00:00
gives ~3x headroom.

The 57 task scans are read from the combine scatter's units_manifest.tsv; each is run
in BOTH spaces (NAT + MNI), matching tedana_loop.py, because filter's bandpass_ME runs
for MNI111 and NAT111 and each reads its own space's denoised bold. -> 114 jobs.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

JOBPREFIX = "iproc_ted"
SPACES = ("MNI", "NAT")
_LABEL_RE = re.compile(r"ses-(\d+)_(.+)_(\d+)$")


def _load_units(manifest: Path):
    """Return [(label, ses, task, bld_int)] for every task scan in the manifest."""
    units = []
    with manifest.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            m = _LABEL_RE.match(row["label"])
            if not m:
                continue
            ses, task, bld = m.group(1), m.group(2), int(m.group(3))
            units.append((row["label"], ses, task, bld))
    return units


def _denoised_path(canon, sub, space, ses, task, bld):
    return (
        Path(canon)
        / "mri_data"
        / sub
        / f"{space}111"
        / ses
        / f"{task}_{bld:03d}"
        / "tedana"
        / f"{ses}_bld{bld:03d}_desc-denoised_bold.nii.gz"
    )


def _done(canon, sub, space, ses, task, bld):
    return _denoised_path(canon, sub, space, ses, task, bld).exists()


def _active(sub):
    """{label_space} for jobs currently queued/running under this prefix."""
    out = subprocess.run(
        ["squeue", "-u", sub_user(), "-h", "-o", "%j"], capture_output=True, text=True
    ).stdout
    return {ln[len(JOBPREFIX) + 1 :] for ln in out.split() if ln.startswith(JOBPREFIX + "_")}


def sub_user():
    import getpass

    return getpass.getuser()


def _container_cmd(args, ses, task, bld, space):
    bld3 = f"{int(bld):03d}"
    outdir = f"{args.canonical_root}/mri_data/{args.sub}/{space}111/{ses}/" f"{task}_{bld3}/tedana"
    denoised = f"{outdir}/{ses}_bld{bld3}_desc-denoised_bold.nii.gz"
    # run_tedana.py no-ops if the tedana/ dir already exists. A dir WITHOUT the
    # denoised file is a partial remnant from an OOM/timeout-killed attempt;
    # remove it (this unit's own dir only) so a retry recomputes instead of
    # silently skipping and producing no output.
    inner = (
        "set -e && "
        f'if [ -d "{outdir}" ] && [ ! -f "{denoised}" ]; then '
        f'echo "removing partial tedana dir: {outdir}"; rm -rf "{outdir}"; fi && '
        "source /opt/iproc-venv/bin/activate && "
        f"cd {args.code_dir} && "
        f"python run_tedana.py --sub {args.sub} --ses {ses} --task {task} "
        f"--run {bld} --mridatadir {args.canonical_root}/mri_data "
        f"--outname tedana --space {space} --resolution {args.resolution}"
    )
    return f"apptainer exec --bind /oak:/oak,/scratch:/scratch {args.sif} " f"bash -c '{inner}'"


def _inflight_count(sub: str, space: str) -> int:
    """Number of per-job tedana jobs currently queued/running for this space
    (excludes the array jobs). Used to honour a partition's MaxSubmit cap.
    (Queries by the OS username, not the imaging subject id.)"""
    out = subprocess.run(
        ["squeue", "-u", sub_user(), "-h", "-o", "%j"], capture_output=True, text=True
    ).stdout
    return sum(
        1
        for ln in out.split()
        if ln.startswith(JOBPREFIX + "_")
        and ln.endswith("_" + space)
        and not ln.startswith(JOBPREFIX + "_array")
    )


def _submit_one(args, label, ses, task, bld, space, logdir: Path):
    logdir.mkdir(parents=True, exist_ok=True)
    name = f"{JOBPREFIX}_{label}_{space}"
    sb = [
        "sbatch",
        "--parsable",
        "--job-name",
        name,
        "--partition",
        args.partition,
        "--time",
        args.time,
        "--mem",
        args.mem,
        "--cpus-per-task",
        str(args.cpus),
        "--output",
        str(logdir / f"slurm_teda_{space}_%j.log"),
        "--error",
        str(logdir / f"slurm_teda_{space}_%j.err"),
        "--wrap",
        _container_cmd(args, ses, task, bld, space),
    ]
    r = subprocess.run(sb, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def cmd_list(args):
    units = _load_units(Path(args.scatter_root) / "units_manifest.tsv")
    done = pending = 0
    for label, ses, task, bld in units:
        for space in SPACES:
            if _done(args.canonical_root, args.sub, space, ses, task, bld):
                done += 1
            else:
                pending += 1
                log.info("PENDING %s %s", label, space)
    log.info(
        "%d scans x %d spaces = %d units: %d done, %d pending",
        len(units),
        len(SPACES),
        len(units) * len(SPACES),
        done,
        pending,
    )
    return 0


def cmd_submit_array(args):
    """Submit all PENDING units as ONE throttled SLURM array (--array=0-N%throttle),
    capping concurrent jobs so the shared partition is not fully soaked. A generated
    runner reads each array task's (scan, space) from a params file and skips units
    whose denoised output already exists (idempotent: re-run picks up only what's left)."""
    units = _load_units(Path(args.scatter_root) / "units_manifest.tsv")
    spaces = (args.space,) if args.space else SPACES
    pending = []
    for label, ses, task, bld in units:
        for space in spaces:
            if not _done(args.canonical_root, args.sub, space, ses, task, bld):
                pending.append((ses, task, str(bld), space, label))
    if not pending:
        log.info("nothing pending for spaces=%s: all done.", spaces)
        return 0

    # Tag params/runner/logs/job-name by space so a per-space array does not
    # clobber a concurrently-running array of the other space (the runner reads
    # its params file by SLURM_ARRAY_TASK_ID at run time).
    tag = args.space if args.space else "all"
    scatter = Path(args.scatter_root)
    (scatter / "logs").mkdir(parents=True, exist_ok=True)
    params = scatter / f"tedana_array_units_{tag}.tsv"
    params.write_text("\n".join("\t".join(p) for p in pending) + "\n")

    runner = scatter / f"tedana_array_runner_{tag}.sh"
    runner.write_text(f"""#!/bin/bash
set -euo pipefail
PARAMS="{params}"
line=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$PARAMS")
ses=$(echo "$line"  | cut -f1)
task=$(echo "$line" | cut -f2)
bld=$(echo "$line"  | cut -f3)
space=$(echo "$line" | cut -f4)
label=$(echo "$line" | cut -f5)
bld3=$(printf '%03d' "$bld")
denoised="{args.canonical_root}/mri_data/{args.sub}/${{space}}111/${{ses}}/${{task}}_${{bld3}}/tedana/${{ses}}_bld${{bld3}}_desc-denoised_bold.nii.gz"
if [ -f "$denoised" ]; then echo "skip (already done): $label $space"; exit 0; fi
echo "=== tedana $label $space (ses=$ses task=$task run=$bld) ==="
apptainer exec --bind /oak:/oak,/scratch:/scratch {args.sif} bash -c \\
  "set -e && source /opt/iproc-venv/bin/activate && cd {args.code_dir} && \\
   python run_tedana.py --sub {args.sub} --ses $ses --task $task --run $bld \\
   --mridatadir {args.canonical_root}/mri_data --outname tedana --space $space \\
   --resolution {args.resolution}"
""")
    runner.chmod(0o755)

    n = len(pending)
    sb = [
        "sbatch",
        "--parsable",
        "--job-name",
        f"{JOBPREFIX}_array_{tag}",
        "--array",
        f"0-{n - 1}%{args.throttle}",
        "--partition",
        args.partition,
        "--time",
        args.time,
        "--mem",
        args.mem,
        "--cpus-per-task",
        str(args.cpus),
        "--output",
        str(scatter / "logs" / f"tedana_array_{tag}_%A_%a.log"),
        "--error",
        str(scatter / "logs" / f"tedana_array_{tag}_%A_%a.err"),
        "--wrap",
        f"bash {runner}",
    ]
    r = subprocess.run(sb, capture_output=True, text=True, check=True)
    log.info(
        "submitted tedana array: %d pending units, throttle %%%d, job %s",
        n,
        args.throttle,
        r.stdout.strip(),
    )
    log.info("params: %s", params)
    return 0


def cmd_submit(args):
    units = _load_units(Path(args.scatter_root) / "units_manifest.tsv")
    active = _active(args.sub)
    logroot = Path(args.scatter_root) / "logs"
    spaces = (args.space,) if args.space else SPACES
    only = args.scan
    # Optional in-flight cap (e.g. bigmem MaxSubmitPU=10): only top up to the cap.
    budget = None
    if args.max_inflight is not None:
        if len(spaces) != 1:
            raise SystemExit("--max-inflight requires a single --space")
        budget = max(0, args.max_inflight - _inflight_count(args.sub, spaces[0]))
        log.info("in-flight cap: %d slots free (max %d)", budget, args.max_inflight)
    submitted = skip_done = skip_active = 0
    for label, ses, task, bld in units:
        if only and label != only and not label.endswith(only.replace("/", "_")):
            continue
        for space in spaces:
            key = f"{label}_{space}"
            if _done(args.canonical_root, args.sub, space, ses, task, bld):
                skip_done += 1
                continue
            if key in active:
                skip_active += 1
                continue
            if budget is not None and budget <= 0:
                continue
            try:
                jid = _submit_one(args, label, ses, task, bld, space, logroot / label)
            except subprocess.CalledProcessError as exc:
                # Most likely the partition's MaxSubmit cap (e.g. bigmem PU=10) was
                # hit (e.g. after a transient squeue undercount). Stop submitting
                # this cycle; the controller retries next pass once slots free.
                err = (exc.stderr or "").strip().splitlines()
                log.warning(
                    "sbatch rejected (%s); stopping this submit cycle.", err[-1] if err else exc
                )
                log.info(
                    "tedana: submitted %d before cap, skipped %d (done) + %d (active).",
                    submitted,
                    skip_done,
                    skip_active,
                )
                return 0
            submitted += 1
            if budget is not None:
                budget -= 1
            log.info("submitted %-34s mem=%s job %s", key, args.mem, jid)
    log.info(
        "tedana: submitted %d, skipped %d (done) + %d (active).", submitted, skip_done, skip_active
    )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["list", "submit", "submit-array"])
    p.add_argument("scan", nargs="?", help="optional single unit label (e.g. ses-01_FLANKER_009)")
    p.add_argument("--space", choices=SPACES, help="restrict to one space")
    p.add_argument("--sub", default="s10")
    p.add_argument(
        "--canonical-root", default="/scratch/users/logben/discovery_bids/derivatives/iproc"
    )
    p.add_argument(
        "--scatter-root",
        default="/scratch/users/logben/discovery_bids/derivatives/iproc/scatter_combine_s10",
    )
    p.add_argument("--code-dir", default="/scratch/users/logben/iProc")
    p.add_argument("--sif", default="/scratch/users/logben/iProc/container/iproc.sif")
    p.add_argument("--resolution", default="111")
    p.add_argument("--partition", default="russpold")
    p.add_argument("--cpus", type=int, default=8)
    p.add_argument("--mem", default="120G")
    p.add_argument("--time", default="04:00:00")
    p.add_argument(
        "--throttle", type=int, default=12, help="max concurrent array tasks (submit-array mode)"
    )
    p.add_argument(
        "--max-inflight",
        type=int,
        default=None,
        help="submit mode: cap total queued/running jobs for the "
        "space at this number (honour partition MaxSubmit, e.g. "
        "bigmem PU=10). Requires a single --space.",
    )
    args = p.parse_args(argv)
    return {"list": cmd_list, "submit": cmd_submit, "submit-array": cmd_submit_array}[args.mode](
        args
    )


if __name__ == "__main__":
    sys.exit(main())
