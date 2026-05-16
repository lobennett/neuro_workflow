"""Tests for scripts/audit_subject_flywheel_vs_bids.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    import sys
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_subject_flywheel_vs_bids.py'
    spec = importlib.util.spec_from_file_location('audit', script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['audit'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_audit_module_imports():
    mod = _load_module()
    assert hasattr(mod, 'audit_subject')
    assert hasattr(mod, 'render_audit_md')
    assert hasattr(mod, 'main')


def test_audit_marks_excluded_per_config(tmp_path):
    """A FW session with exclude:true in overrides shows as EXCLUDED."""
    mod = _load_module()
    bids = tmp_path / 'bids'
    (bids / 'sub-s03' / 'ses-01' / 'anat').mkdir(parents=True)
    fw_sessions = [
        {'fw_session_label': '20210101', 'timestamp': '2021-01-01T10:00:00',
         'acquisitions': [{'label': 'T1w_MPRAGE'}, {'label': 'BOLD_rest'}]},
        {'fw_session_label': '25210', 'timestamp': '2022-05-24T17:10:00',
         'acquisitions': [{'label': 'T1w_SagMPRAGE'}]},
    ]
    overrides = {'25210': {'exclude': True, 'reason': 'test'}}

    rows = mod.audit_subject('s03', bids, fw_sessions, overrides)
    assert len(rows) == 2
    by_label = {r.fw_session_label: r for r in rows}
    assert by_label['25210'].bids_session == 'EXCLUDED'
    assert by_label['25210'].n_t1w == 1


def test_audit_marks_reassigned_per_config(tmp_path):
    """A FW session with reassign_to in overrides shows as REASSIGNED."""
    mod = _load_module()
    bids = tmp_path / 'bids'
    bids.mkdir()
    fw_sessions = [
        {'fw_session_label': '22752', 'timestamp': '2021-02-12T09:00:00',
         'acquisitions': [{'label': 'T1w_MPRAGE'}]},
    ]
    overrides = {'22752': {'reassign_to': 's10', 'reason': 'mislabeled'}}

    rows = mod.audit_subject('s03', bids, fw_sessions, overrides)
    assert rows[0].bids_session == 'REASSIGNED'
    assert 'reassigned to s10' in rows[0].notes.lower()


def test_audit_maps_fw_session_to_bids_chronologically(tmp_path):
    """FW sessions sorted by timestamp map to ses-01, ses-02, ... in BIDS."""
    mod = _load_module()
    bids = tmp_path / 'bids'
    for s in ['ses-01', 'ses-02']:
        (bids / 'sub-s03' / s / 'anat').mkdir(parents=True)
        (bids / 'sub-s03' / s / 'anat' / f'sub-s03_{s}_T1w.nii.gz').touch()
    fw_sessions = [
        {'fw_session_label': 'A', 'timestamp': '2021-01-01T10:00:00',
         'acquisitions': [{'label': 'T1w'}]},
        {'fw_session_label': 'B', 'timestamp': '2021-02-01T10:00:00',
         'acquisitions': [{'label': 'T1w'}]},
    ]
    rows = mod.audit_subject('s03', bids, fw_sessions, {})
    by_label = {r.fw_session_label: r for r in rows}
    assert by_label['A'].bids_session == 'ses-01'
    assert by_label['B'].bids_session == 'ses-02'
