"""Motion exclusion generator: reads fmriprep confound TSVs and applies thresholds.

Scoping note: this generator is dataset-scoped *by construction* — it reads only
``{bids_dir}/derivatives/fmriprep_*`` for the dataset being compiled, so its
output cannot contain out-of-roster subjects. It therefore does NOT apply the
``load_dataset_subjects`` roster filter that ``qa_decisions`` / ``lev1_outlier``
use; those read *pooled* inputs (a shared decisions TSV / cohort QC CSV) that can
contain cross-sample rows and so need the explicit filter. Same for
``behavioral`` (reads the dataset's own ``sourcedata``).
"""

from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

from neuro_workflow.core.thresholds import motion as _motion_thresholds
from neuro_workflow.exclusions.base import register_generator


def _parse_confounds_filename(filename: str) -> dict | None:
    """Extract BIDS entities from a confounds filename."""
    m = re.match(
        r"(sub-\w+)_(ses-\w+)_task-(\w+)_run-(\w+)_desc-confounds_timeseries\.tsv",
        filename,
    )
    if not m:
        return None
    return {
        "subject": m.group(1),
        "session": m.group(2),
        "task": m.group(3),
        "run": m.group(4),
    }


def _compute_metrics(df: pd.DataFrame) -> dict:
    """Compute motion metrics from a confounds dataframe.

    DVARS uses fmriprep's `std_dvars` (standardized, ~0-3 z-units), not the raw
    `dvars` column (BOLD-intensity units, ~10s-100s). The threshold convention
    `>1.5` applies to standardized DVARS. qa/metrics/motion.py already uses
    std_dvars; this matches.
    """
    fd = pd.to_numeric(
        df.get("framewise_displacement", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    dvars = pd.to_numeric(df.get("std_dvars", pd.Series(dtype=float)), errors="coerce").dropna()
    return {
        "fmriprep_fd_mean": float(fd.mean()) if len(fd) > 0 else 0.0,
        "fmriprep_fd_std": float(fd.std()) if len(fd) > 0 else 0.0,
        "fmriprep_proportion_fd_over_0.5": float((fd > 0.5).mean()) if len(fd) > 0 else 0.0,
        "fmriprep_std_dvars_mean": float(dvars.mean()) if len(dvars) > 0 else 0.0,
        "fmriprep_std_dvars_std": float(dvars.std()) if len(dvars) > 0 else 0.0,
        "fmriprep_proportion_std_dvars_over_1.5": float((dvars > 1.5).mean())
        if len(dvars) > 0
        else 0.0,
    }


class MotionGenerator:
    name = "motion"
    description = "Generate motion exclusions from fmriprep confound files"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        t = _motion_thresholds()
        parser.add_argument(
            "--fmriprep-version",
            required=False,
            default="25.2.4",
            help="fMRIPrep version for derivatives path",
        )
        parser.add_argument(
            "--fd-threshold",
            type=float,
            default=t["fd_threshold"],
            help=f"FD mean threshold for resting-state (default: {t['fd_threshold']})",
        )
        parser.add_argument(
            "--proportion-fd-threshold",
            type=float,
            default=t["proportion_fd_threshold"],
            help=f"Proportion FD > 0.5 threshold for task scans (default: {t['proportion_fd_threshold']})",
        )
        parser.add_argument(
            "--proportion-dvars-threshold",
            type=float,
            default=t["proportion_dvars_threshold"],
            help=f"Proportion DVARS > 1.5 threshold (default: {t['proportion_dvars_threshold']})",
        )

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        if pd is None:
            print(
                "Error: 'pandas' required for motion generator. Install with: uv pip install -e \".[qa]\""
            )
            return []

        bids_dir = Path(dataset_config["bids_dir"])
        version = getattr(args, "fmriprep_version", "25.2.4")
        deriv = bids_dir / "derivatives" / f"fmriprep_{version}"

        confound_files = sorted(deriv.glob("sub-*/ses-*/func/*_desc-confounds_timeseries.tsv"))
        if not confound_files:
            # Fail loud, never silently return [] (which compile would record as
            # `motion: 0` — a silent under-exclusion). An empty glob almost
            # always means --fmriprep-version doesn't match the derivatives dir,
            # or fMRIPrep has not run for this dataset.
            raise FileNotFoundError(
                f"motion generator: no confounds TSVs under {deriv}. Check that "
                f"--fmriprep-version (got '{version}') matches the derivatives "
                f"directory and that fMRIPrep has run for dataset '{dataset_name}'."
            )

        fd_thresh = args.fd_threshold
        prop_fd_thresh = args.proportion_fd_threshold
        prop_dvars_thresh = args.proportion_dvars_threshold

        entries = []
        for tsv_path in confound_files:
            parsed = _parse_confounds_filename(tsv_path.name)
            if not parsed:
                continue

            df = pd.read_csv(tsv_path, sep="\t")
            metrics = _compute_metrics(df)

            is_rest = parsed["task"] == "rest"
            reasons = []

            if is_rest:
                if metrics["fmriprep_fd_mean"] > fd_thresh:
                    reasons.append(
                        f"Resting state FD mean ({metrics['fmriprep_fd_mean']:.3f}) "
                        f"exceeded threshold ({fd_thresh})"
                    )
            else:
                if metrics["fmriprep_proportion_fd_over_0.5"] > prop_fd_thresh:
                    reasons.append(
                        f"Proportion FD > 0.5 ({metrics['fmriprep_proportion_fd_over_0.5']:.3f}) "
                        f"exceeded threshold ({prop_fd_thresh})"
                    )

            if metrics["fmriprep_proportion_std_dvars_over_1.5"] > prop_dvars_thresh:
                reasons.append(
                    f"Proportion std_dvars > 1.5 ({metrics['fmriprep_proportion_std_dvars_over_1.5']:.3f}) "
                    f"exceeded threshold ({prop_dvars_thresh})"
                )

            if reasons:
                entries.append(
                    {
                        "subject": parsed["subject"],
                        "session": parsed["session"],
                        "task": f"task-{parsed['task']}",
                        "run": f"run-{parsed['run']}",
                        "source": "motion",
                        "action": "exclude",
                        "reason": "; ".join(reasons),
                        "metrics": metrics,
                    }
                )

        print(
            f"Motion generator: {len(entries)} exclusions from {len(confound_files)} confound files"
        )
        return entries


register_generator(MotionGenerator())
