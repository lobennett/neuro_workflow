import json
import pytest
from pathlib import Path
from unittest.mock import patch
from neuro_workflow.behavioral_archive.sample_validation import (
    load_samples_from_config,
    is_subject_in_sample,
)


def test_load_samples_from_config(tmp_path):
    """Load discovery and validation sample lists from behavioral_session_mapping.json"""
    config_file = tmp_path / "behavioral_session_mapping.json"
    config_data = {
        "discovery": ["s03", "s10", "s19"],
        "validation": ["s247", "s528"],
    }
    config_file.write_text(json.dumps(config_data))

    samples = load_samples_from_config(str(config_file))

    assert set(samples["discovery"]) == {"s03", "s10", "s19"}
    assert set(samples["validation"]) == {"s247", "s528"}


def test_load_samples_missing_file():
    """Raise error if config file not found."""
    with pytest.raises(FileNotFoundError):
        load_samples_from_config("/nonexistent/path/config.json")


def test_is_subject_in_sample_discovery():
    """Check if subject is in discovery sample."""
    samples = {"discovery": ["s03", "s10"], "validation": ["s247"]}

    assert is_subject_in_sample("s03", samples) is True
    assert is_subject_in_sample("s10", samples) is True
    assert is_subject_in_sample("s247", samples) is True
    assert is_subject_in_sample("s999", samples) is False


def test_is_subject_in_sample_with_subject_prefix():
    """Handle both with and without sub- prefix."""
    samples = {"discovery": ["s03", "s10"], "validation": []}

    assert is_subject_in_sample("s03", samples) is True
    assert is_subject_in_sample("sub-s03", samples) is True
