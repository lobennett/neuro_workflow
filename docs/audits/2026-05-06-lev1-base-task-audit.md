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

(none yet)

### Edge cases

(none yet)

### Smoke test

(none yet)

## Visual end-check

Task: render `stopSignal stop_success-go` for s03 in MNI / T1w / surface. Confirm canonical anatomy (rIFG / pre-SMA).

(filled in when run)
