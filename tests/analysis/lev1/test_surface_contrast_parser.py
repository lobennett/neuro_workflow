"""Scientific-correctness tests for ``SurfaceGLM._parse_contrast``.

These tests are not box-checking — they exist to keep the surface contrast
vector identical to the volumetric one for every contrast formula we ship
in production. A bug here is silent: the GLM still runs and writes files,
just with the wrong weights baked into ``effect_size``, ``effect_variance``
and ``z_score``. The previous handwritten parser silently dropped any term
adjacent to ``(``, ``)``, or ``/`` (fractional coefficients), which would
have invalidated ``task-baseline``, ``twoBack-oneBack``, ``match-mismatch``,
``main_vars``, and the ``1/3 *`` formulas in stopSignal and goNogo.

Coverage:

1. **Volumetric/surface parity** — for every YAML contrast in every base
   task, the surface vector must equal the volumetric vector (both come
   from ``nilearn.glm.contrasts.expression_to_contrast_vector``).
2. **Coefficient correctness** — fractional and parenthesized coefficients
   produce the exact expected magnitudes, not approximations or zeros.
3. **Mumford ConstDurRTDur invariant** — a contrast over ConstDur trial
   types must not accidentally weight the pooled ``response_time`` RTDur
   regressor.
4. **Loud failure on unknown regressors** — referencing a missing
   regressor raises a ``ValueError`` rather than silently emitting a
   zero. The old parser silently dropped unknowns, which produced
   undetectable corruption.

Add a test here every time a new contrast pattern enters a task YAML.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from nilearn.glm.contrasts import expression_to_contrast_vector

from neuro_workflow.analysis.lev1.processing.surface_data import SurfaceGLM
from neuro_workflow.analysis.task_config.loader import (
    get_regressor_config,
    get_task_contrasts,
)


BASE_TASKS = [
    'cuedTS',
    'directedForgetting',
    'flanker',
    'goNogo',
    'nBack',
    'shapeMatching',
    'spatialTS',
    'stopSignal',
]


def _make_fitted_glm(regressor_names: list[str]) -> SurfaceGLM:
    """Fit a minimal SurfaceGLM so ``_parse_contrast`` has a regressor list.

    Synthetic data; we only need ``regressor_names_`` populated. AR(1) is
    overkill here but matches production noise model defaults.
    """
    np.random.seed(0)
    n_tp = max(80, 4 * len(regressor_names))
    n_verts = 10
    X = pd.DataFrame(
        np.random.randn(n_tp, len(regressor_names)),
        columns=regressor_names,
    )
    Y = np.random.randn(n_tp, n_verts)
    glm = SurfaceGLM(t_r=1.5, noise_model='ols')
    glm.fit(Y, X)
    return glm


# ---------------------------------------------------------------------------
# 1. Volumetric/surface parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('task_name', BASE_TASKS)
def test_surface_contrast_vector_matches_volumetric_for_all_yaml_contrasts(task_name):
    """Surface ``_parse_contrast`` output must equal the volumetric path's
    contrast vector for every YAML contrast in every base task.

    Both should be exactly ``expression_to_contrast_vector(formula, names)``.
    """
    regressors = list(get_regressor_config(task_name).keys())
    contrasts = get_task_contrasts(task_name)

    glm = _make_fitted_glm(regressors)
    for contrast_name, formula in contrasts.items():
        surface_vec = glm._parse_contrast(formula)
        volumetric_vec = np.asarray(
            expression_to_contrast_vector(formula, regressors)
        )
        assert surface_vec.shape == volumetric_vec.shape, (
            f'{task_name}/{contrast_name}: shape mismatch'
        )
        np.testing.assert_array_equal(
            surface_vec, volumetric_vec,
            err_msg=(
                f'{task_name}/{contrast_name}: surface vector does not match '
                f'volumetric vector for formula {formula!r}'
            ),
        )


# ---------------------------------------------------------------------------
# 2. Coefficient correctness — exact magnitudes for patterns the old parser broke
# ---------------------------------------------------------------------------


def test_fractional_coefficient_in_task_baseline_pattern():
    """``1/3 * (a + b + c)`` weights each regressor at exactly 1/3.

    The old parser produced a zero vector here because the regex captured ``1``
    as the coefficient and ``/3 * a`` as the regressor name.
    """
    glm = _make_fitted_glm(['go', 'stop_failure', 'stop_success'])
    vec = glm._parse_contrast(
        '1/3 * go + 1/3 * stop_failure + 1/3 * stop_success'
    )
    np.testing.assert_allclose(vec, [1 / 3, 1 / 3, 1 / 3])


def test_parenthesized_expression_with_mixed_signs():
    """``0.5 * (a + b - c - d)`` weights ``a, b`` at +0.5 and ``c, d`` at -0.5.

    The old parser dropped the first and last terms (they had ``(`` and ``)``
    glued to the regressor names) and produced ``[0, +1.0, -1.0, 0]``.
    """
    names = ['mismatch_2back', 'match_2back', 'mismatch_1back', 'match_1back']
    glm = _make_fitted_glm(names)
    vec = glm._parse_contrast(
        '0.5 * (mismatch_2back + match_2back - mismatch_1back - match_1back)'
    )
    np.testing.assert_allclose(vec, [0.5, 0.5, -0.5, -0.5])


def test_decimal_coefficient_pair():
    """``0.5 * go + 0.5 * nogo_success`` — a baseline the old parser handled.

    Sanity check that the new parser also handles it. Should produce
    ``[0.5, 0.5]`` against the regressors in declaration order.
    """
    glm = _make_fitted_glm(['go', 'nogo_success'])
    vec = glm._parse_contrast('0.5 * go + 0.5 * nogo_success')
    np.testing.assert_allclose(vec, [0.5, 0.5])


def test_simple_minus_contrast():
    """``stop_success - go`` produces ``[+1, -1]`` with go listed first."""
    glm = _make_fitted_glm(['go', 'stop_success'])
    vec = glm._parse_contrast('stop_success - go')
    np.testing.assert_allclose(vec, [-1.0, 1.0])


# ---------------------------------------------------------------------------
# 3. Mumford ConstDurRTDur invariant
# ---------------------------------------------------------------------------


def test_constdur_contrast_does_not_weight_pooled_rtdur_regressor():
    """A contrast over ConstDur trial-type regressors must have zero weight
    on the pooled ``response_time`` (RTDur) regressor.

    Mumford's RT-modeling paradox approach uses one pooled RTDur regressor to
    absorb trial-to-trial RT variance, leaving the ConstDur regressors to
    capture stimulus-locked activity. A contrast like ``twoBack-oneBack``
    should weight only ConstDur columns; if any nonzero weight lands on
    ``response_time``, the contrast smuggles RT variance into a cognitive
    effect and the Mumford correction is undone.
    """
    regressors = list(get_regressor_config('nBack').keys())
    # nBack includes a pooled `response_time` (RTDur) regressor
    assert 'response_time' in regressors, (
        'nBack regressors must include the pooled RTDur regressor for this '
        'test to be meaningful'
    )
    glm = _make_fitted_glm(regressors)
    rt_idx = regressors.index('response_time')

    for contrast_name in ('twoBack-oneBack', 'match-mismatch', 'task-baseline'):
        formula = get_task_contrasts('nBack')[contrast_name]
        vec = glm._parse_contrast(formula)
        assert vec[rt_idx] == 0.0, (
            f'nBack/{contrast_name}: contrast weights the pooled '
            f'response_time RTDur regressor at {vec[rt_idx]}; this leaks '
            f'RT variance into a ConstDur contrast (formula={formula!r})'
        )


# ---------------------------------------------------------------------------
# 4. Loud failure on unknown regressors
# ---------------------------------------------------------------------------


def test_unknown_regressor_raises_rather_than_silently_zeroing():
    """Referencing a non-existent regressor must raise, not silently emit
    a zero-weighted contrast.

    The old parser silently dropped unknown terms, which produced silently
    corrupt contrasts. nilearn's ``expression_to_contrast_vector`` raises
    a ``ValueError`` — we want that behavior preserved.
    """
    glm = _make_fitted_glm(['go', 'stop_success'])
    with pytest.raises(Exception):
        glm._parse_contrast('go - nonexistent_regressor')


# ---------------------------------------------------------------------------
# 5. Cross-task contrast-balance invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('task_name', BASE_TASKS)
def test_all_yaml_contrasts_have_at_least_one_nonzero_weight(task_name):
    """Every contrast in every YAML must produce at least one nonzero weight.

    If a contrast comes out as the all-zero vector, either the formula uses
    a regressor name that doesn't match any in the design, or the YAML
    contrast list is empty / placeholder. Either way it's not analysis-ready
    and the production rerun should not silently emit a NaN z-map.
    """
    regressors = list(get_regressor_config(task_name).keys())
    contrasts = get_task_contrasts(task_name)
    glm = _make_fitted_glm(regressors)
    for contrast_name, formula in contrasts.items():
        vec = glm._parse_contrast(formula)
        assert np.any(vec != 0), (
            f'{task_name}/{contrast_name}: all-zero contrast vector for '
            f'formula {formula!r}; regressors available: {regressors}'
        )
