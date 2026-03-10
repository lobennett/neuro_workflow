"""Event processing pipeline for first-level GLM analysis.

This module handles preprocessing of BIDS events.tsv files before they are
used to construct GLM design matrices. The pipeline consists of:

1. Raw events.tsv loaded from BIDS directory
2. Onsets adjusted by -(dummy_scans * TR) to account for dummy scan removal
3. Events with negative onsets dropped (they occurred during dummy scans)
4. Negative response times marked as junk and set to NaN
5. Performance feedback breaks renamed via external JSON lookup
6. Nuisance trial columns (omission, commission, rt_fast) computed
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

from neuro_workflow.analysis.task_config.loader import DUMMY_SCANS, TR

logger = logging.getLogger(__name__)

# Constants
MIN_RT = 0.2  # Minimum valid response time in seconds

# Default path to break analysis results
DEFAULT_BREAK_ANALYSIS_PATH = (
    Path(__file__).parent.parent.parent.parent
    / 'data'
    / 'break_analysis_with_performance_feedback.json'
)


def load_break_analysis_results(
    analysis_file: Optional[Union[str, Path]] = None,
) -> Dict:
    """Load break analysis results from JSON file.

    Args:
        analysis_file: Path to break analysis JSON file. If None, uses default path.

    Returns:
        Dictionary with break analysis results.
    """
    if analysis_file is None:
        analysis_file = DEFAULT_BREAK_ANALYSIS_PATH

    analysis_file = Path(analysis_file)

    if not analysis_file.exists():
        logger.warning('Break analysis file not found at %s', analysis_file)
        return {'break_with_performance_feedback': []}

    try:
        with open(analysis_file, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning('Failed to load break analysis file %s: %s', analysis_file, e)
        return {'break_with_performance_feedback': []}


def rename_performance_feedback_breaks(
    events_df: pd.DataFrame,
    subject_id: str,
    session_id: str,
    task_name: str,
    analysis_file: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Rename 'break' trial_id to 'break_with_performance_feedback' based on analysis results.

    Matches break instances in the events DataFrame with entries in the
    break analysis JSON file using subject, session, task name, and break
    instance number (1-based) to determine which breaks should be renamed.

    Args:
        events_df: Events DataFrame from BIDS events.tsv
        subject_id: Subject identifier (with or without 'sub-' prefix)
        session_id: Session identifier (with or without 'ses-' prefix)
        task_name: Standardized task name (e.g., 'spatialTS', 'stopSignal')
        analysis_file: Path to break analysis JSON file. If None, uses default path.

    Returns:
        Events DataFrame with renamed break trial_id values.
    """
    events_df = events_df.copy()

    # Ensure consistent formatting of identifiers
    subject_formatted = (
        subject_id if subject_id.startswith('sub-') else f'sub-{subject_id}'
    )
    session_formatted = (
        session_id if session_id.startswith('ses-') else f'ses-{session_id}'
    )

    # Load break analysis results
    analysis_data = load_break_analysis_results(analysis_file)
    performance_feedback_breaks = analysis_data.get(
        'break_with_performance_feedback', []
    )

    if not performance_feedback_breaks:
        logger.debug('No performance feedback breaks in analysis data')
        return events_df

    # Find matching entries in analysis results
    matching_breaks = [
        entry['block_number']
        for entry in performance_feedback_breaks
        if (
            entry['subject'] == subject_formatted
            and entry['session'] == session_formatted
            and entry['task_name'] == task_name
        )
    ]

    if not matching_breaks:
        logger.debug(
            'No matching performance feedback breaks for %s/%s/%s',
            subject_formatted,
            session_formatted,
            task_name,
        )
        return events_df

    # Find break trials in events dataframe
    break_mask = events_df['trial_id'] == 'break'
    break_indices = events_df[break_mask].index.tolist()

    if not break_indices:
        logger.debug('No break trials found in events dataframe')
        return events_df

    # Rename breaks that match the analysis results
    # Block numbers in analysis start from 1, so we use 1-based indexing
    renamed_count = 0
    missing_count = 0
    for break_instance in matching_breaks:
        break_idx = break_instance - 1  # Convert to 0-based index

        if 0 <= break_idx < len(break_indices):
            events_row_idx = break_indices[break_idx]
            events_df.loc[events_row_idx, 'trial_id'] = (
                'break_with_performance_feedback'
            )
            renamed_count += 1
        else:
            missing_count += 1

    if renamed_count > 0:
        logger.info(
            'Renamed %d/%d break trials to break_with_performance_feedback',
            renamed_count,
            len(break_indices),
        )
    if missing_count > 0:
        logger.warning(
            '%d break instances not found in events (only %d breaks present)',
            missing_count,
            len(break_indices),
        )

    return events_df


def preprocess_events(
    events_df: pd.DataFrame,
    task_name: str,
    adjust_for_dummy_scans: bool = True,
    dummy_scans: int = DUMMY_SCANS,
    tr: float = TR,
    subject_id: Optional[str] = None,
    session_id: Optional[str] = None,
    rename_performance_breaks: bool = True,
    analysis_file: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Preprocess events dataframe with onset adjustment, RT corrections, and junk marking.

    Adjusts event onsets for dummy scan removal (onset -= dummy_scans * TR),
    drops events that fall within the dummy scan window (negative onsets),
    marks negative response times as junk, and optionally renames performance
    feedback breaks using an external JSON lookup.

    Args:
        events_df: Events dataframe from BIDS events.tsv
        task_name: Name of the task
        adjust_for_dummy_scans: Whether to adjust onsets for dummy scan removal
        dummy_scans: Number of dummy scans that were removed
        tr: Repetition time in seconds
        subject_id: Subject identifier for break renaming (optional)
        session_id: Session identifier for break renaming (optional)
        rename_performance_breaks: Whether to rename breaks with performance feedback
        analysis_file: Path to break analysis JSON file (optional)

    Returns:
        Preprocessed events dataframe with additional columns.
    """
    events_df = events_df.copy()

    # Adjust event onsets for dummy scan removal
    if adjust_for_dummy_scans and dummy_scans > 0:
        adjustment = dummy_scans * tr
        logger.info('Adjusting onsets by -%.2fs for dummy scan removal', adjustment)
        events_df['onset'] -= adjustment

    # Drop rows with negative onset values (events during dummy scans)
    initial_rows = len(events_df)
    events_df = events_df[events_df['onset'] >= 0].copy()
    dropped_rows = initial_rows - len(events_df)
    if dropped_rows > 0:
        logger.info('Dropped %d events with negative onsets (dummy scan window)', dropped_rows)

    # Add constant column for modeling
    events_df['constant_1_column'] = 1

    # Initialize junk column if it doesn't exist
    if 'junk' not in events_df.columns:
        events_df['junk'] = 0

    # Handle negative RTs: mark as junk and set to NaN
    if 'response_time' in events_df.columns:
        na_mask = events_df['response_time'] < 0
        events_df['na_trials'] = na_mask.astype(int)
        events_df.loc[na_mask, 'junk'] = 1
        events_df.loc[na_mask, 'response_time'] = np.nan
    else:
        events_df['na_trials'] = 0

    # Rename performance feedback breaks if requested and identifiers are provided
    if (
        rename_performance_breaks
        and subject_id is not None
        and session_id is not None
        and 'trial_type' in events_df.columns
    ):
        events_df = rename_performance_feedback_breaks(
            events_df, subject_id, session_id, task_name, analysis_file
        )

    return events_df


def define_nuisance_trials(events_df: pd.DataFrame, task: str) -> Dict[str, pd.Series]:
    """Define nuisance trials based on task type and response patterns.

    Args:
        events_df: Events dataframe with trial data
        task: Task name

    Returns:
        Dictionary with keys: 'trial_filter', 'bad_trials', 'omission',
        'commission', 'rt_too_fast'.  Each value is a boolean Series mask.
    """
    # Define task groups and their trial identification columns
    test_trial_tasks = {
        'cuedTS',
        'nBack',
        'spatialTS',
        'flanker',
        'shapeMatching',
        'directedForgetting',
    }
    go_trial_tasks = {'stopSignal', 'goNogo'}

    # Determine trial filter based on task type
    if task in test_trial_tasks:
        trial_filter = events_df.trial_id == 'test_trial'
    elif task in go_trial_tasks:
        trial_filter = events_df.trial_type == 'go'
    else:
        raise ValueError(
            f'Unknown task: {task}. Supported tasks: {test_trial_tasks | go_trial_tasks}'
        )

    # Define nuisance trial types
    omission = (events_df.key_press == -1) & trial_filter
    commission = (
        (events_df.key_press != events_df.correct_response)
        & (events_df.key_press != -1)
        & (events_df.response_time >= MIN_RT)
        & trial_filter
    )
    rt_too_fast = (events_df.response_time < MIN_RT) & trial_filter

    # Also include trials already marked as junk
    existing_junk = pd.Series(False, index=events_df.index)
    if 'junk' in events_df.columns:
        existing_junk = (events_df['junk'] == 1) & trial_filter

    bad_trials = omission | commission | rt_too_fast | existing_junk

    return {
        'trial_filter': trial_filter,
        'bad_trials': bad_trials,
        'omission': omission,
        'commission': commission,
        'rt_too_fast': rt_too_fast,
    }


def add_junk_trials(
    events_df: pd.DataFrame, task_name: str
) -> tuple[pd.DataFrame, float]:
    """Calculate percentage of junk trials and add nuisance regressors to dataframe.

    Args:
        events_df: Preprocessed events dataframe
        task_name: Name of the task

    Returns:
        Tuple of (events_df with nuisance columns, percentage of junk trials (0-1)).
    """
    if len(events_df) == 0:
        raise ValueError('Events dataframe is empty')

    events_df = events_df.copy()

    # Get nuisance trial masks
    nuisance_masks = define_nuisance_trials(events_df, task_name)

    # Add nuisance columns to dataframe as integers (0/1)
    events_df['junk_trials'] = nuisance_masks['bad_trials'].astype(int)
    events_df['omission'] = nuisance_masks['omission'].astype(int)
    events_df['commission'] = nuisance_masks['commission'].astype(int)
    events_df['rt_too_fast'] = nuisance_masks['rt_too_fast'].astype(int)

    # Denominator is the number of relevant trials (test/go), not all events,
    # so that non-test events (breaks, cues, etc.) don't dilute the junk rate.
    n_relevant = nuisance_masks['trial_filter'].sum()
    junk_percentage = nuisance_masks['bad_trials'].sum() / n_relevant if n_relevant > 0 else 0.0

    return events_df, junk_percentage


def save_simplified_events(
    regressor_3cols: list, output_file: Union[str, Path]
) -> Path:
    """Save simplified events in 3-column format.

    Args:
        regressor_3cols: List of (3col_tuple, name) pairs from create_design_matrix
        output_file: Path to save simplified events CSV

    Returns:
        Path to saved file.
    """
    output_file = Path(output_file)

    if not regressor_3cols:
        raise ValueError('No regressors provided - regressor_3cols is empty')

    # Convert 3-column tuples to dataframes
    all_events = []
    for (onsets, durations, amplitudes), regressor_name in regressor_3cols:
        if onsets:  # Only if regressor has events
            regressor_df = pd.DataFrame(
                {
                    'onset': onsets,
                    'duration': durations,
                    'amplitude': amplitudes,
                    'regressor': regressor_name,
                }
            )
            # Filter out zero-amplitude entries to avoid redundant rows
            regressor_df = regressor_df[regressor_df['amplitude'] != 0.0]
            if not regressor_df.empty:
                all_events.append(regressor_df)

    # Combine all regressors
    if not all_events:
        raise ValueError('No valid events found after processing regressors')

    simplified_df = pd.concat(all_events, ignore_index=True)

    # Sort by onset time
    simplified_df = simplified_df.sort_values('onset').reset_index(drop=True)

    # Save to CSV
    simplified_df.to_csv(output_file, index=False)

    return output_file


def load_bold_data_with_dummy_removal(
    bold_file: Union[str, Path], dummy_scans: int = DUMMY_SCANS
):
    """Load BOLD data and remove dummy scans.

    Args:
        bold_file: Path to 4D BOLD NIfTI file
        dummy_scans: Number of dummy scans to remove

    Returns:
        BOLD image with dummy scans removed.
    """
    from nilearn.image import load_img

    img = load_img(bold_file)

    if dummy_scans > 0:
        return img.slicer[:, :, :, dummy_scans:]
    return img
