#!/usr/bin/env python3
"""Compute dataset descriptive statistics for the datasets doc.

Scans a BIDS dir: subjects, sessions, per-task run counts, volumes (via NIfTI
header), durations (vols*TR), rest-vs-task minutes per subject, echoes, TR.
One scan == one (sub,ses,task,run) (echoes collapsed). Reports raw (all BOLD in
BIDS) — .bidsignore'd scans included, flagged separately via the .bidsignore.
"""
import glob, json, os, re, sys
from collections import defaultdict
import nibabel as nib

TR = 1.49
BASE = {"cuedTS", "directedForgetting", "flanker", "goNogo", "nBack",
        "shapeMatching", "spatialTS", "stopSignal"}
_RE = re.compile(r"(sub-[^_/]+)_(ses-[^_/]+)_task-([^_]+)_(?:acq-[^_]+_)?"
                 r"(?:dir-[^_]+_)?run-(\d+)(?:_echo-(\d+))?")


def analyze(bids, label):
    scans = {}  # (sub,ses,task,run) -> {echoes:set, nvols:int}
    for f in glob.glob(f"{bids}/sub-*/ses-*/func/*_bold.nii.gz"):
        m = _RE.search(os.path.basename(f))
        if not m:
            continue
        sub, ses, task, run, echo = m.groups()
        key = (sub, ses, task, run)
        rec = scans.setdefault(key, {"echoes": set(), "nvols": None, "path": f})
        rec["echoes"].add(echo or "1")
        if rec["nvols"] is None:  # read vols once per scan (from first echo seen)
            try:
                sh = nib.load(f).shape
                rec["nvols"] = sh[3] if len(sh) > 3 else 1
            except Exception:
                rec["nvols"] = 0

    subs = sorted({k[0] for k in scans})
    sessions_all = sorted({(k[0], k[1]) for k in scans})
    per_sub = defaultdict(lambda: {"ses": set(), "rest_min": 0.0, "task_min": 0.0,
                                   "n_rest": 0, "n_task": 0})
    task_runs = defaultdict(int)
    task_min = defaultdict(float)
    echo_hist = defaultdict(int)
    for (sub, ses, task, run), rec in scans.items():
        mins = (rec["nvols"] or 0) * TR / 60.0
        per_sub[sub]["ses"].add(ses)
        echo_hist[len(rec["echoes"])] += 1
        if task == "rest":
            per_sub[sub]["rest_min"] += mins
            per_sub[sub]["n_rest"] += 1
        else:
            per_sub[sub]["task_min"] += mins
            per_sub[sub]["n_task"] += 1
        task_runs[task] += 1
        task_min[task] += mins

    def agg(vals):
        vals = list(vals)
        return {"mean": round(sum(vals) / len(vals), 1) if vals else 0,
                "min": round(min(vals), 1) if vals else 0,
                "max": round(max(vals), 1) if vals else 0}

    n_ses_per_sub = [len(v["ses"]) for v in per_sub.values()]
    return {
        "cohort": label, "bids": bids,
        "n_subjects": len(subs),
        "n_sessions_total": len(sessions_all),
        "sessions_per_subject": agg(n_ses_per_sub),
        "n_scans_total": len(scans),
        "rest_min_per_subject": agg(v["rest_min"] for v in per_sub.values()),
        "task_min_per_subject": agg(v["task_min"] for v in per_sub.values()),
        "total_bold_min_per_subject": agg(v["rest_min"] + v["task_min"] for v in per_sub.values()),
        "n_rest_runs_per_subject": agg(v["n_rest"] for v in per_sub.values()),
        "n_task_runs_per_subject": agg(v["n_task"] for v in per_sub.values()),
        "cohort_rest_min_total": round(sum(v["rest_min"] for v in per_sub.values()), 1),
        "cohort_task_min_total": round(sum(v["task_min"] for v in per_sub.values()), 1),
        "echoes_per_scan_hist": dict(echo_hist),
        "per_task": {t: {"n_runs": task_runs[t], "total_min": round(task_min[t], 1),
                         "mean_min_per_run": round(task_min[t] / task_runs[t], 1) if task_runs[t] else 0,
                         "is_base": t in BASE}
                     for t in sorted(task_runs)},
    }


if __name__ == "__main__":
    out = {}
    for label, bids in [("discovery", "/scratch/users/logben/discovery_bids"),
                        ("validation", "/scratch/users/logben/validation_bids"),
                        ("excluded", "/scratch/users/logben/excluded_bids")]:
        if os.path.isdir(bids):
            print(f"analyzing {label}...", flush=True)
            out[label] = analyze(bids, label)
    with open("/scratch/users/logben/oak_reexec/dataset_stats.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
