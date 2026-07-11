from argparse import Namespace

from neuro_workflow.exclusions.motion import MotionGenerator


def _make_confounds_tsv(func_dir, subject, session, task, run, fd_values, dvars_values):
    """Create a minimal confounds TSV with framewise_displacement and dvars columns."""
    filename = f"{subject}_{session}_task-{task}_run-{run}_desc-confounds_timeseries.tsv"
    lines = ["framewise_displacement\tdvars"]
    for fd, dv in zip(fd_values, dvars_values, strict=False):
        lines.append(f"{fd}\t{dv}")
    (func_dir / filename).write_text("\n".join(lines))


def _make_deriv_tree(tmp_path, version="25.2.4"):
    """Create a BIDS derivatives tree with confound files."""
    deriv = tmp_path / "bids" / "derivatives" / f"fmriprep_{version}"

    # Good scan (low motion)
    func1 = deriv / "sub-s01" / "ses-01" / "func"
    func1.mkdir(parents=True)
    _make_confounds_tsv(func1, "sub-s01", "ses-01", "flanker", "1", [0.1] * 100, [1.0] * 100)

    # Bad scan (high FD proportion)
    func2 = deriv / "sub-s02" / "ses-01" / "func"
    func2.mkdir(parents=True)
    _make_confounds_tsv(
        func2, "sub-s02", "ses-01", "flanker", "1", [0.6] * 100, [1.0] * 100
    )  # all FD > 0.5

    # Bad resting-state (high FD mean)
    func3 = deriv / "sub-s03" / "ses-01" / "func"
    func3.mkdir(parents=True)
    _make_confounds_tsv(
        func3, "sub-s03", "ses-01", "rest", "1", [0.25] * 100, [1.0] * 100
    )  # mean FD = 0.25 > 0.2

    return str(tmp_path / "bids")


def test_generator_attributes():
    g = MotionGenerator()
    assert g.name == "motion"
    assert g.description


def test_fmriprep_version_default_is_current():
    """The recorded fMRIPrep version default must match the actual derivatives (25.2.4),
    not the stale 24.1.0rc2 — provenance-string correctness."""
    import argparse

    parser = argparse.ArgumentParser()
    MotionGenerator().add_cli_args(parser)
    ns = parser.parse_args([])
    assert ns.fmriprep_version == "25.2.4"


def test_generate_finds_bad_scans(tmp_path):
    bids_dir = _make_deriv_tree(tmp_path)
    g = MotionGenerator()
    config = {"bids_dir": bids_dir}
    args = Namespace(
        fmriprep_version="25.2.4",
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    entries = g.generate("discovery", config, args)
    subjects = {e["subject"] for e in entries}
    # sub-s02 (high FD proportion) and sub-s03 (high rest FD mean) should be flagged
    assert "sub-s02" in subjects
    assert "sub-s03" in subjects
    # sub-s01 should NOT be flagged
    assert "sub-s01" not in subjects


def test_generate_uses_std_dvars_not_raw_dvars(tmp_path):
    """The generator must read fmriprep's standardized DVARS (`std_dvars`),
    not the raw-intensity `dvars` column. Threshold ">1.5" is the standardized
    convention; raw dvars is in BOLD-intensity units (~10s-100s) and would
    flag every scan if used. qa_report.metrics.motion already uses std_dvars
    (qa/metrics/motion.py:34); the generator must agree.
    """
    deriv = tmp_path / "bids" / "derivatives" / "fmriprep_25.2.4"
    func = deriv / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    # Realistic fmriprep numbers: raw dvars ~18 (always >1.5), std_dvars ~1.1 (<1.5)
    fname = "sub-s01_ses-01_task-flanker_run-1_desc-confounds_timeseries.tsv"
    rows = ["framewise_displacement\tdvars\tstd_dvars"]
    for _ in range(100):
        rows.append("0.10\t18.0\t1.10")
    (func / fname).write_text("\n".join(rows))

    g = MotionGenerator()
    config = {"bids_dir": str(tmp_path / "bids")}
    args = Namespace(
        fmriprep_version="25.2.4",
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    entries = g.generate("discovery", config, args)
    # Reading raw `dvars` would yield prop>1.5 = 1.0 and flag the scan.
    # Reading `std_dvars` (1.10 < 1.5) yields prop = 0.0 and produces no entry.
    assert (
        entries == []
    ), f"Expected no exclusions when std_dvars=1.10 is below threshold; got {entries}"


def test_generate_raises_on_missing_or_empty_derivatives(tmp_path):
    """A wrong --fmriprep-version (or fMRIPrep not run) leaves the derivatives
    glob empty. The generator must fail loud rather than silently return [] and
    let compile record `motion: 0` — that would silently under-exclude."""
    import pytest

    (tmp_path / "bids").mkdir()
    g = MotionGenerator()
    args = Namespace(
        fmriprep_version="99.9.9",  # no such derivatives dir
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    with pytest.raises(FileNotFoundError):
        g.generate("discovery", {"bids_dir": str(tmp_path / "bids")}, args)


def test_generate_all_actions_are_exclude(tmp_path):
    bids_dir = _make_deriv_tree(tmp_path)
    g = MotionGenerator()
    config = {"bids_dir": bids_dir}
    args = Namespace(
        fmriprep_version="25.2.4",
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    entries = g.generate("discovery", config, args)
    assert all(e["action"] == "exclude" for e in entries)
    assert all(e["source"] == "motion" for e in entries)
