"""Tests for neuro_workflow.analysis.mshbm.from_fmriprep."""
from __future__ import annotations

import numpy as np
import pandas as pd

from neuro_workflow.analysis.mshbm.from_fmriprep import (
    denoise_timeseries,
    discover_fmriprep_scans,
    make_mshbm_name,
)


def test_make_mshbm_name():
    assert make_mshbm_name("lh", "01", "1", "flanker") == \
        "lh_ses-01_task-flanker_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz"


def test_discover_pairs_hemis_and_finds_confounds(tmp_path):
    func = tmp_path / "sub-s10" / "ses-01" / "func"
    func.mkdir(parents=True)
    base = "sub-s10_ses-01_task-flanker_run-1"
    for hemi in ("L", "R"):
        (func / f"{base}_hemi-{hemi}_space-fsaverage6_bold.func.gii").touch()
    (func / f"{base}_desc-confounds_timeseries.tsv").touch()
    (func / f"{base}_hemi-L_space-fsaverage6_bold.json").write_text(
        '{"RepetitionTime":1.49}'
    )
    scans = discover_fmriprep_scans(tmp_path, "s10")
    assert len(scans) == 1
    s = scans[0]
    assert (s.session, s.task, s.run) == ("01", "flanker", "1")
    assert s.confounds_tsv.name.endswith("_desc-confounds_timeseries.tsv")
    assert s.tr == 1.49


def test_denoise_runs_regress_then_bandpass():
    rng = np.random.default_rng(0)
    V, T = 50, 120
    Y = rng.standard_normal((V, T)).astype(np.float32)
    base = ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "global_signal", "csf", "white_matter"]
    cols = base + [c + "_derivative1" for c in base]
    conf = pd.DataFrame(rng.standard_normal((T, len(cols))), columns=cols)
    out = denoise_timeseries(Y, conf, tr=1.49)
    assert out.shape == (V, T)
    assert np.isfinite(out).all()
    assert np.allclose(out.mean(axis=1), 0, atol=1e-3)
