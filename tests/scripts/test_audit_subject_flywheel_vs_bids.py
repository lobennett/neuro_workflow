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
