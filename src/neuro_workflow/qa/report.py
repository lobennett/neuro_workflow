"""QA report orchestrator — produces HTML cohort dashboard.

Delegates to:
- metrics/ for per-scan and per-subject metric extraction
- cohort.py for cohort-relative outlier flagging
- decisions.py for sidecar decision TSV
- reliability_movies.py for brm integration
- templates/ for Jinja2-rendered HTML output
"""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import asdict
from pathlib import Path

from neuro_workflow.qa.cohort import cohort_euler_outliers
from neuro_workflow.qa.decisions import Decision, ScanKey, load_decisions
from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics, compute_freesurfer
from neuro_workflow.qa.metrics.motion import MotionMetrics, compute_motion
from neuro_workflow.qa.metrics.outputs import OutputCheckResult, ScanID, check_expected_outputs
from neuro_workflow.qa.reliability_movies import MovieResult, render_reliability_movies
from neuro_workflow.qa.templates import render_cohort_html, render_subject_html

log = logging.getLogger(__name__)

_CONFOUNDS_RE = re.compile(
    r"(sub-\w+)_(ses-\w+)_task-(\w+)_run-(\w+)_desc-confounds_timeseries\.tsv"
)


def _discover_subjects(fmriprep_dir: Path) -> list[str]:
    return sorted(p.name for p in fmriprep_dir.glob("sub-*") if p.is_dir())


def _discover_scans(fmriprep_dir: Path, subject: str) -> list[ScanID]:
    out = []
    for confounds in (fmriprep_dir / subject).rglob("*_desc-confounds_timeseries.tsv"):
        m = _CONFOUNDS_RE.search(confounds.name)
        if m:
            out.append(ScanID(subject=m.group(1), session=m.group(2),
                              task=m.group(3), run=m.group(4)))
    return sorted(out, key=lambda s: (s.session, s.task, s.run))


def _find_fs_dir(fmriprep_dir: Path, subject: str) -> Path | None:
    """Find the FreeSurfer subject directory; supports per-session naming."""
    fs_root = fmriprep_dir / "sourcedata" / "freesurfer"
    if not fs_root.is_dir():
        return None
    candidates = list(fs_root.glob(f"{subject}_*"))
    if not candidates:
        candidates = list(fs_root.glob(f"{subject}"))
    if not candidates:
        return None
    # Prefer one that finished without error
    for c in candidates:
        status_log = c / "scripts" / "recon-all-status.log"
        if status_log.is_file() and "finished without error" in status_log.read_text():
            return c
    return candidates[0]


def _is_motion_flagged(motion: MotionMetrics, task: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    is_rest = task == "rest"
    if is_rest and motion.fd_mean > 0.2:
        reasons.append(f"rest FD mean {motion.fd_mean:.3f} > 0.2")
    if not is_rest and motion.fd_prop_over_05 > 0.20:
        reasons.append(f"%FD>0.5 = {motion.fd_prop_over_05*100:.1f}% > 20%")
    if motion.dvars_prop_over_15 > 0.20:
        reasons.append(f"%std_DVARS>1.5 = {motion.dvars_prop_over_15*100:.1f}% > 20%")
    return bool(reasons), reasons


def _scan_dict(scan: ScanID, motion: MotionMetrics, outputs: OutputCheckResult,
               decision: Decision | None) -> dict:
    flagged_motion, motion_reasons = _is_motion_flagged(motion, scan.task)
    flagged_outputs = not outputs.complete
    flag_reasons = list(motion_reasons)
    if flagged_outputs:
        flag_reasons.append(f"{len(outputs.missing)} missing output(s)")
    flagged = flagged_motion or flagged_outputs
    return {
        "session": scan.session, "task": scan.task, "run": scan.run,
        "n_vols": motion.n_vols,
        "fd_mean": motion.fd_mean, "fd_prop_over_05": motion.fd_prop_over_05,
        "dvars_mean": motion.dvars_mean, "dvars_prop_over_15": motion.dvars_prop_over_15,
        "n_motion_outliers": motion.n_motion_outliers,
        "outputs_complete": outputs.complete,
        "missing_outputs": outputs.missing,
        "flagged": flagged, "flag_reasons": flag_reasons,
        "flagged_motion": flagged_motion, "flagged_outputs": flagged_outputs,
        "decision_action": decision.action if decision else "unset",
        "decision_reason": decision.reason if decision else "",
        "carpetplot_svg": "", "coreg_svg": "", "sdc_svg": "",  # filled below
    }


def _embed_svg(path: Path) -> str:
    """Inline an SVG file as a string; empty if missing."""
    if not path.is_file():
        return ""
    try:
        return path.read_text()
    except OSError:
        return ""


def _attach_svgs(scan_dict: dict, fmriprep_dir: Path, subject: str) -> None:
    figures = fmriprep_dir / subject / "figures"
    base = f"{subject}_{scan_dict['session']}_task-{scan_dict['task']}_run-{scan_dict['run']}"
    scan_dict["carpetplot_svg"] = _embed_svg(figures / f"{base}_desc-carpetplot_bold.svg")
    scan_dict["coreg_svg"] = _embed_svg(figures / f"{base}_desc-coreg_bold.svg")
    scan_dict["sdc_svg"] = _embed_svg(figures / f"{base}_desc-sdc_bold.svg")


def build_reports(
    *,
    fmriprep_dir: Path,
    output_dir: Path,
    subjects: list[str] | None = None,
    decisions_path: Path | None = None,
    no_reliability_movies: bool = False,
    euler_n_sigma: float = 2.0,
) -> None:
    """Build cohort + per-subject HTML reports.

    Args:
        fmriprep_dir: fmriprep derivatives root.
        output_dir: where qa_html/ artifacts go.
        subjects: subset to process (default: all subjects in fmriprep_dir).
        decisions_path: optional sidecar TSV with QC decisions.
        no_reliability_movies: skip brm invocation.
        euler_n_sigma: MAD threshold for cohort Euler outliers.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "subjects").mkdir(exist_ok=True)
    (output_dir / "movies").mkdir(exist_ok=True)

    if subjects is None:
        subjects = _discover_subjects(fmriprep_dir)

    decisions = load_decisions(decisions_path) if decisions_path else {}

    # 1) Compute FS metrics per subject
    fs_metrics: dict[str, FreeSurferMetrics] = {}
    for sub in subjects:
        fs_dir = _find_fs_dir(fmriprep_dir, sub)
        fs_metrics[sub] = compute_freesurfer(fs_dir) if fs_dir else compute_freesurfer(Path("/nonexistent"))

    # 2) Cohort outlier set
    outliers = cohort_euler_outliers(fs_metrics, n_sigma=euler_n_sigma)

    # 3) Reliability movies (one per subject)
    movies: dict[str, MovieResult] = {}
    if not no_reliability_movies:
        movies = render_reliability_movies(fmriprep_dir, output_dir / "movies", subjects)

    # 4) Per-subject scan metrics + render subject HTML
    cohort_rows = []
    n_scans_total = 0
    n_flagged_scans_total = 0

    for sub in subjects:
        scans = _discover_scans(fmriprep_dir, sub)
        scan_dicts = []
        for scan in scans:
            confounds = (fmriprep_dir / sub / scan.session / "func"
                         / f"{sub}_{scan.session}_task-{scan.task}_run-{scan.run}_desc-confounds_timeseries.tsv")
            motion = compute_motion(confounds)
            outputs = check_expected_outputs(fmriprep_dir, scan)

            scan_decision = decisions.get(ScanKey(sub, scan.session, scan.task, scan.run))
            d = _scan_dict(scan, motion, outputs, scan_decision)
            _attach_svgs(d, fmriprep_dir, sub)
            scan_dicts.append(d)

        n_scans_total += len(scan_dicts)
        n_flagged_scans_total += sum(1 for s in scan_dicts if s["flagged"])

        # Subject-level decision
        sub_decision = decisions.get(sub)
        sub_action = sub_decision.action if sub_decision else "unset"
        sub_reason = sub_decision.reason if sub_decision else ""

        movie_result = movies.get(sub)
        movie_relpath = (
            f"../movies/{movie_result.path.name}"
            if movie_result and movie_result.path
            else ""
        )

        subject_html = render_subject_html(
            subject=sub,
            fs_metrics=fs_metrics[sub],
            scans=scan_dicts,
            fmriprep_version=fmriprep_dir.name.replace("fmriprep_", ""),
            movie_relpath=movie_relpath,
            decision_action=sub_action,
            decision_reason=sub_reason,
            embed_svg=_embed_svg,
        )
        (output_dir / "subjects" / f"{sub}.html").write_text(subject_html)

        cohort_rows.append({
            "subject": sub,
            "sessions": len({s.session for s in scans}),
            "scans": len(scan_dicts),
            "fs_euler_mean": fs_metrics[sub].euler_mean,
            "fs_holes_mean": fs_metrics[sub].holes_mean,
            "fs_status": fs_metrics[sub].status,
            "scans_flagged_motion": sum(1 for s in scan_dicts if s["flagged_motion"]),
            "scans_flagged_outputs": sum(1 for s in scan_dicts if s["flagged_outputs"]),
            "scan_flags_total": sum(1 for s in scan_dicts if s["flagged"]),
            "decision_action": sub_action,
            "decision_reason": sub_reason,
            "outlier": sub in outliers,
        })

    # 5) Render cohort HTML + TSV
    cohort_html = render_cohort_html(
        rows=cohort_rows,
        n_subjects=len(subjects),
        n_scans=n_scans_total,
        n_flagged_scans=n_flagged_scans_total,
        fmriprep_version=fmriprep_dir.name.replace("fmriprep_", ""),
    )
    (output_dir / "cohort.html").write_text(cohort_html)

    with (output_dir / "cohort.tsv").open("w", newline="") as f:
        if cohort_rows:
            writer = csv.DictWriter(f, fieldnames=list(cohort_rows[0].keys()), delimiter="\t")
            writer.writeheader()
            writer.writerows(cohort_rows)
