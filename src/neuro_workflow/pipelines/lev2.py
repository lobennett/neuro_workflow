from __future__ import annotations

import glob
import re
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources
from neuro_workflow.pipelines.lev1 import BASE_TASKS, DUAL_TASKS, ALL_TASKS


def _discover_contrasts_from_lev1_dirs(lev1_dirs: list[str], task_filter: list[str] | None = None) -> list[str]:
    """Glob fixed-effects files and extract contrast names."""
    contrasts = set()
    for lev1_dir in lev1_dirs:
        pattern = str(Path(lev1_dir) / "sub-*" / "*" / "fixed_effects" / "*_stat-fixed-effects.nii.gz")
        for fpath in glob.glob(pattern):
            fname = Path(fpath).name
            # Extract task_contrast portion: task-TASK_contrast-NAME
            m = re.search(r'((?:task-[^_]+_)+contrast-[^_]+)', fname)
            if m:
                contrast_id = m.group(1).rstrip('_')
                if task_filter is None:
                    contrasts.add(contrast_id)
                else:
                    task_m = re.search(r'task-([^_]+)', contrast_id)
                    if task_m and task_m.group(1) in task_filter:
                        contrasts.add(contrast_id)
    return sorted(contrasts)


class Lev2Pipeline:
    name = "lev2"
    docker_uri = None
    template_name = "lev2.sbatch"
    default_resources = {"nthreads": 2, "mem_gb": 4, "time": "04:00:00"}

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--lev1-dirs", nargs="+", required=True, help="Level-1 results directories")
        parser.add_argument("--results-dir", required=True, help="Level-2 output directory")
        parser.add_argument("--exclusions-csv", required=True, help="Flagged scans CSV")
        contrast_group = parser.add_mutually_exclusive_group(required=True)
        contrast_group.add_argument("--contrasts", nargs="+", help="Specific contrast names")
        contrast_group.add_argument("--all", dest="contrasts_flag", action="store_const", const="all", help="All contrasts from lev1 dirs")
        contrast_group.add_argument("--base-tasks", dest="contrasts_flag", action="store_const", const="base", help="Contrasts from base tasks")
        contrast_group.add_argument("--dual-tasks", dest="contrasts_flag", action="store_const", const="dual", help="Contrasts from dual tasks")
        parser.add_argument("--mask-threshold", type=float, default=0.9, help="Group mask intersection threshold (default: 0.9)")
        parser.add_argument("--num-permutations", type=int, default=5000, help="FSL randomise permutations (default: 5000)")
        parser.add_argument("--nthreads", type=int, default=None, help=f"CPUs per task (default: {self.default_resources['nthreads']})")
        parser.add_argument("--mem-gb", type=int, default=None, help=f"Memory in GB (default: {self.default_resources['mem_gb']})")
        parser.add_argument("--time", default=None, help=f"SLURM time limit (default: {self.default_resources['time']})")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        contrasts_flag = getattr(args, "contrasts_flag", None)
        if contrasts_flag == "all":
            contrasts = _discover_contrasts_from_lev1_dirs(args.lev1_dirs)
        elif contrasts_flag == "base":
            contrasts = _discover_contrasts_from_lev1_dirs(args.lev1_dirs, task_filter=BASE_TASKS)
        elif contrasts_flag == "dual":
            contrasts = _discover_contrasts_from_lev1_dirs(args.lev1_dirs, task_filter=DUAL_TASKS)
        else:
            contrasts = args.contrasts

        if not contrasts:
            print("Error: no contrasts found", file=sys.stderr)
            sys.exit(1)

        results_dir = Path(args.results_dir)
        log_dir = results_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        contrast_list_file = log_dir / "contrast_list.txt"
        contrast_list_file.write_text("\n".join(contrasts) + "\n")

        resources = resolve_resources(args, self.default_resources)

        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "n_contrasts": len(contrasts),
            "nthreads": resources["nthreads"],
            "mem_gb": resources["mem_gb"],
            "time": resources["time"],
            "partition": dataset_config["partition"],
            "log_dir": str(log_dir),
            "mail_line": mail_line,
            "contrast_list_file": str(contrast_list_file),
            "lev1_dirs": " ".join(args.lev1_dirs),
            "results_dir": str(results_dir),
            "exclusions_csv": args.exclusions_csv,
            "mask_threshold": args.mask_threshold,
            "num_permutations": args.num_permutations,
            "neuro_workflow_dir": str(Path(__file__).resolve().parents[3]),
        }


register(Lev2Pipeline())
