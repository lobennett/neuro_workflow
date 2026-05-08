"""Tests for src/neuro_workflow/analysis/lev1/processing/fixed_effects.py."""
from __future__ import annotations


def test_fixed_effects_analyzer_importable():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert a.subject_id == 'sub-x'
    assert a.task_name == 'flanker'
