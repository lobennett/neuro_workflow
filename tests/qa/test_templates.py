"""Tests for src/neuro_workflow/qa/templates rendering."""
from neuro_workflow.qa.templates import render_cohort_html, render_subject_html
from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics
from neuro_workflow.qa.metrics.motion import MotionMetrics
import pandas as pd


def _fs_ok(euler=-100.0):
    return FreeSurferMetrics(
        status="OK", elapsed_hours=10.0,
        euler_lh=int(euler), euler_rh=int(euler), euler_mean=euler,
        holes_lh=51, holes_rh=51, holes_mean=51.0,
        brain_vol=1100000.0, gm_vol=600000.0, wm_vol=500000.0,
        csf_vol=1500.0, etiv=1500000.0,
    )


def test_render_cohort_html_contains_subjects():
    rows = [
        {
            "subject": "sub-s03",
            "sessions": 12,
            "scans": 57,
            "fs_euler_mean": -100.0,
            "fs_holes_mean": 51.0,
            "fs_status": "OK",
            "scans_flagged_motion": 0,
            "scans_flagged_outputs": 0,
            "scan_flags_total": 0,
            "decision_action": "unset",
            "decision_reason": "",
            "outlier": False,
        },
    ]
    html = render_cohort_html(
        rows=rows, n_subjects=1, n_scans=57, n_flagged_scans=0,
        fmriprep_version="25.2.4",
    )
    assert "sub-s03" in html
    assert "DataTable" in html  # the JS library or its initialization
    assert "datatables.min.js" in html or "<script" in html


def test_render_cohort_html_marks_excluded():
    rows = [
        {"subject": "sub-bad", "sessions": 12, "scans": 50,
         "fs_euler_mean": -100.0, "fs_holes_mean": 51.0, "fs_status": "OK",
         "scans_flagged_motion": 0, "scans_flagged_outputs": 0,
         "scan_flags_total": 0, "decision_action": "exclude",
         "decision_reason": "manual exclusion", "outlier": False},
    ]
    html = render_cohort_html(rows=rows, n_subjects=1, n_scans=50,
                              n_flagged_scans=0, fmriprep_version="25.2.4")
    assert "excluded" in html.lower()
