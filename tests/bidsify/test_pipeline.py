"""Tests for bidsify pipeline registration and sbatch submission."""

import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


@pytest.fixture
def bidsify_pipeline():
    # Import triggers registration
    import neuro_workflow.pipelines.bidsify  # noqa: F401
    return get_pipeline("bidsify")


class TestBidsifyPipelineRegistration:
    def test_pipeline_registered(self, bidsify_pipeline):
        assert bidsify_pipeline is not None

    def test_pipeline_name(self, bidsify_pipeline):
        assert bidsify_pipeline.name == "bidsify"

    def test_no_docker_uri(self, bidsify_pipeline):
        assert bidsify_pipeline.docker_uri is None

    def test_requires_dataset_false(self, bidsify_pipeline):
        assert bidsify_pipeline.requires_dataset is False

    def test_template_exists(self, bidsify_pipeline):
        template_path = TEMPLATE_DIR / bidsify_pipeline.template_name
        assert template_path.exists()


class TestBidsifyBuildContext:
    def test_build_context_discovery(self, bidsify_pipeline):
        args = Namespace(
            output_dir="/scratch/users/logben/discovery_BIDS",
            subjects=None,
            flywheel_project=None,
            overwrite=False,
            time=None,
            mem_gb=None,
        )
        config = {"partition": "russpold", "mail_user": "logben@stanford.edu"}
        ctx = bidsify_pipeline.build_context("discovery", config, args)

        assert ctx["sample"] == "discovery"
        assert ctx["output_dir"] == "/scratch/users/logben/discovery_BIDS"
        assert ctx["partition"] == "russpold"
        assert "extra_args" in ctx

    def test_build_context_with_subjects(self, bidsify_pipeline):
        args = Namespace(
            output_dir="/scratch/test",
            subjects=["s03", "s10"],
            flywheel_project=None,
            overwrite=False,
            time=None,
            mem_gb=None,
        )
        ctx = bidsify_pipeline.build_context("discovery", {}, args)
        assert "--subjects s03 s10" in ctx["extra_args"]

    def test_build_context_with_overwrite(self, bidsify_pipeline):
        args = Namespace(
            output_dir="/scratch/test",
            subjects=None,
            flywheel_project="other_project",
            overwrite=True,
            time=None,
            mem_gb=None,
        )
        ctx = bidsify_pipeline.build_context("validation", {}, args)
        assert "--overwrite" in ctx["extra_args"]
        assert '--flywheel-project other_project' in ctx["extra_args"]


class TestBidsifyTemplate:
    def test_template_renders(self, bidsify_pipeline):
        ctx = {
            "sample": "discovery",
            "output_dir": "/scratch/users/logben/discovery_BIDS",
            "partition": "russpold",
            "time": "1-00:00:00",
            "mem_gb": 8,
            "log_dir": "/scratch/users/logben/logs",
            "mail_line": "",
            "container": "/home/groups/russpold/singularity_images/neuro_workflow.sif",
            "extra_args": "",
        }
        template_path = TEMPLATE_DIR / bidsify_pipeline.template_name
        script = render_template(template_path, ctx)
        assert "#!/bin/bash" in script
        assert "bidsify discovery" in script
        assert "--output-dir /scratch/users/logben/discovery_BIDS" in script
        assert "#SBATCH --time=1-00:00:00" in script

    def test_template_includes_extra_args(self, bidsify_pipeline):
        ctx = {
            "sample": "discovery",
            "output_dir": "/scratch/test",
            "partition": "russpold",
            "time": "1-00:00:00",
            "mem_gb": 8,
            "log_dir": "/tmp/logs",
            "mail_line": "",
            "container": "/path/to/container.sif",
            "extra_args": "--subjects s03 s10 --overwrite",
        }
        template_path = TEMPLATE_DIR / bidsify_pipeline.template_name
        script = render_template(template_path, ctx)
        assert "--subjects s03 s10 --overwrite" in script


class TestBidsifySubmitIntegration:
    def test_submit_bidsify_skips_dataset_lookup(self, bidsify_pipeline, monkeypatch):
        """cmd_submit should not call get_dataset for pipelines with requires_dataset=False."""
        monkeypatch.setattr(sys, "argv", [
            "neuro-run", "submit", "bidsify", "discovery",
            "--output-dir", "/scratch/test",
        ])
        with patch("neuro_workflow.cli.submit_sbatch") as mock_submit, \
             patch("neuro_workflow.cli.get_dataset") as mock_get_dataset:
            mock_submit.return_value = "Submitted batch job 12345"
            from neuro_workflow.cli import main
            main()
            mock_get_dataset.assert_not_called()
            mock_submit.assert_called_once()
