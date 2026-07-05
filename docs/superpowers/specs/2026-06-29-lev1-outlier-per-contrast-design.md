# lev1_outlier per-contrast VIF exclusion — design

**Date:** 2026-06-29
**Author:** Logan Bennett (logben@stanford.edu)
**Status:** proposed (pre-implementation)
**Branch:** `repro-harness-2026-06`

## Problem

`lev1_outlier` currently aggregates per-contrast QC to **scan-level** exclusions: if *any*
contrast on `(subject, session, task, run)` fires a rule, the whole scan is excluded.
A cohort diagnosis (2026-06-29) showed this is both wrong-grained and mis-calibrated:

- **65–67% of all VIF≥15 flags are the `task-baseline` contrast** (131/203 discovery,
  909/1361 validation), which is *structurally* high-VIF — the sum-of-all-conditions
  regressor collides with the constant + cosine-drift terms (design condition number
  ~3×10⁷). It is not a data-quality signal.
- Another ~25% are `response_time` (a nuisance regressor — also structurally collinear
  with task timing).
- Only ~22 discovery / ~97 validation flags are on **condition contrasts**
  (DDD/DDS/SSS/…) — the genuine "rare cell in this run → unstable estimate" signal.

Scan-level aggregation + `strict_vif=15` on all contrasts therefore excluded nearly
every scan (the "catastrophe" in the recompile delta). The user's intent: a VIF
exclusion should drop **only that contrast's fixed-effects map from lev2**, not the scan.

## Decision (confirmed)

1. VIF exclusions are **per-contrast**, not per-scan.
2. The `strict_vif` (and `combined`) VIF rules **skip exempt contrasts**
   `{task-baseline, response_time}` (structurally high-VIF, not contrasts of interest).
   The outlier-only rule (`strict_outliers`, no VIF) still applies to all contrasts.
3. A per-contrast exclusion drops that contrast's contribution; via the existing
   `min_runs`/`belowMinRuns` mechanism, a `(subject, task, contrast)` fixed-effects map
   that loses too many runs is tagged `belowMinRuns` and dropped from lev2.

## Design — one new action + a contrast field, reusing belowMinRuns

### Exclusion model
Introduce action **`exclude-contrast`** (distinct from scan-level `exclude`/`trim`) and an
optional **`contrast`** field on exclusion entries.

- **Scan-level** entries (behavioral, motion, qa_decisions, collection): unchanged —
  `action: exclude`, no `contrast`, render to `.bidsignore`, make lev1 skip the run.
- **Contrast-level** entries (lev1_outlier): `action: exclude-contrast`, carry
  `contrast`, key `(subject, session, task, run, contrast)`.

### Per-component changes
1. **`thresholds.yaml`** — add `lev1_outlier.exempt_contrasts: [task-baseline, response_time]`.
2. **`exclusions/lev1_outlier.py`** — emit one `exclude-contrast` entry per flagged
   `(subject, session, run, contrast)` (no scan aggregation); skip the VIF rules for
   exempt contrasts; `reason` carries the metric.
3. **`core/exclusions.py`** — `exclude-contrast` is a valid action; dedup/`_scan_key`
   becomes contrast-aware for it (5-tuple incl. contrast); compiled list + lockfile
   record `contrast`. `is_excluded(...)` (scan-level, used by lev1 to skip runs) stays
   `exclude`/`trim` only → a contrast exclusion does **not** drop the whole run.
4. **`core/exclusions_render.py`** — `_BIDSIGNORE_ACTIONS` stays `{exclude, trim}` →
   contrast-level entries produce **no `.bidsignore` glob** (correct — they aren't BOLD
   removals). `render_md` lists them (informational, grouped by source).
5. **`analysis/lev1/processing/fixed_effects.py`** — when assembling per-run inputs for
   contrast C, drop runs with an `exclude-contrast` entry for `(subject,session,run,C)`;
   apply the existing `min_runs` floor per contrast → `_desc-belowMinRuns` tag.
   Plumb the contrast-exclusion set in via `runner.py` (same path as `min_runs`).
6. **lev2** — unchanged: it already drops `_desc-belowMinRuns` files.
7. **harness** (`testing/reproduce/canonical.py`, `lev2_select.py`) — `compiled_to_keyset`
   includes `contrast` for `exclude-contrast`; `lev2_eligible_set` honors per-contrast
   belowMinRuns.

### Why `exclude-contrast` (not overloading `exclude`)
It makes the right things happen by construction: no `.bidsignore` glob, no whole-run
skip in lev1, contrast-aware dedup — while keeping the 4 scan-level generators untouched.

## Net effect
The committed scan-level lev1_outlier set (0 entries today) is replaced by a per-contrast
set dominated by exempt contrasts that are now skipped; the meaningful exclusions are the
~22 discovery / ~97 validation `(scan, condition-contrast)` drops, each removing one run's
contribution to one contrast's fixed-effects (→ belowMinRuns only if it pushes that
contrast under `min_runs`). No whole scans gutted.

## Testing (TDD)
- `lev1_outlier`: exempt contrasts skipped for VIF rules; per-contrast entries emitted;
  `strict_outliers` still applies to exempt contrasts; entry carries `contrast`.
- `core.exclusions`: `exclude-contrast` validates; contrast-aware dedup; lockfile round-trip.
- `exclusions_render`: contrast-level entry → no `.bidsignore` line; appears in md.
- `fixed_effects`: per-contrast run filtering + per-contrast belowMinRuns.
- harness canonical/lev2_select: contrast keys honored.

## Out of scope
- Re-deriving per-run VIF (read the existing `*_desc-contrastVIFs.csv`).
- Changing the GLM/design (the task-baseline collinearity is inherent; we exempt, not fix).
- The lockfile recompile itself (decision #2 — runs after this lands).
