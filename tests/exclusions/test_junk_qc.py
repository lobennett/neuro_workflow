"""Tests for src/neuro_workflow/exclusions/junk_qc.py.

junk_qc is a pre-lev1 exclusion generator: it flags task scans whose fraction
of junk (nuisance) trials exceeds ``thresholds.junk_fraction_max()`` (== 0.30),
reproducing lev1's runtime ``percent_junk > 0.30`` QA-fail as a first-class,
compiled exclusion. The junk fraction is computed with the exact same
preprocessing lev1 applies (``preprocess_events`` -> ``add_junk_trials``),
including the ``n_scans`` onset-truncation read from the BIDS BOLD.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

nib = pytest.importorskip("nibabel")


def _write_bold(func_dir: Path, subject: str, session: str, task: str, run: str, n_scans: int):
    """Write a tiny 4D BOLD NIfTI (one echo) so n_scans can be read from BIDS."""
    func_dir.mkdir(parents=True, exist_ok=True)
    data = np.zeros((2, 2, 2, n_scans), dtype=np.float32)
    img = nib.Nifti1Image(data, affine=np.eye(4))
    fname = f"{subject}_{session}_task-{task}_run-{run}_echo-1_bold.nii.gz"
    nib.save(img, func_dir / fname)


def _write_events(func_dir: Path, subject: str, session: str, task: str, run: str, df: pd.DataFrame):
    func_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{subject}_{session}_task-{task}_run-{run}_events.tsv"
    df.to_csv(func_dir / fname, sep="\t", index=False)


def _cuedts_events(n_good: int, n_omission: int) -> pd.DataFrame:
    """test_trial-based task events: n_omission junk (key_press=-1) out of total."""
    rows = []
    onset = 0.0
    for _ in range(n_good):
        rows.append(
            {"onset": onset, "duration": 1.0, "trial_id": "test_trial",
             "trial_type": "test", "key_press": 1, "correct_response": 1,
             "response_time": 0.5}
        )
        onset += 2.0
    for _ in range(n_omission):
        rows.append(
            {"onset": onset, "duration": 1.0, "trial_id": "test_trial",
             "trial_type": "test", "key_press": -1, "correct_response": 1,
             "response_time": "n/a"}
        )
        onset += 2.0
    return pd.DataFrame(rows)


def _make_bids(tmp_path: Path, subject: str) -> Path:
    """Build a tiny BIDS tree for `subject`:

    - ses-01 cuedTS run-1: 4 omission / 10 total -> 0.40 junk (> 0.30) => EXCLUDE
    - ses-01 flanker run-1: 0 omission / 8 total -> 0.0 junk (clean)  => keep
    Both get a 4D BOLD long enough that no onset truncation occurs.
    """
    bids = tmp_path / "bids"
    func = bids / subject / "ses-01" / "func"

    junk = _cuedts_events(n_good=6, n_omission=4)
    _write_events(func, subject, "ses-01", "cuedTS", "1", junk)
    _write_bold(func, subject, "ses-01", "cuedTS", "1", n_scans=200)

    clean = _cuedts_events(n_good=8, n_omission=0)
    _write_events(func, subject, "ses-01", "flanker", "1", clean)
    _write_bold(func, subject, "ses-01", "flanker", "1", n_scans=200)

    return bids


def test_generator_importable_and_named():
    from neuro_workflow.exclusions.junk_qc import JunkQCGenerator

    assert JunkQCGenerator.name == "junk_qc"


def test_flags_only_the_junk_scan(tmp_path):
    from neuro_workflow.exclusions.junk_qc import JunkQCGenerator

    bids = _make_bids(tmp_path, "sub-s10")  # s10 is in the discovery roster
    config = {"bids_dir": str(bids)}
    entries = JunkQCGenerator().generate("discovery", config, Namespace())

    assert len(entries) == 1, entries
    e = entries[0]
    assert e["subject"] == "sub-s10"
    assert e["session"] == "ses-01"
    assert e["task"] == "cuedTS"  # bare task, no `task-` prefix
    assert e["run"] == "run-1"
    assert e["action"] == "exclude"
    assert e["source"] == "junk_qc"
    assert "reason" in e and e["reason"]
    # required schema keys present + validate
    from neuro_workflow.core.exclusions import validate_entry

    assert validate_entry(e)
    # metric carried through as a 0-1 fraction
    assert e["metrics"]["percent_junk"] == pytest.approx(0.40, abs=1e-6)


def test_clean_only_tree_emits_nothing(tmp_path):
    from neuro_workflow.exclusions.junk_qc import JunkQCGenerator

    bids = tmp_path / "bids"
    func = bids / "sub-s10" / "ses-01" / "func"
    _write_events(func, "sub-s10", "ses-01", "flanker", "1", _cuedts_events(8, 0))
    _write_bold(func, "sub-s10", "ses-01", "flanker", "1", n_scans=200)

    entries = JunkQCGenerator().generate("discovery", {"bids_dir": str(bids)}, Namespace())
    assert entries == []


def test_out_of_roster_subject_ignored(tmp_path):
    """A subject not in the dataset roster is not emitted even if >30% junk."""
    from neuro_workflow.exclusions.junk_qc import JunkQCGenerator

    # s1035 is a validation subject; must not appear in a discovery compile.
    bids = _make_bids(tmp_path, "sub-s1035")
    entries = JunkQCGenerator().generate("discovery", {"bids_dir": str(bids)}, Namespace())
    assert entries == []


def test_rest_scans_skipped(tmp_path):
    from neuro_workflow.exclusions.junk_qc import JunkQCGenerator

    bids = tmp_path / "bids"
    func = bids / "sub-s10" / "ses-01" / "func"
    # A rest events file (no task trials) must be skipped, not crash.
    rest = pd.DataFrame({"onset": [0.0], "duration": [300.0], "trial_type": ["rest"]})
    _write_events(func, "sub-s10", "ses-01", "rest", "1", rest)
    _write_bold(func, "sub-s10", "ses-01", "rest", "1", n_scans=200)

    entries = JunkQCGenerator().generate("discovery", {"bids_dir": str(bids)}, Namespace())
    assert entries == []
