#!/usr/bin/env python3
"""Level 2 GLM Analysis script for group-level statistical analysis."""

from randomise_prep import setup_randomise_tfce
from pathlib import Path
from nilearn.masking import intersect_masks
from nilearn.image import math_img
from typing import List
import sys
import argparse
import subprocess
import glob
import pandas as pd


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


def filter_flagged_scans(input_files: List[str], flagged_scans_csv: str, contrast_name: str) -> List[str]:
    """
    Filter out input files that are flagged in the flagged scans CSV.
    
    Args:
        input_files: List of paths to input files
        flagged_scans_csv: Path to CSV file with flagged scans
        contrast_name: Name of the contrast being analyzed
        
    Returns:
        Filtered list of input files with flagged scans removed
    """
    if not flagged_scans_csv or not Path(flagged_scans_csv).exists():
        print(f"No flagged scans file provided or file doesn't exist: {flagged_scans_csv}")
        return input_files
        
    # Load flagged scans
    flagged_df = pd.read_csv(flagged_scans_csv)
    
    # Extract contrast from contrast_name (e.g., 'task-baseline' from 'cuedTS_task-baseline')
    if '_' in contrast_name:
        contrast_part = contrast_name.split('_', 1)[1]  # Get part after first underscore
    else:
        contrast_part = contrast_name
    
    # Filter flagged scans for this contrast
    flagged_for_contrast = flagged_df[flagged_df['contrast_name'] == contrast_part]
    
    if flagged_for_contrast.empty:
        print(f"No flagged scans found for contrast: {contrast_part}")
        return input_files
    
    # Build set of flagged file identifiers
    flagged_identifiers = set()
    for _, row in flagged_for_contrast.iterrows():
        # Extract subject, session, run from subject_label (e.g., 'sub-s03_ses-02_run-1')
        subject_label = row['subject_label']
        task_name = row['task_name']
        
        # Create identifier that matches the file path pattern
        flagged_identifiers.add(f"{subject_label}_task-{task_name}")
    
    # Filter input files
    filtered_files = []
    excluded_count = 0
    
    for file_path in input_files:
        file_name = Path(file_path).name
        
        # Check if this file matches any flagged identifier
        is_flagged = any(flagged_id in file_name for flagged_id in flagged_identifiers)
        
        if not is_flagged:
            filtered_files.append(file_path)
        else:
            excluded_count += 1
            print(f"Excluding flagged file: {file_path}")
    
    print(f"Excluded {excluded_count} flagged files out of {len(input_files)} total files")
    print(f"Remaining files for analysis: {len(filtered_files)}")
    
    return filtered_files


def discover_input_files(level1_dirs: List[Path], contrast_name: str) -> List[str]:
    """
    Discover input files for a specific contrast from multiple level1 output directories.

    Args:
        level1_dirs: List of paths to level1 output directories
        contrast_name: Task_contrast name (e.g., 'task-flanker_contrast-incongruent-congruent')

    Returns:
        List of paths to fixed effects files for this contrast
    """
    all_files = []
    
    for level1_dir in level1_dirs:
        # Find all files matching this task_contrast pattern
        pattern = (
            level1_dir
            / 'sub-*'
            / '*'
            / 'fixed_effects'
            / f'*{contrast_name}_rtmodel-*_stat-fixed-effects.nii.gz'
        )
        files = glob.glob(str(pattern))
        all_files.extend(files)

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
    parser.add_argument(
        '--flagged-scans-csv',
        type=str,
        required=True,
        help='Path to CSV file containing flagged scans to exclude from analysis',
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
    print(f'Flagged scans CSV: {args.flagged_scans_csv}')
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

    # Filter out flagged scans using provided CSV file
    print(f'Filtering flagged scans using: {args.flagged_scans_csv}')
    input_files = filter_flagged_scans(input_files, args.flagged_scans_csv, args.contrast)
    
    if not input_files:
        print(f'ERROR: No input files remain after filtering flagged scans for contrast {args.contrast}')
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
