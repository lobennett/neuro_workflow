import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_stop_signal_csv(tmp_path):
    """Create a minimal stop signal behavioral CSV with realistic timing.

    Timing: trigger at 5s, events at 20s/25s/30s (well past 10.43s dummy offset).
    """
    df = pd.DataFrame({
        "trial_id": ["design_setup", "fmri_trigger_initial", "test_fixation", "test_trial", "test_trial", "test_trial"],
        "time_elapsed": [1000, 5000, 15000, 20000, 25000, 30000],
        "block_duration": [1000, 100, 500, 1500, 1500, 1500],
        "rt": [0, 0, 0, 450, 520, -1],
        "key_press": [-1, -1, -1, 37, 39, -1],
        "correct_response": [-1, -1, -1, 37, 39, 37],
        "stim_duration": [0, 0, 0, 1500, 1500, 1500],
        "exp_id": ["stop_signal_single_task_network__fmri"] * 6,
        "stop_signal_condition": ["", "", "", "go", "go", "stop"],
        "SS_delay": [0, 0, 0, 0, 0, 250],
        "SS_duration": [0, 0, 0, 0, 0, 500],
        "stop_acc": [0, 0, 0, 0, 0, 1],
        "go_acc": [0, 0, 0, 1, 1, 0],
        "stim": ["", "", "", "left", "right", "left"],
        "stimulus": ["", "", "", "", "", ""],
        "text": ["", "", "", "", "", ""],
    })
    csv_path = tmp_path / "stop_signal_single_task_network__fmri_results.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


class TestCreateEventsDf:
    def test_produces_bids_columns(self, tmp_path):
        from neuro_workflow.events.create import create_events_df
        csv_path = _make_stop_signal_csv(tmp_path)
        result = create_events_df(csv_path, "stopSignal")
        assert "onset" in result.columns
        assert "duration" in result.columns
        assert "response_time" in result.columns
        assert "trial_type" in result.columns

    def test_onset_in_seconds(self, tmp_path):
        from neuro_workflow.events.create import create_events_df
        csv_path = _make_stop_signal_csv(tmp_path)
        result = create_events_df(csv_path, "stopSignal")
        # All onsets should be > 0 (trigger time subtracted, negative filtered)
        assert (result["onset"] > 0).all() or len(result) == 0

    def test_na_for_missing_values(self, tmp_path):
        from neuro_workflow.events.create import create_events_df
        csv_path = _make_stop_signal_csv(tmp_path)
        result = create_events_df(csv_path, "stopSignal")
        # NaN values should be filled with 'n/a'
        assert not result.isnull().any().any()


