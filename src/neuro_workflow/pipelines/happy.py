import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import ContainerPipeline, register


def _discover_scans(bids_dir: str, version: str) -> list[dict]:
    """Discover BOLD echo + physio file pairs in a BIDS directory."""
    bids = Path(bids_dir)
    scans = []

    for nifti in sorted(bids.glob("sub-s*/ses-*/func/*_task-rest_*_echo-*_bold.nii.gz")):
        func_dir = nifti.parent
        # Strip .nii.gz then add .json
        bold_json = nifti.with_name(nifti.name.replace(".nii.gz", ".json"))

        base = nifti.name.split("_echo-")[0]
        phys_tsv = func_dir / f"{base}_recording-cardiac_physio.tsv.gz"
        phys_json = func_dir / f"{base}_recording-cardiac_physio.json"

        if not bold_json.exists() or not phys_tsv.exists() or not phys_json.exists():
            continue

        rel = nifti.relative_to(bids)
        output = Path(bids_dir) / "derivatives" / f"rapidtide_{version}" / rel

        scans.append(
            {
                "bold": str(nifti),
                "bold_json": str(bold_json),
                "phys_tsv": str(phys_tsv),
                "phys_json": str(phys_json),
                "output": str(output),
            }
        )

    return scans


class HappyPipeline(ContainerPipeline):
    name = "happy"
    docker_uri = "docker://fredericklab/rapidtide"
    template_name = "happy.sbatch"
    default_resources = {
        "nthreads": 4,
        "mem_per_cpu_gb": 2,
        "time": "00:10:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="Rapidtide version tag (e.g. 3.1.8)")
        parser.add_argument("--happy-args", default="", help="Additional happy arguments")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument(
            "--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 2)"
        )
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 00:10:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        # NOTE: happy does NOT use the base _image_path / _log_dir helpers: its
        # image is the unsuffixed "rapidtide_<v>" dir (prefix != self.name, no
        # .sif) and its log_dir hangs off the discovered derivatives dir.
        self._require_version(args)
        resources = self._resolve(args)

        bids_dir = dataset_config["bids_dir"]
        scans = _discover_scans(bids_dir, args.version)

        if not scans:
            print("Error: no BOLD+physio scan pairs found in BIDS directory", file=sys.stderr)
            sys.exit(1)

        deriv_dir = Path(bids_dir) / "derivatives" / f"rapidtide_{args.version}"
        deriv_dir.mkdir(parents=True, exist_ok=True)
        scan_list_file = deriv_dir / "scan_list.txt"
        with open(scan_list_file, "w") as f:
            for s in scans:
                f.write(
                    f"{s['bold']} {s['bold_json']} {s['phys_tsv']} {s['phys_json']} {s['output']}\n"
                )

        image_path = str(Path(dataset_config["image_dir"]) / f"rapidtide_{args.version}")

        return {
            **self._base_context(
                dataset_name,
                dataset_config,
                resources,
                log_dir=str(deriv_dir / "logs"),
                image_path=image_path,
            ),
            "n_scans": len(scans),
            "scan_list_file": str(scan_list_file),
            "happy_args": args.happy_args,
        }


register(HappyPipeline())
