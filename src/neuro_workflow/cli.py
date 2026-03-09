import argparse
import sys
from pathlib import Path

from neuro_workflow.core.config import save_dataset, get_dataset, load_datasets
from neuro_workflow.core.image import ensure_image
from neuro_workflow.core.slurm import render_template, submit_sbatch
from neuro_workflow.pipelines.base import get_pipeline, list_pipelines, TEMPLATE_DIR
from neuro_workflow.qa.base import get_qa_command, list_qa_commands

# Import pipeline modules to trigger auto-registration
import neuro_workflow.pipelines.fmriprep  # noqa: F401
import neuro_workflow.pipelines.qsiprep  # noqa: F401
import neuro_workflow.pipelines.fsqc  # noqa: F401
import neuro_workflow.pipelines.freesurfer  # noqa: F401
import neuro_workflow.pipelines.happy  # noqa: F401

# Import QA modules to trigger auto-registration
import neuro_workflow.qa.neg_events  # noqa: F401
import neuro_workflow.qa.breaks  # noqa: F401
import neuro_workflow.qa.global_signal  # noqa: F401
import neuro_workflow.qa.outlier_report  # noqa: F401
import neuro_workflow.qa.reliability  # noqa: F401


def cmd_add_dataset(args):
    dataset_config = {
        "bids_dir": args.bids_dir,
        "subjects_file": args.subjects_file,
    }
    optional = {
        "partition": args.partition,
        "mail_user": args.mail_user,
        "image_dir": args.image_dir,
        "templateflow_dir": args.templateflow_dir,
    }
    for key, value in optional.items():
        if value is not None:
            dataset_config[key] = value

    for path_key in ("bids_dir", "subjects_file"):
        p = Path(dataset_config[path_key])
        if not p.exists():
            print(f"Warning: {path_key} path does not exist: {p}", file=sys.stderr)

    save_dataset(args.name, dataset_config)
    print(f"Dataset '{args.name}' saved.")


def cmd_show(args, remaining):
    if args.list:
        datasets = load_datasets()
        if not datasets:
            print("No datasets registered. Use 'neuro-run add-dataset' to add one.")
            return
        for name, ds in datasets.items():
            print(f"  {name}: {ds.get('bids_dir', '(no bids_dir)')}")
        return

    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}", file=sys.stderr)
        sys.exit(1)

    # Parse pipeline-specific args
    pipeline_parser = argparse.ArgumentParser()
    pipeline.add_cli_args(pipeline_parser)
    pipeline_args = pipeline_parser.parse_args(remaining)
    # Merge into args namespace
    for key, value in vars(pipeline_args).items():
        setattr(args, key, value)

    config = get_dataset(args.dataset)
    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)
    print(script)


def cmd_submit(args, remaining):
    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}", file=sys.stderr)
        sys.exit(1)

    # Parse pipeline-specific args
    pipeline_parser = argparse.ArgumentParser()
    pipeline.add_cli_args(pipeline_parser)
    pipeline_args = pipeline_parser.parse_args(remaining)
    for key, value in vars(pipeline_args).items():
        setattr(args, key, value)

    config = get_dataset(args.dataset)
    ensure_image(config["image_dir"], pipeline.name, args.version, pipeline.docker_uri)

    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)

    print("--- Generated sbatch script ---")
    print(script)
    print("--- Submitting ---")
    submit_sbatch(script)


def cmd_qa(args, remaining):
    command = get_qa_command(args.qa_command)
    if command is None:
        available = ", ".join(list_qa_commands()) or "(none registered)"
        print(f"Error: unknown QA command '{args.qa_command}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    # Parse QA-command-specific args
    qa_parser = argparse.ArgumentParser()
    command.add_cli_args(qa_parser)
    qa_args = qa_parser.parse_args(remaining)
    for key, value in vars(qa_args).items():
        setattr(args, key, value)

    config = get_dataset(args.dataset)
    command.run(args.dataset, config, args)


def main():
    parser = argparse.ArgumentParser(prog="neuro-run", description="Submit neuroimaging SLURM array jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-dataset (pipeline-agnostic)
    add_p = subparsers.add_parser("add-dataset", help="Register a dataset")
    add_p.add_argument("name", help="Dataset name (e.g., discovery, validation)")
    add_p.add_argument("--bids-dir", required=True, help="Path to BIDS directory")
    add_p.add_argument("--subjects-file", required=True, help="Path to subjects text file")
    add_p.add_argument("--partition", help="SLURM partition")
    add_p.add_argument("--mail-user", help="Email for SLURM notifications")
    add_p.add_argument("--image-dir", help="Directory for SIF images")
    add_p.add_argument("--templateflow-dir", help="TemplateFlow directory")
    add_p.set_defaults(func=lambda args, remaining: cmd_add_dataset(args))

    # show — pipeline-specific args parsed in second pass
    show_p = subparsers.add_parser("show", help="Preview sbatch script or list datasets")
    show_p.add_argument("--list", action="store_true", help="List all registered datasets")
    show_p.add_argument("pipeline", nargs="?", help="Pipeline name (e.g. fmriprep)")
    show_p.add_argument("dataset", nargs="?", help="Dataset name to preview")
    show_p.set_defaults(func=cmd_show)

    # submit — pipeline-specific args parsed in second pass
    sub_p = subparsers.add_parser("submit", help="Submit a pipeline job to SLURM")
    sub_p.add_argument("pipeline", help="Pipeline name (e.g. fmriprep, qsiprep)")
    sub_p.add_argument("dataset", help="Dataset name to submit")
    sub_p.set_defaults(func=cmd_submit)

    # qa — command-specific args parsed in second pass
    qa_p = subparsers.add_parser("qa", help="Run QA analysis scripts")
    qa_p.add_argument("qa_command", help="QA command name")
    qa_p.add_argument("dataset", help="Dataset name")
    qa_p.set_defaults(func=cmd_qa)

    args, remaining = parser.parse_known_args()
    args.func(args, remaining)
