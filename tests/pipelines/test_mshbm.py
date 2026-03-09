from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.mshbm import MshbmPipeline
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_mshbm_pipeline_is_registered():
    pipeline = get_pipeline("mshbm")
    assert pipeline is not None
    assert pipeline.name == "mshbm"


def test_mshbm_has_no_docker_uri():
    p = MshbmPipeline()
    assert p.docker_uri is None


def test_mshbm_template_exists():
    p = MshbmPipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_mshbm_build_context(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\nsub-02\nsub-03\n")

    p = MshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        surface_inputs_dir="/scratch/surface_inputs",
        output_dir=str(tmp_path / "mshbm_out"),
        mshbm_dir="/home/user/PrecisionNetworkMapping",
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["nthreads"] == 1
    assert ctx["mem_gb"] == 64
    assert ctx["time"] == "24:00:00"
    assert ctx["surface_inputs_dir"] == "/scratch/surface_inputs"
    assert ctx["mshbm_dir"] == "/home/user/PrecisionNetworkMapping"
    assert ctx["mail_line"] == ""

    # Verify sub_list_file written with correct subjects
    sub_list_file = Path(ctx["sub_list_file"])
    assert sub_list_file.exists()
    assert sub_list_file.read_text() == "sub-01\nsub-02\nsub-03\n"


def test_mshbm_build_context_default_mshbm_dir(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\n")

    p = MshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        surface_inputs_dir="/scratch/surface_inputs",
        output_dir=str(tmp_path / "mshbm_out"),
        mshbm_dir=None,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert "PrecisionNetworkMapping" in ctx["mshbm_dir"]


def test_mshbm_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\nsub-02\n")

    p = MshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        surface_inputs_dir="/scratch/surface_inputs",
        output_dir=str(tmp_path / "mshbm_out"),
        mshbm_dir="/home/user/PrecisionNetworkMapping",
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH --job-name=mshbm_test_ds" in script
    assert "#SBATCH --mem=64G" in script
    assert "run_MSHBM.sh" in script
    assert "/home/user/PrecisionNetworkMapping" in script
    assert "--mail-user" not in script
