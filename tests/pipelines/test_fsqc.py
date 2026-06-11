from argparse import Namespace

import pytest

from neuro_workflow.pipelines.fsqc import FsqcPipeline


def make_args(**overrides):
    defaults = {
        "version": "2.1.4",
        "freesurfer_dir": "/data/derivatives/freesurfer",
        "fsqc_args": "",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\ns02\n")
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = FsqcPipeline()
    assert p.name == "fsqc"
    assert p.docker_uri == "docker://deepmi/fsqc"
    assert p.template_name == "fsqc.sbatch"


def test_default_resources():
    p = FsqcPipeline()
    assert p.default_resources["nthreads"] == 4
    assert p.default_resources["mem_per_cpu_gb"] == 8
    assert p.default_resources["time"] == "2-00:00:00"


def test_build_context_basic(tmp_path):
    """Ad-hoc (non-canonical) dataset name falls back to the registered
    subjects_file. Subject list comes from that file (s01, s02)."""
    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("adhoc_ds", config, args)
    assert ctx["dataset_name"] == "adhoc_ds"
    assert ctx["freesurfer_dir"] == "/data/derivatives/freesurfer"
    assert ctx["image_path"] == "/images/fsqc_2.1.4.sif"
    assert "sub-s01 sub-s02" == ctx["subjects_list"]


def test_build_context_resolves_canonical_sample(tmp_path):
    """A canonical sample name (discovery) resolves its 5 subjects from
    pipeline_config.json `samples`, ignoring any registered subjects_file."""
    p = FsqcPipeline()
    config = make_config(tmp_path)  # registered file has only s01,s02
    args = make_args()
    ctx = p.build_context("discovery", config, args)
    assert ctx["subjects_list"] == "sub-s03 sub-s10 sub-s19 sub-s29 sub-s43"


def test_build_context_version_required(tmp_path):
    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with pytest.raises(SystemExit):
        p.build_context("validation", config, args)


def test_build_context_freesurfer_dir_required(tmp_path):
    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args(freesurfer_dir=None)
    with pytest.raises(SystemExit):
        p.build_context("validation", config, args)


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("adhoc_ds", config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)
    assert "xvfb-run" in script
    assert "fsqc" in script
    assert "--subjects sub-s01 sub-s02" in script
