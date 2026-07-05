"""End-to-end simulation INPUT gate: a synthetic BIDS + sourcedata + fMRIPrep
cohort whose scans are deliberately planted to be excluded by each real
mechanism (behavioral QC, motion, collection) — or kept.

B1 (``test_synthetic_fmriprep.py``) proved a single stubbed fMRIPrep run drives
the real ``FileFinder`` and ``MotionGenerator``. This module proves the *cohort*
layer:

  1. ``make_behavioral_csv`` writes a sourcedata behavioral CSV that the REAL
     ``neuro_workflow.events.qc`` code (``compute_metrics_from_csv`` /
     ``determine_exclusion`` / ``run_qc``) reads. A high-omission / low-accuracy
     generic (flanker) CSV and a slow-go stopSignal CSV genuinely trip their
     thresholds; a clean one does not. The boundary around the omission
     threshold (0.25, strict ``>``) is pinned, exactly as B1 pinned the motion
     proportion boundary.
  2. ``make_synthetic_cohort`` assembles, under one root, a BIDS tree +
     ``sourcedata`` behavioral CSVs + fMRIPrep derivatives + a collection
     ``.bidsignore`` block, with each scan tagged ``keep`` /
     ``exclude:behavioral`` / ``exclude:motion`` / ``exclude:collection``. Each
     planted target is then shown to be SEEN by its real generator: the real
     behavioral QC flags the behavioral-fail scan, the real ``MotionGenerator``
     flags the motion-fail scan, the collection block contains a glob covering
     the collection scan, and ``FileFinder`` discovers the keep scan's
     derivatives as a complete run.

These tests consume only the additive helpers in
``neuro_workflow.testing`` — no production module is modified.
"""

from __future__ import annotations

import pytest

# Behavioral QC + cohort writers need pandas/nibabel; skip cleanly if absent.
pd = pytest.importorskip("pandas")
nib = pytest.importorskip("nibabel")

from neuro_workflow.analysis.io.file_discovery import FileFinder  # noqa: E402
from neuro_workflow.core.thresholds import (  # noqa: E402
    behavioral_qc as behavioral_qc_thresholds,
)
from neuro_workflow.core.thresholds import (
    motion as motion_thresholds,
)
from neuro_workflow.events.qc import (  # noqa: E402
    compute_metrics_from_csv,
    determine_exclusion,
    run_qc,
)
from neuro_workflow.exclusions.behavioral import BehavioralGenerator  # noqa: E402
from neuro_workflow.exclusions.motion import MotionGenerator  # noqa: E402
from neuro_workflow.testing.cohort import (  # noqa: E402
    CohortSpec,
    ScanSpec,
    SessionSpec,
    SubjectSpec,
    make_behavioral_csv,
    make_synthetic_cohort,
)

_BQC = behavioral_qc_thresholds()
OMISSION_THRESH = _BQC["omission_rate_threshold"]  # 0.25, strict >
ACC_THRESH = _BQC["acc_threshold"]  # 0.55, strict <
GO_RT_THRESH = _BQC["go_rt_threshold_fmri"]  # 1000ms, strict >


# --------------------------------------------------------------------------- #
# Gate 1a: make_behavioral_csv trips the REAL generic (flanker) thresholds.
# --------------------------------------------------------------------------- #
class TestBehavioralCsvGeneric:
    def test_high_omission_is_flagged(self, tmp_path):
        """A flanker CSV with omission_rate=0.5 (> 0.25) trips the real
        omission threshold via determine_exclusion(compute_metrics_from_csv)."""
        csv = make_behavioral_csv(
            tmp_path / "flanker.csv",
            "flanker",
            n_trials=40,
            omission_rate=0.5,
            accuracy=1.0,
            seed=0,
        )
        metrics = compute_metrics_from_csv(csv, "flanker")
        assert metrics["omission_rate"] == pytest.approx(0.5)
        excl = determine_exclusion("flanker", metrics)
        assert excl is not None
        assert "omission_rate" in excl["reason"]

    def test_clean_csv_not_flagged(self, tmp_path):
        """omission_rate=0.0, accuracy=1.0 -> no exclusion."""
        csv = make_behavioral_csv(
            tmp_path / "flanker.csv",
            "flanker",
            n_trials=40,
            omission_rate=0.0,
            accuracy=1.0,
            seed=0,
        )
        metrics = compute_metrics_from_csv(csv, "flanker")
        assert metrics["omission_rate"] == pytest.approx(0.0)
        assert metrics["acc"] == pytest.approx(1.0)
        assert determine_exclusion("flanker", metrics) is None

    def test_low_accuracy_is_flagged(self, tmp_path):
        """accuracy=0.4 (< 0.55) trips the acc threshold; accuracy is computed
        over RESPONDED trials only, so keep omission at 0 to isolate it."""
        csv = make_behavioral_csv(
            tmp_path / "flanker.csv",
            "flanker",
            n_trials=40,
            omission_rate=0.0,
            accuracy=0.4,
            seed=0,
        )
        metrics = compute_metrics_from_csv(csv, "flanker")
        assert metrics["acc"] == pytest.approx(0.4)
        excl = determine_exclusion("flanker", metrics)
        assert excl is not None
        assert "accuracy" in excl["reason"]

    def test_omission_boundary(self, tmp_path):
        """Boundary on the omission threshold (0.25, strict >): exactly 0.25 is
        NOT flagged; just over (11/40 = 0.275) IS — proving the CSV crosses the
        REAL cutoff, not a faked one. Mirrors B1's motion-proportion boundary."""
        n = 40
        at_thresh = OMISSION_THRESH  # 0.25
        # 10/40 == 0.25 exactly -> not flagged (strict >).
        csv_at = make_behavioral_csv(
            tmp_path / "at.csv",
            "flanker",
            n_trials=n,
            omission_rate=at_thresh,
            accuracy=1.0,
            seed=0,
        )
        m_at = compute_metrics_from_csv(csv_at, "flanker")
        assert m_at["omission_rate"] == pytest.approx(at_thresh)
        assert determine_exclusion("flanker", m_at) is None

        # 11/40 == 0.275 -> over threshold -> flagged.
        over = 11 / n
        csv_over = make_behavioral_csv(
            tmp_path / "over.csv",
            "flanker",
            n_trials=n,
            omission_rate=over,
            accuracy=1.0,
            seed=0,
        )
        m_over = compute_metrics_from_csv(csv_over, "flanker")
        assert m_over["omission_rate"] > at_thresh
        assert determine_exclusion("flanker", m_over) is not None


# --------------------------------------------------------------------------- #
# Gate 1b: make_behavioral_csv trips the REAL stopSignal go_rt threshold.
# --------------------------------------------------------------------------- #
class TestBehavioralCsvStopSignal:
    def test_slow_go_rt_is_flagged(self, tmp_path):
        """A stopSignal CSV with go_rt_ms=1200 (> 1000) trips the go_rt rule."""
        csv = make_behavioral_csv(
            tmp_path / "ss.csv",
            "stopSignal",
            n_trials=40,
            go_rt_ms=1200,
            seed=0,
        )
        metrics = compute_metrics_from_csv(csv, "stopSignal")
        assert metrics["go_rt"] == pytest.approx(1200.0)
        excl = determine_exclusion("stopSignal", metrics)
        assert excl is not None
        assert "go_rt" in excl["reason"]

    def test_fast_go_rt_not_flagged(self, tmp_path):
        """A stopSignal CSV with go_rt_ms=500 and a healthy ~50% stop-success
        rate is NOT flagged (go_rt below 1000, stop_success within [0.25,0.75])."""
        csv = make_behavioral_csv(
            tmp_path / "ss.csv",
            "stopSignal",
            n_trials=40,
            go_rt_ms=500,
            seed=0,
        )
        metrics = compute_metrics_from_csv(csv, "stopSignal")
        assert metrics["go_rt"] == pytest.approx(500.0)
        assert 0.25 <= metrics["stop_success_rate"] <= 0.75
        assert determine_exclusion("stopSignal", metrics) is None

    def test_go_rt_boundary(self, tmp_path):
        """Boundary on go_rt (1000ms, strict >): exactly 1000 NOT flagged; just
        over (1001) flagged."""
        csv_at = make_behavioral_csv(
            tmp_path / "at.csv",
            "stopSignal",
            n_trials=40,
            go_rt_ms=GO_RT_THRESH,
            seed=0,
        )
        m_at = compute_metrics_from_csv(csv_at, "stopSignal")
        assert m_at["go_rt"] == pytest.approx(float(GO_RT_THRESH))
        assert determine_exclusion("stopSignal", m_at) is None

        csv_over = make_behavioral_csv(
            tmp_path / "over.csv",
            "stopSignal",
            n_trials=40,
            go_rt_ms=GO_RT_THRESH + 1,
            seed=0,
        )
        m_over = compute_metrics_from_csv(csv_over, "stopSignal")
        assert m_over["go_rt"] > GO_RT_THRESH
        assert determine_exclusion("stopSignal", m_over) is not None


# --------------------------------------------------------------------------- #
# Gate 1c: run_qc (the full sourcedata walk) flags a planted CSV in a tree.
# --------------------------------------------------------------------------- #
class TestRunQcOnPlantedTree:
    def test_run_qc_flags_high_omission_csv(self, tmp_path):
        """A behavioral CSV in a sourcedata tree is flagged by the FULL run_qc
        walk (glob + per-task metric + determine_exclusion), proving the
        filename/columns match what the real generator iterates over."""
        beh = tmp_path / "sourcedata" / "sub-s01" / "ses-01" / "beh"
        beh.mkdir(parents=True)
        make_behavioral_csv(
            beh / "sub-s01_ses-01_task-flanker_run-1_beh.csv",
            "flanker",
            n_trials=40,
            omission_rate=0.5,
            accuracy=1.0,
            seed=0,
        )
        bids = tmp_path  # run_qc only writes sourcedata/behavioral_qc here
        entries, _trim = run_qc(tmp_path / "sourcedata", bids)
        flagged = [e for e in entries if e["subject"] == "sub-s01" and e["task"] == "task-flanker"]
        assert len(flagged) == 1
        assert flagged[0]["action"] == "exclude"
        assert flagged[0]["source"] == "behavioral-qc"

    def test_run_qc_keeps_clean_csv(self, tmp_path):
        """A clean CSV in a sourcedata tree yields no exclusion from run_qc."""
        beh = tmp_path / "sourcedata" / "sub-s01" / "ses-01" / "beh"
        beh.mkdir(parents=True)
        make_behavioral_csv(
            beh / "sub-s01_ses-01_task-flanker_run-1_beh.csv",
            "flanker",
            n_trials=40,
            omission_rate=0.0,
            accuracy=1.0,
            seed=0,
        )
        entries, _trim = run_qc(tmp_path / "sourcedata", tmp_path)
        assert entries == []


# --------------------------------------------------------------------------- #
# Gate 2: make_synthetic_cohort — each planted exclusion seen by its generator.
# --------------------------------------------------------------------------- #
def _small_spec() -> CohortSpec:
    """2 subjects, covering keep + one each of behavioral/motion/collection.

    s01: a keep flanker scan and a behavioral-fail flanker scan (different ses).
    s02: a motion-fail flanker scan and a collection-excluded goNogo scan.
    """
    return CohortSpec(
        subjects=[
            SubjectSpec(
                subject="s01",
                sessions=[
                    SessionSpec(
                        session="01",
                        scans=[
                            ScanSpec(task="flanker", run="1", outcome="keep"),
                        ],
                    ),
                    SessionSpec(
                        session="02",
                        scans=[
                            ScanSpec(
                                task="flanker",
                                run="1",
                                outcome="exclude:behavioral",
                            ),
                        ],
                    ),
                ],
            ),
            SubjectSpec(
                subject="s02",
                sessions=[
                    SessionSpec(
                        session="01",
                        scans=[
                            ScanSpec(
                                task="flanker",
                                run="1",
                                outcome="exclude:motion",
                            ),
                            ScanSpec(
                                task="goNogo",
                                run="1",
                                outcome="exclude:collection",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


class TestMakeSyntheticCohort:
    def test_manifest_records_every_scan(self, tmp_path):
        """The returned manifest has one row per planted scan with its intended
        outcome and the files written, plus the derivatives root + collection
        glob lines."""
        manifest = make_synthetic_cohort(tmp_path, _small_spec())
        scans = manifest["scans"]
        assert len(scans) == 4
        outcomes = {(s["subject"], s["session"], s["task"]): s["outcome"] for s in scans}
        assert outcomes[("sub-s01", "ses-01", "flanker")] == "keep"
        assert outcomes[("sub-s01", "ses-02", "flanker")] == "exclude:behavioral"
        assert outcomes[("sub-s02", "ses-01", "flanker")] == "exclude:motion"
        assert outcomes[("sub-s02", "ses-01", "goNogo")] == "exclude:collection"
        assert "bids_dir" in manifest and "fmriprep_dir" in manifest
        assert manifest["collection_lines"], "collection glob lines expected"

    def test_behavioral_generator_flags_planted_behavioral_scan(self, tmp_path):
        """The REAL behavioral QC (run_qc via BehavioralGenerator) flags exactly
        the exclude:behavioral scan and not the keep scan."""
        manifest = make_synthetic_cohort(tmp_path, _small_spec())
        entries = BehavioralGenerator().generate(
            "sim",
            {"bids_dir": manifest["bids_dir"]},
            _behavioral_args(),
        )
        flagged = {(e["subject"], e["session"], e["task"]) for e in entries}
        assert ("sub-s01", "ses-02", "task-flanker") in flagged
        assert ("sub-s01", "ses-01", "task-flanker") not in flagged

    def test_motion_generator_flags_planted_motion_scan(self, tmp_path):
        """The REAL MotionGenerator flags exactly the exclude:motion scan and
        not the keep scan."""
        manifest = make_synthetic_cohort(tmp_path, _small_spec(), version="25.2.4")
        entries = MotionGenerator().generate(
            "sim",
            {"bids_dir": manifest["bids_dir"]},
            _motion_args(),
        )
        flagged = {(e["subject"], e["session"], e["task"]) for e in entries}
        assert ("sub-s02", "ses-01", "task-flanker") in flagged
        assert ("sub-s01", "ses-01", "task-flanker") not in flagged

    def test_collection_block_covers_planted_collection_scan(self, tmp_path):
        """The emitted collection .bidsignore-style block contains a glob line
        covering the exclude:collection scan (and the collection file is
        written to disk)."""
        manifest = make_synthetic_cohort(tmp_path, _small_spec())
        lines = manifest["collection_lines"]
        # The goNogo collection scan for s02/ses-01 must be covered.
        assert any(
            "sub-s02/ses-01/func/sub-s02_ses-01_task-goNogo" in ln for ln in lines
        ), f"no collection glob for the planted collection scan: {lines}"
        coll_file = manifest.get("collection_file")
        assert coll_file is not None
        from pathlib import Path

        assert Path(coll_file).is_file()

    def test_filefinder_discovers_keep_scan(self, tmp_path):
        """FileFinder discovers the keep scan's MNI derivatives as a complete
        run (events + confounds + mni_data + mni_brain_mask)."""
        manifest = make_synthetic_cohort(tmp_path, _small_spec())
        finder = FileFinder(manifest["bids_dir"], manifest["fmriprep_dir"])
        required = FileFinder.get_required_files_for_space("MNI")
        files = finder.get_files("s01", "flanker", required_files=required)
        assert "ses-01" in files
        assert "run-1" in files["ses-01"]
        run_files = files["ses-01"]["run-1"]
        for ft in required:
            assert ft in run_files, f"FileFinder did not discover {ft}"

    def test_collection_scan_has_no_behavioral_or_motion_fail(self, tmp_path):
        """A collection-excluded scan is otherwise CLEAN (its CSV passes
        behavioral QC and its confounds pass motion) — collection is the only
        mechanism that excludes it, mirroring real irreconcilable-BOLD scans."""
        manifest = make_synthetic_cohort(tmp_path, _small_spec())
        beh_entries = BehavioralGenerator().generate(
            "sim", {"bids_dir": manifest["bids_dir"]}, _behavioral_args()
        )
        mot_entries = MotionGenerator().generate(
            "sim", {"bids_dir": manifest["bids_dir"]}, _motion_args()
        )
        # The goNogo collection scan must not be flagged by behavioral/motion.
        for e in beh_entries + mot_entries:
            assert not (
                e["subject"] == "sub-s02" and e["task"] == "task-goNogo"
            ), f"collection scan unexpectedly flagged by a QC generator: {e}"


# --------------------------------------------------------------------------- #
# Argparse Namespaces matching the real generators' expected attributes.
# --------------------------------------------------------------------------- #
def _behavioral_args():
    from argparse import Namespace

    return Namespace(behavioral_dir=None)


def _motion_args():
    from argparse import Namespace

    t = motion_thresholds()
    return Namespace(
        fmriprep_version="25.2.4",
        fd_threshold=t["fd_threshold"],
        proportion_fd_threshold=t["proportion_fd_threshold"],
        proportion_dvars_threshold=t["proportion_dvars_threshold"],
    )
