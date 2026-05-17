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
    """Returns rows where fs_holes_mean > threshold."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s03', 'fs_holes_mean': 162.0, 'fs_euler_mean': -322.0},
        {'subject': 'sub-s10', 'fs_holes_mean': 4.5, 'fs_euler_mean': -7.0},
        {'subject': 'sub-s19', 'fs_holes_mean': 8.5, 'fs_euler_mean': -15.0},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    result = mod.find_high_hole_subjects(tsv, threshold=100)
    assert list(result['subject']) == ['sub-s03']
    assert result.iloc[0]['fs_holes_mean'] == 162.0


def test_find_high_hole_subjects_empty_when_none_exceed(tmp_path):
    """Returns empty DataFrame when no subjects exceed threshold."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s10', 'fs_holes_mean': 4.5},
        {'subject': 'sub-s19', 'fs_holes_mean': 8.5},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    result = mod.find_high_hole_subjects(tsv, threshold=100)
    assert len(result) == 0


def test_main_writes_markdown_to_stdout(tmp_path, capsys):
    """main() prints a markdown table of flagged subjects."""
    import sys
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s03', 'fs_holes_mean': 162.0, 'fs_euler_mean': -322.0},
        {'subject': 'sub-s10', 'fs_holes_mean': 4.5, 'fs_euler_mean': -7.0},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    sys.argv = ['triage_surface_quality', '--cohort-tsv', str(tsv), '--threshold', '100']
    rc = mod.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert 'sub-s03' in out
    assert 'sub-s10' not in out
    assert '| subject' in out
