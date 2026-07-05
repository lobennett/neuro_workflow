"""Shared imports and helpers for the neuro-run CLI handlers.

Handlers resolve patchable collaborators (``submit_sbatch``, ``get_dataset``,
``ensure_image``, ...) through the ``neuro_workflow.cli`` package namespace at
call time, so that tests which ``monkeypatch.setattr("neuro_workflow.cli.<name>", ...)``
take effect.  Import this module's names into ``cli/__init__.py`` to expose them
on that namespace.
"""

import argparse
import sys
from pathlib import Path

from neuro_workflow.core.config import (
    DatasetNotFoundError,
    get_dataset,
    load_datasets,
    save_dataset,
)
from neuro_workflow.core.exclusions import (
    compile_exclusions,
    load_compiled_exclusions,
    load_overrides,
    save_overrides,
    save_source_entries,
)
from neuro_workflow.core.image import ensure_image
from neuro_workflow.core.slurm import render_template, submit_sbatch
from neuro_workflow.exclusions.base import get_generator, list_generators
from neuro_workflow.pipelines.base import TEMPLATE_DIR, get_pipeline, list_pipelines
from neuro_workflow.qa.base import get_qa_command, list_qa_commands

__all__ = [
    "argparse",
    "sys",
    "Path",
    "DatasetNotFoundError",
    "save_dataset",
    "get_dataset",
    "load_datasets",
    "ensure_image",
    "render_template",
    "submit_sbatch",
    "save_source_entries",
    "save_overrides",
    "load_overrides",
    "compile_exclusions",
    "load_compiled_exclusions",
    "get_pipeline",
    "list_pipelines",
    "TEMPLATE_DIR",
    "get_qa_command",
    "list_qa_commands",
    "get_generator",
    "list_generators",
]
