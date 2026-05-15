"""Tests for scripts/render_surface_fix_status.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'render_surface_fix_status.py'
    spec = importlib.util.spec_from_file_location('render_status', script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['render_status'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_render_status_keep_vs_exclude(tmp_path):
    """Subjects fixed below threshold -> KEEP; still above -> EXCLUDE."""
    mod = _load_module()

    pre = pd.DataFrame([
        {'subject': 'sub-s03', 'fs_holes_mean': 162.0},
        {'subject': 'sub-sXX', 'fs_holes_mean': 207.5},
    ])
    post = pd.DataFrame([
        {'subject': 'sub-s03', 'fs_holes_mean': 10.0},
        {'subject': 'sub-sXX', 'fs_holes_mean': 184.0},
    ])
    pre_tsv = tmp_path / 'pre.tsv'; pre.to_csv(pre_tsv, sep='\t', index=False)
    post_tsv = tmp_path / 'post.tsv'; post.to_csv(post_tsv, sep='\t', index=False)

    md = mod.render_status(pre_tsv, post_tsv, threshold=100)
    assert 'sub-s03' in md
    assert 'KEEP' in md
    assert 'sub-sXX' in md
    assert 'EXCLUDE' in md


def test_render_status_handles_only_subjects_in_post(tmp_path):
    """Subjects in post.tsv but not in pre.tsv are skipped."""
    mod = _load_module()
    pre = pd.DataFrame([{'subject': 'sub-s03', 'fs_holes_mean': 162.0}])
    post = pd.DataFrame([
        {'subject': 'sub-s03', 'fs_holes_mean': 10.0},
        {'subject': 'sub-other', 'fs_holes_mean': 4.0},
    ])
    pre_tsv = tmp_path / 'pre.tsv'; pre.to_csv(pre_tsv, sep='\t', index=False)
    post_tsv = tmp_path / 'post.tsv'; post.to_csv(post_tsv, sep='\t', index=False)

    md = mod.render_status(pre_tsv, post_tsv, threshold=100)
    assert 'sub-s03' in md
    assert 'sub-other' not in md
