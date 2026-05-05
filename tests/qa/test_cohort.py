"""Tests for src/neuro_workflow/qa/cohort.py."""
from neuro_workflow.qa.cohort import cohort_euler_outliers
from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics


def _fs(euler_mean):
    """Build a minimal FreeSurferMetrics with euler_mean only."""
    return FreeSurferMetrics(
        status="OK", elapsed_hours=None,
        euler_lh=None, euler_rh=None, euler_mean=euler_mean,
        holes_lh=None, holes_rh=None, holes_mean=None,
        brain_vol=None, gm_vol=None, wm_vol=None, csf_vol=None, etiv=None,
    )


def test_cohort_euler_outliers_flags_extreme_low():
    # Mostly around -100, one outlier at -1000
    metrics = {f"sub-{i:02d}": _fs(-100.0 + i) for i in range(20)}
    metrics["sub-bad"] = _fs(-1000.0)
    flagged = cohort_euler_outliers(metrics, n_sigma=2.0)
    assert "sub-bad" in flagged
    assert "sub-00" not in flagged


def test_cohort_euler_outliers_no_outliers():
    metrics = {f"sub-{i:02d}": _fs(-100.0 + i) for i in range(20)}
    flagged = cohort_euler_outliers(metrics, n_sigma=2.0)
    assert flagged == set()


def test_cohort_euler_outliers_skips_missing_euler():
    metrics = {
        "sub-A": _fs(-100.0),
        "sub-B": _fs(-105.0),
        "sub-C": _fs(None),         # missing — excluded from cohort
        "sub-bad": _fs(-1000.0),
    }
    flagged = cohort_euler_outliers(metrics, n_sigma=2.0)
    assert "sub-bad" in flagged
    assert "sub-C" not in flagged


def test_cohort_euler_outliers_high_threshold():
    # n_sigma=10 should flag nothing for a normal-ish distribution
    metrics = {f"sub-{i:02d}": _fs(-100.0 + i * 5) for i in range(20)}
    flagged = cohort_euler_outliers(metrics, n_sigma=10.0)
    assert flagged == set()
