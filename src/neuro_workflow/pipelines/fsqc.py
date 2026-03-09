import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import load_subjects
from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources


class FsqcPipeline:
    name = "fsqc"
    docker_uri = "docker://deepmi/fsqc"
    template_name = "fsqc.sbatch"
    default_resources = {
        "nthreads": 4,
        "mem_per_cpu_gb": 8,
        "time": "2-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="FSQC version tag (e.g. 2.1.4)")
        parser.add_argument("--freesurfer-dir", default=None, help="Path to FreeSurfer derivatives directory")
        parser.add_argument("--fsqc-args", default="", help="Additional FSQC arguments")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 2-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for fsqc pipeline", file=sys.stderr)
            sys.exit(1)
        if not getattr(args, "freesurfer_dir", None):
            print("Error: --freesurfer-dir is required for fsqc pipeline", file=sys.stderr)
            sys.exit(1)

        resources = resolve_resources(args, self.default_resources)
        nthreads = resources["nthreads"]
        mem_per_cpu_gb = resources["mem_per_cpu_gb"]
        time = resources["time"]

        image_path = str(Path(dataset_config["image_dir"]) / f"fsqc_{args.version}.sif")

        subjects = load_subjects(dataset_config["subjects_file"])
        subjects_list = " ".join(
            f"sub-{s}" if not s.startswith("sub-") else s for s in subjects
        )

        output_dir = f"{dataset_config['bids_dir']}/derivatives/fsqc_{args.version}"
        log_dir = f"{output_dir}/logs"

        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "time": time,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "image_path": image_path,
            "freesurfer_dir": args.freesurfer_dir,
            "output_dir": output_dir,
            "subjects_list": subjects_list,
            "fsqc_args": args.fsqc_args,
        }


register(FsqcPipeline())
