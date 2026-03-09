import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import register


class FreesurferPipeline:
    name = "freesurfer"
    docker_uri = ""  # local SIF, no pull
    template_name = "freesurfer.sbatch"
    default_resources = {
        "nthreads": 4,
        "mem_per_cpu_gb": 16,
        "time": "4-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="FreeSurfer version tag (e.g. 8.1.0)")
        parser.add_argument("--subjects-file", default=None, help="CSV file: subject_id,ses_t1,run_t1,ses_t2,run_t2")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 16)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 4-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for freesurfer pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        fs_subjects_file = getattr(args, "subjects_file", None) or dataset_config["subjects_file"]
        n_subjects = sum(1 for line in open(fs_subjects_file) if line.strip())

        image_path = str(Path(dataset_config["image_dir"]) / f"freesurfer_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())
        log_dir = f"{dataset_config['bids_dir']}/derivatives/freesurfer_{args.version}/logs"

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
            "image_path": image_path,
            "bids_dir": dataset_config["bids_dir"],
            "fs_license": fs_license,
            "fs_subjects_file": fs_subjects_file,
            "freesurfer_version": args.version,
        }


register(FreesurferPipeline())
