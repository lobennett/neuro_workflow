"""Utilities for normalizing behavioral archive filenames to BIDS format."""

import re


def normalize_task_name(task_str: str) -> str:
    """
    Convert snake_case archive task name to camelCase BIDS format.

    Removes excess suffixes (_single_task_network, _single_task, _network)
    while preserving meaningful _with_ combinations.

    Args:
        task_str: Archive filename or task name in snake_case

    Returns:
        Normalized task name in camelCase (BIDS format)

    Examples:
        "flanker_single_task_network" -> "flanker"
        "stop_signal_with_directed_forgetting" -> "stopSignalWDirectedForgetting"
    """
    # Remove excess suffixes
    task = re.sub(r"_single_task_network$|_single_task$|_network$", "", task_str)

    # Split on underscores
    parts = task.split("_")

    # Convert to camelCase
    if not parts:
        return ""

    camel = parts[0]  # First part stays lowercase
    for part in parts[1:]:
        if part == "with":
            # Special case: _with_ becomes W
            camel += "W"
        else:
            # Capitalize first letter
            camel += part.capitalize()

    return camel


def normalize_mturk_filename(filename: str) -> str:
    """
    Normalize mTurk filename: s528_go_nogo_with_shape_matching.csv
    -> sub-s528_task-goNogoWShapeMatching_behavior.csv

    Args:
        filename: Archive filename (e.g., "s528_go_nogo_with_shape_matching.csv")

    Returns:
        BIDS-normalized filename with sub- prefix

    Raises:
        ValueError: If filename cannot be parsed (no extension or no subject)
    """
    # Split filename and extension
    parts = filename.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Could not parse mTurk filename: {filename}")

    stem, ext = parts

    # Parse subject and task from stem
    # Format: [s###]_[task_name] or [task_name]_[s###]
    stem_parts = stem.split("_")

    subject = None
    task_parts = []

    for part in stem_parts:
        if part.startswith("s") and part[1:].isdigit():
            subject = part
        else:
            task_parts.append(part)

    if not subject or not task_parts:
        raise ValueError(f"Could not parse mTurk filename: {filename}")

    task_name = "_".join(task_parts)
    normalized_task = normalize_task_name(task_name)

    return f"sub-{subject}_task-{normalized_task}_behavior.{ext}"


def normalize_out_of_scanner_filename(filename: str) -> str:
    """
    Normalize out_of_scanner filename: s247_flanker_single_task.csv
    -> sub-s247_task-flanker_behavior.csv

    Args:
        filename: Archive filename (e.g., "s247_flanker_single_task.csv")

    Returns:
        BIDS-normalized filename with sub- prefix

    Raises:
        ValueError: If filename cannot be parsed
    """
    # Same logic as mTurk
    return normalize_mturk_filename(filename)


def normalize_survey_filename(filename: str, subject: str = None) -> str:
    """
    Normalize survey filename: prescan_1.json
    -> prescan-01_survey.json (or sub-s247_prescan-01_survey.json if subject given)

    Args:
        filename: Archive filename (e.g., "prescan_1.json")
        subject: Optional subject ID to include in output

    Returns:
        BIDS-normalized filename

    Raises:
        ValueError: If filename cannot be parsed
    """
    # Extract number and extension (final component only)
    match = re.match(r"prescan_(\d+)\.(.+\.)?([^.]+)$", filename)
    if not match:
        raise ValueError(f"Could not parse survey filename: {filename}")

    number = match.group(1)
    ext = match.group(3)  # Final extension only

    # Zero-pad to 2 digits
    padded_number = number.zfill(2)

    # Build output
    if subject:
        return f"sub-{subject}_prescan-{padded_number}_survey.{ext}"
    else:
        return f"prescan-{padded_number}_survey.{ext}"
