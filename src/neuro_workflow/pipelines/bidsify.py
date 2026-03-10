"""Bidsify pipeline — submit Flywheel -> BIDS conversion as a SLURM job."""

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources


_DEFAULT_CONTAINER = "/home/groups/russpold/singularity_images/neuro_workflow.sif"


class BidsifyPipeline:
    name = "bidsify"
    docker_uri = None
    template_name = "bidsify.sbatch"
    requires_dataset = False
    default_resources = {
        "time": "1-00:00:00",
        "mem_gb": 8,
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--output-dir", required=True, help="BIDS output directory")
        parser.add_argument("--subjects", nargs="+", help="Subject labels (default: all in sample)")
        parser.add_argument("--flywheel-project", default=None, help="Flywheel project label")
        parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 1-00:00:00)")
        parser.add_argument("--mem-gb", type=int, default=None, help="Memory in GB (default: 8)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        resources = resolve_resources(args, self.default_resources)

        # Build extra args string for the bidsify command
        extra_parts = []
        if args.subjects:
            extra_parts.append("--subjects " + " ".join(args.subjects))
        if args.flywheel_project:
            extra_parts.append(f"--flywheel-project {args.flywheel_project}")
        if args.overwrite:
            extra_parts.append("--overwrite")
        extra_args = " ".join(extra_parts)

        output_dir = Path(args.output_dir)
        log_dir = str(output_dir / "logs")

        return {
            "sample": dataset_name,
            "output_dir": str(output_dir),
            "partition": dataset_config.get("partition", "russpold"),
            "time": resources["time"],
            "mem_gb": resources["mem_gb"],
            "log_dir": log_dir,
            "mail_line": build_mail_line(dataset_config),
            "container": _DEFAULT_CONTAINER,
            "extra_args": extra_args,
        }


register(BidsifyPipeline())
