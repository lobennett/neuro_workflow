from argparse import Namespace
from pathlib import Path

import pytest

from neuro_workflow.analysis.task_config.loader import get_all_tasks, get_base_tasks, get_dual_tasks
from neuro_workflow.core.slurm import render_template
from neuro_workflow.pipelines.base import TEMPLATE_DIR, get_pipeline
from neuro_workflow.pipelines.lev1 import Lev1Pipeline


def test_lev1_build_context_no_exclusions_file_and_no_compiled_exits(tmp_path, monkeypatch):
    """With --exclusions-file unset AND no compiled exclusions for the dataset,
    build_context must sys.exit(1) (the 'run exclusions compile first' guard),
    not silently proceed with no exclusions."""
    # Redirect the exclusions store so _compiled_path points at an empty tmp dir
    # (guarantees no compiled file exists for this dataset; never touches the
    # real ~/.config store).
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path / "exclusions")
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=None,  # the branch under test
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    with pytest.raises(SystemExit):
        p.build_context("brand_new_dataset_no_compiled", dataset_config, args)


def test_lev1_pipeline_is_registered():
    pipeline = get_pipeline("lev1")
    assert pipeline is not None
    assert pipeline.name == "lev1"


def test_lev1_has_no_docker_uri():
    p = Lev1Pipeline()
    assert p.docker_uri is None


def test_lev1_default_resources():
    p = Lev1Pipeline()
    assert p.default_resources["nthreads"] == 1
    assert p.default_resources["mem_gb"] == 64
    assert p.default_resources["time"] == "2-00:00:00"


def test_lev1_template_exists():
    p = Lev1Pipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_lev1_task_constants():
    assert len(get_base_tasks()) == 8
    assert len(get_dual_tasks()) == 10
    assert get_all_tasks() == get_base_tasks() + get_dual_tasks()


def test_lev1_build_context_base_tasks(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=None,
        tasks_flag="base",
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["n_jobs"] == 16  # 2 subjects x 8 base tasks
    assert ctx["dataset_name"] == "test_ds"

    # Verify job list file was written
    job_list = Path(ctx["job_list_file"])
    assert job_list.exists()
    lines = [ln for ln in job_list.read_text().strip().split("\n") if ln]
    assert len(lines) == 16


def test_lev1_build_context_explicit_tasks(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=["flanker", "nBack"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["n_jobs"] == 2  # 1 subject x 2 tasks
    job_list = Path(ctx["job_list_file"])
    lines = job_list.read_text().strip().split("\n")
    assert lines[0] == "s03 flanker"
    assert lines[1] == "s03 nBack"


def test_lev1_build_context_extra_flags(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": "user@stanford.edu",
    }
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=5.0,
        residuals=True,
        fc_confounds=True,
        skip_existing=True,
        nthreads=4,
        mem_gb=128,
        time="3-00:00:00",
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    # Extra flags
    assert "--smoothing-fwhm 5.0" in ctx["extra_flags"]
    assert "--residuals" in ctx["extra_flags"]
    assert "--fc-confounds" in ctx["extra_flags"]
    assert "--skip-existing" in ctx["extra_flags"]

    # Mail line
    assert "#SBATCH --mail-user=user@stanford.edu" in ctx["mail_line"]
    assert "#SBATCH --mail-type=ALL" in ctx["mail_line"]

    # Resource overrides
    assert ctx["nthreads"] == 4
    assert ctx["mem_gb"] == 128
    assert ctx["time"] == "3-00:00:00"


def test_lev1_build_context_default_results_dir(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    bids_dir = str(tmp_path / "bids")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": bids_dir,
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=None,
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    expected = str(Path(bids_dir) / "derivatives" / "lev1")
    assert ctx["results_dir"] == expected


def test_lev1_build_context_resolves_canonical_discovery_subjects(tmp_path):
    """V2 unblock: lev1 build_context resolves discovery's 5 canonical subjects
    from pipeline_config.json `samples`, WITHOUT any subjects_*.txt file. The
    job_list pairs each of the 5 subjects with each requested task."""
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        # Bogus/missing registered file: must be ignored for a known sample.
        "subjects_file": "subjects_discovery.txt",
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="surface",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("discovery", dataset_config, args)

    # 5 discovery subjects x 1 task = 5 jobs
    assert ctx["n_jobs"] == 5
    job_list = Path(ctx["job_list_file"])
    subs_in_jobs = [line.split()[0] for line in job_list.read_text().split()[::2]]
    assert subs_in_jobs == ["s03", "s10", "s19", "s29", "s43"]


def test_lev1_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=None,
        tasks_flag="base",
        fmriprep_dir="/oak/data/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH -J lev1_test_ds" in script
    assert "#SBATCH --array=1-16" in script
    assert "#SBATCH --cpus-per-task=1" in script
    assert "#SBATCH --mem=64G" in script
    assert "#SBATCH --time=2-00:00:00" in script
    assert "#SBATCH -p russpold" in script
    assert "neuro_workflow.analysis.lev1.run" in script
    assert "--space MNI" in script
    assert "--within-subject-threshold 1.0" in script
    assert "--mail-user" not in script
