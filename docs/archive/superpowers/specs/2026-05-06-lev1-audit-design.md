# Lev1 audit + cohort outlier QC — design

**Date:** 2026-05-06
**Status:** Draft, ready for review
**Scope:** Project A from the 2026-05-06 brainstorm. Project B (unified exclusion registry) deferred to its own brainstorm.

---

## Context

Production fMRIPrep 25.2.4 run is complete and validated for both cohorts (5 discovery + 41 validation, 2568 active scans, all expected outputs present). Lev1 is the next step. Before running the full cohort, we want to:

- Confirm the 8 base task YAML configs are correct against real events.tsv columns.
- Confirm the lev1 modeling code is correct and produces scientifically sensible outputs in MNI / T1w / surface space.
- Codify findings as tests so regressions surface in CI.
- Build a cohort-level outlier detection module that mirrors Jeanette Mumford's `fmri-outlier-detector/run_network.py`, but tracks our pipeline's output paths so we don't have to fork her package when filenames evolve.
- Place 10 blank dual-task YAMLs so lev1 fails loudly (not silently) on dual-task scans until the configs land.

This spec deliberately scopes out Project B — the unified exclusion registry that will eventually consume `lev1_flagged.tsv` and propagate decisions into fixed effects and lev2. That work needs its own brainstorm; this spec produces the artifacts B will consume.

---

## Goals

1. Every base task YAML's `regressors[*].subset` query references columns that exist in real events.tsv files for that task across all subjects/sessions, and returns >0 rows for at least N% of scans.
2. Every contrast formula references regressor names declared in the same YAML.
3. The 10 lev1 processing modules pass a code-review with concerns surfaced and codified (as tests, fixes, or surfaced questions).
4. Lev1 fails loudly inline when a design matrix is rank-deficient or has a pathological VIF — it never produces silently-wrong outputs.
5. A new `neuro_workflow.qa.lev1_outliers` module produces the same artifacts as Jeanette's `run_network.py` (outlier-% CSV, Jeanette-style PDF, flagged-scans TSV) using our paths.
6. 10 blank dual-task YAMLs prevent lev1 from running scans whose configs aren't defined yet.
7. Edge cases (salvaged scans, missing events, NaN-first-row confounds, session offsets, cross-session anat) covered by tests.
8. Lev1 smoke-tested on s03 across 8 tasks × 3 spaces; if clean, lev1 production-run on the 5-subject discovery cohort with cohort QC.

## Non-goals

- Project B (unified exclusion registry).
- Filling in the 10 dual-task YAMLs (placeholders only — the user has reference code from a separate codebase to draw from later).
- Tuning GLM scientific knobs (HRF, drift, smoothing FWHM, AR(1) noise model) — these stay at current values. The audit verifies they're applied correctly, not whether the values are optimal.
- Validation cohort (41 subjects) lev1 production run — separate go decision after discovery is clean.
- Lev2 integration.

---

## Architecture

Three phases, each gated on the prior:

### Phase 1 — Static audit (no compute)

Pure code/test work. Output is fixes + tests + an audit report.

- **YAML ↔ events alignment** (`tests/analysis/test_yaml_events_alignment.py`, new): for each base task YAML × every events.tsv across both BIDS cohorts, parse each regressor's `subset` query, extract referenced columns, assert they exist in every events.tsv for that task, and assert the query returns >0 rows for at least 80% of scans (configurable per-task floor — some queries legitimately filter to rare trials).
- **Contrast formula sanity** (`tests/analysis/test_yaml_contrasts.py`, new): every contrast formula's referenced regressor names exist in the same YAML's `regressors:` block.
- **Data chain regression** (`tests/analysis/test_lev1_data_chain.py`, new): codifies the BIDS↔fmriprep↔events checks done ad-hoc in the 2026-05-06 conversation as regression tests so it can't silently regress.
- **Code review pass** on `lev1/processing/{events,design,confounds,glm,contrasts,surface_data,residuals,fixed_effects,masks,quality_control}.py`. Fixes land as commits with regression tests; ambiguous concerns surface to the user. Findings recorded in `docs/audits/2026-05-06-lev1-base-task-audit.md` (the audit trail).

### Phase 2 — Code changes (small, contained)

Three concrete deliverables:

#### 2A. Inline design-matrix guard

Modify `src/neuro_workflow/analysis/lev1/processing/glm.py:validate_glm_inputs()`:

- Compute design matrix rank via `np.linalg.matrix_rank` with reasonable tolerance. If rank < n_columns, raise `RankDeficientDesignError` with the most-correlated column pair (find via pairwise `|corr| > 0.999`, then alert on the first such pair).
- Compute per-contrast VIF (lev1 already does this via `quality_control.py`). Abort with `PathologicalVIFError` if any contrast VIF > 100. This is a sentinel for degenerate design matrix bugs (typo in YAML query, all-NaN regressor, etc.) — not a research-level threshold. The research-level VIF threshold of 5 stays at the cohort QC step.
- Both new exceptions subclass `ValueError`. Logged with subject/session/task/run for triage.
- ≤25 added lines. No config flags.

#### 2B. Cohort outlier QC module

New module `src/neuro_workflow/qa/lev1_outliers.py`. Single file, plain functions + dataclasses, ≤300 lines.

```python
def detect_lev1_outliers(
    *,
    lev1_dirs: list[Path],
    output_dir: Path,
    n_std: float = 3.0,                                    # Jeanette's run_network.py default
    vif_threshold: float = 5.0,
    outlier_pct_threshold: float = 10.0,
    contrast_glob: str = "sub-s*/task-*/indiv_contrasts/*stat-effect-size.nii.gz",
    vif_glob: str = "sub-s*/task-*/quality_control/*_desc-contrastVIFs.csv",
    exclusions: set[str] | None = None,                    # placeholder for Project B
) -> None: ...
```

**Discovery globs** are parameterized (defaults match lev1's current output structure). If lev1 reorganizes its output paths (or a third-party lev1 implementation has different ones), pass overrides at the CLI; the module logic is unchanged.

**Computation** (per (task, contrast) group):
1. Stack contrast NIfTIs across subjects.
2. Compute per-voxel cohort mean and SD.
3. Count voxels deviating >n_std SD from the cohort mean per subject ("outlier voxels").
4. Aggregate to outlier % per (subject, session, run, contrast).
5. Read VIF CSVs; aggregate per (subject, session, run, contrast).

**Outputs at `output_dir/`:**
- `lev1_outliers.csv` — one row per (subject, session, run, task, contrast) with `outlier_pct`, `vif`, `flagged_outliers` (= `outlier_pct > outlier_pct_threshold`), `flagged_vif` (= `vif > vif_threshold`).
- `lev1_outliers.pdf` — subject panels per (task, contrast) labeled with VIF + outlier %, plus all-cohort and per-contrast histograms (matches Jeanette's PDF layout).
- `lev1_flagged.tsv` — auto-flag subset (any flag set). The eventual input to Project B.

**CLI**: `scripts/lev1_outliers.py` + `scripts/run_lev1_outliers.sbatch`.

**Plotting**: port the plotting logic to our module (matplotlib + nilearn slicing for the per-subject panels, matplotlib hist for the histograms) with an attribution comment pointing at Jeanette's `plotting_functions.py`. We are not depending on her package as a `uv tool`. Output PDF layout matches hers: (1) one page per (task, contrast) with a slice grid of subject contrast images labeled with subject ID + VIF + outlier %, (2) a final page with a single all-cohort outlier-% histogram, (3) one page per contrast with that contrast's outlier-% histogram.

#### 2C. Dual-task placeholder YAMLs

10 new files in `src/neuro_workflow/analysis/task_config/tasks/`:

```
cuedTSWFlanker.yaml
directedForgettingWCuedTS.yaml
directedForgettingWFlanker.yaml
flankerWShapeMatching.yaml
nBackWShapeMatching.yaml
nBackWSpatialTS.yaml
shapeMatchingWCuedTS.yaml
spatialTSWCuedTS.yaml
spatialTSWShapeMatching.yaml
stopSignalWFlanker.yaml
```

Each contains:

```yaml
# DRAFT — dual-task config not yet defined.
# Will be filled in with regressor configurations from a reference codebase.
# Lev1 raises TaskNotConfiguredError on this task until `regressors:` is non-empty.

tr: 1.49
dummy_scans: 7  # informational; lev1 sets dummy_scans=0 (BOLDs pre-trimmed by trim_bold.py)
expected_sessions: null  # TBD
min_rt: 0.2

regressors: null
contrasts: null
```

Modify `src/neuro_workflow/analysis/task_config/loader.py:get_task_parameters()`:

- New exception class `TaskNotConfiguredError(ValueError)`.
- Single `if config["regressors"] is None: raise TaskNotConfiguredError(...)` branch.

### Phase 3 — Execution

Each step is a checkpoint; do not proceed past a failure.

1. **Static audit** — land Phase 1 tests; iterate fixes until all pass; commit audit report.
2. **Code changes** — TDD-implement Phase 2A, 2B, 2C with tests landing first. All edge-case tests added.
3. **Smoke test on s03** — sbatch lev1 across 8 tasks × 3 spaces × all sessions × all runs. Validation: every expected output file exists per task/run/space; no `RankDeficientDesignError` / `PathologicalVIFError` / `TaskNotConfiguredError` raised; cohort QC runs cleanly on the s03 outputs end-to-end.
4. **Production discovery cohort** — sbatch array on 5 subjects × 8 tasks × 3 spaces. Cohort QC at the end. Triage `lev1_flagged.tsv`.
5. **Visual end-check** — render `stopSignal stop_success-go` for s03 in MNI, T1w, surface. Eyeball-confirm activation lands in canonical rIFG / pre-SMA. Document pass/fail in the audit report.

Validation cohort (41 subjects) lev1 run is a separate go decision after step 5.

---

## Edge case test coverage

Adding to `tests/analysis/lev1/`:

- `test_salvaged_scans.py` — events whose onsets exceed BOLD's actual length get dropped (or flagged), not raise.
- `test_missing_events.py` — scan with events.tsv missing → caller (`run.py`) skips with a logger warning; downstream gets nothing for that scan; no crash.
- `test_confounds_nan_first_row.py` — fmriprep's convention (FD/DVARS undefined at t=0) handled correctly without warnings or crashes.
- `test_session_offset_paths.py` — s321/s1445/s1326/s1391/s1258 path resolution. (Some are validation cohort; tests use BIDS fixtures.)
- `test_cross_session_anat.py` — subject whose chosen T1w is in a different session than the BOLD being processed (e.g., s19 anat in ses-05, BOLDs in ses-01) → lev1 references the right anat for fixed effects across runs.

For new components:

- `tests/qa/test_lev1_outliers.py` — synthetic 4×4×4 NIfTIs with known outlier voxel counts → assertion on detected counts; synthetic VIF CSVs → aggregation correctness; auto-flag rules; placeholder for exclusions parameter (no-op until Project B).
- `tests/analysis/lev1/test_inline_guard.py` — rank-deficient design matrix → raises `RankDeficientDesignError`; VIF >100 → raises `PathologicalVIFError`; clean design matrix passes.

---

## Resources

Sbatch baselines (will tune from real logs):

| Step | Mem | CPUs | Wall |
|---|---|---|---|
| Per-subject-task lev1 array element | 32 GB | 4 | 4 h |
| Cohort QC (single post-array sbatch) | 16 GB | 1 | 1 h |

---

## Code-style guardrails (explicit, non-negotiable)

These are written down because the user surfaced them as a hard constraint and the spec needs to make them stick:

- **Cohort QC**: single file `lev1_outliers.py`, plain functions + dataclasses, ≤300 lines. No class hierarchies. No abstract base classes. No "let's also handle case Y" branches without a real Y in the data.
- **Inline guard**: ≤25 added lines. Two new exception subclasses. No config flags. No "should this be a warning instead?" toggle.
- **Placeholder YAML loader path**: a single `if regressors is None:` branch in `loader.py`. Not a separate function.
- **Edge case tests**: one file per concern. Pytest fixtures via `tmp_path` only — no fixture factories or shared `conftest.py` magic.
- **No retroactive abstractions** ("we might want X later"). YAGNI.
- **No silent fallbacks**. If something can't be computed, raise a clear error or return a sentinel that callers must handle. No "if missing return 0".

This spec inherits the project's existing pattern (see `qa_report.py`, `reliability_movies.py`): single-file modules, frozen dataclasses, plain functions, tests that mock at process boundaries (subprocess.run) rather than mocking internals.

---

## Open questions / decisions deferred to implementation

1. **YAML↔events query floor (80% by default)**: the `test_yaml_events_alignment.py` check asserts each regressor's `subset` query returns ≥1 row in at least 80% of scans of that task. The 80% number balances "regressor is fundamentally broken" (caught) against "rare-but-real trial types" (e.g., `break_with_performance_feedback` may be missing in salvaged-truncated scans). Two options at implementation:
   - **(default) global 80% floor** — simple, may produce false negatives for rare regressors.
   - **per-task configurable floor** — add an `events_query_min_coverage:` field per regressor in the YAML, default to 0.8 if absent. More annotation but tighter. **The implementer should pick whichever produces fewer noisy test failures on the real data; if 80% global passes cleanly across all 8 tasks, leave it global. Otherwise add per-regressor overrides.**

The earlier two open questions (plotting library, glob configurability) are resolved in the design above: plotting is ported to our module; globs are parameterized.

---

## Self-review notes

- Placeholder scan: no TBDs except the three open questions above (explicitly flagged as deferred).
- Internal consistency: architecture, components, and execution plan all reference the same artifacts (`lev1_outliers.csv`, `lev1_flagged.tsv`, the test files) without contradiction.
- Scope check: Phase 1 + Phase 2 + Phase 3 fit in a single implementation plan. Project B explicitly out of scope.
- Ambiguity: every threshold has a number; every component has a single file path.
