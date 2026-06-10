"""Handler for the ``add-dataset`` subcommand (pipeline-agnostic)."""

import sys
from pathlib import Path

from neuro_workflow.core.config import save_dataset


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


def add_dataset_parser(subparsers):
    import neuro_workflow.cli as cli

    add_p = subparsers.add_parser("add-dataset", help="Register a dataset")
    add_p.add_argument("name", help="Dataset name (e.g., discovery, validation)")
    add_p.add_argument("--bids-dir", required=True, help="Path to BIDS directory")
    add_p.add_argument("--subjects-file", required=True, help="Path to subjects text file")
    add_p.add_argument("--partition", help="SLURM partition")
    add_p.add_argument("--mail-user", help="Email for SLURM notifications")
    add_p.add_argument("--image-dir", help="Directory for SIF images")
    add_p.add_argument("--templateflow-dir", help="TemplateFlow directory")
    add_p.set_defaults(func=lambda args, remaining: cli.cmd_add_dataset(args))
