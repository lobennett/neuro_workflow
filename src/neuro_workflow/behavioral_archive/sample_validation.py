"""Utilities for validating subjects against discovery/validation samples."""

import json
from pathlib import Path
from typing import Dict, List, Set, Union, Any


def load_samples_from_config(config_path: Union[str, Path]) -> Dict[str, Union[List[str], Dict[str, Any]]]:
    """
    Load discovery and validation sample lists from behavioral_session_mapping.json.

    Args:
        config_path: Path to config/behavioral_session_mapping.json

    Returns:
        Dict with keys:
        - 'discovery': list of discovery subject IDs
        - 'validation': list of validation subject IDs
        - 'excluded': dict of {subject_id: exclude_reason} for excluded subjects

    Supports multiple config formats:
    1. Top-level arrays: {"discovery": [...], "validation": [...]}
    2. Session array: {"sessions": [{"subject": "s03", "sample": "discovery"}, ...]}
    3. Subjects dict: {"subjects": {"s03": {"sample": "discovery", "excluded": false}, ...}}

    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text())

    discovery = []
    validation = []
    excluded = {}

    # Format 1: Top-level arrays (old format)
    if "discovery" in data or "validation" in data:
        discovery = data.get("discovery", [])
        validation = data.get("validation", [])

    # Format 2: Sessions array (alternative format)
    elif "sessions" in data:
        discovery_set = set()
        validation_set = set()
        for session_info in data.get("sessions", []):
            subject = session_info.get("subject")
            sample = session_info.get("sample")
            if subject and sample:
                if sample == "discovery":
                    discovery_set.add(subject)
                elif sample == "validation":
                    validation_set.add(subject)
        discovery = list(discovery_set)
        validation = list(validation_set)

    # Format 3: Subjects dict (current format from generate_behavioral_mapping.py)
    elif "subjects" in data:
        discovery_set = set()
        validation_set = set()
        for subject_id, subject_info in data.get("subjects", {}).items():
            sample = subject_info.get("sample")
            is_excluded = subject_info.get("excluded", False)
            exclude_reason = subject_info.get("exclude_reason")

            if is_excluded:
                excluded[subject_id] = exclude_reason or "excluded"
            else:
                if sample == "discovery":
                    discovery_set.add(subject_id)
                elif sample == "validation":
                    validation_set.add(subject_id)

        discovery = list(discovery_set)
        validation = list(validation_set)

    return {
        "discovery": discovery,
        "validation": validation,
        "excluded": excluded,
    }


def is_subject_in_sample(subject: str, samples: Dict[str, List[str]]) -> bool:
    """
    Check if subject is in discovery or validation sample.

    Args:
        subject: Subject ID (with or without 'sub-' prefix)
        samples: Dict from load_samples_from_config

    Returns:
        True if subject in either sample, False otherwise
    """
    # Normalize subject (remove sub- prefix if present)
    clean_subject = subject.replace("sub-", "")

    discovery = [s.replace("sub-", "") for s in samples.get("discovery", [])]
    validation = [s.replace("sub-", "") for s in samples.get("validation", [])]

    return clean_subject in discovery or clean_subject in validation
