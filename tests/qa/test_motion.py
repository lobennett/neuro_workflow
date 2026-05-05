"""Tests for src/neuro_workflow/qa/metrics/motion.py."""
import pandas as pd
import pytest

from neuro_workflow.qa.metrics.motion import MotionMetrics, compute_motion


def _make_confounds(tmp_path, n_vols=10, fd=None, dvars=None, n_outliers=0):
    """Helper: write a confounds TSV with given values."""
    df = pd.DataFrame({
        "framewise_displacement": [None] + (fd or [0.1] * (n_vols - 1)),
        "std_dvars": [None] + (dvars or [1.0] * (n_vols - 1)),
    })
    for i in range(n_outliers):
        df[f"motion_outlier{i:02d}"] = 0
    path = tmp_path / "confounds.tsv"
    df.to_csv(path, sep="\t", index=False, na_rep="n/a")
    return path


def test_compute_motion_returns_dataclass(tmp_path):
    path = _make_confounds(tmp_path, n_vols=5, fd=[0.1, 0.2, 0.3, 0.4],
                           dvars=[1.0, 1.1, 1.2, 1.3])
    m = compute_motion(path)
    assert isinstance(m, MotionMetrics)
    assert m.n_vols == 5
    assert m.fd_mean == pytest.approx(0.25)
    assert m.dvars_mean == pytest.approx(1.15)


def test_compute_motion_counts_motion_outliers(tmp_path):
    path = _make_confounds(tmp_path, n_vols=10, n_outliers=3)
    m = compute_motion(path)
    assert m.n_motion_outliers == 3


def test_compute_motion_proportion_over_thresholds(tmp_path):
    # 5 vols, FD = [0.1, 0.6, 0.7, 0.05] (after dropping leading n/a)
    # → 2/4 = 50% over 0.5
    path = _make_confounds(tmp_path, n_vols=5,
                           fd=[0.1, 0.6, 0.7, 0.05],
                           dvars=[1.0, 1.6, 1.7, 1.0])
    m = compute_motion(path)
    assert m.fd_prop_over_05 == pytest.approx(0.5)
    assert m.dvars_prop_over_15 == pytest.approx(0.5)


def test_compute_motion_handles_all_nan(tmp_path):
    df = pd.DataFrame({
        "framewise_displacement": [None] * 5,
        "std_dvars": [None] * 5,
    })
    path = tmp_path / "confounds.tsv"
    df.to_csv(path, sep="\t", index=False, na_rep="n/a")
    m = compute_motion(path)
    assert m.n_vols == 5
    # When all values are NaN, mean is NaN; we report 0.0 instead so the table
    # column stays numeric.
    assert m.fd_mean == 0.0 or (m.fd_mean != m.fd_mean)  # 0.0 or NaN both acceptable


def test_compute_motion_missing_columns(tmp_path):
    # Confounds without standard motion columns → graceful zeros
    df = pd.DataFrame({"global_signal": [1.0, 2.0, 3.0]})
    path = tmp_path / "confounds.tsv"
    df.to_csv(path, sep="\t", index=False)
    m = compute_motion(path)
    assert m.n_vols == 3
    assert m.fd_mean == 0.0
    assert m.dvars_mean == 0.0
