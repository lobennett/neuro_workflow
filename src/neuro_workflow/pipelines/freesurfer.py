from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import ContainerPipeline, register


class FreesurferPipeline(ContainerPipeline):
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
        parser.add_argument(
            "--subjects-file", default=None, help="CSV file: subject_id,ses_t1,run_t1,ses_t2,run_t2"
        )
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument(
            "--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 16)"
        )
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 4-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        self._require_version(args)
        resources = self._resolve(args)

        # FreeSurfer's subjects file is a CSV carrying per-subject anat metadata
        # (subject_id,ses_t1,run_t1,ses_t2,run_t2) that the canonical sample list
        # cannot supply, so recon-all needs an explicit CSV. The canonical
        # resolver does NOT apply here. Prefer --subjects-file; else fall back to
        # the registered subjects_file. Fail loud (instead of an opaque
        # FileNotFoundError) if neither is a real file -- the registered
        # subjects_*.txt was removed in PR1a.
        fs_subjects_file = getattr(args, "subjects_file", None) or dataset_config.get(
            "subjects_file"
        )
        if not fs_subjects_file or not Path(fs_subjects_file).is_file():
            raise ValueError(
                "freesurfer requires a subjects CSV (subject_id,ses_t1,run_t1,"
                "ses_t2,run_t2). Pass --subjects-file pointing at an existing "
                f"CSV. Got: {fs_subjects_file!r} (not an existing file). The "
                "canonical pipeline_config.json sample list cannot supply the "
                "anat session/run columns recon-all needs."
            )
        # Each non-blank CSV row is one subject (no header). The sbatch template
        # indexes rows via `sed -n "${SLURM_ARRAY_TASK_ID}p"` over array 1..n_subjects,
        # so this count must equal the number of data rows -- count_subjects (shared
        # with fmriprep/qsiprep) does exactly that, with a `with` block (no fd leak).
        n_subjects = count_subjects(fs_subjects_file)

        fs_license = str(Path(args.fs_license).expanduser())

        return {
            **self._base_context(
                dataset_name,
                dataset_config,
                resources,
                log_dir=self._log_dir(dataset_config, args.version),
                image_path=self._image_path(dataset_config, args.version),
            ),
            "n_subjects": n_subjects,
            "bids_dir": dataset_config["bids_dir"],
            "fs_license": fs_license,
            "fs_subjects_file": fs_subjects_file,
            "freesurfer_version": args.version,
        }


register(FreesurferPipeline())
