"""Smoke tests: every new pipeline template renders without unresolved placeholders."""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

import pytest

from neuro_workflow.pipelines.base import TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template
from neuro_workflow.pipelines.lev1 import Lev1Pipeline
from neuro_workflow.pipelines.lev2 import Lev2Pipeline
from neuro_workflow.pipelines.prep_mshbm import PrepMshbmPipeline
from neuro_workflow.pipelines.mshbm import MshbmPipeline


def _check_no_unresolved(script: str) -> None:
    """Assert no unresolved Python-style {var} placeholders remain.

    After str.format(), double-braces ``{{SLURM_ARRAY_TASK_ID}}`` become
    ``{SLURM_ARRAY_TASK_ID}`` which is correct shell syntax.  Shell ``${var}``
    references are also fine.  We only flag bare ``{python_var}`` patterns
    (lowercase + underscore) that indicate a missing template variable.
    """
    unresolved = re.findall(r"(?<!\$)\{([a-z_]+)\}", script)
    assert not unresolved, f"Unresolved placeholders: {unresolved}"


# ---- fixtures ---------------------------------------------------------------


@pytest.fixture()
def subs_file(tmp_path: Path) -> Path:
    p = tmp_path / "subjects.txt"
    p.write_text("s01\ns02\n")
    return p


@pytest.fixture()
def exc_file(tmp_path: Path) -> Path:
    p = tmp_path / "exclusions.json"
    p.write_text("[]")
    return p


@pytest.fixture()
def dataset_config(subs_file: Path) -> dict:
    return {
        "bids_dir": "/data",
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
    }


# ---- tests -------------------------------------------------------------------


def test_lev1_template_renders(tmp_path: Path, dataset_config: dict, exc_file: Path) -> None:
    pipeline = Lev1Pipeline()
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/fmriprep",
        results_dir=str(tmp_path / "out"),
        exclusions_file=str(exc_file),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )
    ctx = pipeline.build_context("testds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / pipeline.template_name, ctx)
    _check_no_unresolved(script)


def test_lev2_template_renders(tmp_path: Path, dataset_config: dict) -> None:
    pipeline = Lev2Pipeline()
    args = Namespace(
        lev1_dirs=["/lev1"],
        results_dir=str(tmp_path / "out"),
        contrasts=["task-flanker_contrast-test"],
        contrasts_flag=None,
        mask_threshold=0.9,
        num_permutations=5000,
        nthreads=None,
        mem_gb=None,
        time=None,
    )
    ctx = pipeline.build_context("testds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / pipeline.template_name, ctx)
    _check_no_unresolved(script)


def test_prep_mshbm_template_renders(tmp_path: Path, dataset_config: dict) -> None:
    pipeline = PrepMshbmPipeline()
    args = Namespace(
        glm_dir="/glm",
        fmriprep_dir="/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )
    ctx = pipeline.build_context("testds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / pipeline.template_name, ctx)
    _check_no_unresolved(script)


def test_mshbm_template_renders(tmp_path: Path, dataset_config: dict) -> None:
    pipeline = MshbmPipeline()
    args = Namespace(
        surface_inputs_dir="/inputs",
        output_dir=str(tmp_path / "out"),
        mshbm_dir="/mshbm",
        nthreads=None,
        mem_gb=None,
        time=None,
    )
    ctx = pipeline.build_context("testds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / pipeline.template_name, ctx)
    _check_no_unresolved(script)
