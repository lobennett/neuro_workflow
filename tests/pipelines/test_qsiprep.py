from argparse import Namespace
from unittest.mock import patch

from neuro_workflow.pipelines.qsiprep import QsiprepPipeline


def make_args(**overrides):
    defaults = {
        "version": "1.1.1",
        "output_resolution": 1.5,
        "qsiprep_args": "",
        "fs_license": "~/license.txt",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\ns02\ns03\n")
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/templateflow",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = QsiprepPipeline()
    assert p.name == "qsiprep"
    assert p.docker_uri == "docker://pennlinc/qsiprep"
    assert p.template_name == "qsiprep.sbatch"


def test_default_resources():
    p = QsiprepPipeline()
    assert p.default_resources["nthreads"] == 8
    assert p.default_resources["mem_per_cpu_gb"] == 8
    assert p.default_resources["time"] == "24:00:00"


def test_build_context_basic(tmp_path):
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("personal", config, args)
    assert ctx["dataset_name"] == "personal"
    assert ctx["n_subjects"] == 3
    assert ctx["nthreads"] == 8
    assert ctx["output_resolution"] == 1.5
    assert ctx["image_path"] == "/images/qsiprep_1.1.1.sif"
    assert ctx["qsiprep_version"] == "1.1.1"


def test_build_context_version_required(tmp_path):
    import sys

    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit) as mock_exit:
        try:
            p.build_context("personal", config, args)
        except SystemExit:
            pass
    mock_exit.assert_called_once_with(1)


def test_build_context_custom_resources(tmp_path):
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args(nthreads=4, mem_per_cpu_gb=4, time="12:00:00")
    ctx = p.build_context("personal", config, args)
    assert ctx["nthreads"] == 4
    assert ctx["mem_per_cpu_gb"] == 4
    assert ctx["time"] == "12:00:00"


def test_build_context_mail_line(tmp_path):
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    config["mail_user"] = "user@example.com"
    args = make_args()
    ctx = p.build_context("personal", config, args)
    assert "user@example.com" in ctx["mail_line"]


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("personal", config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)
    assert "qsiprep" in script
    assert "--output-resolution 1.5" in script
    assert "apptainer run" in script
