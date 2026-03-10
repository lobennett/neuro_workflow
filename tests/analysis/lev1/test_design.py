"""Tests for the design matrix creation module."""

import numpy as np
import pandas as pd
import pytest

from neuro_workflow.analysis.lev1.processing.design import create_design_matrix, create_regressor


class TestCreateRegressor:
    """Tests for create_regressor function."""

    @pytest.fixture
    def simple_events(self):
        """Simple events DataFrame for testing."""
        return pd.DataFrame(
            {
                'onset': [10.0, 20.0, 30.0],
                'duration': [1.0, 1.0, 1.0],
                'trial_type': ['go', 'go', 'go'],
                'response_time': [0.5, 0.6, 0.7],
            }
        )

    def test_constant_amplitude_and_duration(self, simple_events):
        """Test regressor with constant amplitude and duration."""
        config = {
            'amplitude_column': 'constant_1_column',
            'duration_column': 'constant_1_column',
            'subset': "trial_type == 'go'",
        }
        reg_df, reg_3col = create_regressor(simple_events, config, 50, 'go')

        assert 'go' in reg_df.columns
        assert len(reg_df) == 50
        # HRF convolution should produce non-zero values
        assert reg_df['go'].abs().sum() > 0

        # 3-column format should have 3 events
        onsets, durations, amplitudes = reg_3col
        assert len(onsets) == 3
        assert all(d == 1.0 for d in durations)
        assert all(a == 1.0 for a in amplitudes)

    def test_column_duration(self, simple_events):
        """Test regressor using column for duration (RT-as-duration)."""
        config = {
            'amplitude_column': 'constant_1_column',
            'duration_column': 'response_time',
            'subset': "trial_type == 'go'",
        }
        reg_df, reg_3col = create_regressor(simple_events, config, 50, 'rt_reg')

        assert len(reg_df) == 50
        _, durations, _ = reg_3col
        assert durations == [0.5, 0.6, 0.7]

    def test_column_amplitude(self):
        """Test regressor using a column for amplitude."""
        events = pd.DataFrame(
            {
                'onset': [10.0, 20.0, 30.0],
                'weight': [0.5, 1.0, 0.0],
                'trial_type': ['go', 'go', 'go'],
            }
        )
        config = {
            'amplitude_column': 'weight',
            'duration_column': 'constant_1_column',
            'subset': "trial_type == 'go'",
        }
        reg_df, reg_3col = create_regressor(events, config, 50, 'weighted')

        _, _, amplitudes = reg_3col
        assert amplitudes == [0.5, 1.0, 0.0]

    def test_empty_subset_returns_zero_regressor(self, simple_events):
        """Test that an empty subset produces a zero regressor."""
        config = {
            'amplitude_column': 'constant_1_column',
            'duration_column': 'constant_1_column',
            'subset': "trial_type == 'nonexistent'",
        }
        reg_df, reg_3col = create_regressor(simple_events, config, 50, 'empty')

        assert len(reg_df) == 50
        assert reg_df['empty'].abs().sum() == 0.0
        assert reg_3col == ([], [], [])

    def test_null_subset_uses_all_rows(self, simple_events):
        """Test that a null/empty subset uses all rows."""
        config = {
            'amplitude_column': 'constant_1_column',
            'duration_column': 'constant_1_column',
            'subset': '',
        }
        reg_df, reg_3col = create_regressor(simple_events, config, 50, 'all')

        onsets, _, _ = reg_3col
        assert len(onsets) == 3

    def test_invalid_column_raises(self, simple_events):
        """Test that referencing a nonexistent column raises ValueError."""
        config = {
            'amplitude_column': 'nonexistent_column',
            'duration_column': 'constant_1_column',
            'subset': "trial_type == 'go'",
        }
        with pytest.raises(ValueError, match='Failed to create regressor'):
            create_regressor(simple_events, config, 50, 'bad')


class TestCreateDesignMatrix:
    """Tests for create_design_matrix and intercept detection."""

    @pytest.fixture
    def flanker_events(self):
        """Events matching flanker task regressors."""
        return pd.DataFrame(
            {
                'onset': [10.0, 15.0, 20.0, 25.0, 30.0, 35.0],
                'duration': [1.0] * 6,
                'trial_type': [
                    'congruent',
                    'incongruent',
                    'congruent',
                    'incongruent',
                    'congruent',
                    'incongruent',
                ],
                'trial_id': ['test_trial'] * 6,
                'key_press': [1, 2, 1, 2, 1, 2],
                'correct_response': [1, 2, 1, 2, 1, 2],
                'response_time': [0.5, 0.6, 0.5, 0.6, 0.5, 0.6],
                'omission': [0, 0, 0, 0, 0, 0],
                'commission': [0, 0, 0, 0, 0, 0],
                'rt_too_fast': [0, 0, 0, 0, 0, 0],
            }
        )

    def test_intercept_added_when_missing(self, flanker_events):
        """Test that a constant column is added when confounds lack one."""
        n_scans = 50
        confounds = pd.DataFrame(
            {
                'trans_x': np.random.randn(n_scans),
                'trans_y': np.random.randn(n_scans),
            }
        )

        dm, _ = create_design_matrix(flanker_events, confounds, 'flanker', n_scans)

        # Should have added a 'constant' column
        assert 'constant' in dm.columns
        assert (dm['constant'] == 1.0).all()

    def test_intercept_not_added_when_present(self, flanker_events):
        """Test that no constant is added when confounds already have one."""
        n_scans = 50
        confounds = pd.DataFrame(
            {
                'trans_x': np.random.randn(n_scans),
                'cosine00': np.ones(n_scans),  # Constant column from fMRIPrep
            }
        )

        dm, _ = create_design_matrix(flanker_events, confounds, 'flanker', n_scans)

        # Should NOT add a redundant 'constant' column
        assert 'constant' not in dm.columns
        # cosine00 should still be present
        assert 'cosine00' in dm.columns

    def test_design_matrix_includes_task_regressors(self, flanker_events):
        """Test that design matrix includes task regressors from YAML config."""
        n_scans = 50
        confounds = pd.DataFrame(
            {
                'cosine00': np.ones(n_scans),
                'trans_x': np.random.randn(n_scans),
            }
        )

        dm, reg_3cols = create_design_matrix(
            flanker_events, confounds, 'flanker', n_scans
        )

        # Flanker should have these regressors
        expected_regressors = [
            'congruent',
            'incongruent',
            'response_time',
            'omission',
            'commission',
            'rt_fast',
            'break_with_performance_feedback',
        ]
        for reg_name in expected_regressors:
            assert reg_name in dm.columns, f'Missing regressor: {reg_name}'

        # Confounds should also be in the design matrix
        assert 'cosine00' in dm.columns
        assert 'trans_x' in dm.columns

    def test_design_matrix_row_count(self, flanker_events):
        """Test that design matrix has correct number of rows."""
        n_scans = 50
        confounds = pd.DataFrame(
            {
                'cosine00': np.ones(n_scans),
            }
        )

        dm, _ = create_design_matrix(flanker_events, confounds, 'flanker', n_scans)
        assert len(dm) == n_scans

    def test_regressor_3col_format(self, flanker_events):
        """Test that regressor 3-column tuples are returned."""
        n_scans = 50
        confounds = pd.DataFrame({'cosine00': np.ones(n_scans)})

        _, reg_3cols = create_design_matrix(
            flanker_events, confounds, 'flanker', n_scans
        )

        # Should have one entry per regressor
        assert len(reg_3cols) > 0
        for reg_3col, name in reg_3cols:
            assert isinstance(name, str)
            assert isinstance(reg_3col, tuple)
            assert len(reg_3col) == 3  # onsets, durations, amplitudes

    def test_zero_column_not_treated_as_intercept(self, flanker_events):
        """Test that a column of zeros is not treated as a constant."""
        n_scans = 50
        confounds = pd.DataFrame(
            {
                'zero_col': np.zeros(n_scans),  # All zeros, NOT a valid intercept
                'trans_x': np.random.randn(n_scans),
            }
        )

        dm, _ = create_design_matrix(flanker_events, confounds, 'flanker', n_scans)

        # A column of zeros is not a valid intercept, so 'constant' should be added
        assert 'constant' in dm.columns
