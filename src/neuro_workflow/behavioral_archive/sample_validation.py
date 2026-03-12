"""Utilities for validating subjects against discovery/validation samples."""

import json
from pathlib import Path
from typing import Dict, List, Set


def load_samples_from_config(config_path: str | Path) -> Dict[str, List[str]]:
    """
    Load discovery and validation sample lists from behavioral_session_mapping.json.

    Args:
        config_path: Path to config/behavioral_session_mapping.json

    Returns:
        Dict with 'discovery' and 'validation' keys containing subject lists

    Raises:
        FileNotFoundError: If config file doesn't exist
        KeyError: If required keys missing from config
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text())

    # Extract sample lists - support different config formats
    samples = {
        "discovery": data.get("discovery", []),
        "validation": data.get("validation", []),
    }

    # If config has session mappings, extract unique subjects
    if "discovery" not in data and "sessions" in data:
        discovery = set()
        validation = set()
        for session_info in data.get("sessions", []):
            subject = session_info.get("subject")
            sample = session_info.get("sample")
            if subject and sample:
                if sample == "discovery":
                    discovery.add(subject)
                elif sample == "validation":
                    validation.add(subject)
        samples["discovery"] = list(discovery)
        samples["validation"] = list(validation)

    return samples


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
