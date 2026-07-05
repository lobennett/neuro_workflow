"""Handlers for the ``show`` and ``submit`` pipeline subcommands."""

import argparse
import sys

from neuro_workflow.core.slurm import render_template
from neuro_workflow.pipelines.base import TEMPLATE_DIR, get_pipeline, list_pipelines


def cmd_show(args, remaining):
    import neuro_workflow.cli as cli

    if args.list:
        datasets = cli.load_datasets()
        if not datasets:
            print("No datasets registered. Use 'neuro-run add-dataset' to add one.")
            return
        for name, ds in datasets.items():
            print(f"  {name}: {ds.get('bids_dir', '(no bids_dir)')}")
        return

    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(
            f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse pipeline-specific args
    pipeline_parser = argparse.ArgumentParser()
    pipeline.add_cli_args(pipeline_parser)
    pipeline_args = pipeline_parser.parse_args(remaining)
    # Merge into args namespace
    for key, value in vars(pipeline_args).items():
        setattr(args, key, value)

    config = cli.get_dataset(args.dataset)
    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)
    print(script)


def cmd_submit(args, remaining):
    import neuro_workflow.cli as cli

    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(
            f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse pipeline-specific args
    pipeline_parser = argparse.ArgumentParser()
    pipeline.add_cli_args(pipeline_parser)
    pipeline_args = pipeline_parser.parse_args(remaining)
    for key, value in vars(pipeline_args).items():
        setattr(args, key, value)

    if getattr(pipeline, "requires_dataset", True):
        config = cli.get_dataset(args.dataset)
        if pipeline.docker_uri:
            cli.ensure_image(config["image_dir"], pipeline.name, args.version, pipeline.docker_uri)
    else:
        config = {}

    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)

    print("--- Generated sbatch script ---")
    print(script)
    print("--- Submitting ---")
    cli.submit_sbatch(script)


def add_show_parser(subparsers):
    import neuro_workflow.cli as cli

    show_p = subparsers.add_parser("show", help="Preview sbatch script or list datasets")
    show_p.add_argument("--list", action="store_true", help="List all registered datasets")
    show_p.add_argument("pipeline", nargs="?", help="Pipeline name (e.g. fmriprep)")
    show_p.add_argument("dataset", nargs="?", help="Dataset name to preview")
    show_p.set_defaults(func=cli.cmd_show)


def add_submit_parser(subparsers):
    import neuro_workflow.cli as cli

    sub_p = subparsers.add_parser("submit", help="Submit a pipeline job to SLURM")
    sub_p.add_argument("pipeline", help="Pipeline name (e.g. fmriprep, qsiprep)")
    sub_p.add_argument("dataset", help="Dataset name to submit")
    sub_p.set_defaults(func=cli.cmd_submit)
