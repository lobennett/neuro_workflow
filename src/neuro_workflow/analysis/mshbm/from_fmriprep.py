"""Build MSHBM fsaverage6 inputs from fMRIPrep surface BOLD + mshbm.preproc.

Arm 3 of the pipeline comparison: fMRIPrep's own fsaverage6 GIFTIs (FS 7.3.2)
denoised with the lab's mshbm.preproc (confound regression + bandpass) and 2mm
smoothing — no XCP-D. Pure discovery/naming/denoise here; wb_command + heavy
array I/O live in scripts/mshbm_inputs_from_fmriprep.py.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from neuro_workflow.analysis.mshbm.io import HEMI_MAP, make_mshbm_name  # noqa: F401
from neuro_workflow.analysis.mshbm.preproc import (
    bandpass_filter,
    build_regressor_matrix_du2025,
    regress_confounds,
)
_BOLD_RE = re.compile(
    r"^sub-(?P<sub>[A-Za-z0-9]+)_ses-(?P<ses>[A-Za-z0-9]+)_"
    r"task-(?P<task>[A-Za-z0-9]+)(?:_run-(?P<run>[A-Za-z0-9]+))?"
    r"_hemi-L_space-fsaverage6_bold\.func\.gii$"
)


@dataclass(frozen=True)
class FmriprepScan:
    """One (session, task, run) cell for one subject, both hemispheres paired."""

    session: str
    task: str
    run: str
    lh_path: Path
    rh_path: Path
    confounds_tsv: Path
    tr: float


def discover_fmriprep_scans(fmriprep_dir: Path, subject: str) -> list[FmriprepScan]:
    """Find paired L/R fsaverage6 BOLD GIFTIs + confounds + TR for one subject."""
    subj = subject if subject.startswith("sub-") else f"sub-{subject}"
    out: list[FmriprepScan] = []
    for lh in sorted((Path(fmriprep_dir) / subj).glob(
            "ses-*/func/*_hemi-L_space-fsaverage6_bold.func.gii")):
        m = _BOLD_RE.match(lh.name)
        if not m:
            continue
        rh = Path(str(lh).replace("hemi-L", "hemi-R"))
        if not rh.exists():
            continue
        run = m.group("run") or "1"
        prefix = lh.name.split("_hemi-L_")[0]
        conf = lh.parent / f"{prefix}_desc-confounds_timeseries.tsv"
        js = lh.with_suffix("").with_suffix(".json")  # *_bold.json
        tr = (float(json.loads(js.read_text())["RepetitionTime"])
              if js.exists() else float("nan"))
        out.append(FmriprepScan(
            m.group("ses"), m.group("task"), run, lh, rh, conf, tr))
    return out


def denoise_timeseries(Y: np.ndarray, confounds_df: pd.DataFrame, tr: float,
                       lowcut: float = 0.009, highcut: float = 0.08) -> np.ndarray:
    """Regress du2025 nuisance set then bandpass. Y is (V, T)."""
    X = build_regressor_matrix_du2025(confounds_df)
    Y = regress_confounds(Y, X)
    Y = bandpass_filter(Y, tr=tr, lowcut=lowcut, highcut=highcut)
    # filtfilt edge transients reintroduce a small per-vertex DC offset on
    # short series; re-center so each vertex is zero-mean (MSHBM expects this).
    Y = Y - Y.mean(axis=1, keepdims=True)
    return np.nan_to_num(Y, nan=0.0).astype(np.float32)
