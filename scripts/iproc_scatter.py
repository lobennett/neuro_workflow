"""Scatter an iProc per-scan stage (combine_and_apply_warp OR filter_and_project)
across one SLURM job per task scan (option B). Generalizes iproc_scatter_combine.py.

WHY: both stages run serially under --executor local (~1 sub-job/hour) and are
embarrassingly parallel across scans. This driver scopes each task scan into its own
single-scan scanlist + cfg and submits one SLURM job per scan, all writing to the
SHARED canonical iProc tree. Outputs are per-scan disjoint; the UNMODIFIED iProc.py
runs in each job (scanlist scoping changes WHICH scan runs, not HOW), so there is zero
scientific divergence.

STAGE-AGNOSTIC design (verified for both stages by reading iProc internals):
  * main() (iProc.py:1290) does an UNCONDITIONAL
    `scan_by_session[MIDVOL_SESS].bold_scans[MIDVOL_BOLDNO]['TYPE']` for EVERY stage,
    so every scoped scanlist must contain the ses-01 midvol bold (FLANKER bld009) +
    ses-01 FMAP, else KeyError: '01'. (combine dry-run confirmed this.)
  * The midvol scan is Analyze=1 => combine/filter would process it in every job.
    Avoided by a WAVE-1 unit that processes it ONCE; WAVE-2 jobs include its row but
    skip it via _outfiles_skip (per-scan, per-stage existing-output check).
  * Under --executor local neither stage writes a shared rmfile dump (save.p is
    slurm-only; combine/filter never call _set_rmfiles; load_rmfile_dump only reads
    unwarp_motioncorrect_align.final). Per-scan outputs land in disjoint
    {NAT,MNI}_RESAMP/sess/task and FS6/sess/task dirs; intermediates in unique mktemp.
  * Shared-state hazards are neutralized: per-job LOGDIR (avoids the
    iproc_{sub}_01_{HHMMSS} log + csv_cfg_archive same-second makedirs collision);
    the dilated brainmask (combine) and the fsaverage6 symlink (filter) already
    exist, so no concurrent creation race.

STAGE specifics:
  combine_and_apply_warp: SKIP size_brainmask + all QC/fslmerge steps (cross-scan,
    racy); keep combine_warps_{parallel,post}_{anat,mni}. Reads unwarp outputs.
  filter_and_project:     NO steps to SKIP (calculate_nuisance_params, nuisance_regress
    + bandpass + wholebrain_only_regress for MNI & NAT, fs6_project_to_surface -- all
    per-scan). Reads each scan's COMBINE output (NAT_RESAMP _mc_unwarp_anat), so it
    must run AFTER that scan's combine. Final output: FS6/sess/task surface giftis.

The SAME generated scanlists/cfgs/cluster_requests serve both stages (the combine-QC
SKIPs are irrelevant to filter). Only --stage, memory, precondition, and job-name
prefix differ.

Modes:
  generate           -- write scoped scanlists + cfgs + scatter cluster_requests
  validate SCAN      -- container --dry-run on one scoped cfg for --stage
  submit-pilot SCAN  -- sbatch ONE scoped job for --stage (verify before the rest)
  submit-rest        -- sbatch all WAVE-2 jobs for --stage. For filter, --pipeline
                        makes each job afterok its matching combine job (iproc_sc_<label>)
                        if still queued -- overlapping filter behind combine per-scan.
Never cancels other jobs.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import glob
import logging
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

SCHEMA_HEADER = (
    "SUBJID,SESSION_ID,Analyze,BLD,TYPE,ANAT,FMAP_MAG,FMAP_PHASE,"
    "FMAP_AP,FMAP_PA,T2,T2_SESSION_ID"
)

# combine_and_apply_warp: flip these to SKIP (size_brainmask + all QC/merge).
COMBINE_SKIP_STEPS = {
    "size_brainmask",
    "fslmerge_meantime_anat_mean",
    "anat_mean_qc",
    "fslmerge_meantime_anat_midvols",
    "anat_midvols_qc",
    "fslmerge_meantime_mni_mean",
    "mni_mean_qc",
    "fslmerge_meantime_mni_midvols",
    "mni_midvols_qc",
}

STAGE_CFG = {
    "combine_and_apply_warp": {
        "jobprefix": "iproc_sc",
        "skip_steps": COMBINE_SKIP_STEPS,
        # combine mem (calibrated: pilot 253 vols hit 48G; tiers have headroom)
        "mem_tiers": [(200, "48G"), (350, "80G"), (520, "128G"), (10**9, "192G")],
    },
    "filter_and_project": {
        "jobprefix": "iproc_fp",
        "skip_steps": set(),  # filter has no QC/cross-scan steps; all run per-scan
        # filter mem (NO empirical data yet -> generous; calibrate after a filter pilot.
        # nuisance regress + AFNI bandpass load the full 4D residual + design.)
        "mem_tiers": [(200, "96G"), (350, "128G"), (520, "192G"), (10**9, "240G")],
    },
}


def parse_scanlist(path: Path):
    text = path.read_text().splitlines()
    cols = text[0].split(",")
    rows = [dict(zip(cols, ln.split(","))) for ln in text[1:] if ln.strip()]
    return text[0], rows


def row_to_line(row):
    return ",".join(row[c] for c in SCHEMA_HEADER.split(","))


def target_nvols(canonical_root, sub, bold_row):
    sess, task = bold_row["SESSION_ID"], bold_row["TYPE"]
    bld = f"{int(bold_row['BLD']):03d}"
    par = (
        Path(canonical_root)
        / "mri_data"
        / sub
        / "NAT"
        / sess
        / f"{task}_{bld}"
        / f"{sess}_bld{bld}_reorient_skip_mc_e1.par"
    )
    return sum(1 for _ in par.open()) if par.exists() else None


def mem_for(nvols, stage):
    tiers = STAGE_CFG[stage]["mem_tiers"]
    if nvols is None:
        return tiers[-2][1]
    for cap, mem in tiers:
        if nvols <= cap:
            return mem
    return tiers[-1][1]


def build_units(rows, midvol_sess, midvol_boldno):
    """One unit per task scan (57). Each non-midvol unit injects the ses-01 midvol
    bold + ses-01 FMAP (for main():1290). The midvol scan is its own WAVE-1 unit."""
    by_sess = {}
    for r in rows:
        by_sess.setdefault(r["SESSION_ID"], []).append(r)
    mv_rows = by_sess[midvol_sess]
    mv_fmap = [r for r in mv_rows if r["TYPE"] == "FMAP"]
    mv_bold = next(
        r
        for r in mv_rows
        if r["TYPE"] not in ("FMAP", "ANAT") and int(r["BLD"]) == int(midvol_boldno)
    )
    mv_label = f"ses-{midvol_sess}_{mv_bold['TYPE']}_{int(mv_bold['BLD']):03d}"

    units = []
    for sess in sorted(by_sess):
        fmap_rows = [r for r in by_sess[sess] if r["TYPE"] == "FMAP"]
        bold_rows = [
            r for r in by_sess[sess] if r["TYPE"] not in ("FMAP", "ANAT") and r["Analyze"] == "1"
        ]
        for b in bold_rows:
            label = f"ses-{sess}_{b['TYPE']}_{int(b['BLD']):03d}"
            if label == mv_label:
                units.append(
                    {
                        "label": label,
                        "session": sess,
                        "bold_rows": [b],
                        "fmap_rows": fmap_rows,
                        "is_wave1": True,
                    }
                )
            else:
                # Always include the midvol bold (FLANKER009): main():1290 looks it up
                # unconditionally AND, when the target IS in the midvol session, the
                # midvol validation (csvHandler) requires MIDVOL_BOLDNO present in that
                # session's bold_scans. (Earlier bug: ses-01 non-FLANKER targets omitted
                # it -> "CSVs have errors".) It is skipped at run time by _outfiles_skip.
                brows, frows = [b], list(fmap_rows)
                if sess != midvol_sess:
                    brows += [mv_bold]  # different session -> add midvol bold + its fmap
                    frows += mv_fmap
                else:
                    brows += [
                        mv_bold
                    ]  # same (midvol) session -> add midvol bold; fmap already present
                units.append(
                    {
                        "label": label,
                        "session": sess,
                        "bold_rows": brows,
                        "fmap_rows": frows,
                        "is_wave1": False,
                    }
                )
    return units


def write_scatter_cluster_requests(orig: Path, dest: Path, skip_steps):
    lines = orig.read_text().splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        if parts[0] in skip_steps:
            parts[1] = "SKIP"
        out.append(",".join(parts))
    dest.write_text("\n".join(out) + "\n")


def write_scoped_cfg(orig_cfg, dest_cfg, scanlist, cluster_requests, logdir):
    out = []
    for line in orig_cfg.read_text().splitlines():
        s = line.strip()
        if s.startswith("SCANLIST="):
            out.append(f"SCANLIST={scanlist}")
        elif s.startswith("CLUSTER_REQUESTS="):
            out.append(f"CLUSTER_REQUESTS={cluster_requests}")
        elif s.startswith("LOGDIR="):
            out.append(f"LOGDIR={logdir}")
        else:
            out.append(line)
    dest_cfg.write_text("\n".join(out) + "\n")


def cmd_generate(args):
    canon = Path(args.canonical_root)
    sl_dir = canon / "mri_data" / args.sub / "subject_lists"
    orig_cfg = sl_dir / f"{args.sub}.cfg"
    scatter = Path(args.scatter_root)
    for d in ("scanlists", "cfgs", "logs"):
        (scatter / d).mkdir(parents=True, exist_ok=True)

    # scatter cluster_requests: combine's QC SKIPs are a safe superset for both stages
    scatter_cr = scatter / "cluster_requests_scatter.csv"
    write_scatter_cluster_requests(
        canon / "configs" / "cluster_requests.csv", scatter_cr, COMBINE_SKIP_STEPS
    )

    _, rows = parse_scanlist(sl_dir / f"scanlist_{args.sub}.csv")
    units = build_units(rows, args.midvol_sess, args.midvol_boldno)
    manifest = []
    for u in units:
        sl = scatter / "scanlists" / f'scanlist_{args.sub}_{u["label"]}.csv'
        sl.write_text(
            "\n".join(
                [SCHEMA_HEADER]
                + [row_to_line(r) for r in u["bold_rows"]]
                + [row_to_line(r) for r in u["fmap_rows"]]
            )
            + "\n"
        )
        jobdir = scatter / "logs" / u["label"]
        jobdir.mkdir(parents=True, exist_ok=True)
        cfg = scatter / "cfgs" / f'{args.sub}_{u["label"]}.cfg'
        write_scoped_cfg(orig_cfg, cfg, sl, scatter_cr, jobdir)
        nvols = target_nvols(canon, args.sub, u["bold_rows"][0])
        manifest.append(
            {
                "label": u["label"],
                "session": u["session"],
                "wave": 1 if u["is_wave1"] else 2,
                "target_nvols": nvols if nvols is not None else "",
                "cfg": str(cfg),
                "scanlist": str(sl),
                "logdir": str(jobdir),
            }
        )
    mpath = scatter / "units_manifest.tsv"
    with mpath.open("w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["label", "session", "wave", "target_nvols", "cfg", "scanlist", "logdir"],
            delimiter="\t",
        )
        w.writeheader()
        w.writerows(manifest)
    log.info("Wrote %d units (stage-agnostic) to %s", len(manifest), mpath)
    log.info("WAVE 1 (midvol): %s", [m["label"] for m in manifest if m["wave"] == 1])
    return 0


def _container_cmd(args, cfg, stage):
    cd = args.code_dir
    bind = (
        "/oak:/oak,/scratch:/scratch,"
        f"{cd}/container/imagemagick-policy.xml:/etc/ImageMagick-6/policy.xml:ro,"
        f"{cd}/container/flirt_wrapper.sh:/opt/fsl-5.0.10/bin/flirt:ro,"
        f"{cd}/container/flirt.real:/opt/.fsl_orig/flirt:ro,"
        f"{cd}/container/convert_xfm_wrapper.sh:/opt/fsl-5.0.10/bin/convert_xfm:ro,"
        f"{cd}/container/convert_xfm.real:/opt/.fsl_orig/convert_xfm:ro"
    )
    extra = "--dry-run" if getattr(args, "_dry", False) else ""
    inner = (
        "set -e && source /opt/iproc-venv/bin/activate && "
        "export FREESURFER_HOME=/opt/freesurfer-6.0.0 && "
        "source /opt/freesurfer-6.0.0/SetUpFreeSurfer.sh && "
        f"cd {cd} && pip install -e . 2>&1 | tail -1 && "
        f"python iProc.py -c {cfg} -s {stage} --bids {args.bids_root}/sub-{args.sub} "
        f"--executor local --no-remove-files {extra}"
    )
    return f"apptainer exec --bind {bind} {args.sif} bash -c '{inner}'"


def _load_units(scatter):
    with (Path(scatter) / "units_manifest.tsv").open() as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _submit_one(unit, args, dependency=None):
    jobdir = Path(unit["logdir"])
    mem = mem_for(int(unit["target_nvols"]) if unit["target_nvols"] else None, args.stage)
    pfx = STAGE_CFG[args.stage]["jobprefix"]
    sb = [
        "sbatch",
        "--parsable",
        "--job-name",
        f'{pfx}_{unit["label"]}',
        "--partition",
        args.partition,
        "--time",
        args.time,
        "--mem",
        mem,
        "--cpus-per-task",
        str(args.cpus),
        "--output",
        str(jobdir / f"slurm_{args.stage[:4]}_%j.log"),
        "--error",
        str(jobdir / f"slurm_{args.stage[:4]}_%j.err"),
    ]
    if dependency:
        sb += ["--dependency", f"afterok:{dependency}"]
    sb += ["--wrap", _container_cmd(args, unit["cfg"], args.stage)]
    r = subprocess.run(sb, capture_output=True, text=True, check=True)
    return r.stdout.strip(), mem


def cmd_validate(args):
    units = _load_units(args.scatter_root)
    m = next(
        (
            u
            for u in units
            if u["label"] == args.scan or u["label"].endswith(args.scan.replace("/", "_"))
        ),
        None,
    )
    if not m:
        log.error("no unit matches %s", args.scan)
        return 2
    args._dry = True
    wrap = _container_cmd(args, m["cfg"], args.stage)
    res = subprocess.run(wrap, shell=True, capture_output=True, text=True, timeout=900)
    planned = sorted(set(re.findall(r"NAT/[0-9]+/[A-Z]+_[0-9]+", res.stdout + res.stderr)))
    log.info("[%s] %s rc=%s planned=%s", args.stage, m["label"], res.returncode, planned)
    tail = (res.stdout + res.stderr).splitlines()[-12:]
    log.info("--- tail ---\n%s", "\n".join(tail))
    return 0


def _midvol_done(args):
    """Stage-aware: has the midvol (ses-01 FLANKER009) produced this stage's outputs?
    So WAVE-2 jobs skip it via _outfiles_skip. Globs are robust to dir-name details."""
    base = Path(args.canonical_root) / "mri_data" / args.sub
    if args.stage == "combine_and_apply_warp":
        need = list(
            (base / "NAT111" / args.midvol_sess).glob("FLANKER_*/*_mc_unwarp_anat_e?.nii.gz")
        ) + list((base / "MNI111" / args.midvol_sess).glob("FLANKER_*/*_mni_e?.nii.gz"))
        return len(need) >= 6, need
    # filter_and_project: final fsaverage6 surface giftis for the midvol scan
    # match both single-echo (*resid_bpss*) and multi-echo (*tedana_bpss*) naming
    surf = list(base.glob(f"**/{args.midvol_sess}/FLANKER_*/lh.*bpss_fsaverage6_sm*.nii.gz"))
    return len(surf) >= 1, surf


def _combine_jobid_for(label):
    """Live SLURM job id of the matching combine job (iproc_sc_<label>), if queued."""
    out = subprocess.run(
        ["squeue", "-u", getpass.getuser(), "-h", "-o", "%i %j"], capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        jid, _, name = line.strip().partition(" ")
        if name == f"iproc_sc_{label}":
            return jid
    return None


def _active_labels(stage):
    """Labels with a queued/running job for this stage (for idempotent re-submit)."""
    pfx = STAGE_CFG[stage]["jobprefix"]
    out = subprocess.run(
        ["squeue", "-u", getpass.getuser(), "-h", "-o", "%j"], capture_output=True, text=True
    ).stdout
    return {ln[len(pfx) + 1 :] for ln in out.split() if ln.startswith(pfx + "_")}


def _unit_done(unit, args):
    """True if this stage's per-scan outputs for the unit's TARGET already exist."""
    base = Path(args.canonical_root) / "mri_data" / args.sub
    label = unit["label"]  # ses-NN_TASK_BBB
    m = re.match(r"ses-(\d+)_(.+)_(\d+)$", label)
    if not m:
        return False
    sess, task, bld = m.group(1), m.group(2), f"{int(m.group(3)):03d}"
    if args.stage == "combine_and_apply_warp":
        anat = list((base / "NAT111" / sess / f"{task}_{bld}").glob("*_mc_unwarp_anat_e?.nii.gz"))
        mni = list((base / "MNI111" / sess / f"{task}_{bld}").glob("*_mni_e?.nii.gz"))
        return len(anat) >= 3 and len(mni) >= 3
    surf = list(base.glob(f"**/{sess}/{task}_{bld}/lh.*bpss_fsaverage6_sm*.nii.gz"))
    return len(surf) >= 1


def cmd_submit_pilot(args):
    units = _load_units(args.scatter_root)
    m = next(
        (
            u
            for u in units
            if u["label"] == args.scan or u["label"].endswith(args.scan.replace("/", "_"))
        ),
        None,
    )
    if not m:
        log.error("no unit matches %s", args.scan)
        return 2
    jid, mem = _submit_one(m, args)
    log.info("PILOT [%s] %s mem=%s job %s", args.stage, m["label"], mem, jid)
    return 0


def cmd_submit_rest(args):
    ok, found = _midvol_done(args)
    if not ok:
        log.error(
            "[%s] midvol (FLANKER009) outputs not present (%d found); run the "
            "wave-1 pilot for this stage first.",
            args.stage,
            len(found),
        )
        return 2
    log.info("[%s] midvol outputs present -> wave-2 jobs will skip FLANKER009.", args.stage)
    active = _active_labels(args.stage)  # idempotent: don't double-submit
    units = _load_units(args.scatter_root)
    submitted = skipped_active = skipped_done = 0
    for u in units:
        if int(u["wave"]) == 1:
            continue
        if u["label"] in active:
            skipped_active += 1
            continue
        if _unit_done(u, args):
            skipped_done += 1
            continue
        dep = None
        if args.pipeline and args.stage == "filter_and_project":
            dep = _combine_jobid_for(u["label"])  # afterok matching combine job if live
        jid, mem = _submit_one(u, args, dependency=dep)
        submitted += 1
        log.info(
            "submitted %-42s mem=%-5s job %s%s",
            u["label"],
            mem,
            jid,
            f" (afterok combine:{dep})" if dep else "",
        )
    log.info(
        "[%s] submitted %d, skipped %d (active) + %d (already done)%s.",
        args.stage,
        submitted,
        skipped_active,
        skipped_done,
        " [pipelined]" if args.pipeline else "",
    )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["generate", "validate", "submit-pilot", "submit-rest"])
    p.add_argument("scan", nargs="?", help="unit label for validate/submit-pilot")
    p.add_argument("--stage", default="combine_and_apply_warp", choices=list(STAGE_CFG))
    p.add_argument("--sub", default="s10")
    p.add_argument(
        "--canonical-root", default="/scratch/users/logben/discovery_bids/derivatives/iproc"
    )
    p.add_argument(
        "--scatter-root",
        default="/scratch/users/logben/discovery_bids/derivatives/iproc/scatter_combine_s10",
    )
    p.add_argument("--midvol-sess", default="01")
    p.add_argument("--midvol-boldno", default="009")
    p.add_argument("--code-dir", default="/scratch/users/logben/iProc")
    p.add_argument("--sif", default="/scratch/users/logben/iProc/container/iproc.sif")
    p.add_argument("--bids-root", default="/scratch/users/logben/discovery_bids")
    p.add_argument("--partition", default="russpold")
    p.add_argument("--cpus", type=int, default=8)
    p.add_argument("--time", default="18:00:00")
    p.add_argument(
        "--pipeline",
        action="store_true",
        help="filter only: afterok each scan's matching combine job if still queued",
    )
    args = p.parse_args(argv)
    return {
        "generate": cmd_generate,
        "validate": cmd_validate,
        "submit-pilot": cmd_submit_pilot,
        "submit-rest": cmd_submit_rest,
    }[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
