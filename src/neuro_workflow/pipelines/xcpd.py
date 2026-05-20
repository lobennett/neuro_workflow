import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources


class XcpdPipeline:
    name = "xcpd"
    docker_uri = "docker://pennlinc/xcp_d"
    template_name = "xcpd.sbatch"
    default_resources = {
        "nthreads": 16,
        "mem_per_cpu_gb": 24,
        "time": "1-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="XCP-D version tag (e.g. 26.0.2)")
        parser.add_argument("--fmriprep-version", default="25.2.4",
                            help="fMRIPrep derivatives version to consume (default: 25.2.4)")
        parser.add_argument(
            "--fmriprep-dir-override",
            default=None,
            help="Path to bind as /data instead of <bids_dir>/derivatives/fmriprep_<version>/. "
                 "Use to point XCP-D at a preflight symlink view that omits T2w-only anat dirs.",
        )
        parser.add_argument("--xcpd-args", default="", help="Additional XCP-D arguments (appended to hardcoded flags)")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 16)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 24)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 1-00:00:00, bigmem cap)")
        parser.add_argument("--array-throttle", type=int, default=8, help="Max concurrent array tasks (default: 8)")
        parser.add_argument("--partition", default=None, help="SLURM partition (default: dataset config, typically 'bigmem')")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for xcpd pipeline", file=sys.stderr)
            sys.exit(1)

        resources = resolve_resources(args, self.default_resources)
        nthreads = resources["nthreads"]
        mem_per_cpu_gb = resources["mem_per_cpu_gb"]
        time = resources["time"]

        n_subjects = count_subjects(dataset_config["subjects_file"])

        image_path = str(Path(dataset_config["image_dir"]) / f"xcpd_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/xcpd_{dataset_name}_{args.version}"

        fmriprep_dir = getattr(args, "fmriprep_dir_override", None) or \
            f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.fmriprep_version}"
        output_dir = f"{dataset_config['bids_dir']}/derivatives/xcp_d_{args.version}"
        log_dir = f"{output_dir}/logs"

        partition = args.partition if args.partition else dataset_config.get("partition", "bigmem")
        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_subjects": n_subjects,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": partition,
            "log_dir": log_dir,
            "mail_line": mail_line,
            "subjects_file": dataset_config["subjects_file"],
            "image_path": image_path,
            "fmriprep_dir": fmriprep_dir,
            "output_dir": output_dir,
            "work_dir": work_dir,
            "fs_license": fs_license,
            "xcpd_version": args.version,
            "fmriprep_version": args.fmriprep_version,
            "xcpd_args": args.xcpd_args,
            "array_throttle": args.array_throttle,
        }


register(XcpdPipeline())
