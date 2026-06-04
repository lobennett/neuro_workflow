"""Characterization tests for mshbm.preproc primitives.

These pin the CURRENT behavior of the denoise/motion primitives so the module
(notably the Du-2025 nuisance path) can be refactored or re-tuned safely. The
test file was absent from the tree despite the PREP task list; restored here.
"""
import numpy as np
import pandas as pd
import pytest

from neuro_workflow.analysis.mshbm.preproc import (
    bandpass_filter,
    build_motion_mask,
    build_regressor_matrix,
    build_regressor_matrix_du2025,
    interpolate_bad_frames,
    regress_confounds,
    write_censor_tsv,
)


class TestRegressConfounds:
    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            regress_confounds(np.zeros((3, 10)), np.zeros((9, 2)))  # T mismatch

    def test_removes_intercept_and_linear_trend(self):
        T = 50
        Y = np.vstack([np.full(T, 5.0), np.linspace(-3, 7, T)])  # const + ramp
        resid = regress_confounds(Y, np.zeros((T, 0)))  # no nuisance; detrend only
        assert np.allclose(resid, 0.0, atol=1e-6)

    def test_removes_a_confound_regressor(self):
        rng = np.random.default_rng(0)
        T = 100
        x = rng.standard_normal(T)
        Y = np.vstack([3.0 * x + 2.0, -1.5 * x])  # both linear in the confound
        resid = regress_confounds(Y, x[:, None])
        assert np.allclose(resid, 0.0, atol=1e-6)

    def test_nan_rows_in_confounds_are_zeroed_not_crash(self):
        T = 40
        Y = np.random.default_rng(1).standard_normal((5, T))
        X = np.ones((T, 1))
        X[0, 0] = np.nan  # fmriprep emits NaN in first derivative row
        out = regress_confounds(Y, X)
        assert out.shape == (5, T) and np.isfinite(out).all()


class TestBuildMotionMask:
    def test_thresholds_and_nan(self):
        fd = np.array([0.1, 0.5, 0.2, np.nan])
        dvars = np.array([1.0, 1.0, 3.0, 1.0])
        mask = build_motion_mask(fd, dvars, fd_thresh=0.4, dvars_thresh=2.0)
        assert mask.tolist() == [1, 0, 0, 0]  # keep, FD-drop, DVARS-drop, NaN-drop
        assert mask.dtype == np.int8


class TestInterpolateBadFrames:
    def test_interpolates_interior_bad_frame(self):
        Y = np.array([[0.0, 99.0, 20.0, 30.0, 40.0]])
        mask = np.array([1, 0, 1, 1, 1], dtype=np.int8)
        out = interpolate_bad_frames(Y, mask)
        assert out[0, 1] == pytest.approx(10.0)  # between 0 and 20

    def test_edge_bad_frame_clamps(self):
        Y = np.array([[99.0, 10.0, 20.0]])
        mask = np.array([0, 1, 1], dtype=np.int8)
        out = interpolate_bad_frames(Y, mask)
        assert out[0, 0] == pytest.approx(10.0)  # clamped to nearest good

    def test_all_bad_returns_copy_unchanged(self):
        Y = np.array([[1.0, 2.0, 3.0]])
        out = interpolate_bad_frames(Y, np.zeros(3, dtype=np.int8))
        assert np.array_equal(out, Y) and out is not Y


class TestBandpassFilter:
    def test_invalid_band_raises(self):
        with pytest.raises(ValueError):
            bandpass_filter(np.zeros((2, 100)), tr=2.0, lowcut=0.1, highcut=0.01)

    def test_removes_dc_offset(self):
        Y = np.ones((1, 200)) * 7.0  # pure DC, below the low cutoff
        out = bandpass_filter(Y, tr=2.0, lowcut=0.01, highcut=0.1)
        assert out.shape == (1, 200)
        assert abs(out[0, 50:150].mean()) < 0.1  # DC strongly attenuated


class TestBuildRegressorMatrix:
    def _confounds(self, T=30, du=False):
        base = ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"]
        cols = list(base)
        if du:
            cols += ["global_signal", "csf", "white_matter"]
            cols += [c + "_derivative1" for c in cols]
        else:
            cols += [c + "_derivative1" for c in base]
            cols += [c + "_power2" for c in base]
            cols += [c + "_derivative1_power2" for c in base]
            cols += ["white_matter", "csf"] + [f"a_comp_cor_0{i}" for i in range(5)]
        df = pd.DataFrame(np.random.default_rng(2).standard_normal((T, len(cols))), columns=cols)
        df.iloc[0] = np.nan  # first-row NaN like fmriprep derivatives
        return df

    def test_31p_shape_and_nan_zeroed(self):
        X = build_regressor_matrix(self._confounds())
        assert X.shape == (30, 31)
        assert np.isfinite(X).all() and (X[0] == 0).all()

    def test_du2025_18p_shape_and_columns(self):
        X = build_regressor_matrix_du2025(self._confounds(du=True))
        assert X.shape == (30, 18)
        assert np.isfinite(X).all() and (X[0] == 0).all()

    def test_missing_columns_raise(self):
        with pytest.raises(KeyError):
            build_regressor_matrix(pd.DataFrame({"trans_x": [0.0, 1.0]}))
        with pytest.raises(KeyError):
            build_regressor_matrix_du2025(pd.DataFrame({"trans_x": [0.0, 1.0]}))


class TestWriteCensorTsv:
    def test_writes_single_column_01(self, tmp_path):
        out = tmp_path / "sub" / "censor.tsv"
        write_censor_tsv(np.array([1, 0, 1, 1], dtype=np.int8), out)
        assert out.read_text() == "1\n0\n1\n1\n"
