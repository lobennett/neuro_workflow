#!/usr/bin/env python3
import argparse
import logging
import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import nibabel as nib

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_DISCOVERY_BIDS = '/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/'
DEFAULT_VALIDATION_BIDS = '/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/'
DEFAULT_OUTPUT_DIR = '/scratch/users/logben/global_signal_figs'

def parse_bids_meta(path: Path):
    """Extracts sub, ses, and task for hierarchical numerical sorting."""
    # Extract digits specifically after the 's' in sub-s
    sub_match = re.search(r'sub-s(\d+)', path.name)
    ses_match = re.search(r'ses-(\d+)', path.name)
    task_match = re.search(r'task-([a-zA-Z0-9]+)', path.name)
    
    return {
        # Convert to int for proper numerical sorting (e.g., 3 < 10 < 1035)
        'sub_val': int(sub_match.group(1)) if sub_match else 0,
        'sub_str': sub_match.group(0) if sub_match else "sub-unknown",
        'ses_val': int(ses_match.group(1)) if ses_match else 0,
        'task': task_match.group(1) if task_match else "unknown",
        'path': path
    }

def calculate_global_signal(nifti_path: Path) -> np.ndarray:
    """Calculates mean signal per TR."""
    img = nib.load(str(nifti_path))
    data = img.get_fdata()
    return np.mean(data, axis=(0, 1, 2))

def parse_args():
    parser = argparse.ArgumentParser(description='Calculate and plot global signal for echo-2 BOLD data.')
    parser.add_argument('--discovery-bids', type=str, default=DEFAULT_DISCOVERY_BIDS,
                        help='Path to discovery BIDS directory')
    parser.add_argument('--validation-bids', type=str, default=DEFAULT_VALIDATION_BIDS,
                        help='Path to validation BIDS directory')
    parser.add_argument('--output-dir', type=str, default=DEFAULT_OUTPUT_DIR,
                        help='Output directory for figures')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    discovery_bids = Path(args.discovery_bids)
    validation_bids = Path(args.validation_bids)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / 'all_subjects_global_signal.pdf'

    # 1. Collect all echo-2 files
    all_files = list(discovery_bids.glob('sub-s*/ses-*/func/*echo-2*nii.gz')) + \
                list(validation_bids.glob('sub-s*/ses-*/func/*echo-2*nii.gz'))
    
    # 2. Parse and Sort Hierarchically: Subject -> Session -> Task
    meta_list = [parse_bids_meta(f) for f in all_files]
    meta_list.sort(key=lambda x: (x['sub_val'], x['ses_val'], x['task']))

    # 3. Group by Subject ID (keeping the numerical order for PDF pages)
    # Using dict.fromkeys to preserve order of first appearance in sorted meta_list
    ordered_subs = list(dict.fromkeys(m['sub_val'] for m in meta_list))
    
    with PdfPages(pdf_path) as pdf:
        for sub_val in ordered_subs:
            # Filter metadata for this specific subject
            sub_files = [m for m in meta_list if m['sub_val'] == sub_val]
            sub_str = sub_files[0]['sub_str']
            num_runs = len(sub_files)
            
            logger.info(f'Processing {sub_str}: {num_runs} runs...')

            # Figure sizing based on number of runs
            fig, axes = plt.subplots(num_runs, 1, figsize=(12, 2.5 * num_runs), squeeze=False)

            for i, (m, ax_arr) in enumerate(zip(sub_files, axes)):
                ax = ax_arr[0]
                try:
                    gs = calculate_global_signal(m['path'])
                    ax.plot(gs, color='#1a5276', linewidth=1.0)

                    # Vertical line at TR = 7
                    ax.axvline(x=7, color='#c0392b', linestyle='--', alpha=0.7, label='TR=7')

                    ax.set_title(f"ses-{m['ses_val']:02d} | task-{m['task']} | {m['path'].name}", fontsize=8)
                    ax.set_ylabel('Intensity', fontsize=7)
                    if i == num_runs - 1:
                        ax.set_xlabel('TR', fontsize=8)
                except Exception as e:
                    logger.error(f'Error processing {m["path"].name}: {e}')

            plt.tight_layout()
            png_path = output_dir / f'{sub_str}_global_signal.png'
            fig.savefig(png_path, dpi=150)
            pdf.savefig(fig)
            plt.close()

    logger.info(f'Consolidated PDF created at: {pdf_path}')
    return 0

if __name__ == '__main__':
    exit(main())