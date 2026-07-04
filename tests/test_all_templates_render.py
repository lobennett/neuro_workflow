"""Smoke tests: every registered pipeline's sbatch template renders without unresolved placeholders.

The parametrized test is DYNAMIC — it iterates over ``list_pipelines()`` at
collection time so a newly-added pipeline is automatically covered.  A missing
fixture entry is a hard FAIL, never a skip, so no pipeline can silently escape
coverage.
"""

from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Callable

import pytest

# Importing neuro_workflow.cli triggers all pipeline auto-registrations.
import neuro_workflow.cli  # noqa: F401

from neuro_workflow.pipelines.base import TEMPLATE_DIR, list_pipelines
from neuro_workflow.core.slurm import render_template


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _check_no_unresolved(script: str) -> None:
    """Assert no unresolved Python-style {var} placeholders remain.

    After str.format(), double-braces ``{{SLURM_ARRAY_TASK_ID}}`` become
    ``{SLURM_ARRAY_TASK_ID}`` which is correct shell syntax.  Shell ``${var}``
    references are also fine.  We only flag bare ``{python_var}`` patterns
    (lowercase + underscore) that indicate a missing template variable.
    """
    unresolved = re.findall(r"(?<!\$)\{([a-z_]+)\}", script)
    assert not unresolved, f"Unresolved placeholders: {unresolved}"


# ---------------------------------------------------------------------------
# Per-pipeline context builders
#
# Each builder is a callable(tmp_path: Path) -> (dataset_name, dataset_config, args).
# The args Namespace is produced by building a parser with pipeline.add_cli_args()
# and parsing a minimal valid argv, so it exactly mirrors what the real CLI produces.
# ---------------------------------------------------------------------------


def _build_fmriprep(tmp_path: Path):
    subs_file = tmp_path / "subjects.txt"
    subs_file.write_text("s01\ns02\n")

    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
        "image_dir": str(tmp_path / "images"),
        "templateflow_dir": str(tmp_path / "templateflow"),
    }

    from neuro_workflow.pipelines.fmriprep import FmriprepPipeline

    pipeline = FmriprepPipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(["--version", "25.2.4"])

    return "testds", dataset_config, args


def _build_freesurfer(tmp_path: Path):
    subs_file = tmp_path / "subjects.txt"
    subs_file.write_text("s01\ns02\n")

    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
        "image_dir": str(tmp_path / "images"),
    }

    from neuro_workflow.pipelines.freesurfer import FreesurferPipeline

    pipeline = FreesurferPipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(["--version", "8.1.0"])

    return "testds", dataset_config, args


def _build_qsiprep(tmp_path: Path):
    subs_file = tmp_path / "subjects.txt"
    subs_file.write_text("s01\ns02\n")

    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
        "image_dir": str(tmp_path / "images"),
    }

    from neuro_workflow.pipelines.qsiprep import QsiprepPipeline

    pipeline = QsiprepPipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(["--version", "1.1.1"])

    return "testds", dataset_config, args


def _build_happy(tmp_path: Path):
    """Build a minimal BIDS tree with one BOLD+physio scan for happy to discover."""
    bids_dir = tmp_path / "bids"
    func_dir = bids_dir / "sub-s01" / "ses-01" / "func"
    func_dir.mkdir(parents=True)

    base = "sub-s01_ses-01_task-rest_run-01_echo-1_bold"
    (func_dir / f"{base}.nii.gz").write_text("fake")
    (func_dir / f"{base}.json").write_text("{}")
    phys_base = "sub-s01_ses-01_task-rest_run-01"
    (func_dir / f"{phys_base}_recording-cardiac_physio.tsv.gz").write_text("fake")
    (func_dir / f"{phys_base}_recording-cardiac_physio.json").write_text("{}")

    dataset_config = {
        "bids_dir": str(bids_dir),
        "partition": "normal",
        "mail_user": None,
        "image_dir": str(tmp_path / "images"),
    }

    from neuro_workflow.pipelines.happy import HappyPipeline

    pipeline = HappyPipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(["--version", "3.1.8"])

    return "testds", dataset_config, args


def _build_fsqc(tmp_path: Path):
    subs_file = tmp_path / "subjects.txt"
    subs_file.write_text("s01\ns02\n")

    dataset_config = {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
        "image_dir": str(tmp_path / "images"),
    }

    from neuro_workflow.pipelines.fsqc import FsqcPipeline

    pipeline = FsqcPipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(
        [
            "--version",
            "2.1.4",
            "--freesurfer-dir",
            str(tmp_path / "freesurfer"),
        ]
    )

    return "testds", dataset_config, args


def _build_lev1(tmp_path: Path):
    subs_file = tmp_path / "subjects.txt"
    subs_file.write_text("s01\ns02\n")
    exc_file = tmp_path / "exclusions.json"
    exc_file.write_text("[]")

    dataset_config = {
        "bids_dir": "/data",
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
    }

    from neuro_workflow.pipelines.lev1 import Lev1Pipeline

    pipeline = Lev1Pipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(
        [
            "--tasks",
            "flanker",
            "--fmriprep-dir",
            "/fmriprep",
            "--results-dir",
            str(tmp_path / "out"),
            "--exclusions-file",
            str(exc_file),
        ]
    )

    return "testds", dataset_config, args


def _build_lev2(tmp_path: Path):
    subs_file = tmp_path / "subjects.txt"
    subs_file.write_text("s01\ns02\n")

    dataset_config = {
        "bids_dir": "/data",
        "subjects_file": str(subs_file),
        "partition": "normal",
        "mail_user": None,
    }

    from neuro_workflow.pipelines.lev2 import Lev2Pipeline

    pipeline = Lev2Pipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(
        [
            "--lev1-dirs",
            "/lev1",
            "--results-dir",
            str(tmp_path / "out"),
            "--contrasts",
            "task-flanker_contrast-test",
        ]
    )

    return "testds", dataset_config, args


def _build_bidsify(tmp_path: Path):
    dataset_config = {
        "partition": "russpold",
        "mail_user": None,
    }

    from neuro_workflow.pipelines.bidsify import BidsifyPipeline

    pipeline = BidsifyPipeline()
    parser = ArgumentParser()
    pipeline.add_cli_args(parser)
    args = parser.parse_args(["--output-dir", str(tmp_path / "bids")])

    return "testds", dataset_config, args


# ---------------------------------------------------------------------------
# Fixture registry: pipeline name -> builder callable
#
# INVARIANT: this dict must cover every pipeline in list_pipelines().
# If it doesn't, test_pipeline_registry_is_fully_covered will FAIL (not skip).
# ---------------------------------------------------------------------------

_FIXTURE_BUILDERS: dict[str, Callable[[Path], tuple]] = {
    "bidsify": _build_bidsify,
    "fmriprep": _build_fmriprep,
    "freesurfer": _build_freesurfer,
    "fsqc": _build_fsqc,
    "happy": _build_happy,
    "lev1": _build_lev1,
    "lev2": _build_lev2,
    "qsiprep": _build_qsiprep,
}


# ---------------------------------------------------------------------------
# Coverage guard: must run at collection time to catch mis-coverage early,
# AND as an explicit test so the CI result is unambiguous.
# ---------------------------------------------------------------------------


def test_pipeline_registry_is_fully_covered() -> None:
    """Fail if a registered pipeline has no fixture builder (coverage invariant)."""
    registered = set(list_pipelines().keys())
    fixtured = set(_FIXTURE_BUILDERS.keys())

    missing = registered - fixtured
    extra = fixtured - registered

    assert not missing, f"Registered pipelines with NO fixture builder (add one to _FIXTURE_BUILDERS): {sorted(missing)}"
    assert (
        not extra
    ), f"_FIXTURE_BUILDERS has entries for unknown pipelines (stale? rename?): {sorted(extra)}"


# ---------------------------------------------------------------------------
# Parametrized render test — one case per registered pipeline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pipeline_name", sorted(list_pipelines().keys()))
def test_template_renders_without_unresolved_placeholders(
    pipeline_name: str,
    tmp_path: Path,
) -> None:
    """Every registered pipeline's sbatch template must render cleanly."""
    pipeline = list_pipelines()[pipeline_name]

    builder = _FIXTURE_BUILDERS.get(pipeline_name)
    if builder is None:
        pytest.fail(
            f"No fixture builder for pipeline '{pipeline_name}'. "
            "Add an entry to _FIXTURE_BUILDERS in this file."
        )

    dataset_name, dataset_config, args = builder(tmp_path)

    ctx = pipeline.build_context(dataset_name, dataset_config, args)
    script = render_template(TEMPLATE_DIR / pipeline.template_name, ctx)
    _check_no_unresolved(script)
