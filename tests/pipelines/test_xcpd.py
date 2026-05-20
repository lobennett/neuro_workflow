import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from neuro_workflow.pipelines.xcpd import XcpdPipeline


def make_args(**overrides):
    defaults = {
        "version": "26.0.2",
        "fmriprep_version": "25.2.4",
        "xcpd_args": "",
        "fs_license": "~/license.txt",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
        "array_throttle": 8,
        "partition": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s10\ns19\ns29\n")
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "bigmem",
        "image_dir": "/images",
        "templateflow_dir": "/templateflow",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = XcpdPipeline()
    assert p.name == "xcpd"
    assert p.docker_uri == "docker://pennlinc/xcp_d"
    assert p.template_name == "xcpd.sbatch"


def test_default_resources():
    p = XcpdPipeline()
    assert p.default_resources["nthreads"] == 16
    assert p.default_resources["mem_per_cpu_gb"] == 24
    assert p.default_resources["time"] == "1-00:00:00"


def test_build_context_basic(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery_xcpd", config, args)
    assert ctx["dataset_name"] == "discovery_xcpd"
    assert ctx["n_subjects"] == 3
    assert ctx["nthreads"] == 16
    assert ctx["mem_per_cpu_gb"] == 24
    assert ctx["image_path"] == "/images/xcpd_26.0.2.sif"
    assert ctx["xcpd_version"] == "26.0.2"
    assert ctx["fmriprep_dir"].endswith("derivatives/fmriprep_25.2.4")
    assert ctx["output_dir"].endswith("derivatives/xcp_d_26.0.2")
    assert ctx["array_throttle"] == 8


def test_build_context_version_required(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery_xcpd", config, args)
        except SystemExit:
            return
    assert False, "expected SystemExit"


def test_build_context_custom_resources(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args(nthreads=8, mem_per_cpu_gb=32, time="12:00:00", array_throttle=4)
    ctx = p.build_context("discovery_xcpd", config, args)
    assert ctx["nthreads"] == 8
    assert ctx["mem_per_cpu_gb"] == 32
    assert ctx["time"] == "12:00:00"
    assert ctx["array_throttle"] == 4


def test_build_context_custom_fmriprep_version(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args(fmriprep_version="24.1.1")
    ctx = p.build_context("discovery_xcpd", config, args)
    assert ctx["fmriprep_dir"].endswith("derivatives/fmriprep_24.1.1")


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery_xcpd", config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)
    assert "--mode abcd" in script
    assert "--combine-runs" in script
    assert "--band-stop-min 12" in script
    assert "--motion-filter-type notch" in script
    assert "--participant-label" in script
    assert "{" not in script.replace("${SLURM_ARRAY_TASK_ID}", "").replace("${subject}", "")
    assert "apptainer run" in script
