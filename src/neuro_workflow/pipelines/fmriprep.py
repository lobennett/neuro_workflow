import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import register


class FmriprepPipeline:
    name = "fmriprep"
    docker_uri = "docker://nipreps/fmriprep"
    template_name = "fmriprep.sbatch"
    default_resources = {
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="fMRIPrep version tag (e.g. 25.2.4)")
        parser.add_argument("--output-spaces", default="", help="fMRIPrep output spaces")
        parser.add_argument("--fmriprep-args", default="", help="Additional fMRIPrep arguments")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--bids-filter-file", default=None, help="BIDS filter JSON file path")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 8)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 5-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for fmriprep pipeline", file=sys.stderr)
            sys.exit(1)
        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        n_subjects = count_subjects(dataset_config["subjects_file"])
        mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

        image_path = str(Path(dataset_config["image_dir"]) / f"fmriprep_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{args.version}"
        log_dir = f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.version}/logs"

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        if args.bids_filter_file:
            filter_path = Path(args.bids_filter_file)
            config_bind_line = f"-B {filter_path.parent}:/config \\"
            bids_filter_arg = f"--bids-filter-file /config/{filter_path.name}"
        else:
            config_bind_line = ""
            bids_filter_arg = ""

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
            "templateflow_dir": dataset_config["templateflow_dir"],
            "work_dir": work_dir,
            "config_bind_line": config_bind_line,
            "fmriprep_version": args.version,
            "mem_mb": mem_mb,
            "output_spaces": args.output_spaces,
            "fs_license_container": fs_license,
            "bids_filter_arg": bids_filter_arg,
            "fmriprep_args": args.fmriprep_args,
        }


# Auto-register when module is imported
register(FmriprepPipeline())
