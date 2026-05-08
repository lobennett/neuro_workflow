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


def test_build_base_filename_no_tag_at_floor():
    """n_runs == min_runs (=2 default) -> no _desc-belowMinRuns substring."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-s03', 'flanker', min_runs=2)
    a.contrast_results['incongruent-congruent'] = {
        'n_runs': 2, 'fixed_effect': None, 'fixed_variance': None,
        'fixed_stat': None, 'input_files': {'effects': [], 'variances': []},
    }
    fname = a._build_base_filename('incongruent-congruent')
    assert '_desc-belowMinRuns' not in fname
    assert 'sub-s03' in fname
    assert 'task-flanker' in fname
    assert 'contrast-incongruent-congruent' in fname
    assert '_rtmodel-RTDur' in fname
    assert '_stat-fixed-effects' in fname


def test_build_base_filename_tags_below_floor():
    """n_runs < min_runs -> filename includes _desc-belowMinRuns_."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-s10', 'flanker', min_runs=2)
    a.contrast_results['response_time'] = {
        'n_runs': 1, 'fixed_effect': None, 'fixed_variance': None,
        'fixed_stat': None, 'input_files': {'effects': [], 'variances': []},
    }
    fname = a._build_base_filename('response_time')
    assert '_desc-belowMinRuns_' in fname


def test_build_base_filename_min_runs_is_configurable():
    """min_runs=3 with n_runs=2 -> tagged."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-s19', 'cuedTS', min_runs=3)
    a.contrast_results['cue_switch_cost'] = {
        'n_runs': 2, 'fixed_effect': None, 'fixed_variance': None,
        'fixed_stat': None, 'input_files': {'effects': [], 'variances': []},
    }
    assert '_desc-belowMinRuns_' in a._build_base_filename('cue_switch_cost')
