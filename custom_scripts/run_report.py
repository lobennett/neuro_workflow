import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import re
from collections import defaultdict
from typing import List

def get_flag_reason(df: pd.DataFrame, thresholds: dict) -> pd.Series:
    """
    Checks a DataFrame against flagging criteria
    """
    vif_thresh = thresholds['vif_exclusion']
    outlier_thresh = thresholds['outlier_exclusion']
    
    conditions = [
        (df['VIF'] >= vif_thresh) & (df['image_outlier_percentage'] >= outlier_thresh),
        df['VIF'] >= vif_thresh,
        df['image_outlier_percentage'] >= outlier_thresh,
    ]
    reasons = [
        f'VIF >= {vif_thresh}; Outlier >= {outlier_thresh}%',
        f'VIF >= {vif_thresh}',
        f'Outlier >= {outlier_thresh}%',
    ]
    return np.select(conditions, reasons, default='')


def summarize_flagged_scans(flagged_df: pd.DataFrame):
    """
    Groups flagged scans by contrast and returns a summary DataFrame.
    """
    if flagged_df.empty:
        print('No scans were flagged. No summary to generate.')
        return pd.DataFrame()

    contrast_counts = (
        flagged_df.groupby('contrast_name')
        .size()
        .reset_index(name='flagged_scan_count')
    )
    contrast_counts = contrast_counts.sort_values(
        by='flagged_scan_count', ascending=False
    )

    total_flags = contrast_counts['flagged_scan_count'].sum()
    total_row = pd.DataFrame(
        [{'contrast_name': 'Total', 'flagged_scan_count': total_flags}]
    )

    summary_df = pd.concat([contrast_counts, total_row], ignore_index=True)
    return summary_df


def summarize_flagged_by_category(flagged_df: pd.DataFrame, thresholds: dict):
    """
    Summarize flagged scans by category: VIF only, Outliers only, or Both.
    """
    if flagged_df.empty:
        print('No scans were flagged for category breakdown.')
        return pd.DataFrame()

    # Define categories based on new criteria
    vif_thresh = thresholds['vif_exclusion']
    outlier_thresh = thresholds['outlier_exclusion']
    
    vif_only = (flagged_df['VIF'] >= vif_thresh) & (flagged_df['image_outlier_percentage'] < outlier_thresh)
    outliers_only = (flagged_df['VIF'] < vif_thresh) & (flagged_df['image_outlier_percentage'] >= outlier_thresh)
    both = (flagged_df['VIF'] >= vif_thresh) & (flagged_df['image_outlier_percentage'] >= outlier_thresh)

    category_counts = pd.DataFrame([
        {'category': f'VIF >= {vif_thresh} only', 'count': vif_only.sum()},
        {'category': f'Outliers >= {outlier_thresh}% only', 'count': outliers_only.sum()},
        {'category': f'Both (VIF >= {vif_thresh} & Outliers >= {outlier_thresh}%)', 'count': both.sum()},
        {'category': 'Total', 'count': len(flagged_df)}
    ])
    
    return category_counts


def create_contrast_exclusion_summary(flagged_df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """
    Create a detailed CSV summary grouped by contrast showing exclusion counts
    for discovery/validation network samples.
    """
    if flagged_df.empty:
        print('No scans were flagged for contrast summary.')
        return pd.DataFrame()
    
    # Group by contrast and count exclusions with detailed breakdown
    contrast_summary = []
    
    for contrast, group in flagged_df.groupby('contrast_name'):
        # Count total exclusions for this contrast
        total_excluded = len(group)
        
        # Count by exclusion reason
        vif_thresh = thresholds['vif_exclusion']
        outlier_thresh = thresholds['outlier_exclusion']
        
        vif_only = len(group[(group['VIF'] >= vif_thresh) & (group['image_outlier_percentage'] < outlier_thresh)])
        outliers_only = len(group[(group['VIF'] < vif_thresh) & (group['image_outlier_percentage'] >= outlier_thresh)])
        both = len(group[(group['VIF'] >= vif_thresh) & (group['image_outlier_percentage'] >= outlier_thresh)])
        
        # Count unique subjects affected
        unique_subjects = group['subject_label'].nunique()
        
        # Get basic stats
        mean_vif = group['VIF'].mean()
        mean_outlier_pct = group['image_outlier_percentage'].mean()
        
        contrast_summary.append({
            'contrast_name': contrast,
            'total_exclusions': total_excluded,
            'exclusions_vif_only': vif_only,
            'exclusions_outliers_only': outliers_only,
            'exclusions_both': both,
            'unique_subjects_affected': unique_subjects,
            'mean_vif': round(mean_vif, 2),
            'mean_outlier_percentage': round(mean_outlier_pct, 2),
            'vif_range': f"{group['VIF'].min():.1f}-{group['VIF'].max():.1f}",
            'outlier_range': f"{group['image_outlier_percentage'].min():.1f}-{group['image_outlier_percentage'].max():.1f}%"
        })
    
    summary_df = pd.DataFrame(contrast_summary)
    summary_df = summary_df.sort_values('total_exclusions', ascending=False)
    
    # Add total row
    total_row = pd.DataFrame([{
        'contrast_name': 'TOTAL_ALL_CONTRASTS',
        'total_exclusions': summary_df['total_exclusions'].sum(),
        'exclusions_vif_only': summary_df['exclusions_vif_only'].sum(),
        'exclusions_outliers_only': summary_df['exclusions_outliers_only'].sum(),
        'exclusions_both': summary_df['exclusions_both'].sum(),
        'unique_subjects_affected': flagged_df['subject_label'].nunique(),
        'mean_vif': round(flagged_df['VIF'].mean(), 2),
        'mean_outlier_percentage': round(flagged_df['image_outlier_percentage'].mean(), 2),
        'vif_range': f"{flagged_df['VIF'].min():.1f}-{flagged_df['VIF'].max():.1f}",
        'outlier_range': f"{flagged_df['image_outlier_percentage'].min():.1f}-{flagged_df['image_outlier_percentage'].max():.1f}%"
    }])
    
    return pd.concat([summary_df, total_row], ignore_index=True)


def parse_contrast_filepath(filepath: Path) -> dict:
    """
    Parse contrast filepath to extract subject, session, task, contrast information.
    
    Example filepath: sub-s03_ses-10_task-cuedTS_run-1_contrast-task_switch_cost_rtmodel-RTDur_stat-effect-size.nii.gz
    """
    filename = filepath.name
    
    # Extract components using regex
    subject_match = re.search(r'(sub-s\d+)', filename)
    session_match = re.search(r'(ses-\d+)', filename)
    task_match = re.search(r'task-([^_]+)', filename)
    run_match = re.search(r'run-(\d+)', filename)
    
    # Extract contrast name between 'contrast-' and '_rtmodel-'
    contrast_match = re.search(r'contrast-([^_]+(?:_[^_]+)*)_rtmodel-', filename)
    
    return {
        'subject': subject_match.group(1) if subject_match else None,
        'session': session_match.group(1) if session_match else None,
        'task': task_match.group(1) if task_match else None,
        'run': run_match.group(1) if run_match else None,
        'contrast': contrast_match.group(1) if contrast_match else None,
        'filepath': filepath
    }


def count_total_contrast_files(lev1_dirs: List[Path]) -> pd.DataFrame:
    """
    Count total available contrast files by subject/session/task/contrast across multiple directories.
    
    Returns DataFrame with columns: subject, session, task, contrast, total_files
    """
    if not lev1_dirs:
        print("No level 1 directories provided")
        return pd.DataFrame()
    
    # Parse all files and group counts across all directories
    file_counts = defaultdict(int)
    total_files_found = 0
    
    for lev1_dir in lev1_dirs:
        if not lev1_dir.exists():
            print(f"Level 1 directory not found: {lev1_dir}")
            continue
        
        # Find all contrast files
        contrast_pattern = "**/indiv_contrasts/*stat-effect-size.nii.gz"
        contrast_files = list(lev1_dir.glob(contrast_pattern))
        
        if not contrast_files:
            print(f"No contrast files found in {lev1_dir}")
            continue
        
        print(f"Found {len(contrast_files)} contrast files in {lev1_dir}")
        total_files_found += len(contrast_files)
        
        for filepath in contrast_files:
            info = parse_contrast_filepath(filepath)
            if all([info['subject'], info['session'], info['task'], info['contrast']]):
                key = (info['subject'], info['session'], info['task'], info['contrast'])
                file_counts[key] += 1
    
    print(f"Found {total_files_found} total contrast files across all directories")
    
    # Convert to DataFrame
    rows = []
    for (subject, session, task, contrast), count in file_counts.items():
        rows.append({
            'subject': subject,
            'session': session, 
            'task': task,
            'contrast': contrast,
            'total_files': count
        })
    
    return pd.DataFrame(rows)


def calculate_scan_proportions(input_df: pd.DataFrame, lev1_dirs: List[Path], thresholds: dict) -> pd.DataFrame:
    """
    Calculate proportion of good vs total scans for each subject/session/task/contrast.
    
    Args:
        input_df: DataFrame with VIF and outlier data
        lev1_dirs: List of paths to first-level output directories
        thresholds: Dictionary with exclusion thresholds
    
    Returns:
        DataFrame with scan proportions
    """
    if not lev1_dirs:
        print("No lev1-output directories provided, skipping proportion calculation")
        return pd.DataFrame()
    
    # Get total file counts
    total_counts_df = count_total_contrast_files(lev1_dirs)
    if total_counts_df.empty:
        return pd.DataFrame()
    
    # Parse input data to match format
    input_parsed = []
    for _, row in input_df.iterrows():
        # Parse subject_label: sub-s1035_ses-02_run-1 -> sub-s1035, ses-02
        parts = row['subject_label'].split('_')
        subject = parts[0]  # sub-s1035
        session = parts[1]  # ses-02
        
        # Convert contrast_name format: cuedTS_cue_switch_cost -> cue_switch_cost
        contrast = row['contrast_only']  # This should be just the contrast part
        task = row['task_name']
        
        input_parsed.append({
            'subject': subject,
            'session': session,
            'task': task,
            'contrast': contrast,
            'VIF': row['VIF'],
            'outlier_pct': row['image_outlier_percentage'],
            'is_flagged': (row['VIF'] >= thresholds['vif_exclusion']) | 
                         (row['image_outlier_percentage'] >= thresholds['outlier_exclusion'])
        })
    
    input_parsed_df = pd.DataFrame(input_parsed)
    
    # Group by subject/session/task/contrast and count good vs total
    proportion_results = []
    
    for _, total_row in total_counts_df.iterrows():
        subject = total_row['subject']
        session = total_row['session'] 
        task = total_row['task']
        contrast = total_row['contrast']
        total_files = total_row['total_files']
        
        # Find matching rows in input data
        matching_input = input_parsed_df[
            (input_parsed_df['subject'] == subject) &
            (input_parsed_df['session'] == session) &
            (input_parsed_df['task'] == task) &
            (input_parsed_df['contrast'] == contrast)
        ]
        
        if not matching_input.empty:
            # Count good (non-flagged) scans
            good_scans = len(matching_input[~matching_input['is_flagged']])
            total_scans_with_data = len(matching_input)
            
            # Calculate proportion
            if total_files > 0:
                proportion_good = good_scans / total_files
                data_coverage = total_scans_with_data / total_files
            else:
                proportion_good = 0
                data_coverage = 0
        else:
            # No data available for this combination
            good_scans = 0
            total_scans_with_data = 0
            proportion_good = 0
            data_coverage = 0
        
        proportion_results.append({
            'subject': subject,
            'session': session,
            'task': task,
            'contrast': contrast,
            'total_available_files': total_files,
            'total_scans_with_data': total_scans_with_data,
            'good_scans': good_scans,
            'flagged_scans': total_scans_with_data - good_scans,
            'proportion_good': round(proportion_good, 4),
            'data_coverage': round(data_coverage, 4)
        })
    
    return pd.DataFrame(proportion_results)


def calculate_subject_level_exclusions(input_df: pd.DataFrame, lev1_dirs: List[Path], thresholds: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate subject-level contrast exclusions based on session counts.
    
    A subject is excluded for a task/contrast if they have ≤2 good sessions remaining.
    
    Args:
        input_df: DataFrame with VIF and outlier data
        lev1_dirs: List of paths to first-level output directories 
        thresholds: Dictionary with exclusion thresholds
    
    Returns:
        Tuple of (subject_level_summary_df, exclusions_df)
    """
    if not lev1_dirs:
        print("No lev1-output directories provided, skipping subject-level analysis")
        return pd.DataFrame(), pd.DataFrame()
    
    # Get total file counts from lev1 directories
    total_counts_df = count_total_contrast_files(lev1_dirs)
    if total_counts_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # Parse input data and determine flagged status
    input_parsed = []
    for _, row in input_df.iterrows():
        # Parse subject_label: sub-s1035_ses-02_run-1 -> sub-s1035, ses-02
        parts = row['subject_label'].split('_')
        subject = parts[0]  # sub-s1035
        session = parts[1]  # ses-02
        
        # Use contrast_only for the contrast name
        contrast = row['contrast_only']
        task = row['task_name']
        
        is_flagged = (row['VIF'] >= thresholds['vif_exclusion']) | (row['image_outlier_percentage'] >= thresholds['outlier_exclusion'])
        
        input_parsed.append({
            'subject': subject,
            'session': session,
            'task': task,
            'contrast': contrast,
            'VIF': row['VIF'],
            'outlier_pct': row['image_outlier_percentage'],
            'is_flagged': is_flagged
        })
    
    input_parsed_df = pd.DataFrame(input_parsed)
    
    # Calculate subject-level summaries
    subject_summaries = []
    exclusions = []
    
    # Group by subject/task/contrast
    for (subject, task, contrast), group in input_parsed_df.groupby(['subject', 'task', 'contrast']):
        # Get total sessions available from lev1 directory
        matching_total = total_counts_df[
            (total_counts_df['subject'] == subject) &
            (total_counts_df['task'] == task) &
            (total_counts_df['contrast'] == contrast)
        ]
        
        if not matching_total.empty:
            total_available = matching_total['total_files'].iloc[0]
        else:
            total_available = 0
        
        # Count sessions with data
        total_sessions_with_data = len(group)
        flagged_sessions = len(group[group['is_flagged']])
        good_sessions = total_sessions_with_data - flagged_sessions
        
        # Calculate proportions
        if total_available > 0:
            proportion_flagged = flagged_sessions / total_available
            proportion_good = good_sessions / total_available
            data_coverage = total_sessions_with_data / total_available
        else:
            proportion_flagged = 0
            proportion_good = 0
            data_coverage = 0
        
        # Determine if subject should be excluded (≤2 good sessions)
        subject_excluded = good_sessions <= 2
        
        subject_summary = {
            'subject': subject,
            'task': task,
            'contrast': contrast,
            'total_available_sessions': total_available,
            'total_sessions_with_data': total_sessions_with_data,
            'good_sessions': good_sessions,
            'flagged_sessions': flagged_sessions,
            'proportion_good': round(proportion_good, 4),
            'proportion_flagged': round(proportion_flagged, 4),
            'data_coverage': round(data_coverage, 4),
            'subject_excluded': subject_excluded
        }
        
        subject_summaries.append(subject_summary)
        
        # Add to exclusions list if subject is excluded
        if subject_excluded:
            exclusions.append(subject_summary)
    
    subject_summaries_df = pd.DataFrame(subject_summaries)
    exclusions_df = pd.DataFrame(exclusions)
    
    return subject_summaries_df, exclusions_df


def create_parser():
    """
    Parser to customize input/output directories and flag thresholds
    """
    parser = argparse.ArgumentParser(
        description='Flag and summarize outlier scans from imaging data.'
    )
    parser.add_argument(
        '--input-file',
        type=Path,
        required=True,
        help="Path to the 'percent_outlier_data.csv' file.",
    )
 
    parser.add_argument(
        '--output-dir',
        type=Path,
        required=True,
        help="Directory to save the output 'flagged.csv' and 'summary.csv' files.",
    )
    parser.add_argument(
        '--vif-threshold-strict',
        type=int,
        default=15,
        help='VIF threshold for strict flagging.',
    )
    parser.add_argument(
        '--outlier-threshold-strict',
        type=int,
        default=15,
        help='Outlier percentage threshold for strict flagging.',
    )
    parser.add_argument(
        '--vif-threshold-combined',
        type=int,
        default=10,
        help='VIF threshold for combined flagging.',
    )
    parser.add_argument(
        '--outlier-threshold-combined',
        type=int,
        default=10,
        help='Outlier percentage threshold for combined flagging.',
    )
    parser.add_argument(
        '--vif-exclusion-threshold',
        type=int,
        default=15,
        help='VIF threshold for simple OR exclusion criteria (default: 15).',
    )
    parser.add_argument(
        '--outlier-exclusion-threshold',
        type=int,
        default=15,
        help='Outlier percentage threshold for simple OR exclusion criteria (default: 15).',
    )
    parser.add_argument(
        '--lev1-output',
        type=Path,
        nargs='+',
        help='Path(s) to first-level modeling output directories for calculating scan proportions (can specify multiple).',
    )
    return parser

def create_summary(args, thresholds):
    try:
        # Load and preprocess data
        input_file = args.input_file
        if not input_file.exists():
            raise FileNotFoundError(f'Input file not found at: {input_file}')

        df = pd.read_csv(input_file)
        print('Successfully loaded and preprocessed data.')

        # Simple OR condition: VIF >= threshold OR outliers >= threshold STD 
        vif_mask = df['VIF'] >= thresholds['vif_exclusion']
        outlier_mask = df['image_outlier_percentage'] >= thresholds['outlier_exclusion']
        combined_mask = vif_mask | outlier_mask
        flagged_df = df[combined_mask].copy()

        print(f'\n--- Flagged Scans ({len(flagged_df)} total) ---')
        print(f'Criteria: (VIF >= {thresholds["vif_exclusion"]}) OR (Outlier >= {thresholds["outlier_exclusion"]}%)')

        if not flagged_df.empty:
            # Get reasons and sort the final output
            flagged_df['flag_reason'] = get_flag_reason(flagged_df, thresholds)

            flagged_df['subject_num'] = (
                flagged_df['subject_label'].str.extract(r'sub-s(\d+)').astype(int)
            )
            flagged_df['session_num'] = flagged_df['session_id'].astype(int)

            sorted_df = flagged_df.sort_values(
                by=['subject_num', 'task_name', 'session_num']
            )

            final_columns = [
                'subject_label',
                'task_name',
                'contrast_name',
                'image_outlier_percentage',
                'VIF',
                'flag_reason',
            ]
            final_df = sorted_df[final_columns]

            # Save flagged scans
            args.output_dir.mkdir(parents=True, exist_ok=True)
            flagged_fpath = args.output_dir / 'flagged_scans.csv'
            final_df.to_csv(flagged_fpath, index=False)
            print(f'\nSaved {len(final_df)} flagged scans to: {flagged_fpath}')

            # Summarize and save summary
            summary_df = summarize_flagged_scans(flagged_df)
            if not summary_df.empty:
                summary_fpath = args.output_dir / 'flagged_summary.csv'
                summary_df.to_csv(summary_fpath, index=False)
                print(f'Saved summary to: {summary_fpath}')
                print('\n--- Summary of Flagged Scans by Contrast ---')
                print(summary_df.to_string(index=False))
            
            # Category breakdown summary
            category_df = summarize_flagged_by_category(flagged_df, thresholds)
            if not category_df.empty:
                category_fpath = args.output_dir / 'flagged_category_summary.csv'
                category_df.to_csv(category_fpath, index=False)
                print(f'Saved category breakdown to: {category_fpath}')
                print('\n--- Summary of Flagged Scans by Category ---')
                print(category_df.to_string(index=False))
            
            # Detailed contrast exclusion summary
            contrast_summary_df = create_contrast_exclusion_summary(flagged_df, thresholds)
            if not contrast_summary_df.empty:
                contrast_summary_fpath = args.output_dir / 'contrast_exclusion_summary.csv'
                contrast_summary_df.to_csv(contrast_summary_fpath, index=False)
                print(f'Saved detailed contrast exclusion summary to: {contrast_summary_fpath}')
                print('\n--- Detailed Exclusion Summary by Contrast ---')
                print(contrast_summary_df.to_string(index=False))
        else:
            print('No scans met the flagging criteria.')
        
        # Calculate scan proportions if lev1-output directories provided
        if args.lev1_output:
            print('\n--- Computing Scan Proportions ---')
            print(f'Using {len(args.lev1_output)} level 1 directories: {args.lev1_output}')
            proportions_df = calculate_scan_proportions(df, args.lev1_output, thresholds)
            if not proportions_df.empty:
                proportions_fpath = args.output_dir / 'scan_proportions.csv'
                proportions_df.to_csv(proportions_fpath, index=False)
                print(f'Saved scan proportions to: {proportions_fpath}')
                print(f'Calculated proportions for {len(proportions_df)} subject/session/task/contrast combinations')
                
                # Show summary statistics
                mean_proportion = proportions_df['proportion_good'].mean()
                mean_coverage = proportions_df['data_coverage'].mean()
                print(f'Average proportion of good scans: {mean_proportion:.3f}')
                print(f'Average data coverage: {mean_coverage:.3f}')
            else:
                print('No scan proportions calculated')
            
            # Calculate subject-level exclusions
            print('\n--- Computing Subject-Level Contrast Exclusions ---')
            subject_summaries_df, exclusions_df = calculate_subject_level_exclusions(df, args.lev1_output, thresholds)
            
            if not subject_summaries_df.empty:
                # Save subject-level summary
                subject_summary_fpath = args.output_dir / 'subject_level_summary.csv'
                subject_summaries_df.to_csv(subject_summary_fpath, index=False)
                print(f'Saved subject-level summary to: {subject_summary_fpath}')
                
                # Save exclusions (subjects with ≤2 good sessions)
                if not exclusions_df.empty:
                    exclusions_fpath = args.output_dir / 'exclusions.csv'
                    exclusions_df.to_csv(exclusions_fpath, index=False)
                    print(f'Saved exclusions to: {exclusions_fpath}')
                    print(f'{len(exclusions_df)} subject/task/contrast combinations will be excluded (≤2 good sessions)')
                    
                    # Show breakdown of excluded subjects
                    excluded_subjects = exclusions_df['subject'].nunique()
                    print(f'This affects {excluded_subjects} unique subjects')
                else:
                    print('No subjects require exclusion (all have >2 good sessions per task/contrast)')
                
                # Show overall statistics
                total_combinations = len(subject_summaries_df)
                excluded_combinations = len(exclusions_df)
                print(f'Total subject/task/contrast combinations analyzed: {total_combinations}')
                print(f'Combinations requiring exclusion: {excluded_combinations} ({excluded_combinations/total_combinations*100:.1f}%)')
            else:
                print('No subject-level analysis performed')
        else:
            print('Skipping scan proportion and subject-level analysis (--lev1-output not provided)')

    except FileNotFoundError as e:
        print(f'Error: {e}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')



def main():
    """
    Main execution pipeline to load, flag, and summarize outlier scans.
    """

    args = create_parser().parse_args()

    thresholds = {
        'vif_strict': args.vif_threshold_strict,
        'outlier_strict': args.outlier_threshold_strict,
        'vif_combined': args.vif_threshold_combined,
        'outlier_combined': args.outlier_threshold_combined,
        'vif_exclusion': args.vif_exclusion_threshold,
        'outlier_exclusion': args.outlier_exclusion_threshold,
    }

    create_summary(args, thresholds)


if __name__ == '__main__':
    main()
