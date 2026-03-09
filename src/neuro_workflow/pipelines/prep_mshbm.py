from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import load_subjects
from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources


class PrepMshbmPipeline:
    name = "prep-mshbm"
    docker_uri = None
    template_name = "prep_mshbm.sbatch"
    default_resources = {"nthreads": 1, "mem_gb": 64, "time": "24:00:00"}

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--glm-dir", required=True, help="Level-1 GLM results directory")
        parser.add_argument("--fmriprep-dir", required=True, help="fMRIPrep derivatives directory")
        parser.add_argument("--rest-fmriprep-dir", default=None, help="Separate fMRIPrep directory for rest BOLD (optional)")
        parser.add_argument("--output-dir", required=True, help="Output directory for MSHBM surface inputs")
        parser.add_argument("--residuals-space", default="surface", choices=["surface", "MNI", "T1w"], help="Space of task residuals (default: surface)")
        parser.add_argument("--sessions", nargs="+", default=None, help="Only process these sessions (optional)")
        parser.add_argument("--nthreads", type=int, default=None, help=f"CPUs per task (default: {self.default_resources['nthreads']})")
        parser.add_argument("--mem-gb", type=int, default=None, help=f"Memory in GB (default: {self.default_resources['mem_gb']})")
        parser.add_argument("--time", default=None, help=f"SLURM time limit (default: {self.default_resources['time']})")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        subjects = load_subjects(dataset_config["subjects_file"])

        output_dir = Path(args.output_dir)
        log_dir = output_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        subject_list_file = log_dir / "subject_list.txt"
        subject_list_file.write_text("\n".join(subjects) + "\n")

        resources = resolve_resources(args, self.default_resources)

        # Build extra flags
        extra_flags = []
        if args.rest_fmriprep_dir:
            extra_flags.append(f"--rest-fmriprep-dir {args.rest_fmriprep_dir}")
        if args.sessions:
            extra_flags.append("--sessions " + " ".join(args.sessions))

        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "n_subjects": len(subjects),
            "nthreads": resources["nthreads"],
            "mem_gb": resources["mem_gb"],
            "time": resources["time"],
            "partition": dataset_config["partition"],
            "log_dir": str(log_dir),
            "mail_line": mail_line,
            "subject_list_file": str(subject_list_file),
            "glm_dir": args.glm_dir,
            "fmriprep_dir": args.fmriprep_dir,
            "output_dir": str(output_dir),
            "residuals_space": args.residuals_space,
            "extra_flags": " ".join(extra_flags),
            "neuro_workflow_dir": str(Path(__file__).resolve().parents[3]),
        }


register(PrepMshbmPipeline())
