"""Integration tests for src/neuro_workflow/qa/report.py orchestrator."""
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

from neuro_workflow.qa.report import build_reports
from neuro_workflow.qa.reliability_movies import MovieResult


def _build_fixture(tmp_path: Path) -> Path:
    """Build a minimal fmriprep derivatives tree with one subject + one scan."""
    deriv = tmp_path / "fmriprep_25.2.4"
    func_dir = deriv / "sub-s03" / "ses-01" / "func"
    func_dir.mkdir(parents=True)
    base = "sub-s03_ses-01_task-rest_run-1"

    # Confounds (the only file we actually parse)
    pd.DataFrame({
        "framewise_displacement": [None] + [0.1] * 9,
        "std_dvars": [None] + [1.0] * 9,
    }).to_csv(func_dir / f"{base}_desc-confounds_timeseries.tsv",
              sep="\t", index=False, na_rep="n/a")

    # Touch all expected outputs so check_expected_outputs returns complete
    for suffix in [
        f"{base}_desc-preproc_bold.nii.gz",
        f"{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz",
        f"{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz",
        f"{base}_space-T1w_desc-preproc_bold.nii.gz",
        f"{base}_hemi-L_space-fsaverage6_bold.func.gii",
        f"{base}_hemi-R_space-fsaverage6_bold.func.gii",
        f"{base}_hemi-L_space-fsnative_bold.func.gii",
        f"{base}_hemi-R_space-fsnative_bold.func.gii",
        f"{base}_space-fsLR_den-91k_bold.dtseries.nii",
    ]:
        (func_dir / suffix).touch()

    # FreeSurfer
    fs = deriv / "sourcedata" / "freesurfer" / "sub-s03_ses-01"
    (fs / "scripts").mkdir(parents=True)
    (fs / "stats").mkdir(parents=True)
    (fs / "scripts" / "recon-all-status.log").write_text(
        "recon-all -s sub-s03_ses-01 finished without error at ...\n")
    (fs / "scripts" / "recon-all.log").write_text(
        "orig.nofix lheno = -100, rheno = -80\n"
        "#@#%# recon-all-run-time-hours 9.5\n")
    (fs / "stats" / "aseg.stats").write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1100000.0, mm^3\n"
        "# Measure TotalGray, TotalGrayVol, Total gray matter volume, 600000.0, mm^3\n"
        "# Measure CerebralWhiteMatter, CerebralWhiteMatterVol, Cerebral White Matter Volume, 500000.0, mm^3\n"
        "# Measure CSF, CSFVol, CSF Volume, 1500.0, mm^3\n"
        "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n")
    return deriv


def test_build_reports_emits_cohort_and_subject_html(tmp_path):
    deriv = _build_fixture(tmp_path)
    out = tmp_path / "qa_html"

    with patch("neuro_workflow.qa.report.render_reliability_movies") as MV:
        MV.return_value = {"sub-s03": MovieResult(out / "movies/sub-s03.mp4", None)}
        build_reports(
            fmriprep_dir=deriv,
            output_dir=out,
            subjects=["sub-s03"],
            decisions_path=None,
            no_reliability_movies=False,
            euler_n_sigma=2.0,
        )

    assert (out / "cohort.html").is_file()
    assert (out / "cohort.tsv").is_file()
    assert (out / "subjects" / "sub-s03.html").is_file()


def test_build_reports_skips_brm_when_no_reliability_movies(tmp_path):
    deriv = _build_fixture(tmp_path)
    out = tmp_path / "qa_html"

    with patch("neuro_workflow.qa.report.render_reliability_movies") as MV:
        build_reports(
            fmriprep_dir=deriv,
            output_dir=out,
            subjects=["sub-s03"],
            decisions_path=None,
            no_reliability_movies=True,
            euler_n_sigma=2.0,
        )
        MV.assert_not_called()

    assert (out / "subjects" / "sub-s03.html").is_file()


def test_build_reports_renders_decision_from_tsv(tmp_path):
    deriv = _build_fixture(tmp_path)
    out = tmp_path / "qa_html"
    decisions = tmp_path / "decisions.tsv"
    decisions.write_text(
        "subject\tsession\ttask\trun\taction\treason\n"
        "sub-s03\t-\t-\t-\texclude\tmanual call\n"
    )

    with patch("neuro_workflow.qa.report.render_reliability_movies") as MV:
        MV.return_value = {"sub-s03": MovieResult(out / "movies/sub-s03.mp4", None)}
        build_reports(
            fmriprep_dir=deriv,
            output_dir=out,
            subjects=["sub-s03"],
            decisions_path=decisions,
            no_reliability_movies=False,
            euler_n_sigma=2.0,
        )

    cohort_html = (out / "cohort.html").read_text()
    assert "exclude" in cohort_html
    assert "manual call" in cohort_html
    # Excluded styling applied (see style.css):
    assert "excluded" in cohort_html
