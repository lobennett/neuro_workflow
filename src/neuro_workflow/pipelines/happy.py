import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import register


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

        scans.append({
            "bold": str(nifti),
            "bold_json": str(bold_json),
            "phys_tsv": str(phys_tsv),
            "phys_json": str(phys_json),
            "output": str(output),
        })

    return scans


class HappyPipeline:
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
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 2)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 00:10:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for happy pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

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
                f.write(f"{s['bold']} {s['bold_json']} {s['phys_tsv']} {s['phys_json']} {s['output']}\n")

        image_path = str(Path(dataset_config["image_dir"]) / f"rapidtide_{args.version}")
        log_dir = str(deriv_dir / "logs")

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_scans": len(scans),
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "scan_list_file": str(scan_list_file),
            "image_path": image_path,
            "happy_args": args.happy_args,
        }


register(HappyPipeline())
