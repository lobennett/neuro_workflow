from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.analysis.task_config.loader import (
    get_all_tasks,
    get_base_tasks,
    get_dual_tasks,
)
from neuro_workflow.core.exclusions import _compiled_path
from neuro_workflow.pipelines.base import (
    LocalAnalysisPipeline,
    register,
    resolve_pipeline_subjects,
)


class Lev1Pipeline(LocalAnalysisPipeline):
    name = "lev1"
    docker_uri = None
    template_name = "lev1.sbatch"
    default_resources = {"nthreads": 1, "mem_gb": 64, "time": "2-00:00:00"}

    def add_cli_args(self, parser: ArgumentParser) -> None:
        task_group = parser.add_mutually_exclusive_group(required=True)
        task_group.add_argument("--tasks", nargs="+", help="Task name(s) to run")
        task_group.add_argument(
            "--all", dest="tasks_flag", action="store_const", const="all", help="Run all tasks"
        )
        task_group.add_argument(
            "--base-tasks",
            dest="tasks_flag",
            action="store_const",
            const="base",
            help="Run base tasks",
        )
        task_group.add_argument(
            "--dual-tasks",
            dest="tasks_flag",
            action="store_const",
            const="dual",
            help="Run dual tasks",
        )
        parser.add_argument("--fmriprep-dir", required=True, help="fMRIPrep derivatives directory")
        parser.add_argument(
            "--results-dir",
            default=None,
            help="Output directory (default: {bids_dir}/derivatives/lev1)",
        )
        parser.add_argument(
            "--exclusions-file",
            default=None,
            help="Path to exclusions JSON file (default: compiled exclusions for dataset)",
        )
        parser.add_argument(
            "--space",
            default="MNI",
            choices=["MNI", "T1w", "surface", "fsaverage6", "fsLR"],
            help="Analysis space",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=1.0,
            help="Mask intersection threshold (default: 1.0)",
        )
        parser.add_argument(
            "--smoothing-fwhm", type=float, default=None, help="Spatial smoothing FWHM in mm"
        )
        parser.add_argument(
            "--residuals",
            action="store_true",
            default=False,
            help="Compute task-regressed residuals",
        )
        parser.add_argument(
            "--fc-confounds",
            action="store_true",
            default=False,
            help="Regress tissue confounds from residuals",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=False,
            help="Skip runs where outputs already exist",
        )
        parser.add_argument(
            "--skip-qc-plots",
            action="store_true",
            default=False,
            help="Skip per-contrast surface QC plots (the .func.gii files are still saved)",
        )
        parser.add_argument(
            "--no-rt",
            action="store_true",
            default=False,
            help="lev1 without response_time (rtmodel-noRT)",
        )
        parser.add_argument(
            "--nthreads",
            type=int,
            default=None,
            help=f"CPUs per task (default: {self.default_resources['nthreads']})",
        )
        parser.add_argument(
            "--mem-gb",
            type=int,
            default=None,
            help=f"Memory in GB (default: {self.default_resources['mem_gb']})",
        )
        parser.add_argument(
            "--time",
            default=None,
            help=f"SLURM time limit (default: {self.default_resources['time']})",
        )

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        # Resolve tasks
        tasks_flag = getattr(args, "tasks_flag", None)
        if tasks_flag == "all":
            tasks = get_all_tasks()
        elif tasks_flag == "base":
            tasks = get_base_tasks()
        elif tasks_flag == "dual":
            tasks = get_dual_tasks()
        else:
            tasks = args.tasks

        # Canonical subject resolution (pipeline_config.json `samples`),
        # fail-loud. The (subject, task) pairs are baked into job_list.txt
        # below, so no separate subjects file is needed for the array.
        subjects = resolve_pipeline_subjects(dataset_name, dataset_config)

        # Resolve results dir (default: {bids_dir}/derivatives/lev1)
        if args.results_dir:
            results_dir = Path(args.results_dir)
        else:
            results_dir = Path(dataset_config["bids_dir"]) / "derivatives" / "lev1"

        # Resolve exclusions file (default: compiled exclusions for this dataset)
        if args.exclusions_file:
            exclusions_file = args.exclusions_file
        else:
            compiled = _compiled_path(dataset_name)
            if not compiled.exists():
                print(
                    f"Error: no --exclusions-file given and no compiled exclusions found for "
                    f"'{dataset_name}'. Run 'neuro-run exclusions compile {dataset_name}' first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            exclusions_file = str(compiled)
            print(f"Using compiled exclusions: {exclusions_file}")
        log_dir = self._make_log_dir(results_dir)
        pairs = [(subj, task) for subj in subjects for task in tasks]
        job_list_file = self._write_list_file(
            log_dir, "job_list.txt", [f"{subj} {task}" for subj, task in pairs]
        )

        resources = self._resolve(args)

        # Build extra flags
        extra_flags = []
        if args.smoothing_fwhm is not None:
            extra_flags.append(f"--smoothing-fwhm {args.smoothing_fwhm}")
        if args.residuals:
            extra_flags.append("--residuals")
        if args.fc_confounds:
            extra_flags.append("--fc-confounds")
        if args.skip_existing:
            extra_flags.append("--skip-existing")
        if getattr(args, "skip_qc_plots", False):
            extra_flags.append("--skip-qc-plots")
        if getattr(args, "no_rt", False):
            extra_flags.append("--no-rt")

        return {
            **self._base_context(dataset_name, dataset_config, resources, log_dir, results_dir),
            "n_jobs": len(pairs),
            "job_list_file": str(job_list_file),
            "bids_dir": dataset_config["bids_dir"],
            "fmriprep_dir": args.fmriprep_dir,
            "exclusions_file": exclusions_file,
            "space": args.space,
            "threshold": args.threshold,
            "extra_flags": " ".join(extra_flags),
        }


register(Lev1Pipeline())
