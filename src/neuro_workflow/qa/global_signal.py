from __future__ import annotations

import logging
import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import numpy as np
    import nibabel as nib
except ImportError:
    plt = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

logger = logging.getLogger(__name__)


def parse_bids_meta(path: Path) -> dict:
    sub_match = re.search(r"sub-s(\d+)", path.name)
    ses_match = re.search(r"ses-(\d+)", path.name)
    task_match = re.search(r"task-([a-zA-Z0-9]+)", path.name)
    return {
        "sub_val": int(sub_match.group(1)) if sub_match else 0,
        "sub_str": sub_match.group(0) if sub_match else "sub-unknown",
        "ses_val": int(ses_match.group(1)) if ses_match else 0,
        "task": task_match.group(1) if task_match else "unknown",
        "path": path,
    }


def _calculate_global_signal(nifti_path: Path):
    img = nib.load(str(nifti_path))
    data = img.get_fdata()
    return np.mean(data, axis=(0, 1, 2))


class GlobalSignalQa:
    name = "global-signal"
    description = "Calculate and plot global signal from echo-2 BOLD data"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--output-dir", default=None, help="Output directory for figures")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if plt is None:
            print(
                "Error: 'matplotlib', 'nibabel', 'numpy' required. Install with: uv pip install -e \".[qa]\""
            )
            return

        bids_dir = Path(dataset_config["bids_dir"])
        output_dir = Path(
            getattr(args, "output_dir", None) or f"{bids_dir}/derivatives/global_signal_figs"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        all_files = list(bids_dir.glob("sub-s*/ses-*/func/*echo-2*nii.gz"))
        if not all_files:
            print("No echo-2 BOLD files found")
            return

        meta_list = [parse_bids_meta(f) for f in all_files]
        meta_list.sort(key=lambda x: (x["sub_val"], x["ses_val"], x["task"]))

        ordered_subs = list(dict.fromkeys(m["sub_val"] for m in meta_list))
        pdf_path = output_dir / "all_subjects_global_signal.pdf"

        with PdfPages(pdf_path) as pdf:
            for sub_val in ordered_subs:
                sub_files = [m for m in meta_list if m["sub_val"] == sub_val]
                sub_str = sub_files[0]["sub_str"]
                num_runs = len(sub_files)
                logger.info(f"Processing {sub_str}: {num_runs} runs...")

                fig, axes = plt.subplots(num_runs, 1, figsize=(12, 2.5 * num_runs), squeeze=False)
                for i, (m, ax_arr) in enumerate(zip(sub_files, axes)):
                    ax = ax_arr[0]
                    try:
                        gs = _calculate_global_signal(m["path"])
                        ax.plot(gs, color="#1a5276", linewidth=1.0)
                        ax.axvline(x=7, color="#c0392b", linestyle="--", alpha=0.7, label="TR=7")
                        ax.set_title(
                            f"ses-{m['ses_val']:02d} | task-{m['task']} | {m['path'].name}",
                            fontsize=8,
                        )
                        ax.set_ylabel("Intensity", fontsize=7)
                        if i == num_runs - 1:
                            ax.set_xlabel("TR", fontsize=8)
                    except Exception as e:
                        logger.error(f'Error processing {m["path"].name}: {e}')

                plt.tight_layout()
                png_path = output_dir / f"{sub_str}_global_signal.png"
                fig.savefig(png_path, dpi=150)
                pdf.savefig(fig)
                plt.close()

        print(f"PDF created at: {pdf_path}")


register_qa(GlobalSignalQa())
