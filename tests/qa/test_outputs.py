"""Tests for src/neuro_workflow/qa/metrics/outputs.py."""

from neuro_workflow.qa.metrics.outputs import (
    OutputCheckResult,
    ScanID,
    check_expected_outputs,
)


def _make_scan_outputs(
    tmp_path, subject="sub-s03", session="ses-01", task="rest", run="1", spaces=None
):
    """Build a fake fmriprep derivatives tree with the listed output spaces."""
    func_dir = tmp_path / subject / session / "func"
    func_dir.mkdir(parents=True)
    base = f"{subject}_{session}_task-{task}_run-{run}"
    spaces = spaces or [""]  # "" = bold ref space (no _space- suffix)

    for space in spaces:
        if space.endswith("hemi-L_fsaverage6") or space.endswith("hemi-R_fsaverage6"):
            hemi = "L" if "hemi-L" in space else "R"
            (func_dir / f"{base}_hemi-{hemi}_space-fsaverage6_bold.func.gii").touch()
        elif space.endswith("hemi-L_fsnative") or space.endswith("hemi-R_fsnative"):
            hemi = "L" if "hemi-L" in space else "R"
            (func_dir / f"{base}_hemi-{hemi}_space-fsnative_bold.func.gii").touch()
        elif space == "fsLR_91k":
            (func_dir / f"{base}_space-fsLR_den-91k_bold.dtseries.nii").touch()
        elif space == "":
            (func_dir / f"{base}_desc-preproc_bold.nii.gz").touch()
        elif space.startswith("MNI152NLin2009cAsym_res-1"):
            (func_dir / f"{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz").touch()
        elif space.startswith("MNI152NLin6Asym_res-2"):
            (func_dir / f"{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz").touch()
        elif space == "T1w":
            (func_dir / f"{base}_space-T1w_desc-preproc_bold.nii.gz").touch()
        elif space == "confounds":
            (func_dir / f"{base}_desc-confounds_timeseries.tsv").touch()
    return tmp_path


def test_check_expected_outputs_complete(tmp_path):
    fmriprep = _make_scan_outputs(
        tmp_path,
        spaces=[
            "",
            "MNI152NLin2009cAsym_res-1",
            "MNI152NLin6Asym_res-2",
            "T1w",
            "hemi-L_fsaverage6",
            "hemi-R_fsaverage6",
            "hemi-L_fsnative",
            "hemi-R_fsnative",
            "fsLR_91k",
            "confounds",
        ],
    )
    result = check_expected_outputs(fmriprep, ScanID("sub-s03", "ses-01", "rest", "1"))
    assert result.complete
    assert result.missing == []


def test_check_expected_outputs_missing_some(tmp_path):
    # Only the bold ref + confounds; no MNI / surface / CIFTI
    fmriprep = _make_scan_outputs(tmp_path, spaces=["", "confounds"])
    result = check_expected_outputs(fmriprep, ScanID("sub-s03", "ses-01", "rest", "1"))
    assert not result.complete
    assert any("MNI152NLin2009cAsym" in m for m in result.missing)
    assert any("fsLR" in m for m in result.missing)


def test_check_expected_outputs_no_files_at_all(tmp_path):
    result = check_expected_outputs(tmp_path, ScanID("sub-s03", "ses-01", "rest", "1"))
    assert not result.complete
    assert len(result.missing) == 10  # all expected outputs missing
