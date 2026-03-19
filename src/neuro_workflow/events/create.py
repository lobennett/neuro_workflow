"""Generate BIDS _events.tsv files from behavioral CSVs."""
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from neuro_workflow.events.utils import (
    get_neg_rt_correction,
    cal_time_elapsed,
    add_choice_acc,
    add_cols,
    response_time_and_junk,
)

log = logging.getLogger(__name__)

# --- Name mapping (same as rename script, also used by create_events) ---

LONG_NAME_TO_SHORT = {
    "stop_signal": "stopSignal",
    "flanker": "flanker",
    "go_nogo": "goNogo",
    "n_back": "nBack",
    "cued_task_switching": "cuedTS",
    "spatial_task_switching": "spatialTS",
    "directed_forgetting": "directedForgetting",
    "shape_matching": "shapeMatching",
    "stop_signal_with_flanker": "stopSignalWFlanker",
    "stop_signal_with_directed_forgetting": "stopSignalWDirectedForgetting",
    "directed_forgetting_with_flanker": "directedForgettingWFlanker",
    "directed_forgetting_with_cued_task_switching": "directedForgettingWCuedTS",
    "cued_task_switching_with_directed_forgetting": "directedForgettingWCuedTS",
    "spatial_task_switching_with_cued_task_switching": "spatialTSWCuedTS",
    "flanker_with_shape_matching": "flankerWShapeMatching",
    "flanker_with_cued_task_switching": "cuedTSWFlanker",
    "n_back_with_shape_matching": "nBackWShapeMatching",
    "n_back_with_spatial_task_switching": "nBackWSpatialTS",
    "shape_matching_with_cued_task_switching": "shapeMatchingWCuedTS",
    "shape_matching_with_spatial_task_switching": "spatialTSWShapeMatching",
}


def long_name_to_short_name(long_name: str) -> str:
    return LONG_NAME_TO_SHORT[long_name]


def get_task_from_filename(filename: str) -> str:
    """Extract long task name from behavioral CSV filename."""
    long_name = filename.split("__fmri")[0]
    if "_single_task_network" in long_name:
        long_name = long_name.split("_single_task_network")[0]
    elif "task-" in long_name:
        parts = long_name.split("_")
        for p in parts:
            if p.startswith("task-"):
                long_name = p.replace("task-", "").replace("-", "_")
                break
    return long_name


# --- Rename cells (trial_id label standardization) ---

_RENAME_CELLS_LOOKUP = {
    "stop_signal_single_task_network__fmri": {"fixation": "test_fixation", "practice-no-stop-feedback": "break"},
    "shape_matching_single_task_network__fmri": {"fixation": "test_fixation", "mask": "test_mask", "practice-no-stop-feedback": "break"},
    "n_back_single_task_network__fmri": {"practice-no-stop-feedback": "break", "fixation": "test_fixation"},
    "go_nogo_single_task_network__fmri": {"update_correct_response": "test_fixation", "feedback_block": "break"},
    "spatial_task_switching_single_task_network__fmri": {"feedback_block": "break", "practice_cue": "blank_screen"},
    "cued_task_switching_single_task_network__fmri": {"practice-stop-feedback": "break"},
    "directed_forgetting_single_task_network__fmri": {"fixation": "test_fixation", "stim": "test_stim", "cue": "test_cue", "test_feedback": "break"},
    "flanker_single_task_network__fmri": {"practice-no-stop-feedback": "break"},
    "directed_forgetting_with_flanker__fmri": {"test_start_fixation": "test_fixation", "test_feedback": "break"},
    "stop_signal_with_directed_forgetting__fmri": {"ITI_fixation": "test_fixation", "stim": "test_stim", "cue": "test_cue", "fixation": "test_fixation", "feedback_block": "break"},
    "stop_signal_with_flanker__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
    "cued_task_switching_with_directed_forgetting__fmri": {"test_start_fixation": "test_fixation", "test_feedback": "break"},
    "spatial_task_switching_with_cued_task_switching__fmri": {"test_cue_block": "test_cue", "fixation": "test_fixation", "feedback_block": "break"},
    "flanker_with_shape_matching__fmri": {"feedback_block": "break"},
    "flanker_with_cued_task_switching__fmri": {"practice-stop-feedback": "break"},
    "flanker_with_cued_task_switching": {"practice-stop-feedback": "break"},
    "n_back_with_shape_matching__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
    "shape_matching_with_spatial_task_switching__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
    "shape_matching_with_cued_task_switching__fmri": {"fixation": "test_fixation", "cue": "test_cue", "feedback_block": "break"},
    "shape_matching_with_cued_task_switching": {"fixation": "test_fixation", "cue": "test_cue", "feedback_block": "break"},
    "n_back_with_spatial_task_switching__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
}


def _rename_cells(df: pd.DataFrame, exp_id: str) -> pd.DataFrame:
    change = _RENAME_CELLS_LOOKUP.get(exp_id)
    if change is None:
        log.warning("No rename_cells mapping for exp_id: %s", exp_id)
        return df
    for key, value in change.items():
        df["trial_id"] = df["trial_id"].replace(key, value)
    if "cued_task_switching_" in exp_id:
        df.loc[df["trial_id"] == "test_cue", "correct_response"] = "n/a"
    return df


def _set_default_event_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df.time_elapsed > 0]
    df = df.rename(columns={"time_elapsed": "onset", "choice_acc": "acc", "stim_duration": "duration", "rt": "response_time"})
    df["onset"] = df["onset"] / 1000
    df["duration"] = df["duration"] / 1000
    df["response_time"] = df["response_time"] / 1000
    df["response_time"] = df["response_time"].replace(-0.001, np.nan)
    first_columns = ["onset", "duration", "response_time", "trial_id", "trial_type", "key_press", "correct_response"]
    new_column_order = first_columns + [col for col in df.columns if col not in first_columns]
    df = df[new_column_order]
    return df


def _flagged_feedback(text_content: str) -> bool:
    keywords = ["accuracy", "slowly", "respond", "response"]
    return any(keyword in text_content.lower() for keyword in keywords)


def is_placeholder_behavioral_csv(csv_file: Path) -> bool:
    """Check if behavioral CSV is a placeholder (missing data marker).

    Args:
        csv_file: Path to behavioral CSV file

    Returns:
        True if file contains PLACEHOLDER marker, False otherwise
    """
    try:
        with open(csv_file, encoding='utf-8') as f:
            first_line = f.readline()
            return "PLACEHOLDER" in first_line
    except Exception as e:
        log.warning("Error checking if %s is placeholder: %s", csv_file, e)
        return False


def create_empty_events_df() -> pd.DataFrame:
    """Create empty events DataFrame with required BIDS columns.

    Returns:
        Empty DataFrame with standard BIDS events columns
    """
    return pd.DataFrame(columns=[
        "onset",
        "duration",
        "trial_id",
        "trial_type",
        "response_time",
        "key_press",
        "correct_response",
    ])


def _get_rows_with_feedback(df: pd.DataFrame, original_df: pd.DataFrame):
    feedback_block_rows = original_df[original_df["trial_id"] == "test_feedback"]
    if len(feedback_block_rows) == 0:
        feedback_block_rows = original_df[original_df["trial_id"] == "feedback_block"]
    if len(feedback_block_rows) == 0 and "stimulus" in original_df.columns:
        stimulus_col = original_df["stimulus"].astype(str)
        feedback_block_rows = original_df[stimulus_col.str.contains("completed", na=False)]
    indices_to_change = []
    for index, row in feedback_block_rows.iterrows():
        stimulus = row["stimulus"]
        if _flagged_feedback(stimulus):
            indices_to_change.append(index)
    return feedback_block_rows, indices_to_change


def create_events_df(filename: Path, short_name: str) -> pd.DataFrame:
    """Create a BIDS events dataframe from a behavioral CSV."""
    original_df = pd.read_csv(filename)
    exp_id = original_df["exp_id"][0]
    log.info("Processing %s for %s", filename, exp_id)
    df = original_df.copy()
    df = get_neg_rt_correction(df)
    df = cal_time_elapsed(df)
    df = add_choice_acc(df)
    df = add_cols(df, exp_id)
    df = response_time_and_junk(df, short_name)
    df = _set_default_event_cols(df)
    df = _rename_cells(df, exp_id)

    # Convert all columns to object dtype before filling NaN with "n/a"
    # (newer pandas refuses to fill float columns with string values)
    for col in df.columns:
        if df[col].isna().any():
            df[col] = df[col].astype(object)
    df.fillna("n/a", inplace=True)

    # Fix spatialTS "na" trial_type
    if "spatial_task_switching" in exp_id:
        df.loc[(df["trial_id"] == "test_trial") & (df["trial_type"] == "na"), "trial_type"] = "tn/a_cn/a"
        df.loc[(df["trial_id"] == "test_trial") & (df["trial_type"] == "tn/a_cn/a"), "task_switch"] = "tn/a_cn/a"

    # Detect performance feedback blocks
    feedback_block_rows, indices_to_change = _get_rows_with_feedback(df, original_df)
    for index in indices_to_change:
        df.loc[index, "trial_id"] = "break_with_performance_feedback"

    return df


def run_create_events(
    behavioral_dir: Path,
    bids_dir: Path,
    subjects: list[str] | None = None,
    sessions: list[str] | None = None,
) -> None:
    """Walk sourcedata behavioral CSVs and write BIDS event files.

    Args:
        behavioral_dir: Path to sourcedata/ with sub-*/ses-*/beh/*.csv
        bids_dir: Path to BIDS dataset root (events written to func/ dirs)
        subjects: Optional list of subjects to process (default: all)
        sessions: Optional list of sessions to process (default: all)
    """
    for sub_dir in sorted(behavioral_dir.glob("sub-*")):
        if subjects and sub_dir.name not in subjects:
            continue
        for ses_dir in sorted(sub_dir.glob("ses-*")):
            if sessions and ses_dir.name not in sessions:
                continue
            beh_dir = ses_dir / "beh"
            if not beh_dir.exists():
                continue
            func_dir = bids_dir / sub_dir.name / ses_dir.name / "func"
            if not func_dir.exists():
                log.warning("No func dir for %s %s, skipping", sub_dir.name, ses_dir.name)
                continue

            # Get tasks that have NIfTIs
            nifti_tasks = set()
            for nii in func_dir.glob("*.nii.gz"):
                m = re.search(r"task-([^_]+)", nii.name)
                if m and m.group(1) != "rest":
                    nifti_tasks.add(m.group(1))

            # Group CSVs by task
            csv_files = sorted(beh_dir.glob("*.csv"))
            task_to_files: dict[str, list[Path]] = {}
            for csv_file in csv_files:
                # Extract task from BIDS-style sourcedata filename (stop at underscore)
                m = re.search(r"task-([^_]+)", csv_file.name)
                if m:
                    task_name = m.group(1)
                    if task_name in nifti_tasks:
                        task_to_files.setdefault(task_name, []).append(csv_file)

            # Track which tasks have been processed
            tasks_with_events = set()

            for task_name, files in task_to_files.items():
                for run_idx, csv_file in enumerate(files, 1):
                    outname = f"{sub_dir.name}_{ses_dir.name}_task-{task_name}_run-{run_idx}_events.tsv"
                    outpath = func_dir / outname

                    # Check if this is a placeholder behavioral file
                    if is_placeholder_behavioral_csv(csv_file):
                        log.info(
                            "Creating empty events.tsv for placeholder behavioral: %s",
                            outpath,
                        )
                        df = create_empty_events_df()
                    else:
                        # Normal processing of behavioral CSV
                        try:
                            df = create_events_df(csv_file, task_name)
                            log.info("Writing events.tsv from behavioral: %s", outpath)
                        except Exception as e:
                            log.warning(
                                "Failed to process behavioral %s: %s. Creating empty events.tsv.",
                                csv_file,
                                e,
                            )
                            df = create_empty_events_df()

                    df.to_csv(outpath, sep="\t", index=False)
                    tasks_with_events.add(task_name)

            # Check for BOLD scans without behavioral data
            for bold_task in nifti_tasks:
                if bold_task not in tasks_with_events:
                    log.warning(
                        "BOLD scan exists without behavioral data: %s %s task-%s",
                        sub_dir.name,
                        ses_dir.name,
                        bold_task,
                    )
                    outname = f"{sub_dir.name}_{ses_dir.name}_task-{bold_task}_run-1_events.tsv"
                    outpath = func_dir / outname
                    log.info(
                        "Creating empty events.tsv for BOLD without behavioral: %s",
                        outpath,
                    )
                    df = create_empty_events_df()
                    df.to_csv(outpath, sep="\t", index=False)
