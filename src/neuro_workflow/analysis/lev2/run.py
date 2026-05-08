#!/usr/bin/env python3
"""Level 2 GLM Analysis script for group-level statistical analysis."""

# Note: `randomise_prep` is lazy-imported inside run_level2_analysis (the only
# call site). Module-level import would force test environments without the
# `lev1` extras installed to fail at import time, even when only testing
# helpers like discover_input_files. Lazy import surfaces a clear
# ModuleNotFoundError when randomise actually gets called in production.

from pathlib import Path
from nilearn.masking import intersect_masks
from nilearn.image import math_img
from typing import List
import sys
import argparse
import subprocess
import glob


def compute_mask(input_files, threshold=1.0, connected=True):
    """
    Computes a group mask by intersecting individual subject masks.

    Each subject's effect size map is converted to a binary mask (1 where
    data is not zero, 0 otherwise). These individual masks are then
    intersected to create a final group mask.

    Parameters
    ----------
    input_files : list of str or Path
        List of paths to first-level effect size files.
    threshold : float, optional
        The proportion of masks in which a voxel must be active to be
        included in the final mask. 1.0 (default) means a strict
        intersection (voxel must be in all masks).
    connected : bool, optional
        If True, only the largest connected component of the final
        mask is returned. Default is True.

    Returns
    -------
    nibabel.nifti1.Nifti1Image
        The combined group mask image.
    """
    print('== Generating a mask for each of the input files ==')
    subject_masks = [math_img('img != 0', img=f) for f in input_files]

    print('== Intersecting subject masks to create the final group mask ==')
    group_mask = intersect_masks(
        subject_masks, threshold=threshold, connected=connected
    )

    return group_mask


def discover_input_files(level1_dirs: List[Path], contrast_name: str) -> List[str]:
    """
    Discover input files for a specific contrast from multiple level1 output directories.

    Files tagged `_desc-belowMinRuns_` (subjects whose fixed-effects came
    from fewer than `min_runs` retained sessions, see lev1 design 2026-05-07)
    are filtered out automatically.

    Args:
        level1_dirs: List of paths to level1 output directories
        contrast_name: Task_contrast name (e.g., 'task-flanker_contrast-incongruent-congruent')

    Returns:
        List of paths to fixed effects files for this contrast (excluding
        _desc-belowMinRuns_ files).
    """
    all_files: List[str] = []
    n_dropped = 0

    for level1_dir in level1_dirs:
        pattern = (
            level1_dir
            / 'sub-*'
            / '*'
            / 'fixed_effects'
            / f'*{contrast_name}_rtmodel-*_stat-fixed-effects.nii.gz'
        )
        files = glob.glob(str(pattern))
        kept = [f for f in files if '_desc-belowMinRuns_' not in f]
        n_dropped += len(files) - len(kept)
        all_files.extend(kept)

    if n_dropped:
        print(
            f'discover_input_files: dropped {n_dropped} '
            f'_desc-belowMinRuns files for contrast {contrast_name}'
        )

    return sorted(all_files)


def run_level2_analysis(
    contrast_name: str,
    input_files: List[str],
    output_dir: Path,
    mask_threshold: float = 1.0,
    num_permutations: int = 5000,
) -> None:
    """Run level 2 analysis for a specific contrast."""
    print(f'Running Level 2 analysis for: {contrast_name}')
    print(f'Found {len(input_files)} input files')

    if not input_files:
        print(f'Error: No input files found for contrast {contrast_name}')
        return

    contrast_output_dir = output_dir / contrast_name
    contrast_output_dir.mkdir(parents=True, exist_ok=True)

    print('Computing group analysis mask...')
    group_mask_img = compute_mask(input_files, threshold=mask_threshold)
    group_mask_path = contrast_output_dir / 'group_mask.nii.gz'
    group_mask_img.to_filename(group_mask_path)
    print(f'--> Group mask saved to: {group_mask_path}')

    print('Setting up FSL randomise...')
    # Lazy import so test environments without the lev1 extras installed
    # can still import + exercise the helpers in this module. In production
    # randomise_prep is in the lev1 extras group; install it via
    # `uv pip install "randomise-prep @ git+https://github.com/jmumford/randomise-prep.git"`
    # if missing. Failure here surfaces a clear ModuleNotFoundError.
    from randomise_prep import setup_randomise_tfce

    script_path = setup_randomise_tfce(
        input_files=input_files,
        group_mask=str(group_mask_path),
        output_directory=str(contrast_output_dir),
        analysis_type='onesample_2sided',
        num_perm=num_permutations,
    )

    print('Running FSL randomise...')
    try:
        result = subprocess.run(
            ['bash', script_path], capture_output=True, text=True, check=True
        )
        print('✓ FSL randomise completed successfully')
        print(f'Results saved to: {contrast_output_dir}')
    except subprocess.CalledProcessError as e:
        print(f'✗ FSL randomise failed: {e}')
        print(f'Stdout: {e.stdout}')
        print(f'Stderr: {e.stderr}')


def get_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Level 2 GLM Analysis for Network R01 dataset'
    )
    parser.add_argument(
        '--contrast',
        type=str,
        required=True,
        help='Contrast name (e.g., "nBack_twoBack-oneBack")',
    )
    parser.add_argument(
        '--level1-dirs', nargs='+', type=str, required=True, help='Level 1 output directories (can specify multiple)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        required=False,
        default='./level2_output',
        help='Level 2 output directory',
    )
    parser.add_argument(
        '--mask-threshold',
        type=float,
        default=0.9,
        help='Threshold for group mask intersection (0.0-1.0)',
    )
    parser.add_argument(
        '--num-permutations',
        type=int,
        default=5000,
        help='Number of permutations for FSL randomise',
    )
    return parser


def main() -> None:
    """Run level 2 analysis with command line arguments."""
    parser = get_parser()
    args = parser.parse_args()

    print('=' * 60)
    print('Level 2 GLM Analysis')
    print('=' * 60)
    print(f'Contrast: {args.contrast}')
    print(f'Level 1 directories: {args.level1_dirs}')
    print(f'Output directory: {args.output_dir}')
    print(f'Mask threshold: {args.mask_threshold}')
    print(f'Permutations: {args.num_permutations}')
    print('=' * 60)
    print()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    level1_dirs = [Path(d) for d in args.level1_dirs]
    for level1_dir in level1_dirs:
        if not level1_dir.exists():
            print(f'ERROR: Level 1 directory not found: {level1_dir}')
            return 1

    # Discover input files for the specific contrast
    print(f'Discovering input files for contrast: {args.contrast}')
    input_files = discover_input_files(level1_dirs, args.contrast)

    if not input_files:
        print(f'ERROR: No input files found for contrast {args.contrast}')
        return 1

    # Run analysis for the specific contrast
    run_level2_analysis(
        args.contrast,
        input_files,
        output_dir,
        args.mask_threshold,
        args.num_permutations,
    )

    print(f'\nLevel 2 GLM analysis completed for {args.contrast}')
    return 0


if __name__ == '__main__':
    exit(main())
