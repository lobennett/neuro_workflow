"""Tests for src/neuro_workflow/analysis/lev1/processing/fixed_effects.py."""
from __future__ import annotations

import logging

import pytest


def test_missing_contrast_warning_lists_contrasts_with_no_files(tmp_path, caplog):
    """``compute_all_task_fixed_effects`` must warn when expected contrasts
    have no per-run files at all.

    Previously these silently vanished from the subject's output — a regressor
    that was zero-variance in every run got its contrast skipped at write
    time, leaving lev2 to discover the absence from a glob. The warning
    surfaces the loss at the per-subject log level so cohort runs don't
    silently emit incomplete output sets.
    """
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )

    analyzer = FixedEffectsAnalyzer('sub-x', 'flanker')
    contrasts = {
        'incongruent-congruent': 'incongruent - congruent',
        'response_time': 'response_time',
        'task-baseline': '0.5 * (congruent + incongruent)',
    }

    # No effect/variance files exist on disk → every contrast is "missing"
    contrast_dir = tmp_path / 'contrasts'
    contrast_dir.mkdir()
    output_dir = tmp_path / 'fixed'
    output_dir.mkdir()

    with caplog.at_level(logging.WARNING,
                          logger='neuro_workflow.analysis.lev1.processing.fixed_effects'):
        result = analyzer.compute_all_task_fixed_effects(
            contrast_dir, output_dir, exclusions=set(), contrasts=contrasts,
        )

    assert result == {}, (
        'No contrast files exist on disk; the result map should be empty.'
    )

    warning_text = '\n'.join(rec.message for rec in caplog.records
                              if rec.levelno == logging.WARNING)
    assert 'sub-x' in warning_text
    assert 'flanker' in warning_text
    # Every contrast name should be enumerated in the warning so the user
    # can see exactly what's missing rather than just a count.
    for name in contrasts.keys():
        assert name in warning_text, (
            f'Warning text should mention missing contrast {name!r}; '
            f'got: {warning_text!r}'
        )


def test_no_warning_when_every_contrast_has_files(tmp_path, caplog, monkeypatch):
    """Inverse of the above — when every contrast has files, no warning."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )

    analyzer = FixedEffectsAnalyzer('sub-x', 'flanker')
    contrasts = {'go': 'go'}

    # Stub find_contrast_files to claim files exist, and stub the compute
    # method to return a dummy result so we never touch real I/O.
    monkeypatch.setattr(
        analyzer, 'find_contrast_files',
        lambda *a, **kw: (['effect.nii.gz'], ['variance.nii.gz']),
    )
    monkeypatch.setattr(
        analyzer, 'compute_fixed_effects_contrast',
        lambda *a, **kw: ('effect', 'variance', 'stat'),
    )
    monkeypatch.setattr(
        analyzer, 'save_fixed_effects_maps',
        lambda *a, **kw: {'effect': tmp_path / 'effect.nii.gz'},
    )

    with caplog.at_level(logging.WARNING,
                          logger='neuro_workflow.analysis.lev1.processing.fixed_effects'):
        result = analyzer.compute_all_task_fixed_effects(
            tmp_path, tmp_path, exclusions=set(), contrasts=contrasts,
        )

    assert 'go' in result
    missing_warning = [r for r in caplog.records
                       if r.levelno == logging.WARNING
                       and 'expected contrasts have no fixed-effects' in r.message]
    assert not missing_warning, (
        'No contrasts are missing; the silent-loss warning must not fire.'
    )


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


def test_compute_subject_fixed_effects_accepts_min_runs(tmp_path):
    """The module-level helper accepts and threads `min_runs` to the analyzer."""
    from neuro_workflow.analysis.lev1.processing import fixed_effects as fe

    captured = {}
    real_init = fe.FixedEffectsAnalyzer.__init__

    def spy_init(self, *args, **kwargs):
        captured['min_runs'] = kwargs.get('min_runs', None)
        # Avoid actually running the analysis: raise after capturing.
        raise RuntimeError('stop after capture')

    fe.FixedEffectsAnalyzer.__init__ = spy_init
    try:
        try:
            fe.compute_subject_fixed_effects(
                'sub-x', 'flanker',
                contrast_dir=tmp_path, output_dir=tmp_path,
                min_runs=4,
            )
        except RuntimeError:
            pass
    finally:
        fe.FixedEffectsAnalyzer.__init__ = real_init

    assert captured['min_runs'] == 4


# ---------------------------------------------------------------------------
# Task 5: --min-runs CLI flag
# Scaffold uses: --subj-id, --task-name, --bids-dir, --fmriprep-dir (required),
# --space MNI (valid choice), --exclusions-file (required).
# get_parser() uses hyphenated long-form names; --space MNI152NLin2009cAsym is
# NOT a valid choice, so MNI is used instead.
# ---------------------------------------------------------------------------

_MINIMAL_ARGS = [
    '--subj-id', 'sub-x',
    '--task-name', 'flanker',
    '--bids-dir', '/tmp',
    '--fmriprep-dir', '/tmp',
    '--space', 'MNI',
    '--exclusions-file', '/tmp/excl.json',
]


def test_lev1_cli_accepts_min_runs_flag():
    """Parsing `--min-runs 3` produces args.min_runs == 3."""
    from neuro_workflow.analysis.lev1.run import get_parser
    parser = get_parser()
    args = parser.parse_args([*_MINIMAL_ARGS, '--min-runs', '3'])
    assert args.min_runs == 3


def test_lev1_cli_min_runs_default_is_2():
    """Omitting --min-runs leaves the default of 2."""
    from neuro_workflow.analysis.lev1.run import get_parser
    parser = get_parser()
    args = parser.parse_args(_MINIMAL_ARGS)
    assert args.min_runs == 2


def test_lev1_cli_min_runs_must_be_positive():
    """`--min-runs 0` aborts via SystemExit."""
    import pytest as _pytest
    from neuro_workflow.analysis.lev1.run import get_parser
    parser = get_parser()
    with _pytest.raises(SystemExit):
        parser.parse_args([*_MINIMAL_ARGS, '--min-runs', '0'])


def test_no_high_exclusion_attribute():
    """Regression: high_exclusion plumbing must stay deleted."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert not hasattr(a, 'high_exclusion'), (
        'FixedEffectsAnalyzer should not carry a high_exclusion attribute'
    )
