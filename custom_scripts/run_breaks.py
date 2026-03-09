#!/usr/bin/env python3
"""
Computes which breaks received performance feedback. 

To do this, we read in the raw behavioral files and extract stimulus content
from feedback rows, parsing for performance-related strings.
"""

from pathlib import Path
import pandas as pd
import logging
import json
from typing import Dict, List, Optional, Union, Any

# PATHS
BEHAVIORAL_DIR = Path("/oak/stanford/groups/russpold/data/network_grant/behavioral_data/raw_cleaned")
DISCOVERY_BIDS = Path("/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/")
VALIDATION_BIDS = Path("/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/")

# Constants for feedback analysis
FEEDBACK_TRIAL_IDS = frozenset([
    "test_feedback", 
    "feedback_block", 
    "practice-no-stop-feedback", 
    "practice-stop-feedback"
])

PERFORMANCE_FEEDBACK_STRINGS = frozenset([
    "accuracy",
    "responding", 
    "slowly",
    "Remember:",
    "simply"
])

# Task name mapping from long names to short names
TASK_NAME_MAPPING = {
    'stop_signal': 'stopSignal',
    'stop_signal_with_flanker': 'stopSignalWFlanker',
    'spatial_switching': 'spatialTS',
    'spatial_task_switching': 'spatialTS',
    'cued_task_switching': 'cuedTS',
    'n_back': 'nBack',
    'directed_forgetting': 'directedForgetting',
    'flanker': 'flanker',
    'go_nogo': 'goNogo',
    'shape_matching': 'shapeMatching',
    'stop_signal_with_directed_forgetting': 'stopSignalWDirectedForgetting',
    'directed_forgetting_with_flanker': 'directedForgettingWFlanker',
    'cued_switching': 'cuedTS',
    's43_stop_w_flanker.csv': 'stopSignalWFlanker',
    's43.csv': 'stopSignalWFlanker',
    'directed_forgetting_with_cued_task_switching': 'directedForgettingWCuedTS',
    'cued_task_switching_with_directed_forgetting': 'directedForgettingWCuedTS',
    'spatial_task_switching_with_cued_task_switching': 'spatialTSWCuedTS',
    'flanker_with_shape_matching': 'flankerWShapeMatching',
    'cued_task_switching_with_flanker': 'cuedTSWFlanker',
    'spatial_task_switching_with_shape_matching': 'spatialTSWShapeMatching',
    'shape_matching_with_spatial_task_switching': 'spatialTSWShapeMatching',
    'n_back_with_shape_matching': 'nBackWShapeMatching',
    'n_back_with_spatial_task_switching': 'nBackWSpatialTS',
    'flanker_with_cued_task_switching': 'cuedTSWFlanker',
    'shape_matching_with_cued_task_switching': 'shapeMatchingWCuedTS'
}


def setup_logging() -> None:
    """Setup logging configuration with INFO level."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def extract_task_name_from_filename(filename: str) -> Optional[str]:
    """
    Extract and convert task name from filename to standardized short name.
    
    Args:
        filename: The behavioral data filename
        
    Returns:
        Standardized short task name or None if not found
    """
    # Remove file extension and fmri suffix
    base_name = filename.split("__fmri")[0] if "__fmri" in filename else filename.rsplit('.', 1)[0]
    
    # Handle single task network pattern
    if "_single_task_network" in base_name:
        base_name = base_name.split("_single_task_network")[0]
    
    # Handle task- prefix pattern
    elif "task-" in base_name:
        for part in base_name.split('_'):
            if part.startswith("task-"):
                base_name = part.replace("task-", "").replace("-", "_")
                break
    
    return TASK_NAME_MAPPING.get(base_name, base_name)


def calculate_dynamic_block_numbers(feedback_rows: pd.DataFrame) -> Dict[int, int]:
    """
    Calculate block numbers dynamically based on feedback row order and type.
    
    Args:
        feedback_rows: DataFrame containing feedback rows
        
    Returns:
        Dictionary mapping row indices to block numbers
    """
    block_counters = {}
    block_numbers = {}
    
    for idx, row in feedback_rows.iterrows():
        trial_id = row['trial_id']
        
        # Initialize counter for this trial_id type if not seen before
        if trial_id not in block_counters:
            block_counters[trial_id] = 0
            
        # Increment counter for this trial_id type
        block_counters[trial_id] += 1
        
        # Assign block number based on occurrence count
        block_numbers[idx] = block_counters[trial_id]
    
    return block_numbers


def analyze_stimulus_for_performance_feedback(stimulus: Union[str, float, None]) -> tuple[List[str], bool]:
    """
    Analyze stimulus content for performance feedback indicators.
    
    Args:
        stimulus: The stimulus content to analyze
        
    Returns:
        Tuple of (performance_indicators_list, has_performance_feedback_bool)
    """
    if not isinstance(stimulus, str) or pd.isna(stimulus):
        return [], False
    
    indicators = [
        indicator for indicator in PERFORMANCE_FEEDBACK_STRINGS
        if indicator.lower() in stimulus.lower()
    ]
    
    return indicators, len(indicators) > 0


def extract_feedback_data_from_file(file_path: Path) -> List[Dict[str, Any]]:
    """
    Extract feedback stimulus data from a single behavioral file.
    
    Args:
        file_path: Path to the behavioral CSV file
        
    Returns:
        List of feedback row data dictionaries
    """
    subject = file_path.parent.parent.name
    session = file_path.parent.name  
    filename = file_path.name
    
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        logging.error(f"Failed to read {file_path}: {e}")
        return []
    
    # Validate required columns
    required_cols = {'trial_id', 'stimulus'}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        logging.error(f"Missing columns {missing} in {subject}/{session}/{filename}")
        return []
    
    # Filter to test trials if available
    test_trial_mask = df['trial_id'] == 'test_trial'
    if test_trial_mask.any():
        start_idx = test_trial_mask.idxmax()
        df = df.iloc[df.index.get_loc(start_idx):]
        logging.debug(f"Filtered to test trials starting at row {start_idx}")
    else:
        logging.warning(f"No test_trial found in {subject}/{session}/{filename}")
    
    # Find feedback rows
    feedback_mask = df['trial_id'].isin(FEEDBACK_TRIAL_IDS)
    feedback_rows = df[feedback_mask]
    
    if feedback_rows.empty:
        logging.warning(f"No feedback rows found in {subject}/{session}/{filename}")
        return []
    
    logging.info(f"Found {len(feedback_rows)} feedback rows in {subject}/{session}/{filename}")
    
    # Extract task name and calculate dynamic block numbers
    task_name = extract_task_name_from_filename(filename)
    dynamic_block_numbers = calculate_dynamic_block_numbers(feedback_rows)
    
    results = []
    for idx, row in feedback_rows.iterrows():
        performance_indicators, has_performance_feedback = analyze_stimulus_for_performance_feedback(
            row['stimulus']
        )
        
        # Ensure subject has 'sub-' prefix
        subject_with_prefix = subject if subject.startswith('sub-') else f"sub-{subject}"
        
        result_entry = {
            "subject": subject_with_prefix,
            "session": session,
            "filename": filename,
            "task_name": task_name,
            "row_index": int(idx),
            "trial_id": row['trial_id'],
            "block_number": dynamic_block_numbers.get(idx),
            "stimulus_content": str(row['stimulus']) if pd.notna(row['stimulus']) else "",
            "performance_indicators": performance_indicators,
            "has_performance_feedback": has_performance_feedback
        }
        
        results.append(result_entry)
        logging.debug(f"Processed row {idx} ({row['trial_id']}): block={dynamic_block_numbers.get(idx)}, feedback={has_performance_feedback}")
    
    return results


def create_summary_statistics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create summary statistics for the analysis results."""
    total_files = len({(r['subject'], r['session'], r['filename']) for r in results})
    performance_files = len({
        (r['subject'], r['session'], r['filename']) 
        for r in results if r['has_performance_feedback']
    })
    
    return {
        "total_files_processed": total_files,
        "total_feedback_rows": len(results), 
        "rows_with_performance_feedback": sum(r['has_performance_feedback'] for r in results),
        "files_with_performance_feedback": performance_files
    }


def save_analysis_results(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """
    Save analysis results to JSON files.
    
    Args:
        results: List of all feedback analysis results
        output_dir: Directory to save output files
    """
    output_dir.mkdir(exist_ok=True)
    summary = create_summary_statistics(results)
    
    # Master file with all results
    master_file = output_dir / "break_analysis_master.json"
    master_data = {
        "break_feedback_analysis": results,
        "summary": summary
    }
    
    with open(master_file, 'w', encoding='utf-8') as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
    logging.info(f"Saved master results to {master_file}")
    
    # Filtered file with only performance feedback
    performance_results = [r for r in results if r['has_performance_feedback']]
    filtered_file = output_dir / "break_analysis_with_performance_feedback.json"
    filtered_data = {
        "break_with_performance_feedback": performance_results,
        "summary": create_summary_statistics(performance_results)
    }
    
    with open(filtered_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, indent=2, ensure_ascii=False)
    logging.info(f"Saved performance feedback results to {filtered_file}")


def main() -> int:
    """
    Main function to process behavioral files and analyze break feedback.
    
    Returns:
        Exit code (0 for success)
    """
    setup_logging()
    logging.info("Starting break analysis with stimulus column extraction...")
    
    # Collect all behavioral files
    behavioral_files = list(BEHAVIORAL_DIR.glob("s*/ses-*/*.csv"))
    
    if not behavioral_files:
        logging.error(f"No behavioral files found in {BEHAVIORAL_DIR}")
        return 1
    
    logging.info(f"Processing {len(behavioral_files)} behavioral files...")
    
    # Process all files
    all_results = []
    for file_path in behavioral_files:
        logging.info(f"Processing {file_path.parent.parent.name}/{file_path.parent.name}/{file_path.name}")
        file_results = extract_feedback_data_from_file(file_path)
        all_results.extend(file_results)
    
    if not all_results:
        logging.warning("No feedback data extracted from any files")
        return 1
    
    # Save results
    output_dir = Path("data")
    save_analysis_results(all_results, output_dir)
    
    # Log final summary
    summary = create_summary_statistics(all_results)
    logging.info("\nAnalysis Summary:")
    for key, value in summary.items():
        logging.info(f"  - {key.replace('_', ' ').title()}: {value}")
    
    logging.info("\nResults saved to:")
    logging.info("  - Master file: data/break_analysis_master.json")
    logging.info("  - Performance feedback only: data/break_analysis_with_performance_feedback.json")
    
    return 0


if __name__ == '__main__':
    exit(main())