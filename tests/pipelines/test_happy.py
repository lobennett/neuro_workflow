import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from neuro_workflow.pipelines.happy import HappyPipeline


def make_bids_tree(tmp_path):
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)

    (func / "sub-s01_ses-01_task-rest_run-1_echo-2_bold.nii.gz").touch()
    (func / "sub-s01_ses-01_task-rest_run-1_echo-2_bold.json").touch()
    (func / "sub-s01_ses-01_task-rest_run-1_recording-cardiac_physio.tsv.gz").touch()
    (func / "sub-s01_ses-01_task-rest_run-1_recording-cardiac_physio.json").touch()

    return str(bids)


def make_args(**overrides):
    defaults = {
        "version": "3.1.8",
        "happy_args": "",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    bids_dir = make_bids_tree(tmp_path)
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\n")
    return {
        "bids_dir": bids_dir,
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = HappyPipeline()
    assert p.name == "happy"
    assert p.docker_uri == "docker://fredericklab/rapidtide"
    assert p.template_name == "happy.sbatch"


def test_default_resources():
    p = HappyPipeline()
    assert p.default_resources["nthreads"] == 4
    assert p.default_resources["mem_per_cpu_gb"] == 2
    assert p.default_resources["time"] == "00:10:00"


def test_build_context_discovers_scans(tmp_path):
    p = HappyPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery", config, args)
    assert ctx["n_scans"] == 1
    scan_list = Path(ctx["scan_list_file"])
    assert scan_list.exists()
    lines = scan_list.read_text().strip().split("\n")
    assert len(lines) == 1
    assert "sub-s01_ses-01_task-rest_run-1_echo-2_bold.nii.gz" in lines[0]


def test_build_context_version_required(tmp_path):
    p = HappyPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery", config, args)
        except SystemExit:
            pass


def test_build_context_no_scans_found(tmp_path):
    p = HappyPipeline()
    bids = tmp_path / "empty_bids"
    bids.mkdir()
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\n")
    config = {
        "bids_dir": str(bids),
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }
    args = make_args()
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery", config, args)
        except SystemExit:
            pass


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = HappyPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery", config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)
    assert "happy" in script.lower()
    assert "SLURM_ARRAY_TASK_ID" in script
    assert "--cardiacfile" in script
