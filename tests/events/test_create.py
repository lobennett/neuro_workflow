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


class TestRunCreateEventsHelpers:
    def test_parse_bidsignore_extracts_sub_ses_task(self, tmp_path):
        from neuro_workflow.events.create import parse_bidsignore
        (tmp_path / ".bidsignore").write_text(
            "# a comment\n"
            "sub-s01/ses-01/func/sub-s01_ses-01_task-flanker_run-1_bold.nii.gz\n"
            "\n"
            "sub-s10/ses-03/func/sub-s10_ses-03_task-nBack_run-1_bold.nii.gz\n"
        )
        ignored = parse_bidsignore(tmp_path)
        # NOTE: the regex's greedy \w+ after `task-` also captures the trailing
        # `_run`, so the task token is e.g. "flanker_run" — a *known* mismatch
        # with discover_nifti_tasks (which captures the bare "flanker"), meaning
        # events-stage .bidsignore filtering is currently inert. This pins the
        # existing behavior; the bug is tracked separately, not fixed in this
        # behavior-preserving refactor.
        assert ("s01", "ses-01", "flanker_run") in ignored
        assert ("s10", "ses-03", "nBack_run") in ignored

    def test_parse_bidsignore_missing_file_returns_empty(self, tmp_path):
        from neuro_workflow.events.create import parse_bidsignore
        assert parse_bidsignore(tmp_path) == set()

    def test_discover_nifti_tasks_excludes_rest_and_ignored(self, tmp_path):
        from neuro_workflow.events.create import discover_nifti_tasks
        func = tmp_path / "func"
        func.mkdir()
        for name in (
            "sub-s01_ses-01_task-flanker_run-1_bold.nii.gz",
            "sub-s01_ses-01_task-rest_run-1_bold.nii.gz",
            "sub-s01_ses-01_task-nBack_run-1_bold.nii.gz",
        ):
            (func / name).touch()
        tasks = discover_nifti_tasks(func, "s01", "ses-01", {("s01", "ses-01", "nBack")})
        assert tasks == {"flanker"}  # rest excluded, nBack ignored

    def test_group_csvs_by_task_filters_and_reads_run(self, tmp_path):
        from neuro_workflow.events.create import group_csvs_by_task
        beh = tmp_path / "beh"
        beh.mkdir()
        (beh / "sub-s01_ses-01_task-flanker_run-2_beh.csv").touch()
        (beh / "sub-s01_ses-01_task-flanker_beh.csv").touch()  # no run -> 1
        (beh / "sub-s01_ses-01_task-rest_beh.csv").touch()  # not allowed
        out = group_csvs_by_task(beh, {"flanker"})
        runs = sorted((t, r) for t, r, _ in out)
        assert runs == [("flanker", 1), ("flanker", 2)]


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


