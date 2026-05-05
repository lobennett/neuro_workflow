"""Tests for src/neuro_workflow/qa/metrics/freesurfer.py."""
import pytest

from neuro_workflow.qa.metrics.freesurfer import (
    FreeSurferMetrics,
    compute_freesurfer,
    parse_euler_from_log,
    parse_recon_all_status,
    parse_aseg_stats,
)


def _make_fs_dir(tmp_path, status="OK", euler_lh=-100, euler_rh=-80,
                 elapsed_hours=10.0, brain_vol=1100000.0):
    """Build a minimal FreeSurfer subject directory."""
    fs = tmp_path / "sub-X_ses-01"
    (fs / "scripts").mkdir(parents=True)
    (fs / "stats").mkdir(parents=True)
    (fs / "mri").mkdir(parents=True)
    (fs / "surf").mkdir(parents=True)

    # recon-all-status.log
    if status == "OK":
        (fs / "scripts" / "recon-all-status.log").write_text(
            "Started\n"
            f"recon-all -s sub-X_ses-01 finished without error at Wed Apr 29 19:05:44 PDT 2026\n"
        )
    elif status == "FAILED":
        (fs / "scripts" / "recon-all-status.log").write_text(
            f"recon-all -s sub-X_ses-01 exited with ERRORS at Wed Apr 29 12:00:00 PDT 2026\n"
        )
    elif status == "INCOMPLETE":
        (fs / "scripts" / "recon-all-status.log").write_text("Started\n#@# Tessellate\n")

    # recon-all.log with Euler info + multi-stage runtime
    (fs / "scripts" / "recon-all.log").write_text(
        f"#@# Topology lh\n"
        f"orig.nofix lheno = {euler_lh}, rheno = {euler_rh}\n"
        f"#@# DONE\n"
        f"#@#%# recon-all-run-time-hours {elapsed_hours / 2.0}\n"   # stage 1
        f"#@#%# recon-all-run-time-hours {elapsed_hours / 2.0}\n"   # stage 2
    )

    # aseg.stats
    (fs / "stats" / "aseg.stats").write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, "
        f"{brain_vol}, mm^3\n"
        "# Measure TotalGray, TotalGrayVol, Total gray matter volume, 600000.0, mm^3\n"
        "# Measure CerebralWhiteMatter, CerebralWhiteMatterVol, Cerebral White Matter Volume, 500000.0, mm^3\n"
        "# Measure VentricleChoroidVol, VentricleChoroidVol, Volume of ventricles and choroid plexus, 12000.0, mm^3\n"
        "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n"
    )
    return fs


def test_parse_euler_from_log(tmp_path):
    log = tmp_path / "recon-all.log"
    log.write_text(
        "blah\n"
        "orig.nofix lheno = -366, rheno = -278\n"
        "more blah\n"
    )
    result = parse_euler_from_log(log)
    assert result == (-366, -278)


def test_parse_euler_from_log_missing_returns_none(tmp_path):
    log = tmp_path / "recon-all.log"
    log.write_text("no euler info here\n")
    assert parse_euler_from_log(log) is None


def test_parse_recon_all_status_ok(tmp_path):
    f = tmp_path / "recon-all-status.log"
    f.write_text("recon-all -s X finished without error at ...\n")
    assert parse_recon_all_status(f) == "OK"


def test_parse_recon_all_status_failed(tmp_path):
    f = tmp_path / "recon-all-status.log"
    f.write_text("recon-all -s X exited with ERRORS at ...\n")
    assert parse_recon_all_status(f) == "FAILED"


def test_parse_recon_all_status_incomplete(tmp_path):
    f = tmp_path / "recon-all-status.log"
    f.write_text("Started\n#@# Tessellate\n")
    assert parse_recon_all_status(f) == "INCOMPLETE"


def test_parse_aseg_stats(tmp_path):
    f = tmp_path / "aseg.stats"
    f.write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1100000.5, mm^3\n"
        "# Measure TotalGray, TotalGrayVol, Total gray matter volume, 600000.0, mm^3\n"
        "# Measure CerebralWhiteMatter, CerebralWhiteMatterVol, Cerebral White Matter Volume, 500000.0, mm^3\n"
        "# Measure VentricleChoroidVol, VentricleChoroidVol, Volume of ventricles and choroid plexus, 12000.0, mm^3\n"
        "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n"
    )
    vols = parse_aseg_stats(f)
    assert vols["brain_vol"] == pytest.approx(1100000.5)
    assert vols["gm_vol"] == pytest.approx(600000.0)
    assert vols["wm_vol"] == pytest.approx(500000.0)
    assert vols["csf_vol"] == pytest.approx(12000.0)
    assert vols["etiv"] == pytest.approx(1500000.0)


def test_compute_freesurfer_full(tmp_path):
    fs = _make_fs_dir(tmp_path)
    m = compute_freesurfer(fs)
    assert isinstance(m, FreeSurferMetrics)
    assert m.status == "OK"
    assert m.elapsed_hours == pytest.approx(10.0)
    assert m.euler_lh == -100
    assert m.euler_rh == -80
    assert m.euler_mean == pytest.approx(-90.0)
    assert m.holes_lh == 51   # (2 - (-100)) / 2 = 51
    assert m.holes_rh == 41
    assert m.holes_mean == pytest.approx(46.0)
    assert m.brain_vol == pytest.approx(1100000.0)


def test_compute_freesurfer_missing_dir(tmp_path):
    m = compute_freesurfer(tmp_path / "nonexistent")
    assert m.status == "MISSING"
    assert m.euler_mean is None
    assert m.brain_vol is None


def test_compute_freesurfer_failed_recon(tmp_path):
    fs = _make_fs_dir(tmp_path, status="FAILED")
    m = compute_freesurfer(fs)
    assert m.status == "FAILED"


def test_compute_freesurfer_incomplete_recon(tmp_path):
    fs = _make_fs_dir(tmp_path, status="INCOMPLETE")
    m = compute_freesurfer(fs)
    assert m.status == "INCOMPLETE"


def test_parse_elapsed_sums_multiple_stages(tmp_path):
    """recon-all-run-time-hours can appear once per stage; total = sum."""
    from neuro_workflow.qa.metrics.freesurfer import _parse_elapsed
    log = tmp_path / "recon-all.log"
    log.write_text(
        "#@#%# recon-all-run-time-hours 0.149\n"
        "#@#%# recon-all-run-time-hours 0.027\n"
        "#@#%# recon-all-run-time-hours 1.518\n"
        "#@#%# recon-all-run-time-hours 1.344\n"
        "#@#%# recon-all-run-time-hours 0.130\n"
    )
    total = _parse_elapsed(log)
    assert total == pytest.approx(0.149 + 0.027 + 1.518 + 1.344 + 0.130)
