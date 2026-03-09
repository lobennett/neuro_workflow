from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import load_subjects
from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources


class MshbmPipeline:
    name = "mshbm"
    docker_uri = None
    template_name = "mshbm.sbatch"
    default_resources = {"nthreads": 1, "mem_gb": 64, "time": "24:00:00"}

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--surface-inputs-dir", required=True, help="Output directory from prep-mshbm")
        parser.add_argument("--output-dir", required=True, help="MSHBM output directory")
        parser.add_argument("--mshbm-dir", default=None, help="Path to PrecisionNetworkMapping repo (default: sibling of neuro_workflow_dir)")
        parser.add_argument("--nthreads", type=int, default=None, help=f"CPUs (default: {self.default_resources['nthreads']})")
        parser.add_argument("--mem-gb", type=int, default=None, help=f"Memory in GB (default: {self.default_resources['mem_gb']})")
        parser.add_argument("--time", default=None, help=f"SLURM time limit (default: {self.default_resources['time']})")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        subjects = load_subjects(dataset_config["subjects_file"])

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        sub_list_file = output_dir / "sub_list.txt"
        sub_list_file.write_text("\n".join(subjects) + "\n")

        neuro_workflow_dir = Path(__file__).resolve().parents[3]
        mshbm_dir = args.mshbm_dir if args.mshbm_dir else str(neuro_workflow_dir.parent / "PrecisionNetworkMapping")

        resources = resolve_resources(args, self.default_resources)

        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "nthreads": resources["nthreads"],
            "mem_gb": resources["mem_gb"],
            "time": resources["time"],
            "partition": dataset_config["partition"],
            "mail_line": mail_line,
            "sub_list_file": str(sub_list_file),
            "output_dir": str(output_dir),
            "mshbm_dir": mshbm_dir,
            "surface_inputs_dir": args.surface_inputs_dir,
        }


register(MshbmPipeline())
