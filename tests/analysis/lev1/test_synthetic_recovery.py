"""Scientific-validity simulation: planted-contrast recovery through the
REAL lev1 GLM path.

This test plants a known contrast effect into synthetic BOLD data, then runs
that data through the actual production lev1 code:

  * ``analysis.lev1.processing.design.create_design_matrix``
        — turns a real task's regressor config + an events DataFrame into a
          design matrix (uses the real flanker YAML via the task_config loader).
  * ``analysis.lev1.processing.glm.fit_run_glm``
        — fits a nilearn ``FirstLevelModel`` to the synthetic 4D BOLD.
  * ``FirstLevelModel.compute_contrast`` (as called by
        ``analysis.lev1.processing.contrasts.compute_run_contrasts``)
        — evaluates the real flanker contrast formula
          ``incongruent - congruent``.

If the contrast machinery (design build, fit, or contrast evaluation) were
wrong — e.g. the formula were parsed with a flipped sign, or amplitudes were
silently dropped — the recovered estimate would not match the planted +5 and
this test would fail. (Mentally flipping the planted sign to incongruent <
congruent would flip the recovered estimate's sign, which the sign assert
below would catch.)

The synthetic helpers live in ``neuro_workflow.testing.synthetic`` and are
purely additive test support — no production module is exercised by them.
"""

import numpy as np
import pandas as pd
import pytest

from neuro_workflow.analysis.lev1.processing.contrasts import compute_run_contrasts
from neuro_workflow.analysis.lev1.processing.design import create_design_matrix
from neuro_workflow.analysis.lev1.processing.glm import fit_run_glm
from neuro_workflow.analysis.task_config.loader import get_task_contrasts
from neuro_workflow.testing.synthetic import (
    as_4d_nifti,
    make_events,
    make_mask,
    make_synthetic_run,
    plant_bold,
)

TASK = "flanker"
TR = 1.49
N_SCANS = 220  # ~5.5 min run; ample to estimate well-separated trials


def _build_real_design():
    """Build a flanker design matrix via the REAL lev1 design code.

    Returns the design matrix and the events used (for traceability). The
    confounds frame carries a single explicit intercept ('constant'); the
    real ``create_design_matrix`` concatenates it with the task regressors.
    """
    events = make_events(TASK, n_trials=18, tr=TR)
    # Minimal confounds: just an explicit intercept so the GLM has a baseline.
    # create_design_matrix concatenates this with the convolved task regressors.
    confounds = pd.DataFrame({"constant": np.ones(N_SCANS)})
    design, _reg3 = create_design_matrix(
        events_df=events,
        confounds_df=confounds,
        task_name=TASK,
        n_scans=N_SCANS,
        tr=TR,
    )
    return design, events


def test_design_has_real_flanker_regressors():
    """Sanity: the real loader/design path produces the flanker condition
    regressors the planted contrast relies on."""
    design, _ = _build_real_design()
    assert "congruent" in design.columns
    assert "incongruent" in design.columns
    assert design.shape[0] == N_SCANS
    # The convolved condition regressors must actually carry signal (non-zero
    # variance), else the GLM could not recover a planted effect.
    assert design["congruent"].var() > 0
    assert design["incongruent"].var() > 0


def test_planted_contrast_is_recovered_through_real_glm():
    """Plant incongruent=10, congruent=5 (contrast +5) and recover it via the
    REAL fit + REAL contrast formula."""
    design, _ = _build_real_design()

    planted = {"incongruent": 10.0, "congruent": 5.0, "constant": 100.0}
    # Modest noise relative to the planted effect; deterministic via seed.
    img, _ = make_synthetic_run(design, planted, noise_sd=0.5, seed=42)

    # REAL first-level fit (nilearn FirstLevelModel under the project wrapper),
    # with an explicit mask (a real fit_run_glm parameter) so auto-masking
    # doesn't reject the spatially-uniform synthetic block.
    fitted = fit_run_glm(
        img, design, analysis_type="task", tr=TR, mask_img=make_mask(img)
    )

    # REAL contrast formula from the flanker YAML.
    contrasts = get_task_contrasts(TASK)
    formula = contrasts["incongruent-congruent"]
    assert formula == "incongruent - congruent"  # guards against config drift

    # REAL contrast evaluation (same call compute_run_contrasts makes).
    result = fitted.compute_contrast(formula, output_type="effect_size")
    recovered = float(np.mean(result.get_fdata()))

    planted_effect = planted["incongruent"] - planted["congruent"]  # = +5.0
    assert planted_effect == pytest.approx(5.0)

    # Directional recovery: must be clearly positive.
    assert recovered > 0, f"expected positive contrast, got {recovered}"
    # Approximate-magnitude recovery within generous tolerance.
    assert recovered == pytest.approx(planted_effect, abs=1.0), (
        f"recovered {recovered:.3f} not within 1.0 of planted {planted_effect}"
    )


def test_null_contrast_recovers_near_zero():
    """When congruent and incongruent are planted EQUAL, the
    incongruent-congruent contrast must recover ~0 (no spurious effect)."""
    design, _ = _build_real_design()

    # Equal condition betas -> true contrast is exactly 0.
    planted = {"incongruent": 7.0, "congruent": 7.0, "constant": 100.0}
    img, _ = make_synthetic_run(design, planted, noise_sd=0.5, seed=7)

    fitted = fit_run_glm(
        img, design, analysis_type="task", tr=TR, mask_img=make_mask(img)
    )
    formula = get_task_contrasts(TASK)["incongruent-congruent"]
    result = fitted.compute_contrast(formula, output_type="effect_size")
    recovered = float(np.mean(result.get_fdata()))

    assert recovered == pytest.approx(0.0, abs=1.0), (
        f"null contrast should be ~0, got {recovered:.3f}"
    )


def test_noiseless_recovery_is_tight():
    """With zero noise the real GLM should recover the planted +5 contrast
    essentially exactly — proving the design/fit/contrast path is unbiased."""
    design, _ = _build_real_design()

    planted = {"incongruent": 10.0, "congruent": 5.0, "constant": 100.0}
    ts = plant_bold(design, planted, noise_sd=0.0, seed=0)
    img = as_4d_nifti(ts)
    fitted = fit_run_glm(
        img, design, analysis_type="task", tr=TR, mask_img=make_mask(img)
    )
    formula = get_task_contrasts(TASK)["incongruent-congruent"]
    result = fitted.compute_contrast(formula, output_type="effect_size")
    recovered = float(np.mean(result.get_fdata()))

    assert recovered == pytest.approx(5.0, abs=0.05), (
        f"noiseless recovery {recovered:.4f} should be ~5.0"
    )


def test_compute_run_contrasts_saves_recovered_effect(tmp_path):
    """Exercise the higher-level compute_run_contrasts wrapper end-to-end:
    it should write an effect-size map whose mean recovers the planted +5."""
    design, _ = _build_real_design()
    planted = {"incongruent": 10.0, "congruent": 5.0, "constant": 100.0}
    img, _ = make_synthetic_run(design, planted, noise_sd=0.5, seed=123)

    fitted = fit_run_glm(
        img, design, analysis_type="task", tr=TR, mask_img=make_mask(img)
    )
    saved = compute_run_contrasts(
        fitted_glm=fitted,
        task_name=TASK,
        output_dir=tmp_path,
        base_filename="sub-synth_task-flanker_run-01",
    )

    assert "incongruent-congruent" in saved
    effect_path = saved["incongruent-congruent"]["effect_size"]
    assert effect_path.exists()

    import nibabel as nib

    recovered = float(np.mean(nib.load(str(effect_path)).get_fdata()))
    assert recovered == pytest.approx(5.0, abs=1.0), (
        f"saved effect-size map mean {recovered:.3f} not within 1.0 of +5"
    )
