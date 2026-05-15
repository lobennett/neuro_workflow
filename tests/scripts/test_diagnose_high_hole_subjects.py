"""Tests for scripts/diagnose_high_hole_subjects.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    import sys
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'diagnose_high_hole_subjects.py'
    spec = importlib.util.spec_from_file_location('diagnose', script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['diagnose'] = mod  # Register before exec_module to fix dataclass
    spec.loader.exec_module(mod)
    return mod


def test_module_imports():
    mod = _load_module()
    assert hasattr(mod, 'diagnose_subject')
    assert hasattr(mod, 'main')
