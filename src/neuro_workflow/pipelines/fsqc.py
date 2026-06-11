import sys
from argparse import ArgumentParser, Namespace

from neuro_workflow.pipelines.base import (
    ContainerPipeline,
    register,
    resolve_pipeline_subjects,
)


class FsqcPipeline(ContainerPipeline):
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
        self._require_version(args)
        if not getattr(args, "freesurfer_dir", None):
            print("Error: --freesurfer-dir is required for fsqc pipeline", file=sys.stderr)
            sys.exit(1)

        resources = self._resolve(args)

        subjects = resolve_pipeline_subjects(dataset_name, dataset_config)
        subjects_list = " ".join(
            f"sub-{s}" if not s.startswith("sub-") else s for s in subjects
        )

        output_dir = f"{dataset_config['bids_dir']}/derivatives/fsqc_{args.version}"

        return {
            **self._base_context(
                dataset_name,
                dataset_config,
                resources,
                log_dir=f"{output_dir}/logs",
                image_path=self._image_path(dataset_config, args.version),
            ),
            "freesurfer_dir": args.freesurfer_dir,
            "output_dir": output_dir,
            "subjects_list": subjects_list,
            "fsqc_args": args.fsqc_args,
        }


register(FsqcPipeline())
