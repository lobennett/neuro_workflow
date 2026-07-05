"""Tests for scripts/build_xcpd_view.py plan_links logic."""
from pathlib import Path


def _touch(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")


def _make_fmriprep_tree(root: Path):
    """Minimal fMRIPrep-output layout: subject-level figures, session-level
    anat/func/fmap, and a ses-multi-*/log."""
    sub = root / "sub-s10"
    _touch(sub / "figures" / "fig1.svg")
    # ses-01: anat (whole-dir) + func (2 scans) + fmap
    _touch(sub / "ses-01" / "anat" / "sub-s10_ses-01_T1w.nii.gz")
    _touch(sub / "ses-01" / "func" / "sub-s10_ses-01_task-rest_run-1_desc-preproc_bold.nii.gz")
    _touch(sub / "ses-01" / "func" / "sub-s10_ses-01_task-flanker_run-1_desc-preproc_bold.nii.gz")
    _touch(sub / "ses-01" / "fmap" / "sub-s10_ses-01_acq-x_epi.nii.gz")
    # ses-multi: log
    _touch(sub / "ses-multi-abcd" / "log" / "run.log")
    _touch(root / "dataset_description.json")
    _touch(root / ".bidsignore")


def test_plan_links_drops_excluded_scan_keeps_others(tmp_path):
    from scripts.build_xcpd_view import plan_links

    fmriprep = tmp_path / "fmriprep_25.2.4"
    _make_fmriprep_tree(fmriprep)
    view = tmp_path / "xcp_d_input"
    drop = {"sub-s10_ses-01_task-rest_run-1"}  # exclude the rest scan

    links = plan_links(fmriprep, view, drop)
    targets = {p.relative_to(view).as_posix() for p in links}

    # excluded rest func file dropped; kept flanker func file present
    assert "sub-s10/ses-01/func/sub-s10_ses-01_task-flanker_run-1_desc-preproc_bold.nii.gz" in targets
    assert not any("task-rest_run-1" in t for t in targets)
    # anat is whole-dir (the dir itself is linked, not its files)
    assert "sub-s10/ses-01/anat" in targets
    assert "sub-s10/ses-01/func/sub-s10_ses-01_task-rest_run-1_desc-preproc_bold.nii.gz" not in targets
    # log whole-dir + subject-level figures + fmap file + top-level metadata
    assert "sub-s10/ses-multi-abcd/log" in targets
    assert "sub-s10/figures" in targets
    assert "sub-s10/ses-01/fmap/sub-s10_ses-01_acq-x_epi.nii.gz" in targets
    assert "dataset_description.json" in targets
    assert ".bidsignore" in targets


def test_plan_links_fmap_without_scankey_kept(tmp_path):
    from scripts.build_xcpd_view import plan_links

    fmriprep = tmp_path / "fmriprep_25.2.4"
    _make_fmriprep_tree(fmriprep)
    view = tmp_path / "xcp_d_input"
    # even if some task scan is excluded, a fieldmap with no task/run key survives
    links = plan_links(fmriprep, view, {"sub-s10_ses-01_task-flanker_run-1"})
    targets = {p.relative_to(view).as_posix() for p in links}
    assert "sub-s10/ses-01/fmap/sub-s10_ses-01_acq-x_epi.nii.gz" in targets
    assert not any("task-flanker_run-1" in t for t in targets)
