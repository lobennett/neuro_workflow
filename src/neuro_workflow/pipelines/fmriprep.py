import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import (
    ContainerPipeline,
    register,
    resolve_pipeline_subjects,
    write_subjects_file,
)


class FmriprepPipeline(ContainerPipeline):
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
        output_group = parser.add_mutually_exclusive_group()
        output_group.add_argument("--output-dir", default=None,
            help="Output derivatives root (default: <bids_dir>/derivatives)")
        output_group.add_argument(
            "--bids-dir-override",
            default=None,
            help="Path to bind as /data instead of the registered bids_dir. Use to "
                 "point fmriprep at a symlink BIDS view. Output derivatives still go "
                 "to <registered bids_dir>/derivatives/fmriprep_<version>/.",
        )
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 8)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 5-00:00:00)")
        parser.add_argument("--array-throttle", type=int, default=8, help="Max concurrent array tasks (default: 8)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        self._require_version(args)
        resources = self._resolve(args)
        nthreads = resources["nthreads"]
        mem_per_cpu_gb = resources["mem_per_cpu_gb"]

        # Canonical subject resolution (pipeline_config.json `samples`),
        # fail-loud. Write the list to a real file in the run's work dir so the
        # rendered sbatch references an existing path (the registered
        # subjects_*.txt was removed in PR1a).
        subjects = resolve_pipeline_subjects(dataset_name, dataset_config)
        n_subjects = len(subjects)
        mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

        image_path = self._image_path(dataset_config, args.version)
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{args.version}"
        subjects_file = str(
            write_subjects_file(subjects, work_dir, "subjects.txt")
        )

        bids_dir_override = getattr(args, "bids_dir_override", None)
        output_dir = getattr(args, "output_dir", None)

        if bids_dir_override:
            # Input is the view; output is forced to the registered BIDS dir's derivatives/
            bids_dir_for_bind = bids_dir_override
            registered_derivs = f"{dataset_config['bids_dir']}/derivatives"
            output_bind_line = f"  -B {registered_derivs}:/out \\\n"
            output_container = "/out"
            log_dir = f"{registered_derivs}/fmriprep_{args.version}/logs"
        elif output_dir:
            bids_dir_for_bind = dataset_config["bids_dir"]
            output_bind_line = f"  -B {output_dir}:/out \\\n"
            output_container = "/out"
            log_dir = f"{output_dir}/fmriprep_{args.version}/logs"
        else:
            bids_dir_for_bind = dataset_config["bids_dir"]
            output_bind_line = ""
            output_container = "/data/derivatives"
            log_dir = self._log_dir(dataset_config, args.version)

        if args.bids_filter_file:
            filter_path = Path(args.bids_filter_file)
            config_bind_line = f"  -B {filter_path.parent}:/config \\\n"
            bids_filter_arg = f"--bids-filter-file /config/{filter_path.name}"
        else:
            config_bind_line = ""
            bids_filter_arg = ""

        return {
            **self._base_context(
                dataset_name,
                dataset_config,
                resources,
                log_dir=log_dir,
                image_path=image_path,
            ),
            "n_subjects": n_subjects,
            "array_throttle": getattr(args, "array_throttle", 8),
            "subjects_file": subjects_file,
            "bids_dir": bids_dir_for_bind,
            "templateflow_dir": dataset_config["templateflow_dir"],
            "work_dir": work_dir,
            "config_bind_line": config_bind_line,
            "output_bind_line": output_bind_line,
            "output_container": output_container,
            "fmriprep_version": args.version,
            "mem_mb": mem_mb,
            "output_spaces": args.output_spaces,
            "fs_license_container": fs_license,
            "bids_filter_arg": bids_filter_arg,
            "fmriprep_args": args.fmriprep_args,
        }


# Auto-register when module is imported
register(FmriprepPipeline())
