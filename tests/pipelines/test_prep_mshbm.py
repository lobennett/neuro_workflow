from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.prep_mshbm import PrepMshbmPipeline
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_prep_mshbm_pipeline_is_registered():
    pipeline = get_pipeline("prep-mshbm")
    assert pipeline is not None
    assert pipeline.name == "prep-mshbm"


def test_prep_mshbm_has_no_docker_uri():
    p = PrepMshbmPipeline()
    assert p.docker_uri is None


def test_prep_mshbm_template_exists():
    p = PrepMshbmPipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_prep_mshbm_build_context(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\nsub-02\nsub-03\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["n_subjects"] == 3
    assert ctx["nthreads"] == 1
    assert ctx["mem_gb"] == 64
    assert ctx["time"] == "24:00:00"
    assert ctx["glm_dir"] == "/oak/lev1"
    assert ctx["fmriprep_dir"] == "/oak/fmriprep"
    assert ctx["residuals_space"] == "surface"
    assert ctx["extra_flags"] == ""
    assert ctx["mail_line"] == ""

    # Verify subject list file was written
    subject_list_file = Path(ctx["subject_list_file"])
    assert subject_list_file.exists()
    assert subject_list_file.read_text() == "sub-01\nsub-02\nsub-03\n"


def test_prep_mshbm_build_context_with_extras(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\nsub-02\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": "user@stanford.edu",
    }
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir="/oak/rest_fmriprep",
        output_dir=str(tmp_path / "out"),
        residuals_space="MNI",
        sessions=["ses-01", "ses-02"],
        nthreads=4,
        mem_gb=128,
        time="48:00:00",
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["nthreads"] == 4
    assert ctx["mem_gb"] == 128
    assert ctx["time"] == "48:00:00"
    assert "--rest-fmriprep-dir /oak/rest_fmriprep" in ctx["extra_flags"]
    assert "--sessions ses-01 ses-02" in ctx["extra_flags"]
    assert "#SBATCH --mail-user=user@stanford.edu" in ctx["mail_line"]
    assert "#SBATCH --mail-type=ALL" in ctx["mail_line"]


def test_prep_mshbm_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\nsub-02\nsub-03\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH -J prep_mshbm_test_ds" in script
    assert "#SBATCH --array=1-3" in script
    assert "#SBATCH --mem=64G" in script
    assert "--glm-dir \"/oak/lev1\"" in script
    assert "--fmriprep-dir \"/oak/fmriprep\"" in script
    assert "--residuals-space surface" in script
    assert "--mail-user" not in script
