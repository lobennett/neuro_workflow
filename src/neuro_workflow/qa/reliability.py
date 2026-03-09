from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

try:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.animation import FuncAnimation
    from nilearn.image import mean_img
    from nilearn.plotting import plot_epi
except ImportError:
    plt = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

FILENAME_PATTERN = re.compile(
    r'sub-(\w+)_ses-(\w+)_task-(\w+)_run-(\d+)_space-T1w_desc-preproc_bold\.nii\.gz'
)


def parse_bids_filename(filename: str) -> Optional[dict]:
    match = FILENAME_PATTERN.search(filename)
    if not match:
        return None
    return {
        'subject': match.group(1),
        'session': match.group(2),
        'task': match.group(3),
        'run': int(match.group(4)),
    }


def _group_by_subject(file_paths):
    subjects = {}
    for fp in file_paths:
        parsed = parse_bids_filename(fp.name)
        if parsed is None:
            continue
        sub = parsed['subject']
        subjects.setdefault(sub, []).append({'path': fp, **{k: v for k, v in parsed.items() if k != 'subject'}})
    return subjects


def _sort_frames(frames):
    def key(f):
        ses_num = int(re.search(r'\d+', f['session']).group())
        return (ses_num, f['task'], f['run'])
    return sorted(frames, key=key)


def _create_movie(subject, frames, output_path):
    mean_images = []
    coords = None
    for frame in frames:
        avg = mean_img(str(frame['path']))
        if coords is None:
            coords = (avg.shape[0] // 2, avg.shape[1] // 2, avg.shape[2] // 2)
        mean_images.append(avg)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    views = [('z', coords[2], 'axial'), ('x', coords[0], 'sagittal'), ('y', coords[1], 'coronal')]

    def update(idx):
        for ax in axes:
            ax.clear()
        frame = frames[idx]
        label = f'{frame["task"]} ses-{frame["session"]} run-{frame["run"]:02d}'
        for ax, (mode, coord, title) in zip(axes, views):
            plot_epi(mean_images[idx], display_mode=mode, cut_coords=[coord], title=title, axes=ax, annotate=False, colorbar=False)
        fig.suptitle(label, fontsize=14)
        return []

    anim = FuncAnimation(fig, update, frames=len(mean_images), interval=1000, blit=False)
    anim.save(str(output_path), writer='ffmpeg', fps=1, codec='mpeg4')
    plt.close(fig)
    print(f'  Saved movie: {output_path} ({len(mean_images)} frames)')


class ReliabilityQa:
    name = "reliability"
    description = "Create MP4 movies showing fMRI reliability across sessions"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--fmriprep-version", default=None, help="fMRIPrep version for derivatives path")
        parser.add_argument("--output-dir", default=None, help="Output directory for movies")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if plt is None:
            print("Error: 'nilearn', 'matplotlib' required. Install with: uv pip install -e \".[qa]\"")
            return

        bids_dir = Path(dataset_config["bids_dir"])
        version = getattr(args, "fmriprep_version", None) or "24.1.0rc2"
        deriv_dir = bids_dir / "derivatives" / f"fmriprep_{version}"
        output_dir = Path(getattr(args, "output_dir", None) or str(bids_dir / "derivatives" / "reliability_figs"))
        output_dir.mkdir(parents=True, exist_ok=True)

        files = list(deriv_dir.glob("sub-s*/ses-*/func/*space-T1w_desc-preproc_bold.nii.gz"))
        if not files:
            print(f"No preprocessed BOLD files found in {deriv_dir}")
            return

        print(f"Found {len(files)} T1w preprocessed files")
        subjects = _group_by_subject(files)
        print(f"Found {len(subjects)} subjects")

        for sub in sorted(subjects):
            print(f"\nProcessing sub-{sub} ({len(subjects[sub])} files)...")
            frames = _sort_frames(subjects[sub])
            out = output_dir / f"sub-{sub}_reliability_movie.mp4"
            try:
                _create_movie(sub, frames, out)
            except Exception as e:
                print(f"  ERROR for sub-{sub}: {e}")

        print("\nDone.")


register_qa(ReliabilityQa())
