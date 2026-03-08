import argparse
import sys
from pathlib import Path

from fmriprep_workflow.config import save_dataset, get_dataset, load_datasets
from fmriprep_workflow.image import ensure_image
from fmriprep_workflow.submit import render_sbatch, submit_sbatch


def cmd_add_dataset(args):
    dataset_config = {
        "bids_dir": args.bids_dir,
        "subjects_file": args.subjects_file,
        "fmriprep_version": args.fmriprep_version,
    }
    # Only include optional args if provided
    optional = {
        "output_spaces": args.output_spaces,
        "fmriprep_args": args.fmriprep_args,
        "partition": args.partition,
        "nthreads": args.nthreads,
        "mem_per_cpu_gb": args.mem_per_cpu_gb,
        "time": args.time,
        "image_dir": args.image_dir,
        "templateflow_dir": args.templateflow_dir,
        "fs_license": args.fs_license,
        "bids_filter_file": args.bids_filter_file,
        "mail_user": args.mail_user,
    }
    for key, value in optional.items():
        if value is not None:
            dataset_config[key] = value

    # Path existence warnings
    for path_key in ("bids_dir", "subjects_file"):
        p = Path(dataset_config[path_key])
        if not p.exists():
            print(f"Warning: {path_key} path does not exist: {p}", file=sys.stderr)

    save_dataset(args.name, dataset_config)
    print(f"Dataset '{args.name}' saved.")


def cmd_show(args):
    if args.list:
        datasets = load_datasets()
        if not datasets:
            print("No datasets registered. Use 'fmriprep-run add-dataset' to add one.")
            return
        for name, ds in datasets.items():
            print(f"  {name}: {ds.get('bids_dir', '(no bids_dir)')}")
        return

    config = get_dataset(args.name)
    script = render_sbatch(args.name, config)
    print(script)


def cmd_submit(args):
    config = get_dataset(args.name)
    ensure_image(config["image_dir"], config["fmriprep_version"])
    script = render_sbatch(args.name, config)
    print("--- Generated sbatch script ---")
    print(script)
    print("--- Submitting ---")
    submit_sbatch(script)


def main():
    parser = argparse.ArgumentParser(prog="fmriprep-run", description="Submit fMRIPrep SLURM array jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-dataset
    add_p = subparsers.add_parser("add-dataset", help="Register a dataset")
    add_p.add_argument("name", help="Dataset name (e.g., discovery, validation)")
    add_p.add_argument("--bids-dir", required=True, help="Path to BIDS directory")
    add_p.add_argument("--subjects-file", required=True, help="Path to subjects text file")
    add_p.add_argument("--fmriprep-version", required=True, help="fMRIPrep version tag")
    add_p.add_argument("--output-spaces", help="fMRIPrep output spaces")
    add_p.add_argument("--fmriprep-args", help="Additional fMRIPrep arguments")
    add_p.add_argument("--partition", help="SLURM partition")
    add_p.add_argument("--nthreads", type=int, help="CPUs per task")
    add_p.add_argument("--mem-per-cpu-gb", type=int, help="Memory per CPU in GB")
    add_p.add_argument("--time", help="SLURM time limit")
    add_p.add_argument("--image-dir", help="Directory for SIF images")
    add_p.add_argument("--templateflow-dir", help="TemplateFlow directory")
    add_p.add_argument("--fs-license", help="FreeSurfer license file path")
    add_p.add_argument("--bids-filter-file", help="BIDS filter JSON file path")
    add_p.add_argument("--mail-user", help="Email for SLURM notifications")
    add_p.set_defaults(func=cmd_add_dataset)

    # show
    show_p = subparsers.add_parser("show", help="Preview sbatch script or list datasets")
    show_p.add_argument("name", nargs="?", help="Dataset name to preview")
    show_p.add_argument("--list", action="store_true", help="List all registered datasets")
    show_p.set_defaults(func=cmd_show)

    # submit
    sub_p = subparsers.add_parser("submit", help="Submit fMRIPrep job to SLURM")
    sub_p.add_argument("name", help="Dataset name to submit")
    sub_p.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)
