# File: tests/bidsify/test_exclusions_manifest.py
import json
import tempfile
from pathlib import Path
import pytest

from neuro_workflow.bidsify.exclusions_manifest import (
    ExclusionsManifest,
)


def test_manifest_creates_valid_json():
    """Test that manifest creates valid exclusions JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "exclusions.json"

        manifest = ExclusionsManifest(output_file)

        # Add some exclusions
        manifest.add_dummy_removal("s19", "ses-07", "stopSignal")
        manifest.add_behavioral_trim(
            "s19", "ses-07", "stopSignal",
            original_trs=493, trimmed_trs=229,
            behavioral_cutoff_ms=342700
        )

        # Save
        manifest.save()

        # Verify valid JSON
        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)

        assert "scans" in data
        assert len(data["scans"]) == 2
