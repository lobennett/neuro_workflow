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


def test_diagnose_subject_classifies_skull_strip(tmp_path):
    """recon-all.log with 'Topology fixer' + brainmask issues -> skull_strip."""
    mod = _load_module()
    sd = tmp_path / 'fs'
    fs_subj = 'sub-s03_ses-05'
    scripts = sd / fs_subj / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'recon-all.log').write_text(
        'mri_watershed: brainmask too aggressive\n'
        'WARNING: skull-stripping may have removed brain tissue\n'
        'Topology fixer found 324 defects\n'
        'recon-all -all finished without error\n'
    )
    (scripts / 'recon-all-status.log').write_text(
        'recon-all -s sub-s03_ses-05 finished without error at Sun Apr  5 12:34:56 PDT 2026\n'
    )

    result = mod.diagnose_subject(sd, fs_subj, pre_fix_holes_mean=162.0)
    assert result.subject == 'sub-s03'
    assert result.cause == 'skull_strip'
    assert '324 defects' in result.evidence


def test_diagnose_subject_classifies_unknown_when_no_log(tmp_path):
    """Missing recon-all.log -> cause='log_missing'."""
    mod = _load_module()
    sd = tmp_path / 'fs'
    (sd / 'sub-sXX_ses-01').mkdir(parents=True)

    result = mod.diagnose_subject(sd, 'sub-sXX_ses-01', pre_fix_holes_mean=150.0)
    assert result.cause == 'log_missing'
