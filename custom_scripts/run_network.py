import argparse
import json
import os
import re
from collections import defaultdict
from glob import glob
from typing import Dict, List, Set, Optional

import numpy as np
import pandas as pd

from plotting_functions import generate_all_data_summaries


def load_exclusions(exclusions_file: str) -> Set[str]:
    """Load exclusions from JSON file and return a set of exclusion keys."""
    if not os.path.exists(exclusions_file):
        raise FileNotFoundError(f'Exclusions file {exclusions_file} does not exist.')

    try:
        with open(exclusions_file, 'r') as f:
            exclusions_data = json.load(f)
        
        excluded_keys = set()
        
        # Process fMRIPrep exclusions
        for exclusion in exclusions_data.get('fmriprep_exclusions', []):
            key = f"{exclusion['subject']}_{exclusion['session']}_{exclusion['task']}_{exclusion['run']}"
            excluded_keys.add(key)
        
        # Process behavioral exclusions 
        for exclusion in exclusions_data.get('behavioral_exclusions', []):
            key = f"{exclusion['subject']}_{exclusion['session']}_{exclusion['task']}_{exclusion['run']}"
            excluded_keys.add(key)

        print(f'Loaded {len(excluded_keys)} exclusions from {exclusions_file}')
        print(f'Excluded keys include: {excluded_keys}\n')
        return excluded_keys
        
    except Exception as e:
        print(f'Warning: Could not load exclusions from {exclusions_file}: {e}')
        return set()


def is_scan_excluded(path: str, exclusions: Set[str]) -> bool:
    """Check if a scan should be excluded based on BIDS entities."""
    if not exclusions:
        return False
    
    entities = parse_bids_entities(path)

    if not all(entities.get(k) for k in ['subject', 'session', 'task', 'run']):
        return False
    
    # Create key to match exclusions format (which already includes prefixes)
    base_key = f"sub-s{entities['subject']}_ses-{entities['session']}_task-{entities['task']}_run-{entities['run']}"
    keys_to_check = [base_key]

    return any(key in exclusions for key in keys_to_check)


def parse_bids_entities(path: str) -> Dict[str, Optional[str]]:
    """
    Extracts BIDS-like entities from a filepath using robust, non-greedy patterns.
    """
    filename = os.path.basename(path)
    patterns = {
        'subject': re.compile(r'sub-s([^_]+)'),
        'session': re.compile(r'ses-([^_]+)'),
        'run': re.compile(r'run-([^_]+)'),
        'task': re.compile(r'task-([^_]+)'),
        'contrast': re.compile(r'contrast-(.+?)_(?:rtmodel-[^_]+_)?stat-'),
    }

    entities = {key: None for key in patterns}
    entities['sub_ses_key'] = None

    for key, pattern in patterns.items():
        match = pattern.search(filename)
        if match:
            entities[key] = match.group(1)

    if entities['subject'] and entities['session']:
        entities['sub_ses_key'] = (
            f'sub-s{entities["subject"]}_ses-{entities["session"]}'
        )

    return entities


def group_paths_by_filename_pattern(file_paths: List[str]) -> Dict[str, List[str]]:
    """Groups file paths by filename patterns, normalizing identifiers."""
    grouped = defaultdict(list)
    for path in file_paths:
        filename = os.path.basename(path)
        pattern = re.sub(r'sub-s[^_]+', 'sub-sXXX', filename)
        pattern = re.sub(r'ses-[^_]+', 'ses-XX', pattern)
        pattern = re.sub(r'run-[^_]+', 'run-X', pattern)
        grouped[pattern].append(path)
    return dict(sorted(grouped.items()))


def extract_vif_from_csv(csv_path: str) -> Dict[str, float]:
    """Extracts VIF data from a contrast VIF CSV file."""
    try:
        df = pd.read_csv(csv_path)
        return dict(zip(df['contrast'], df['VIF']))
    except Exception as e:
        print(f'Warning: Could not read VIF data from {csv_path}: {e}')
        return {}


def find_vif_files(base_dirs: List[str]) -> Dict[str, Dict[str, float]]:
    """Finds and reads all VIF CSV files across multiple base directories."""
    all_vif_data = {}
    for base_dir in base_dirs:
        vif_pattern = os.path.join(
            base_dir, 'sub-s*', 'task-*', 'quality_control', '*_desc-contrastVIFs.csv'
        )
        vif_files = glob(vif_pattern)
        print(f'Found {len(vif_files)} VIF files in {base_dir}')

        for vif_file in vif_files:
            entities = parse_bids_entities(vif_file)
            if entities['sub_ses_key'] and entities['task']:
                # For new format, include run if available
                if entities['run']:
                    key = f'{entities["sub_ses_key"]}_run-{entities["run"]}_{entities["task"]}'
                else:
                    key = f'{entities["sub_ses_key"]}_{entities["task"]}'
                all_vif_data[key] = extract_vif_from_csv(vif_file)
    print(f'Found VIF data for {len(all_vif_data)} subject-session-task combinations total.')
    return all_vif_data


def get_contrast_vif_labels(
    vif_data: Dict[str, Dict[str, float]], nifti_paths: List[str], contrast_name: str
) -> List[str]:
    """Generates VIF labels for a list of NIFTI paths."""
    vif_labels = []
    for path in nifti_paths:
        entities = parse_bids_entities(path)
        label = '(vif=?)'

        if entities['sub_ses_key'] and entities['task'] and entities['run']:
            # For new format, include run in the key
            vif_key = f'{entities["sub_ses_key"]}_run-{entities["run"]}_{entities["task"]}'
            
            # Try new format first, fallback to old format
            if vif_key not in vif_data:
                vif_key = f'{entities["sub_ses_key"]}_{entities["task"]}'

            if vif_key in vif_data:
                # CSV contrast names don't include task prefix, so use just the contrast part
                contrast_only = entities.get('contrast', '')
                
                if contrast_only in vif_data[vif_key]:
                    vif_value = vif_data[vif_key][contrast_only]
                    label = f'(vif={vif_value:.2f})'
                else:
                    print(f'\n[DEBUG] VIF MISS for {os.path.basename(path)}:')
                    print(f"  > Looking for contrast: '{contrast_only}'")
                    print(f'  > Available contrasts: {list(vif_data[vif_key].keys())}')
            else:
                print(
                    f"\n[DEBUG] VIF KEY NOT FOUND for {os.path.basename(path)}: > Generated Key: '{vif_key}'"
                )
        vif_labels.append(label)
    return vif_labels


def find_nifti_files(base_dirs: List[str]) -> List[str]:
    """Finds all stat-effect-size.nii.gz files across multiple base directories."""
    all_files = []
    for base_dir in base_dirs:
        nifti_pattern = os.path.join(
            base_dir, 'sub-s*', 'task-*', 'indiv_contrasts', '*stat-effect-size.nii.gz'
        )
        files = glob(nifti_pattern)
        print(f'Found {len(files)} NIFTI files in {base_dir}')
        all_files.extend(files)
    return sorted(all_files)


def make_list_of_input_dicts(base_dirs: List[str], exclusions: Set[str]) -> List[Dict[str, object]]:
    """Creates a list of dictionaries, one for each contrast to be processed."""
    print(f'Starting data preparation with base_dirs: {base_dirs}')

    nifti_files = find_nifti_files(base_dirs)
    print(f'Found {len(nifti_files)} total NIFTI files across all directories.')
    
    # Apply exclusions if provided
    if exclusions:
        original_count = len(nifti_files)
        nifti_files = [f for f in nifti_files if not is_scan_excluded(f, exclusions)]
        excluded_count = original_count - len(nifti_files)
        print(f'Excluded {excluded_count} files based on exclusions criteria.')
        print(f'Remaining {len(nifti_files)} NIFTI files after exclusions.')

    vif_data = find_vif_files(base_dirs)

    grouped_lists = group_paths_by_filename_pattern(nifti_files)
    list_of_input_dicts = []

    for pattern, file_paths in grouped_lists.items():
        if not file_paths:
            continue

        first_file_entities = parse_bids_entities(file_paths[0])
        task_name = first_file_entities.get('task')
        contrast_name = first_file_entities.get('contrast')

        if not task_name or not contrast_name:
            print(
                f'Warning: Could not extract task or contrast from files in group: {pattern}'
            )
            continue

        nifti_paths = sorted(file_paths)
        vif_labels = get_contrast_vif_labels(vif_data, nifti_paths, contrast_name)

        path_entities = [parse_bids_entities(p) for p in nifti_paths]
        sub_ids = [e.get('subject', 'N/A') for e in path_entities]
        session_ids = [e.get('session', 'N/A') for e in path_entities]
        run_ids = [e.get('run', 'N/A') for e in path_entities]

        image_labels = [
            f'sub-s{sub_id}_ses-{ses_id}_run-{run_id}'
            for sub_id, ses_id, run_id in zip(sub_ids, session_ids, run_ids)
        ]

        list_of_input_dicts.append(
            {
                'main_title': f'{task_name}_{contrast_name}',
                'nifti_paths': nifti_paths,
                'image_labels': image_labels,
                'vif_labels': vif_labels,
                'data_type_label': 'Contrast Estimate',
                'task_name': task_name,
                'contrast_name': contrast_name,
                'session_ids': session_ids,
            }
        )

    print(f'Created {len(list_of_input_dicts)} input dictionaries for plotting.')
    return list_of_input_dicts


def process_contrasts(base_dirs: List[str], output_dir: str, exclusions_file: str) -> None:
    """Main pipeline for processing contrasts and generating summaries."""
    exclusions = load_exclusions(exclusions_file)
    dicts_list = make_list_of_input_dicts(base_dirs, exclusions)
    if dicts_list:
        generate_all_data_summaries(dicts_list, n_std=3, output_dir=output_dir)
    else:
        print('No data dictionaries were created; skipping summary generation.')


def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Process fMRI contrast files and generate a QA outlier analysis report.'
    )
    parser.add_argument(
        '--base_dirs',
        type=str,
        nargs='+',
        required=True,
        help='Base directories containing the first-level analysis output (can specify multiple).',
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        required=True,
        help='Directory where the output PDF and CSV files will be saved.',
    )
    parser.add_argument(
        '--exclusions-file',
        type=str,
        required=True,
        help='Path to JSON file containing exclusions.',
    )
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()
    process_contrasts(args.base_dirs, args.output_dir, args.exclusions_file)


if __name__ == '__main__':
    main()
