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

- **2026-05-06 `d3a1359`** — Salvaged scans: lev1 didn't trim events whose `onset >= n_scans * tr`. GLM output was unaffected (nilearn silently truncated past-end events) but `*_simplifiedEvents.csv` was writing phantom rows for past-end events. Fixed by adding optional `n_scans` kwarg to `preprocess_events`; `run.py` now passes it. 5 tests in `test_salvaged_scans.py` cover the fix.
- **2026-05-06 `9fc145b`** — Missing events.tsv: `_filter_complete_runs` in `file_discovery.py` was silently dropping any run that lacked a required file (events, BOLD, etc.) with no log. Real salvaged subjects could lose scans without anyone noticing. Fixed by emitting `logger.warning("Skipping %s/%s: missing required file(s): %s", ...)` per partially-discovered run while still ignoring fully-absent runs (no noise for subjects with no scans for a task). 4 tests in `test_missing_events.py` cover the fix.
- **2026-05-06 `b188437`** — Confounds NaN at row 0 (fmriprep convention for FD/DVARS undefined at t=0): `load_and_process_confounds` already calls `.fillna(0)` before regex column selection. No fix needed; codified in `test_confounds_nan_first_row.py`.
- **2026-05-06 `6f3ecf6`** — Session-offset subjects (s321/s1445/s1326/s1391/s1258 with +1 BIDS-vs-behavioral session offset): `FileFinder.get_files()` discovers via on-disk glob, so it's structurally agnostic to behavioral-vs-BIDS distinctions — whatever's in the fmriprep tree is what surfaces. Confirmed by 3 tests in `test_session_offset_paths.py` including an adversarial stray-behavioral-session-dir case.
- **2026-05-06 `a50e6f5`** — Cross-session anat (s19/s10/s29/s43 etc. with anat from a different BIDS session than their BOLDs): real fmriprep layout is per-session (`sub-X/ses-Y/anat/`), not subject-level (`sub-X/anat/`) as the plan assumed. Lev1 base GLM doesn't reference anatomical T1w directly (only mshbm does, via `find_anat_dir`). 9 tests in `test_cross_session_anat.py` confirm the real layout and the resolution path.
  - **Follow-up note:** `surface_data.py:506` has a stale subject-level (`sub-X/anat/`) fallback for finding anat. It's a fallback after FreeSurfer dirs are checked and "almost never fires" per the implementer's read, but the assumption is wrong for this project. Worth a follow-up fix when convenient — not in scope for this audit.

### Visual end-check + downstream finding

- **2026-05-06 `6f35957`** — Saved fixed-effects "z_score" file was actually nilearn's `fixed_fx_stat_img` (3rd return = effect/sqrt(variance)), which blows up to ±10^10 at out-of-mask voxels where variance=0. Now uses nilearn's `fixed_fx_z_score_img` (4th return) when available; values are bounded.
- **2026-05-06 OPEN — needs investigation, surfaced for triage** — visual end-check on s03 stopSignal `stop_success-go` after the fixed-effects fix shows 28% of in-mask voxels capped at z = ±37.047 (scipy float-precision floor for `norm.ppf` near p ≈ 0). Root cause: **per-run variance maps are 99.6%+ zeros even inside the brain mask**. Example values for sub-s03 task-stopSignal `stop_success-go`:
  - ses-02 run-1 variance: median=0, zeros=99.67%, max=667K
  - ses-04 run-1 variance: median=0, zeros=99.37%, max=623K
  - ses-06 run-1 variance: median=0, zeros=99.64%, max=2M
  - Combined mask has 265K in-mask voxels (29%); variance has only ~0.4% non-zero voxels — so even within the GLM mask, most variance values are zero. This is upstream of fixed effects (in lev1's contrast computation or variance-map saving). Affects all base tasks on disk.
  - Hypotheses: (a) the GLM applies a stricter internal mask than the saved combined mask and only writes variance for a sub-region, (b) `compute_run_contrasts` zero-fills variance outside its compute region, (c) nilearn's contrast computation has a known quirk where variance is only valid where the design has full rank locally.
  - Lev1 contrast effect-size maps look healthy (e.g. range -350 to +464). The bug is specific to variance.
  - **Triage decision required from user.**

### Smoke test

s03 × all 8 base tasks × MNI space (alphabetical, single-task per submission, gating each on the prior succeeding):

| Task | Job ID | Runs | Contrasts | Notes |
|---|---|---|---|---|
| cuedTS | 24132551 | 5/5 | 5 | clean (after VIF + 4-tuple fixes) |
| directedForgetting | 24133294 | 5/5 | 3 | clean |
| flanker | 24135244 | 5/5 | 3 | clean |
| goNogo | 24138005 | 4/5 | 4 | ses-01 legit behavioral exclusion (junk 32.8% > 30%) |
| nBack | 24138867 | 5/5 | 4 | clean |
| shapeMatching | 24139689 | 5/5 | 10 | clean |
| spatialTS | 24140329 | 5/5 | 5 | clean |
| stopSignal | 24143959 | 5/5 | 8 | clean |

**Total: 39/40 (s03) per-run lev1 fits succeeded. 1 legit behavioral exclusion. 0 unexplained failures.**

Extended smoke for cohort QC validation (s03 + s10, 8 tasks each, MNI):

- s10 × 8 tasks submitted in parallel (jobs 24190335–24190344). Result: 7/8 fully clean; goNogo had ses-03 excluded for legit behavioral junk (30.6% > 30% threshold), matching s03's pattern.
- Cohort QC on 2-subject cohort (job 24192035): 408 (scan, contrast) rows in `lev1_outliers.csv`, 216 flagged for VIF > 5, but **all `outlier_pct` values are 0.0**. This is mathematically expected: with N subjects and population SD, the maximum |z-score| at any voxel is `sqrt(N−1)`, so n_std=3 (Jeanette's default) requires ≥10 subjects per (task, contrast) group to detect any outliers (cohort=2 gives max |z|=1.0; cohort=5 gives 2.0; cohort=10 gives 3.0). Implication: outlier voxel detection is meaningful only at full discovery+validation cohort (N=46). For discovery alone (N=5), VIF flagging in `lev1_flagged.tsv` is the only useful signal from cohort QC. No code change needed; `lev1_outliers.py` runs correctly at any N — the outlier_pct values are just degenerate by construction at small N.

Bugs surfaced + fixed during smoke (4 real lev1 fixes):

- **2026-05-06 `c41a662`** — `file_discovery.py` had `MNI152NLin2009cAsym_res-2` hardcoded; our fmriprep produced `:res-1` for that template and `:res-2` only for `MNI152NLin6Asym`. Added `--mni-template` / `--mni-res` CLI args (defaults to `MNI152NLin6Asym` + `2`).
- **2026-05-06 `3cc916a`** — nilearn 0.10+'s `compute_fixed_effects` returns 4 values (added z-score image); lev1 was unpacking 3. Now takes `result[:3]` to match the surface path's 3-tuple.
- **2026-05-06 `33f23b5` → `473ab6e` → `2d42f51`** — VIF inline guard was too aggressive on per-column motion + motion² + drift collinearity (real BOLDs hit VIFs 100–1500). Iterated: 100 → 1000 → 10000, then refactored entirely. Now: inline guard checks rank deficiency only; contrast VIFs are computed and saved to `*_desc-contrastVIFs.csv` for review by `neuro_workflow.qa.lev1_outliers` (which thresholds at default 5 and emits `lev1_flagged.tsv`). Lev1 does NOT auto-skip scans on contrast VIF — researchers can review flagged scans manually.

## Visual end-check

Task: render `stopSignal stop_success-go` for s03 in MNI / T1w / surface. Confirm canonical anatomy (rIFG / pre-SMA).

(filled in when run)
