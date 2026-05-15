"""Tests for scripts/triage_surface_quality.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def test_triage_module_imports():
    """The script's main function can be imported."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, 'find_high_hole_subjects')
    assert hasattr(mod, 'main')
