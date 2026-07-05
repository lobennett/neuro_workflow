import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "exclusion_gate", Path(__file__).resolve().parents[2] / "scripts" / "exclusion_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _entry(sub, ses, task, run, action="exclude", source="motion", contrast=None, reason="r"):
    return {
        "subject": sub,
        "session": ses,
        "task": task,
        "run": run,
        "action": action,
        "source": source,
        "contrast": contrast,
        "reason": reason,
    }


def _write(tmp_path, name, entries):
    p = tmp_path / name
    p.write_text(json.dumps(entries))
    return p


def test_identical_sets_no_drift(tmp_path):
    ref = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1")]
    new = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1")]
    r = _write(tmp_path, "ref.json", ref)
    n = _write(tmp_path, "new.json", new)
    result = gate.diff_gate(new_path=n, reference_path=r)
    assert result["added"] == [] and result["dropped"] == []
    assert result["ok"] is True


def test_added_and_dropped_detected(tmp_path):
    ref = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1")]
    new = [_entry("sub-s2", "ses-02", "task-flanker", "run-2")]
    result = gate.diff_gate(
        new_path=_write(tmp_path, "new.json", new), reference_path=_write(tmp_path, "ref.json", ref)
    )
    assert result["ok"] is False
    assert len(result["added"]) == 1 and len(result["dropped"]) == 1


def test_source_filter_scopes_the_diff(tmp_path):
    # ref has a motion + a behavioral entry; new drops the behavioral one.
    ref = [
        _entry("sub-s1", "ses-01", "task-goNogo", "run-1", source="motion"),
        _entry("sub-s9", "ses-09", "task-nBack", "run-1", source="behavioral-qc"),
    ]
    new = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1", source="motion")]
    # Scoped to motion → no drift (motion identical).
    res_motion = gate.diff_gate(
        new_path=_write(tmp_path, "new.json", new),
        reference_path=_write(tmp_path, "ref.json", ref),
        source="motion",
    )
    assert res_motion["ok"] is True
    # Unscoped → the behavioral drop shows.
    res_all = gate.diff_gate(
        new_path=_write(tmp_path, "new2.json", new),
        reference_path=_write(tmp_path, "ref2.json", ref),
    )
    assert res_all["ok"] is False and len(res_all["dropped"]) == 1


def test_exclude_contrast_drift_detected(tmp_path):
    # lev1_outlier exclusions are per-contrast; a change from contrast-DDS to
    # contrast-SSS on the same scan must flag BOTH an add and a drop.
    ref = [
        _entry(
            "sub-s1",
            "ses-01",
            "task-shapeMatching",
            "run-1",
            action="exclude-contrast",
            source="lev1_outlier",
            contrast="DDS",
        )
    ]
    new = [
        _entry(
            "sub-s1",
            "ses-01",
            "task-shapeMatching",
            "run-1",
            action="exclude-contrast",
            source="lev1_outlier",
            contrast="SSS",
        )
    ]
    result = gate.diff_gate(
        new_path=_write(tmp_path, "new.json", new), reference_path=_write(tmp_path, "ref.json", ref)
    )
    assert result["ok"] is False
    assert len(result["added"]) == 1 and len(result["dropped"]) == 1
    assert result["added"][0]["contrast"] == "SSS"
    assert result["dropped"][0]["contrast"] == "DDS"


def test_scan_level_vs_contrast_level_not_confused(tmp_path):
    # A scan-level exclude (contrast None) and a per-contrast exclude on the same
    # scan are distinct — changing action from exclude to exclude-contrast flags both.
    ref = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1", action="exclude", source="motion")]
    new = [
        _entry(
            "sub-s1",
            "ses-01",
            "task-goNogo",
            "run-1",
            action="exclude-contrast",
            source="lev1_outlier",
            contrast="go",
        )
    ]
    result = gate.diff_gate(
        new_path=_write(tmp_path, "new.json", new), reference_path=_write(tmp_path, "ref.json", ref)
    )
    assert result["ok"] is False
    assert len(result["added"]) == 1 and len(result["dropped"]) == 1
