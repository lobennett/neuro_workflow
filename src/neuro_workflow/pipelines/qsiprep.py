import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import ContainerPipeline, register


class QsiprepPipeline(ContainerPipeline):
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
        self._require_version(args)
        resources = self._resolve(args)

        n_subjects = count_subjects(dataset_config["subjects_file"])
        mem_mb = int(resources["nthreads"] * resources["mem_per_cpu_gb"] * 1000 * 0.9)
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/qsiprep_{dataset_name}_{args.version}"

        return {
            **self._base_context(
                dataset_name,
                dataset_config,
                resources,
                log_dir=self._log_dir(dataset_config, args.version),
                image_path=self._image_path(dataset_config, args.version),
            ),
            "n_subjects": n_subjects,
            "subjects_file": dataset_config["subjects_file"],
            "bids_dir": dataset_config["bids_dir"],
            "work_dir": work_dir,
            "fs_license": fs_license,
            "qsiprep_version": args.version,
            "mem_mb": mem_mb,
            "output_resolution": args.output_resolution,
            "qsiprep_args": args.qsiprep_args,
        }


register(QsiprepPipeline())
