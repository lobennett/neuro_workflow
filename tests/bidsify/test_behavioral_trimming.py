# File: tests/bidsify/test_behavioral_trimming.py
import tempfile
from pathlib import Path
import pandas as pd
import pytest

from neuro_workflow.bidsify.behavioral_trimming import trim_behavioral_csv


def test_trim_behavioral_csv_at_time_elapsed():
    """Test trimming behavioral CSV at time_elapsed cutoff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock behavioral CSV with time_elapsed in milliseconds
        beh_df = pd.DataFrame({
            'trial': [1, 2, 3, 4, 5],
            'time_elapsed': [500, 2000, 5000, 10000, 15000],
            'response': ['go', 'nogo', 'go', 'nogo', 'go'],
        })
        beh_file = tmpdir / "behavior.csv"
        beh_df.to_csv(beh_file, index=False)

        # Trim at 10000 ms
        trim_behavioral_csv(beh_file, cutoff_time_ms=10000)

        # Verify output
        trimmed = pd.read_csv(beh_file)
        assert len(trimmed) == 4  # Rows where time_elapsed <= 10000
        assert trimmed['time_elapsed'].max() == 10000
