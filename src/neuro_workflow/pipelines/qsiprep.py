import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import register


class QsiprepPipeline:
    name = "qsiprep"
    docker_uri = "docker://pennlinc/qsiprep"
    template_name = "qsiprep.sbatch"
    default_resources = {
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "24:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="QSIPrep version tag (e.g. 1.1.1)")
        parser.add_argument("--output-resolution", type=float, default=1.5, help="Output resolution in mm (default: 1.5)")
        parser.add_argument("--qsiprep-args", default="", help="Additional QSIPrep arguments")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 8)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 24:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for qsiprep pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        n_subjects = count_subjects(dataset_config["subjects_file"])
        mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

        image_path = str(Path(dataset_config["image_dir"]) / f"qsiprep_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/qsiprep_{dataset_name}_{args.version}"
        log_dir = f"{dataset_config['bids_dir']}/derivatives/qsiprep_{args.version}/logs"

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_subjects": n_subjects,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "subjects_file": dataset_config["subjects_file"],
            "image_path": image_path,
            "bids_dir": dataset_config["bids_dir"],
            "work_dir": work_dir,
            "fs_license": fs_license,
            "qsiprep_version": args.version,
            "mem_mb": mem_mb,
            "output_resolution": args.output_resolution,
            "qsiprep_args": args.qsiprep_args,
        }


register(QsiprepPipeline())
