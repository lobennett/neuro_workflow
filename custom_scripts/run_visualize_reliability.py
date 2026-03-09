#!/usr/bin/env python3
"""
Creates movies of averaged scan data to see reliability across sessions. Attempts to
replicate Kendrick Kay's quality assurance figures from his talk.
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation
from nilearn.image import mean_img
from nilearn.plotting import plot_epi

# PATHS
DISCOVERY_BIDS = Path(
    '/oak/stanford/groups/russpold/data/network_grant/'
    'discovery_BIDS_20250402/derivatives/fmriprep_24.1.0rc2'
)
OUTPUT_DIR = Path(
    '/oak/stanford/groups/russpold/data/network_grant/'
    'discovery_BIDS_20250402/derivatives/reliability_figs'
)

FILENAME_PATTERN = re.compile(
    r'sub-(\w+)_ses-(\w+)_task-(\w+)_run-(\d+)_space-T1w_desc-preproc_bold\.nii\.gz'
)


def parse_bids_filename(filename):
    """Extract subject, session, task, and run from a BIDS filename."""
    match = FILENAME_PATTERN.search(filename)
    if not match:
        return None
    return {
        'subject': match.group(1),
        'session': match.group(2),
        'task': match.group(3),
        'run': int(match.group(4)),
    }


def group_files_by_subject(file_paths):
    """Group file paths by subject, with parsed BIDS metadata."""
    subjects = {}
    for file_path in file_paths:
        parsed = parse_bids_filename(file_path.name)
        if parsed is None:
            print(f'  Skipping unrecognized filename: {file_path.name}')
            continue
        sub = parsed['subject']
        subjects.setdefault(sub, []).append({
            'path': file_path,
            'session': parsed['session'],
            'task': parsed['task'],
            'run': parsed['run'],
        })
    return subjects


def sort_frames(frames):
    """Sort frames by session (numeric), task (alpha), run (numeric)."""
    def sort_key(frame):
        ses_num = int(re.search(r'\d+', frame['session']).group())
        return (ses_num, frame['task'], frame['run'])

    return sorted(frames, key=sort_key)


def get_middle_coords(img):
    """Return the middle voxel coordinates (x, y, z) of a 3D image."""
    return (
        img.shape[0] // 2,
        img.shape[1] // 2,
        img.shape[2] // 2,
    )


def create_subject_movie(subject, frames, output_path):
    """Create an MP4 movie for a single subject.

    Each frame shows axial, sagittal, and coronal slices side by side.
    """
    print(f'  Computing mean images for {len(frames)} files...')
    mean_images = []
    coords = None

    for i, frame in enumerate(frames):
        avg_img = mean_img(str(frame['path']))
        if coords is None:
            coords = get_middle_coords(avg_img)
            print(f'  Using middle coords (x={coords[0]}, y={coords[1]}, z={coords[2]}) for all frames')
        mean_images.append(avg_img)
        print(f'    [{i + 1}/{len(frames)}] {frame["task"]} ses-{frame["session"]} run-{frame["run"]:02d}')

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    views = [('z', coords[2], 'axial'), ('x', coords[0], 'sagittal'), ('y', coords[1], 'coronal')]

    def update(frame_idx):
        for ax in axes:
            ax.clear()
        frame = frames[frame_idx]
        label = f'{frame["task"]} ses-{frame["session"]} run-{frame["run"]:02d}'
        for ax, (mode, coord, view_label) in zip(axes, views):
            plot_epi(
                mean_images[frame_idx],
                display_mode=mode,
                cut_coords=[coord],
                title=view_label,
                axes=ax,
                annotate=False,
                colorbar=False,
            )
        fig.suptitle(label, fontsize=14)
        return []

    anim = FuncAnimation(
        fig,
        update,
        frames=len(mean_images),
        interval=1000,
        blit=False,
    )

    anim.save(str(output_path), writer='ffmpeg', fps=1, codec='mpeg4')
    plt.close(fig)
    print(f'  Saved movie to {output_path} ({len(mean_images)} frames)')


def main() -> int:
    """
    Main function to create "movie" figures from optimally combined images.

    Returns:
        Exit code (0 for success)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    discovery_files = list(
        DISCOVERY_BIDS.glob('sub-s*/ses-*/func/*space-T1w_desc-preproc_bold.nii.gz')
    )
    print(f'Found {len(discovery_files)} T1w preprocessed files')
    print('=' * 60)

    subjects = group_files_by_subject(discovery_files)
    print(f'Found {len(subjects)} subjects')

    for sub in sorted(subjects):
        print(f'\nProcessing sub-{sub} ({len(subjects[sub])} files)...')
        frames = sort_frames(subjects[sub])
        output_path = OUTPUT_DIR / f'sub-{sub}_reliability_movie.mp4'

        try:
            create_subject_movie(sub, frames, output_path)
        except Exception as e:
            print(f'  ERROR for sub-{sub}: {e}')

    print('\nDone.')
    return 0


if __name__ == '__main__':
    exit(main())
