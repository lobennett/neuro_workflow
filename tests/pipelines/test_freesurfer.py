from argparse import Namespace

import pytest

from neuro_workflow.pipelines.freesurfer import FreesurferPipeline


def make_csv(tmp_path):
    csv = tmp_path / "subs_fs.csv"
    csv.write_text("s03,ses-01,1,ses-01,1\ns04,ses-02,1,,\n")
    return str(csv)


def make_args(tmp_path, **overrides):
    defaults = {
        "version": "8.1.0",
        "subjects_file": make_csv(tmp_path),
        "fs_license": "~/license.txt",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(tmp_path / "subs.txt"),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = FreesurferPipeline()
    assert p.name == "freesurfer"
    assert p.template_name == "freesurfer.sbatch"


def test_default_resources():
    p = FreesurferPipeline()
    assert p.default_resources["nthreads"] == 4
    assert p.default_resources["mem_per_cpu_gb"] == 16
    assert p.default_resources["time"] == "4-00:00:00"


def test_build_context_basic(tmp_path):
    p = FreesurferPipeline()
    config = make_config(tmp_path)
    args = make_args(tmp_path)
    ctx = p.build_context("discovery", config, args)
    assert ctx["dataset_name"] == "discovery"
    assert ctx["n_subjects"] == 2
    assert ctx["image_path"] == "/images/freesurfer_8.1.0.sif"
    assert ctx["fs_subjects_file"] == args.subjects_file


def test_build_context_version_required(tmp_path):
    p = FreesurferPipeline()
    config = make_config(tmp_path)
    args = make_args(tmp_path, version=None)
    with pytest.raises(SystemExit):
        p.build_context("discovery", config, args)


def test_n_subjects_equals_data_rows_and_ignores_trailing_blank(tmp_path):
    """The subjects CSV has NO header: every non-blank row is one subject, and
    the sbatch template selects row N for SLURM_ARRAY_TASK_ID=N over array
    1..n_subjects. n_subjects must therefore equal the number of data rows, and
    a trailing blank line must NOT inflate the count (else the array would index
    past the last `sed` line). Pins count<->indexing agreement (no off-by-one).
    """
    csv = tmp_path / "subs_fs_3rows.csv"  # distinct from make_csv's default file
    # 3 data rows + a trailing newline producing a blank final element.
    csv.write_text("s03,ses-01,1,ses-01,1\ns04,ses-02,1,,\ns05,ses-01,1,,\n")
    config = make_config(tmp_path)
    args = make_args(tmp_path, subjects_file=str(csv))
    ctx = FreesurferPipeline().build_context("discovery", config, args)
    assert ctx["n_subjects"] == 3

    # The template's last addressable row is `sed -n "<n_subjects>p"`; it must be
    # a real data row, never a blank line, so the array never reads nothing.
    rows = [ln for ln in csv.read_text().splitlines() if ln.strip()]
    assert len(rows) == ctx["n_subjects"]
    assert rows[ctx["n_subjects"] - 1].startswith("s05")


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = FreesurferPipeline()
    config = make_config(tmp_path)
    args = make_args(tmp_path)
    ctx = p.build_context("discovery", config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)
    assert "recon-all" in script
    assert "freesurfer_8.1.0" in script
    assert "SLURM_ARRAY_TASK_ID" in script
