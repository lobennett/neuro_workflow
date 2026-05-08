"""Tests for src/neuro_workflow/analysis/lev1/processing/fixed_effects.py."""
from __future__ import annotations


def test_fixed_effects_analyzer_importable():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert a.subject_id == 'sub-x'
    assert a.task_name == 'flanker'


def test_min_runs_constructor_param_defaults_to_2():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert a.min_runs == 2


def test_min_runs_constructor_param_is_settable():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker', min_runs=3)
    assert a.min_runs == 3
