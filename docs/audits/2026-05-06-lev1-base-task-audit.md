# Lev1 base-task audit — 2026-05-06

**Spec:** `docs/superpowers/specs/2026-05-06-lev1-audit-design.md`
**Plan:** `docs/superpowers/plans/2026-05-06-lev1-audit.md`
**Branch:** `lev1-audit-2026-05-06`

## What was checked

- 8 base task YAMLs (`cuedTS`, `directedForgetting`, `flanker`, `goNogo`, `nBack`, `shapeMatching`, `spatialTS`, `stopSignal`) against real events.tsv columns and row counts across both cohorts (~2094 task scans).
- Contrast formulas reference declared regressor names.
- BIDS↔fmriprep↔events chain consistent (no scan slipping between stages).
- Lev1 processing modules reviewed for correctness (events, design, glm, contrasts, surface_data, residuals, fixed_effects, masks, confounds, quality_control).
- Edge cases: salvaged scans, missing events, NaN-first-row confounds, session offsets, cross-session anat.
- Smoke test on s03 across 8 tasks × 3 spaces (MNI/T1w/surface).

## Findings

### YAML schema

- **2026-05-06 `28184de`** — `spatialTS.yaml` had a dead `task_na_cue_na` regressor querying `trial_type == 'tn/a_cn/a'` — fired in 0/230 scans cohort-wide. Looks like a copy-paste from `cuedTS.yaml`. Real spatialTS events emit only 3 trial types (`tstay_cstay`, `tstay_cswitch`, `tswitch_cswitch`). Removed the regressor block; cleaned up the `response_time` subset (dropped redundant `trial_type != 'tn/a_cn/a'` clause); updated header comment. No contrasts referenced the dead regressor.
- **2026-05-06 `28184de`** — `break_with_performance_feedback` is a legitimately rare regressor (fires in 0–21% of scans depending on task; `break_with_performance_feedback` appears in 290 cohort-wide files vs `break` in 2085). The 80% global coverage floor was wrong for it. Resolution: per-regressor `events_query_min_coverage:` field added to YAML schema (default 0.8; set to 0.0 for `break_with_performance_feedback` in all 8 base task YAMLs). The test additionally asserts every regressor must match in ≥1 scan cohort-wide regardless of floor — this catches "dead regressor" bugs (e.g. `task_na_cue_na`) that would otherwise pass with floor=0.0.
- **2026-05-06 `ed6b67f`** — All 8 base task contrast formulas reference only declared regressor names + arithmetic; no typos.
- **2026-05-06** — Observation (out of scope for this audit): `stopSignalWDirectedForgetting.yaml` (a dual-task config that already exists) has empty `contrasts: {}`. Not in the 8 base-task scope but worth flagging when dual-task YAMLs are filled in.

### Lev1 code review

- **2026-05-06 `a894f10`** — Inline design-matrix guard added to `glm.py`: `RankDeficientDesignError`, `PathologicalVIFError`, `check_design_matrix_health()`. Wired into `validate_glm_inputs` (records errors instead of raising). Two bugs in the spec'd code surfaced and fixed during implementation: (i) `np.fill_diagonal` requires a writable array (used `to_numpy(copy=True)`); (ii) zero-variance columns (intercept) were producing `VIF=inf` and tripping `PathologicalVIFError` on every clean design matrix — now treated as `VIF=1.0` (uninformative for collinearity).
- **2026-05-06** — 5 pre-existing test failures triaged and resolved (none reflected real lev1 bugs; all were stale tests):
  - `test_preprocess_events_negative_onset_filtering` and `test_preprocess_events_negative_onset_with_dummy_scans` — DELETED. They asserted `preprocess_events` filters negative onsets, but the function's docstring explicitly says onset adjustment is upstream (`events/create.py`). Tests checked behavior the function doesn't claim. The second test also had a latent bug (`adjust_for_dummy_scans=True` with default `dummy_scans=0`).
  - `test_all_nan_vertex` (surface fixed effects) — UPDATED. Asserted output `0.0` for all-NaN vertices, but `compute_surface_fixed_effects` deliberately preserves NaN at fully-invalid vertices to avoid silently treating them as zero during group-level thresholding (per its own code comment). Test now asserts `np.isnan(...)`.
  - `test_performance_feedback_flag` — DELETED. Tested for `has_performance_feedback_breaks` key in `get_task_parameters` output that doesn't exist anywhere in the codebase. Functionality is now superseded by the per-regressor `events_query_min_coverage` override added in Task 1.
  - `tests/analysis/lev1/test_vol2fsaverage.py` — DELETED. Imported from `prepare_mshbm_inputs` which doesn't exist in the repo (orphaned test, deleted module).
  After cleanup: 175/175 `tests/analysis/lev1/` tests pass.

### Edge cases

(none yet)

### Smoke test

(none yet)

## Visual end-check

Task: render `stopSignal stop_success-go` for s03 in MNI / T1w / surface. Confirm canonical anatomy (rIFG / pre-SMA).

(filled in when run)
