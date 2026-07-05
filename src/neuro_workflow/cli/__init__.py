"""neuro-run command-line interface.

This package preserves the original ``neuro_workflow.cli`` module surface:

- ``neuro_workflow.cli:main`` remains the ``neuro-run`` entry point.
- ``import neuro_workflow.cli`` still triggers auto-registration of all
  pipelines, QA commands and exclusion generators (side-effect imports below).
- The shared collaborators (``submit_sbatch``, ``get_dataset``, ...) and every
  ``cmd_*`` handler are re-exported here, so existing tests that
  ``monkeypatch.setattr("neuro_workflow.cli.<name>", ...)`` keep working.

Handlers live in per-subsystem modules (``pipelines``, ``qa``, ``exclusions``,
``events``, ``bidsify``, ``dataset``) and resolve patchable collaborators
through this package namespace at call time.
"""

import argparse
import sys

import neuro_workflow.exclusions.behavioral  # noqa: F401
import neuro_workflow.exclusions.collection  # noqa: F401
import neuro_workflow.exclusions.lev1_outlier  # noqa: F401

# Import exclusion generators to trigger auto-registration
import neuro_workflow.exclusions.motion  # noqa: F401
import neuro_workflow.exclusions.qa_decisions  # noqa: F401
import neuro_workflow.pipelines.bidsify  # noqa: F401

# Import pipeline modules to trigger auto-registration
import neuro_workflow.pipelines.fmriprep  # noqa: F401
import neuro_workflow.pipelines.freesurfer  # noqa: F401
import neuro_workflow.pipelines.fsqc  # noqa: F401
import neuro_workflow.pipelines.happy  # noqa: F401
import neuro_workflow.pipelines.lev1  # noqa: F401
import neuro_workflow.pipelines.lev2  # noqa: F401
import neuro_workflow.pipelines.qsiprep  # noqa: F401
import neuro_workflow.qa.fieldmap_check  # noqa: F401

# Import QA modules to trigger auto-registration
import neuro_workflow.qa.global_signal  # noqa: F401

# Shared collaborators re-exported on the package namespace (patch targets).
from neuro_workflow.cli._common import (  # noqa: F401
    TEMPLATE_DIR,
    DatasetNotFoundError,
    compile_exclusions,
    ensure_image,
    get_dataset,
    get_generator,
    get_pipeline,
    get_qa_command,
    list_generators,
    list_pipelines,
    list_qa_commands,
    load_compiled_exclusions,
    load_datasets,
    load_overrides,
    render_template,
    save_dataset,
    save_overrides,
    save_source_entries,
    submit_sbatch,
)
from neuro_workflow.cli.bidsify import add_bidsify_parser, cmd_bidsify  # noqa: F401

# Per-subsystem handlers + parser-builders.
from neuro_workflow.cli.dataset import add_dataset_parser, cmd_add_dataset  # noqa: F401
from neuro_workflow.cli.events import (  # noqa: F401
    add_events_parser,
    cmd_events_create,
    cmd_events_qc,
    cmd_events_trim,
)
from neuro_workflow.cli.exclusions import (  # noqa: F401
    add_exclusions_parser,
    cmd_exclusions_compile,
    cmd_exclusions_generate,
    cmd_exclusions_import,
    cmd_exclusions_query,
    cmd_exclusions_render_bidsignore,
    cmd_exclusions_render_md,
    cmd_exclusions_show,
)
from neuro_workflow.cli.pipelines import (  # noqa: F401
    add_show_parser,
    add_submit_parser,
    cmd_show,
    cmd_submit,
)
from neuro_workflow.cli.qa import add_qa_parser, cmd_qa  # noqa: F401


def main():
    parser = argparse.ArgumentParser(
        prog="neuro-run", description="Submit neuroimaging SLURM array jobs"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-dataset (pipeline-agnostic)
    add_dataset_parser(subparsers)

    # show — pipeline-specific args parsed in second pass
    add_show_parser(subparsers)

    # submit — pipeline-specific args parsed in second pass
    add_submit_parser(subparsers)

    # qa — command-specific args parsed in second pass
    add_qa_parser(subparsers)

    # exclusions
    add_exclusions_parser(subparsers)

    # bidsify
    add_bidsify_parser(subparsers)

    # events
    add_events_parser(subparsers)

    args, remaining = parser.parse_known_args()
    try:
        args.func(args, remaining)
    except DatasetNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
