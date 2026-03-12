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
