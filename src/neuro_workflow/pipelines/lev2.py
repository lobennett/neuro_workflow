from __future__ import annotations

import glob
import re
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.analysis.task_config.loader import get_base_tasks, get_dual_tasks
from neuro_workflow.pipelines.base import LocalAnalysisPipeline, register


def _discover_contrasts_from_lev1_dirs(
    lev1_dirs: list[str], task_filter: list[str] | None = None, space: str = "volume",
) -> list[str]:
    """Glob fixed-effects files and extract contrast names.

    Real lev1 contrast names contain underscores (e.g. `cue_switch_cost`,
    `response_time`, `task_switch_cue_switch-task_stay_cue_stay`). The
    capture must take everything between `task-` and the next BIDS-entity
    boundary (`_rtmodel-` for current outputs, `_stat-` as a fallback for
    older fixtures), not truncate at the first underscore.

    space selects the fixed-effects file type: volume globs the NIfTI maps;
    surface globs one hemisphere's GIFTI maps (contrasts are identical across
    hemispheres, so the L glob enumerates them).
    """
    if space == "surface":
        leaf = "*_hemi-L_*_stat-fixed-effects.func.gii"
    else:
        leaf = "*_stat-fixed-effects.nii.gz"
    contrasts = set()
    for lev1_dir in lev1_dirs:
        pattern = str(Path(lev1_dir) / "sub-*" / "*" / "fixed_effects" / leaf)
        for fpath in glob.glob(pattern):
            fname = Path(fpath).name
            # Capture task-TASK_contrast-NAME up to the next BIDS entity
            # (rtmodel- if present; stat- as fallback). Non-greedy so multi-
            # underscore contrast names are preserved end-to-end.
            m = re.search(r'(task-[^_]+_contrast-.+?)_(?:rtmodel-|stat-)', fname)
            if m:
                contrast_id = m.group(1)
                if task_filter is None:
                    contrasts.add(contrast_id)
                else:
                    task_m = re.search(r'task-([^_]+)', contrast_id)
                    if task_m and task_m.group(1) in task_filter:
                        contrasts.add(contrast_id)
    return sorted(contrasts)


class Lev2Pipeline(LocalAnalysisPipeline):
    name = "lev2"
    docker_uri = None
    template_name = "lev2.sbatch"
    default_resources = {"nthreads": 2, "mem_gb": 4, "time": "04:00:00"}

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--lev1-dirs", nargs="+", required=True, help="Level-1 results directories")
        parser.add_argument("--results-dir", required=True, help="Level-2 output directory")
        contrast_group = parser.add_mutually_exclusive_group(required=True)
        contrast_group.add_argument("--contrasts", nargs="+", help="Specific contrast names")
        contrast_group.add_argument("--all", dest="contrasts_flag", action="store_const", const="all", help="All contrasts from lev1 dirs")
        contrast_group.add_argument("--base-tasks", dest="contrasts_flag", action="store_const", const="base", help="Contrasts from base tasks")
        contrast_group.add_argument("--dual-tasks", dest="contrasts_flag", action="store_const", const="dual", help="Contrasts from dual tasks")
        parser.add_argument("--space", choices=["volume", "surface"], default="volume", help="volume: FSL randomise on NIfTI fixed-effects (default). surface: sign-flip permutation on GIFTI surface fixed-effects.")
        parser.add_argument("--mask-threshold", type=float, default=0.9, help="Group mask intersection threshold, volume only (default: 0.9)")
        parser.add_argument("--num-permutations", type=int, default=5000, help="Permutations (randomise for volume; sign-flip for surface) (default: 5000)")
        parser.add_argument("--seed", type=int, default=0, help="RNG seed for the surface sign-flip permutation (default: 0)")
        parser.add_argument("--nthreads", type=int, default=None, help=f"CPUs per task (default: {self.default_resources['nthreads']})")
        parser.add_argument("--mem-gb", type=int, default=None, help=f"Memory in GB (default: {self.default_resources['mem_gb']})")
        parser.add_argument("--time", default=None, help=f"SLURM time limit (default: {self.default_resources['time']})")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        space = getattr(args, "space", "volume")
        contrasts_flag = getattr(args, "contrasts_flag", None)
        if contrasts_flag == "all":
            contrasts = _discover_contrasts_from_lev1_dirs(args.lev1_dirs, space=space)
        elif contrasts_flag == "base":
            contrasts = _discover_contrasts_from_lev1_dirs(args.lev1_dirs, task_filter=get_base_tasks(), space=space)
        elif contrasts_flag == "dual":
            contrasts = _discover_contrasts_from_lev1_dirs(args.lev1_dirs, task_filter=get_dual_tasks(), space=space)
        else:
            contrasts = args.contrasts

        if not contrasts:
            print("Error: no contrasts found", file=sys.stderr)
            sys.exit(1)

        results_dir = Path(args.results_dir)
        log_dir = self._make_log_dir(results_dir)
        contrast_list_file = self._write_list_file(log_dir, "contrast_list.txt", contrasts)

        resources = self._resolve(args)

        # Surface uses the self-contained numpy sign-flip test (no FSL); volume
        # uses FSL randomise.
        module_loads = (
            "module load uv" if space == "surface"
            else "module load biology fsl\nmodule load uv"
        )

        return {
            **self._base_context(dataset_name, dataset_config, resources, log_dir, results_dir),
            "n_contrasts": len(contrasts),
            "contrast_list_file": str(contrast_list_file),
            "lev1_dirs": " ".join(args.lev1_dirs),
            "space": space,
            "module_loads": module_loads,
            "mask_threshold": args.mask_threshold,
            "num_permutations": args.num_permutations,
            "seed": getattr(args, "seed", 0),
        }


register(Lev2Pipeline())
