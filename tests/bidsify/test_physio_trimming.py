# File: tests/bidsify/test_physio_trimming.py
import gzip
import json
import tempfile
from pathlib import Path
import pytest

from neuro_workflow.bidsify.physio_trimming import (
    trim_physio_data,
    update_physio_json,
)


def test_trim_physio_removes_dummy_samples_cardiac():
    """Test that dummy samples are removed from cardiac physio (100 Hz)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock physio TSV with 2000 samples (100 Hz = 20 second recording)
        # Each sample is 10 ms apart
        physio_file = tmpdir / "test_physio.tsv.gz"
        header = "cardiac\ttrigger\n"
        data_lines = [f"{0.5}\t{0}\n" for _ in range(2000)]

        with gzip.open(physio_file, 'wt') as f:
            f.write(header)
            f.writelines(data_lines)

        # Create mock JSON
        json_file = tmpdir / "test_physio.json"
        sidecar = {
            "SamplingFrequency": 100,
            "StartTime": 0.0,
            "Columns": ["cardiac", "trigger"],
        }
        json_file.write_text(json.dumps(sidecar))

        # Trim (remove 7 dummies = 10,430 ms = 1043 samples at 100 Hz)
        trim_physio_data(
            physio_file,
            json_file,
            dummy_scans=7,
            tr=1.49,
            behavioral_cutoff_ms=None,
        )

        # Read trimmed file and check
        with gzip.open(physio_file, 'rt') as f:
            lines = f.readlines()

        # Should have header + (2000 - 1043) = 957 data lines
        assert len(lines) == 958  # 957 data + 1 header

        # Check JSON was updated
        updated = json.loads(json_file.read_text())
        assert updated["StartTime"] == 10.43
        assert updated["DummyScansRemoved"] == 7


def test_trim_physio_with_behavioral_cutoff():
    """Test trimming at both dummy and behavioral cutoff points."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock physio TSV with 2000 samples
        physio_file = tmpdir / "test_physio.tsv.gz"
        header = "cardiac\ttrigger\n"
        data_lines = [f"{0.5}\t{0}\n" for _ in range(2000)]

        with gzip.open(physio_file, 'wt') as f:
            f.write(header)
            f.writelines(data_lines)

        # Create mock JSON
        json_file = tmpdir / "test_physio.json"
        sidecar = {
            "SamplingFrequency": 100,
            "StartTime": 0.0,
            "Columns": ["cardiac", "trigger"],
        }
        json_file.write_text(json.dumps(sidecar))

        # Trim with behavioral cutoff at 15 seconds = 1500 samples from start
        # Dummy offset = 10.43 seconds = 1043 samples
        # So we keep from sample 1043 to sample 1500, giving 457 samples
        trim_physio_data(
            physio_file,
            json_file,
            dummy_scans=7,
            tr=1.49,
            behavioral_cutoff_ms=15000,  # 15 seconds from original start
        )

        # Read trimmed file
        with gzip.open(physio_file, 'rt') as f:
            lines = f.readlines()

        # Should have header + 457 data lines (1500 - 1043 = 457)
        assert len(lines) == 458

        # Check JSON metadata
        updated = json.loads(json_file.read_text())
        assert updated["StartTime"] == 10.43
        assert updated.get("BehavioralTrimApplied") is True
        assert updated.get("BehavioralTrimPointMs") == 15000


def test_trim_physio_behavioral_cutoff_less_than_dummy_offset():
    """Test handling when behavioral_cutoff_ms < dummy_offset_ms."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create 2000 sample mock physio
        physio_file = tmpdir / "test_physio.tsv.gz"
        header = "cardiac\ttrigger\n"
        data_lines = [f"{0.5}\t{0}\n" for _ in range(2000)]

        with gzip.open(physio_file, 'wt') as f:
            f.write(header)
            f.writelines(data_lines)

        # Create JSON
        json_file = tmpdir / "test_physio.json"
        sidecar = {
            "SamplingFrequency": 100,
            "StartTime": 0.0,
            "Columns": ["cardiac", "trigger"],
        }
        json_file.write_text(json.dumps(sidecar))

        # Trim with behavioral_cutoff_ms < dummy_offset_ms (5000 < 10430)
        trim_physio_data(
            physio_file,
            json_file,
            dummy_scans=7,
            tr=1.49,
            behavioral_cutoff_ms=5000,  # Less than dummy offset
        )

        # Verify file was trimmed (dummies removed but behavioral cutoff skipped)
        with gzip.open(physio_file, 'rt') as f:
            lines = f.readlines()

        # Should have dummy-trimmed data (1000 lines), not behavioral-trimmed
        assert len(lines) == 958  # 957 data + 1 header

        # Check JSON was updated
        updated = json.loads(json_file.read_text())
        assert updated["StartTime"] == 10.43
        assert updated["DummyScansRemoved"] == 7
        # BehavioralTrimApplied should NOT be set since cutoff was invalid
        assert updated.get("BehavioralTrimApplied") is None
