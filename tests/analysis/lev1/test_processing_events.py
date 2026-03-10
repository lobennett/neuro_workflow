"""Tests for the events processing module."""

import numpy as np
import pandas as pd
import pytest

from neuro_workflow.analysis.lev1.processing.events import (
    define_nuisance_trials,
    preprocess_events,
)


class TestPreprocessEvents:
    """Tests for preprocess_events function."""

    def test_preprocess_events_basic(self, sample_events_data):
        """Test basic event preprocessing."""
        processed = preprocess_events(sample_events_data, 'cuedTS')

        # Check that junk column is added
        assert 'junk' in processed.columns
        assert 'na_trials' in processed.columns

        # Should not modify original dataframe
        assert processed is not sample_events_data

    def test_preprocess_events_negative_rt_handling(self):
        """Test handling of negative RT values."""
        events_data = pd.DataFrame(
            {
                'onset': [
                    20.0,
                    30.0,
                    40.0,
                    50.0,
                ],  # Use larger onsets to avoid negative after dummy adjustment
                'response_time': [0.5, -1.0, 0.7, -999],
                'trial_id': ['test_trial'] * 4,
                'trial_type': [
                    'tstay_cstay',
                    'tswitch_cswitch',
                    'tstay_cstay',
                    'tstay_cswitch',
                ],
            }
        )

        processed = preprocess_events(events_data, 'cuedTS')

        # Should have 4 rows (no negative onsets after dummy adjustment)
        assert len(processed) == 4

        # Check by actual row position in processed dataframe
        # Row 1 (original index 1) has RT -1.0 -> should be junk=1, RT=NaN
        # Row 3 (original index 3) has RT -999 -> should be junk=1, RT=NaN
        junk_rows = processed[processed['junk'] == 1]
        non_junk_rows = processed[processed['junk'] == 0]

        assert len(junk_rows) == 2
        assert len(non_junk_rows) == 2

        # Check that negative RTs became NaN in junk rows
        assert all(pd.isna(junk_rows['response_time']))

        # Check that positive RTs remain unchanged in non-junk rows
        assert 0.5 in non_junk_rows['response_time'].values
        assert 0.7 in non_junk_rows['response_time'].values

    def test_preprocess_events_negative_onset_filtering(self):
        """Test filtering of events with negative onset values."""
        events_data = pd.DataFrame(
            {
                'onset': [10.0, -2.0, 30.0, -5.0, 50.0],
                'response_time': [0.5, 0.6, 0.7, 0.8, 0.9],
                'trial_id': ['test_trial'] * 5,
                'trial_type': ['tstay_cswitch'] * 5,
            }
        )

        # Disable dummy scan adjustment to test pure negative onset filtering
        processed = preprocess_events(
            events_data, 'cuedTS', adjust_for_dummy_scans=False
        )

        # Should drop rows with negative onset values
        assert len(processed) == 3
        assert all(processed['onset'] >= 0)

        # Check that the correct rows remain (indices 0, 2, 4 from original)
        expected_onsets = [10.0, 30.0, 50.0]
        expected_rts = [0.5, 0.7, 0.9]

        assert processed['onset'].tolist() == expected_onsets
        assert processed['response_time'].tolist() == expected_rts

    def test_preprocess_events_negative_onset_with_dummy_scans(self):
        """Test negative onset filtering after dummy scan adjustment."""
        events_data = pd.DataFrame(
            {
                'onset': [5.0, 8.0, 12.0, 15.0],
                'response_time': [0.5, 0.6, 0.7, 0.8],
                'trial_id': ['test_trial'] * 4,
                'trial_type': ['go'] * 4,
            }
        )

        # With default dummy_scans=7 and tr=1.49, subtract 7*1.49=10.43s from onsets
        processed = preprocess_events(
            events_data, 'cuedTS', adjust_for_dummy_scans=True
        )

        # After adjustment: onsets become [5.0-10.43, 8.0-10.43, 12.0-10.43, 15.0-10.43]
        # = [-5.43, -2.43, 1.57, 4.57]
        # Only the last two should remain
        assert len(processed) == 2
        assert all(processed['onset'] >= 0)

        # Check expected onsets (rounded to 2 decimal places for comparison)
        expected_onsets = [1.57, 4.57]
        actual_onsets = [round(onset, 2) for onset in processed['onset'].tolist()]
        assert actual_onsets == expected_onsets


class TestDefineNuisanceTrials:
    """Tests for define_nuisance_trials function."""

    def test_define_nuisance_trials_task_switching(self):
        """Test nuisance trial definition for cuedTS."""
        events_data = pd.DataFrame(
            {
                'trial_id': ['test_trial'] * 6,
                'key_press': [1, 2, -1, 3, 1, 2],
                'correct_response': [1, 2, 1, 2, 1, 2],
                'response_time': [0.5, 0.15, -1, 0.6, 0.7, 0.8],
                'junk': [0, 0, 0, 0, 1, 0],
            }
        )

        nuisance_masks = define_nuisance_trials(events_data, 'cuedTS')

        # Check expected nuisance types
        expected_keys = {'trial_filter', 'bad_trials', 'omission', 'commission', 'rt_too_fast'}
        assert set(nuisance_masks.keys()) == expected_keys

        # Verify specific trials
        assert nuisance_masks['bad_trials'].iloc[4]  # junk == 1
        assert nuisance_masks['omission'].iloc[2]  # key_press == -1
        assert nuisance_masks['commission'].iloc[3]  # wrong key press
        assert nuisance_masks['rt_too_fast'].iloc[1]  # RT < 0.2

    def test_define_nuisance_trials_stop_signal(self):
        """Test nuisance trial definition for stop-signal task."""
        events_data = pd.DataFrame(
            {
                'trial_type': ['go', 'go', 'stop_success', 'go'],
                'key_press': [1, 2, -1, 3],
                'correct_response': [1, 2, -1, 2],
                'response_time': [0.5, 0.15, -1, 0.6],
                'junk': [0, 0, 0, 0],
            }
        )

        nuisance_masks = define_nuisance_trials(events_data, 'stopSignal')

        # For stop-signal, trial_mask should be 'go' trials only
        assert nuisance_masks['omission'].sum() == 0  # No omissions in go trials
        assert nuisance_masks['commission'].iloc[3]  # Wrong response in go trial
        assert nuisance_masks['rt_too_fast'].iloc[1]  # Fast RT in go trial
