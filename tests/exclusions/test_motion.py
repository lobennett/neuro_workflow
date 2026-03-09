from argparse import Namespace
from pathlib import Path

from neuro_workflow.exclusions.motion import MotionGenerator


def _make_confounds_tsv(func_dir, subject, session, task, run, fd_values, dvars_values):
    """Create a minimal confounds TSV with framewise_displacement and dvars columns."""
    filename = f"{subject}_{session}_task-{task}_run-{run}_desc-confounds_timeseries.tsv"
    lines = ["framewise_displacement\tdvars"]
    for fd, dv in zip(fd_values, dvars_values):
        lines.append(f"{fd}\t{dv}")
    (func_dir / filename).write_text("\n".join(lines))


def _make_deriv_tree(tmp_path, version="24.1.0rc2"):
    """Create a BIDS derivatives tree with confound files."""
    deriv = tmp_path / "bids" / "derivatives" / f"fmriprep_{version}"

    # Good scan (low motion)
    func1 = deriv / "sub-s01" / "ses-01" / "func"
    func1.mkdir(parents=True)
    _make_confounds_tsv(func1, "sub-s01", "ses-01", "flanker", "1",
                        [0.1] * 100, [1.0] * 100)

    # Bad scan (high FD proportion)
    func2 = deriv / "sub-s02" / "ses-01" / "func"
    func2.mkdir(parents=True)
    _make_confounds_tsv(func2, "sub-s02", "ses-01", "flanker", "1",
                        [0.6] * 100, [1.0] * 100)  # all FD > 0.5

    # Bad resting-state (high FD mean)
    func3 = deriv / "sub-s03" / "ses-01" / "func"
    func3.mkdir(parents=True)
    _make_confounds_tsv(func3, "sub-s03", "ses-01", "rest", "1",
                        [0.25] * 100, [1.0] * 100)  # mean FD = 0.25 > 0.2

    return str(tmp_path / "bids")


def test_generator_attributes():
    g = MotionGenerator()
    assert g.name == "motion"
    assert g.description


def test_generate_finds_bad_scans(tmp_path):
    bids_dir = _make_deriv_tree(tmp_path)
    g = MotionGenerator()
    config = {"bids_dir": bids_dir}
    args = Namespace(
        fmriprep_version="24.1.0rc2",
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


def test_generate_all_actions_are_exclude(tmp_path):
    bids_dir = _make_deriv_tree(tmp_path)
    g = MotionGenerator()
    config = {"bids_dir": bids_dir}
    args = Namespace(
        fmriprep_version="24.1.0rc2",
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    entries = g.generate("discovery", config, args)
    assert all(e["action"] == "exclude" for e in entries)
    assert all(e["source"] == "motion" for e in entries)
