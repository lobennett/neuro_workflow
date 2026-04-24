import os
from argparse import Namespace
from pathlib import Path
from neuro_workflow.pipelines.fmriprep import FmriprepPipeline
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_fmriprep_pipeline_is_registered():
    pipeline = get_pipeline("fmriprep")
    assert pipeline is not None
    assert pipeline.name == "fmriprep"


def test_fmriprep_has_correct_docker_uri():
    p = FmriprepPipeline()
    assert p.docker_uri == "docker://nipreps/fmriprep"


def test_fmriprep_default_resources():
    p = FmriprepPipeline()
    assert p.default_resources["nthreads"] == 8
    assert p.default_resources["mem_per_cpu_gb"] == 8
    assert p.default_resources["time"] == "5-00:00:00"


def test_fmriprep_template_exists():
    p = FmriprepPipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_fmriprep_build_context_basic(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/home/groups/russpold/templateflow",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2 fsnative",
        fmriprep_args="--no-submm-recon",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["n_subjects"] == 2
    assert ctx["nthreads"] == 8  # from default_resources
    assert ctx["mem_mb"] == 57600  # 8 * 8 * 1000 * 0.9
    assert ctx["fmriprep_version"] == "24.1.0"
    assert ctx["output_spaces"] == "MNI152NLin2009cAsym:res-2 fsnative"
    assert ctx["image_path"] == "/images/fmriprep_24.1.0.sif"
    assert ctx["mail_line"] == ""


def test_fmriprep_build_context_with_mail(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": "user@stanford.edu",
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "#SBATCH --mail-user=user@stanford.edu" in ctx["mail_line"]
    assert "#SBATCH --mail-type=ALL" in ctx["mail_line"]


def test_fmriprep_build_context_with_bids_filter(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file="/home/user/filter.json",
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "-B /home/user:/config" in ctx["config_bind_line"]
    assert ctx["bids_filter_arg"] == "--bids-filter-file /config/filter.json"


def test_fmriprep_build_context_override_resources(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=4,
        mem_per_cpu_gb=16,
        time="2-00:00:00",
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["nthreads"] == 4
    assert ctx["mem_per_cpu_gb"] == 16
    assert ctx["time"] == "2-00:00:00"
    assert ctx["mem_mb"] == int(4 * 16 * 1000 * 0.9)


def test_fmriprep_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/home/groups/russpold/templateflow",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2 fsnative",
        fmriprep_args="--no-submm-recon",
        fs_license="/home/user/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH -J fmriprep_test_ds" in script
    assert "#SBATCH --array=1-2" in script
    assert "--participant-label \"$subject\"" in script
    assert "/images/fmriprep_24.1.0.sif" in script
    assert "--no-submm-recon" in script
    assert "--output-spaces MNI152NLin2009cAsym:res-2 fsnative" in script
    assert "--mail-user" not in script
    assert "--mem_mb 57600" in script


def test_fmriprep_output_dir_default(tmp_path):
    """When --output-dir is not set, derivatives land inside the BIDS bind."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["output_bind_line"] == ""
    assert ctx["output_container"] == "/data/derivatives"
    assert ctx["log_dir"] == "/oak/data/bids/derivatives/fmriprep_24.1.0/logs"


def test_fmriprep_output_dir_override(tmp_path):
    """When --output-dir is set, derivatives land in a bound external path."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.5",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir="/scratch/users/logben/fmriprep_bug_repro",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "-B /scratch/users/logben/fmriprep_bug_repro:/out" in ctx["output_bind_line"]
    assert ctx["output_container"] == "/out"
    assert ctx["log_dir"] == "/scratch/users/logben/fmriprep_bug_repro/fmriprep_25.2.5/logs"


def test_fmriprep_render_with_output_dir(tmp_path):
    """Full render with --output-dir does NOT write into BIDS derivatives."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.5",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="/home/user/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir="/scratch/users/logben/fmriprep_bug_repro",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "-B /scratch/users/logben/fmriprep_bug_repro:/out" in script
    assert "/out/fmriprep_25.2.5" in script
    assert "/data/derivatives" not in script
