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


def test_find_high_hole_subjects_filters_by_threshold(tmp_path):
    """Returns rows where (lh_holes + rh_holes) / 2 > threshold."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s03', 'lh_holes': 184, 'rh_holes': 140},
        {'subject': 'sub-s10', 'lh_holes': 2, 'rh_holes': 7},
        {'subject': 'sub-s19', 'lh_holes': 13, 'rh_holes': 4},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    result = mod.find_high_hole_subjects(tsv, threshold=100)
    assert list(result['subject']) == ['sub-s03']
    assert result.iloc[0]['mean_holes'] == 162.0


def test_find_high_hole_subjects_empty_when_none_exceed(tmp_path):
    """Returns empty DataFrame when no subjects exceed threshold."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s10', 'lh_holes': 2, 'rh_holes': 7},
        {'subject': 'sub-s19', 'lh_holes': 13, 'rh_holes': 4},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    result = mod.find_high_hole_subjects(tsv, threshold=100)
    assert len(result) == 0
