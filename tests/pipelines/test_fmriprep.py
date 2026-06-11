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
    assert ctx["config_bind_line"].endswith(" \\\n")
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
    assert ctx["output_bind_line"].endswith(" \\\n")
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

    assert "-B /scratch/users/logben/fmriprep_bug_repro:/out \\" in script
    assert "/data /out/fmriprep_25.2.5 participant" in script
    assert "/data/derivatives" not in script

    import subprocess, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"Rendered script has bash syntax errors: {r.stderr}"


def test_fmriprep_bids_dir_override(tmp_path):
    """When --bids-dir-override is set, /data binds the override path and
    derivatives output redirects to the original BIDS dir's derivatives/."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input",
    )

    ctx = p.build_context("discovery", dataset_config, args)

    # /data should bind the override path
    assert ctx["bids_dir"] == "/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input"
    # Output should bind the registered BIDS dir's derivatives/ as /out
    assert "-B /scratch/users/logben/discovery_bids/derivatives:/out" in ctx["output_bind_line"]
    assert ctx["output_container"] == "/out"
    # Logs should still go to the registered BIDS dir
    assert ctx["log_dir"] == "/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/logs"


def test_fmriprep_bids_dir_override_in_rendered_template(tmp_path):
    """Full render confirms /data and /out paths are correct in the sbatch."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="--no-submm-recon --skip-bids-validation --cifti-output 91k",
        fs_license="/home/user/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input",
    )

    ctx = p.build_context("discovery", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    # /data binds the view, not the original BIDS dir
    assert "-B /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input:/data" in script
    # /out binds the original BIDS dir's derivatives/
    assert "-B /scratch/users/logben/discovery_bids/derivatives:/out" in script
    # fmriprep CLI uses /data input, /out/fmriprep_25.2.4 output
    assert "/data /out/fmriprep_25.2.4 participant" in script
    # No /data/derivatives anywhere (would mean output is going under the view)
    assert "/data/derivatives" not in script
    # bash syntax
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"bash syntax error: {r.stderr}"


def test_fmriprep_bids_dir_override_default_none(tmp_path):
    """Without --bids-dir-override, behavior is unchanged."""
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
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["bids_dir"] == "/oak/data/bids"
    assert ctx["output_bind_line"] == ""
    assert ctx["output_container"] == "/data/derivatives"


def test_fmriprep_bids_dir_override_and_output_dir_are_mutually_exclusive():
    """Argparse should reject --bids-dir-override and --output-dir together."""
    import argparse
    import pytest
    parser = argparse.ArgumentParser()
    p = FmriprepPipeline()
    p.add_cli_args(parser)
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--version", "25.2.4",
            "--output-dir", "/some/out",
            "--bids-dir-override", "/some/view",
        ])


def test_fmriprep_resolves_canonical_sample_and_writes_subjects_file(tmp_path, monkeypatch):
    """A canonical sample (discovery) resolves its 5 subjects from
    pipeline_config.json `samples` -- NOT from a registered subjects_file --
    and writes a real subjects file into the run's work dir for the sbatch."""
    monkeypatch.setenv("SCRATCH", str(tmp_path / "scratch"))

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        # Deliberately a bogus/nonexistent subjects_file: canonical resolution
        # must ignore it for a known sample (this is the gap being fixed).
        "subjects_file": "subjects_discovery.txt",
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override=None,
    )

    ctx = p.build_context("discovery", dataset_config, args)

    # 5 discovery subjects -> array 1-5
    assert ctx["n_subjects"] == 5
    # The rendered subjects_file is the generated one in the work dir, not the
    # registered relative path.
    assert ctx["subjects_file"] != "subjects_discovery.txt"
    assert ctx["subjects_file"].endswith("subjects.txt")
    written = Path(ctx["subjects_file"])
    assert written.is_file()
    assert written.read_text().split() == ["s03", "s10", "s19", "s29", "s43"]


def test_fmriprep_unknown_dataset_without_subjects_file_fails_loud(tmp_path, monkeypatch):
    """An unknown sample with no resolvable subjects_file fails loud (no silent
    empty SLURM array)."""
    import pytest
    monkeypatch.setenv("SCRATCH", str(tmp_path / "scratch"))
    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": "/nonexistent/subjects_bogus.txt",
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4", output_spaces="", fmriprep_args="",
        fs_license="~/license.txt", bids_filter_file=None, nthreads=None,
        mem_per_cpu_gb=None, time=None, output_dir=None, bids_dir_override=None,
    )
    with pytest.raises(ValueError, match="cannot resolve subjects"):
        p.build_context("not_a_sample", dataset_config, args)


def test_fmriprep_template_includes_exit_1_workaround(tmp_path):
    """The rendered sbatch must detect fmriprep#3634 benign exit-1 and treat as success."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override=None,
    )
    ctx = p.build_context("discovery", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    # The success-detection workaround must be present
    assert 'fMRIPrep finished successfully' in script
    assert 'fmriprep#3634' in script
    assert 'exitcode=0' in script  # the line that flips exit-1 to 0


def test_fmriprep_template_includes_work_dir_cleanup(tmp_path):
    """The rendered sbatch must clean up the per-subject work dir on success."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override=None,
    )
    ctx = p.build_context("discovery", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    # Cleanup logic
    assert 'Cleaned up work dir on success' in script
    # Cleans the subject-specific subdirectory, not the whole work dir
    assert 'rm -rf "$subject_work"' in script
    # The cleanup is gated by exit code 0
    assert 'if [ "$exitcode" -eq 0 ]' in script


def test_fmriprep_template_log_path_uses_array_job_id(tmp_path):
    """The wrapper must reference the actual .out file path used by SLURM."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override=None,
    )
    ctx = p.build_context("discovery", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    # Must reference SLURM array job ID and task ID in the log file path
    assert "${SLURM_ARRAY_JOB_ID}" in script
    assert "${SLURM_ARRAY_TASK_ID}" in script
    # The log filename pattern must match the SBATCH -o directive: fmriprep_<ds>-%A-%a.out
    assert 'fmriprep_discovery-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}.out' in script

    # Bash syntax must be valid
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"bash syntax error: {r.stderr}"
