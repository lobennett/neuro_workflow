"""End-to-end simulation gate: synthetic fMRIPrep derivatives drive the REAL
file-discovery and motion-exclusion code.

PR6 added planted-contrast recovery through the real lev1 GLM. The missing
keystone for a no-fMRIPrep / no-Flywheel simulation is a stub that the *real*
machinery accepts:

  1. ``analysis.io.file_discovery.FileFinder`` must DISCOVER a stubbed run for
     the volume (MNI) space and for a surface space, exactly as it would
     discover production fMRIPrep output — proving the stub filenames match
     FileFinder's globs with no near-misses.
  2. ``exclusions.motion.MotionGenerator`` must run against a stubbed confounds
     TSV and produce NO exclusion for a ``motion="clean"`` run and an exclusion
     for a ``motion="high"`` run — proving the confounds columns/filename are
     correct and that the thresholds in ``config/thresholds.yaml`` are exercised
     deterministically (not faked).

These tests consume only the additive helpers in
``neuro_workflow.testing.synthetic``; no production module is modified.
"""

from argparse import Namespace

import pytest

# Surface/volume writers need nibabel; skip cleanly if the lev1 extra is absent.
nib = pytest.importorskip("nibabel")
pd = pytest.importorskip("pandas")

from neuro_workflow.analysis.io.file_discovery import FileFinder  # noqa: E402
from neuro_workflow.core.thresholds import motion as motion_thresholds  # noqa: E402
from neuro_workflow.exclusions.motion import MotionGenerator  # noqa: E402
from neuro_workflow.testing.synthetic import (  # noqa: E402
    make_events,
    make_fmriprep_run,
    write_confounds_tsv,
    write_fmriprep_bold,
)

SUBJECT = "s01"
SESSION = "01"
TASK = "flanker"
RUN = "1"
N_TRS = 100


def _write_events(bids_dir, *, subject=SUBJECT, session=SESSION, task=TASK, run=RUN):
    """Drop a matching BIDS events.tsv where FileFinder expects it.

    FileFinder discovers events from ``<bids_dir>/sub-X/ses-Y/func`` with the
    glob ``ses-*/func/*task-{task}_*events.tsv`` and requires a ``run-N`` token
    in the name. Reuse the real ``make_events`` so the table is a valid events
    file (the simulation feeds the same file to the lev1 design path).
    """
    func = bids_dir / f"sub-{subject}" / f"ses-{session}" / "func"
    func.mkdir(parents=True, exist_ok=True)
    events = make_events(task, n_trials=6)
    name = f"sub-{subject}_ses-{session}_task-{task}_run-{run}_events.tsv"
    path = func / name
    events.to_csv(path, sep="\t", index=False)
    return path


# --------------------------------------------------------------------------- #
# Gate 1: FileFinder discovers the stub (volume MNI + surface fsaverage6).
# --------------------------------------------------------------------------- #
class TestFileFinderDiscoversStub:
    def test_discovers_mni_volume_run(self, tmp_path):
        """A stubbed MNI run is discovered as a complete run with mni_data +
        mni_brain_mask + confounds + events."""
        bids = tmp_path / "bids"
        fmriprep = tmp_path / "fmriprep"
        _write_events(bids)
        written = make_fmriprep_run(
            fmriprep, SUBJECT, SESSION, TASK, RUN,
            space="MNI", n_trs=N_TRS, motion="clean", seed=0,
        )
        assert "mni_data" in written and "mni_brain_mask" in written
        assert "confounds" in written

        finder = FileFinder(bids, fmriprep)  # production defaults: NLin6Asym, res-2
        required = FileFinder.get_required_files_for_space("MNI")
        files = finder.get_files(SUBJECT, TASK, required_files=required)

        assert f"ses-{SESSION}" in files
        assert f"run-{RUN}" in files[f"ses-{SESSION}"]
        run_files = files[f"ses-{SESSION}"][f"run-{RUN}"]
        for ft in required:
            assert ft in run_files, f"FileFinder did not discover {ft}"
        assert "MNI152NLin6Asym_res-2" in run_files["mni_data"].name

    def test_discovers_surface_fsaverage6_run(self, tmp_path):
        """A stubbed fsaverage6 surface run is discovered with left/right
        GIFTI surfaces + confounds + events."""
        bids = tmp_path / "bids"
        fmriprep = tmp_path / "fmriprep"
        _write_events(bids)
        written = make_fmriprep_run(
            fmriprep, SUBJECT, SESSION, TASK, RUN,
            space="fsaverage6", n_trs=N_TRS, motion="clean", seed=0,
        )
        assert "left_surface" in written and "right_surface" in written

        finder = FileFinder(bids, fmriprep)
        required = FileFinder.get_required_files_for_space("fsaverage6")
        files = finder.get_files(
            SUBJECT, TASK, required_files=required, surface_space="fsaverage6"
        )

        assert f"ses-{SESSION}" in files
        run_files = files[f"ses-{SESSION}"][f"run-{RUN}"]
        for ft in required:
            assert ft in run_files, f"FileFinder did not discover {ft}"
        assert "hemi-L_space-fsaverage6" in run_files["left_surface"].name
        assert "hemi-R_space-fsaverage6" in run_files["right_surface"].name

    def test_discovers_fslr_cifti_run(self, tmp_path):
        """A stubbed fsLR cifti run is discovered with the dtseries cifti."""
        bids = tmp_path / "bids"
        fmriprep = tmp_path / "fmriprep"
        _write_events(bids)
        written = make_fmriprep_run(
            fmriprep, SUBJECT, SESSION, TASK, RUN,
            space="fsLR", n_trs=N_TRS, motion="clean", seed=0,
        )
        assert "cifti_bold" in written

        finder = FileFinder(bids, fmriprep)
        required = FileFinder.get_required_files_for_space("fsLR")
        files = finder.get_files(
            SUBJECT, TASK, required_files=required, surface_space="fsLR"
        )
        run_files = files[f"ses-{SESSION}"][f"run-{RUN}"]
        assert "cifti_bold" in run_files
        assert "space-fsLR_den-91k_bold.dtseries.nii" in run_files["cifti_bold"].name

    def test_t1w_volume_run(self, tmp_path):
        """A stubbed T1w run is discovered with t1w_data + t1w_brain_mask."""
        bids = tmp_path / "bids"
        fmriprep = tmp_path / "fmriprep"
        _write_events(bids)
        make_fmriprep_run(
            fmriprep, SUBJECT, SESSION, TASK, RUN,
            space="T1w", n_trs=N_TRS, motion="clean", seed=0,
        )
        finder = FileFinder(bids, fmriprep)
        required = FileFinder.get_required_files_for_space("T1w")
        files = finder.get_files(SUBJECT, TASK, required_files=required)
        run_files = files[f"ses-{SESSION}"][f"run-{RUN}"]
        for ft in required:
            assert ft in run_files


# --------------------------------------------------------------------------- #
# Gate 2: the REAL motion generator flags `high` and not `clean`.
# --------------------------------------------------------------------------- #
def _motion_args():
    """Argparse Namespace with the canonical thresholds the generator reads."""
    t = motion_thresholds()
    return Namespace(
        fmriprep_version="25.2.4",
        fd_threshold=t["fd_threshold"],
        proportion_fd_threshold=t["proportion_fd_threshold"],
        proportion_dvars_threshold=t["proportion_dvars_threshold"],
    )


class TestMotionGeneratorOnStub:
    def test_clean_run_not_flagged(self, tmp_path):
        """A motion='clean' stub (low FD, no spikes) yields NO exclusion."""
        bids = tmp_path / "bids"
        deriv = bids / "derivatives" / "fmriprep_25.2.4"
        make_fmriprep_run(
            deriv, SUBJECT, SESSION, TASK, RUN,
            space="MNI", n_trs=N_TRS, motion="clean", seed=0,
        )
        entries = MotionGenerator().generate(
            "sim", {"bids_dir": str(bids)}, _motion_args()
        )
        assert entries == [], f"clean run should not be flagged, got {entries}"

    def test_high_run_is_flagged(self, tmp_path):
        """A motion='high' stub plants enough FD>0.5 / std_dvars>1.5 frames to
        exceed the proportion thresholds -> exactly one exclusion entry."""
        bids = tmp_path / "bids"
        deriv = bids / "derivatives" / "fmriprep_25.2.4"
        make_fmriprep_run(
            deriv, SUBJECT, SESSION, TASK, RUN,
            space="MNI", n_trs=N_TRS, motion="high", seed=0,
        )
        entries = MotionGenerator().generate(
            "sim", {"bids_dir": str(bids)}, _motion_args()
        )
        assert len(entries) == 1, f"high run should be flagged once, got {entries}"
        e = entries[0]
        assert e["subject"] == f"sub-{SUBJECT}"
        assert e["session"] == f"ses-{SESSION}"
        assert e["task"] == f"task-{TASK}"
        assert e["run"] == f"run-{RUN}"
        assert e["action"] == "exclude"
        assert e["source"] == "motion"

    def test_clean_and_high_side_by_side(self, tmp_path):
        """Two stubs in one derivatives tree: only the high one is flagged.
        Proves the decision tracks the planted spikes, not the filename."""
        bids = tmp_path / "bids"
        deriv = bids / "derivatives" / "fmriprep_25.2.4"
        make_fmriprep_run(
            deriv, "s01", SESSION, TASK, RUN,
            space="MNI", n_trs=N_TRS, motion="clean", seed=1,
        )
        make_fmriprep_run(
            deriv, "s02", SESSION, TASK, RUN,
            space="MNI", n_trs=N_TRS, motion="high", seed=2,
        )
        entries = MotionGenerator().generate(
            "sim", {"bids_dir": str(bids)}, _motion_args()
        )
        flagged = {e["subject"] for e in entries}
        assert flagged == {"sub-s02"}, f"only sub-s02 should be flagged, got {flagged}"

    def test_rest_clean_not_flagged_high_fd_mean_flagged(self, tmp_path):
        """For rest scans the generator uses FD MEAN > fd_threshold (0.2), a
        different branch than the task proportion rule. A clean rest stub
        (fd_mean below threshold) is not flagged; a high one is."""
        bids = tmp_path / "bids"
        deriv = bids / "derivatives" / "fmriprep_25.2.4"
        make_fmriprep_run(
            deriv, "s01", SESSION, "rest", RUN,
            space="MNI", n_trs=N_TRS, motion="clean", seed=0,
        )
        make_fmriprep_run(
            deriv, "s02", SESSION, "rest", RUN,
            space="MNI", n_trs=N_TRS, motion="high", seed=0,
        )
        entries = MotionGenerator().generate(
            "sim", {"bids_dir": str(bids)}, _motion_args()
        )
        flagged = {e["subject"] for e in entries}
        assert "sub-s02" in flagged
        assert "sub-s01" not in flagged


# --------------------------------------------------------------------------- #
# Unit-level checks on the confounds writer.
# --------------------------------------------------------------------------- #
class TestConfoundsWriter:
    def test_columns_and_nan_first_row(self, tmp_path):
        """confounds TSV has framewise_displacement + std_dvars; FD's first
        row is NaN exactly as fmriprep writes it."""
        func = tmp_path / "func"
        func.mkdir()
        prefix = f"sub-{SUBJECT}_ses-{SESSION}_task-{TASK}_run-{RUN}"
        path = write_confounds_tsv(func, prefix=prefix, n_trs=N_TRS, seed=0)
        assert path.name == f"{prefix}_desc-confounds_timeseries.tsv"

        df = pd.read_csv(path, sep="\t")
        assert "framewise_displacement" in df.columns
        assert "std_dvars" in df.columns
        assert len(df) == N_TRS
        # fmriprep convention: first FD value is n/a (NaN after read).
        assert pd.isna(df["framewise_displacement"].iloc[0])
        # std_dvars first row is also n/a in fmriprep output.
        assert pd.isna(df["std_dvars"].iloc[0])

    def test_spikes_controllable(self, tmp_path):
        """fd_spikes plants exactly that many FD>0.5 frames; with 30/100 the
        task proportion (0.30) clears the 0.2 threshold."""
        func = tmp_path / "func"
        func.mkdir()
        prefix = f"sub-{SUBJECT}_ses-{SESSION}_task-{TASK}_run-{RUN}"
        path = write_confounds_tsv(
            func, prefix=prefix, n_trs=N_TRS, fd_mean=0.05,
            fd_spikes=30, dvars_spikes=0, seed=0,
        )
        df = pd.read_csv(path, sep="\t")
        fd = pd.to_numeric(df["framewise_displacement"], errors="coerce").dropna()
        prop = float((fd > 0.5).mean())
        assert prop == pytest.approx(30 / (N_TRS - 1), abs=1e-9)
        assert prop > 0.2


class TestBoldWriter:
    def test_writes_loadable_nifti_for_mni(self, tmp_path):
        """The MNI BOLD writer produces a 4D NIfTI nibabel can load with the
        expected number of timepoints, and the matching brain mask."""
        func = tmp_path / "func"
        func.mkdir()
        prefix = f"sub-{SUBJECT}_ses-{SESSION}_task-{TASK}_run-{RUN}"
        written = write_fmriprep_bold(
            func, prefix=prefix, space="MNI", n_trs=N_TRS, seed=0
        )
        bold = written["mni_data"]
        mask = written["mni_brain_mask"]
        assert bold.exists() and mask.exists()
        img = nib.load(str(bold))
        assert img.shape[-1] == N_TRS
        assert nib.load(str(mask)).ndim == 3
