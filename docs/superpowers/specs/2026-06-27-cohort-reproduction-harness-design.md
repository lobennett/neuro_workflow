# Cohort reproduction harness — design

**Date:** 2026-06-27
**Author:** Logan Bennett (logben@stanford.edu)
**Status:** Approved design (pre-implementation)
**Branch:** `repro-harness-2026-06`

## Purpose

Provide a **machine-checked guarantee that the current codebase exactly reproduces
the discovery + validation datasets** — from Flywheel inventory through bidsify,
trimming, events, all exclusion generators, the compiled lockfile + `.bidsignore`,
to the final set of `(subject, task, contrast)` fixed-effects maps that feed the
second-level (group) model.

It complements — does not replace — the existing hermetic synthetic harness
(`testing/simulate.py`), which proves the pipeline *logic* is faithful on a
planted synthetic cohort. This harness proves the *specific real cohorts*
reproduce, using real metric inputs but stub (empty) large NIfTIs.

### Why this exists (motivating audit)

A reproduction-readiness audit (2026-06-27) found the committed exclusion
artifacts are **stale**: both lockfiles were compiled at an older SHA
(`eec3159+dirty`; HEAD `59b2322`) before 2 commits touching exclusions code, the
`lev1_outlier` generator exists in code but is in **neither** lockfile, and the
motion source recorded fMRIPrep `24.1.0rc2` while derivatives on disk are
`25.2.4`. BIDS↔lockfile reconciliation passes. So the datasets are **not currently
exactly reproducible**. This harness is the durable mechanism that (a) verifies a
fresh recompile reproduces the committed artifacts and (b) catches future drift.

## Locked scope decisions (from brainstorming)

1. **Data fidelity:** the harness reads the **real small metric-driver files**
   (behavioral CSVs, fMRIPrep confounds TSVs, `lev1_outliers.csv`,
   `qc_decisions.tsv`, `<cohort>_collection.bidsignore`, `<cohort>_overrides.json`)
   so it reproduces the **exact** real exclusion set; it **stubs** only the large
   BOLD/anat NIfTIs (empty placeholders — the GB savings).
2. **Flywheel→BIDS source of truth:** a **committed Flywheel inventory snapshot**
   (subject/session/acquisition metadata, captured once via the real client) is
   replayed through `FakeFlywheel` → real `run_bidsify`, producing filenames
   **independently** and diffed against the real BIDS trees (non-circular test of
   the real naming logic + config).
3. **Endpoint:** the harness asserts the **full post-exclusion lev2-eligible
   `(subject, task, contrast)` set** (after exclusions + events + rest filtering +
   the fixed-effects `min_runs` floor), not just the exclusion lockfile.
4. **Run mode:** an **on-demand Sherlock driver + report**, wrapped as a pytest
   that **auto-skips when real inputs are absent**. The existing synthetic e2e
   test is unchanged (portable logic guarantee).

## Architecture & module layout

A focused package that imports production stages and reuses the validated
`simulate_exclusions()` glue. `simulate.py` is **not modified**.

```
src/neuro_workflow/testing/reproduce/
  __init__.py
  snapshot.py       # load Flywheel inventory JSON -> FlywheelCohortSpec (adapter to fake_flywheel)
  replay.py         # snapshot -> FakeFlywheel(empty blobs) -> run_bidsify -> trim_bold -> events.create
  stage_metrics.py  # symlink real metric inputs into the stub tree so generators read genuine metrics
  lev2_select.py    # model the post-exclusion lev2-eligible {subject,task,contrast} set
  canonical.py      # provenance-stripped canonical forms (exclusion set, filename set, lev2 set)
  report.py         # render repro_report.md: 3 diffs + PASS/FAIL + provenance
scripts/
  capture_fw_inventory.py   # one-time: real fw client -> data/repro/fw_inventory_<cohort>.json (committed)
  reproduce_cohort.py       # CLI: reproduce_cohort.py {discovery,validation} [--out ...]
tests/analysis/e2e/
  test_reproduce_units.py   # hermetic unit tests (tiny synthetic fixtures) per unit
  test_reproduce_cohort.py  # Sherlock e2e; auto-skips when real inputs/snapshot absent
data/repro/
  fw_inventory_discovery.json   # committed Flywheel inventory snapshots
  fw_inventory_validation.json
```

Each unit has one responsibility, a documented interface, and is independently
testable. Only `snapshot`/`replay`/`stage_metrics`/`lev2_select`/`canonical`/`report`
are new logic; every pipeline-load-bearing step is production code
(`run_bidsify`, `trim_bold`, `events.create`, the 5 exclusion generators,
`compile_exclusions`, `render_bidsignore_with_collection`, `FileFinder`, the
`min_runs` logic, `lev2.discover_input_files`).

## Flywheel inventory snapshot

`scripts/capture_fw_inventory.py` runs **once on Sherlock with Flywheel auth**,
introspecting the real project the same way `run_bidsify` does, and records the
metadata bidsify consumes: per subject → sessions `{label, timestamp}` → acquisitions
`{label, timestamp, files:[{name, type, classification, echo}]}`. Subject aliases
and the 5 session-offset overrides are **not** in the snapshot — they come from the
committed `pipeline_config.json`, exactly as production bidsify reads them.
`snapshot.load_inventory()` adapts the JSON into a `FlywheelCohortSpec` (the type
`make_fake_flywheel` already consumes); reproduction specs carry no synthetic
`outcome`/`plant_contrast` tags. **Snapshot-schema fidelity is load-bearing:** it
must carry exactly what bidsify reads for session numbering, run numbering, echo,
and fieldmap naming.

## Data flow

Per cohort, into a scratch root (`$SCRATCH/repro_<cohort>/`):

1. **Replay** — `load_inventory` → `FakeFlywheel` (returns empty NIfTI blobs) →
   real `run_bidsify` → stub BIDS tree (correct names, 0-byte BOLD/anat) → real
   `trim_bold` (idempotent; writes `NumberOfVolumesDiscardedByUser=7` sidecars) →
   real `events.create` (reads the real behavioral CSVs).
2. **Stage metrics** — symlink the real fMRIPrep confounds derivative, behavioral
   sourcedata, and `lev1_outliers.csv` into / alongside the stub tree so the
   generators read genuine metrics.
3. **Exclusions** — reuse `simulate_exclusions()`: run all 5 real generators
   (behavioral, motion, qa_decisions, lev1_outlier, collection) + `compile_exclusions`
   + `render_bidsignore_with_collection`, hermetically (paths redirected into the
   scratch root).
4. **Lev2 set** — `lev2_select` models the eligible set (see below).

## The three diffs + comparison semantics

`canonical.py` reduces both produced and reference artifacts to comparable,
**provenance-stripped** forms (lockfiles embed timestamps + code SHAs, so
byte-equality is impossible by construction):

1. **Filenames** — the produced **full BIDS file set** (bold, events.tsv, JSON
   sidecars, anat) as relative paths **vs** the real `discovery_bids` /
   `validation_bids` trees. Set equality (stub files have no content; only names
   are compared). Independent test of Flywheel→BIDS naming + trim/events outputs.
2. **Exclusion set** — the **gating key** is the tuple `(subject, session, task,
   run, action, source)` for `action ∈ {exclude, trim}` from the fresh compile
   **vs** the same tuples from the committed (regenerated) `<cohort>_lock.json`;
   plus the rendered `.bidsignore` glob-line set vs the committed one. The `reason`
   string is compared and **reported** but a reason-only difference is a WARNING,
   not a FAIL (reasons are generated text that can drift cosmetically without the
   exclusion decision changing).
3. **Lev2-eligible set** — modeled `{(subject, task, contrast)}` **vs** the set of
   fixed-effects contrast maps actually present in the real `lev1_*`/fixed-effects
   outputs that lev2 globs.

A diff is `{matched, only_in_produced, only_in_reference}` per layer; the cohort
**PASSES** iff all three `only_*` sets are empty.

## The lev2-eligible-set model + reference

`lev2_select` reproduces the selection deterministically (no real GLM needed):
BIDS func inventory → drop excluded (lockfile/`.bidsignore`) → drop rest + scans
with no events → apply the fixed-effects **`min_runs` floor** (a `(subject, task)`
with `< min_runs` surviving runs is `_desc-belowMinRuns`-tagged and excluded from
lev2) → expand to `{subject, task, contrast}` via the task contrast configs. It
reuses production selectors (`FileFinder`, the `min_runs` logic,
`lev2.discover_input_files`) rather than reimplementing them.

**Reference:** the set of fixed-effects contrast maps present in the real lev1 /
fixed-effects output dirs that lev2 actually consumes. A mismatch indicates either
an exclusion drift or a selection-logic drift — both in scope to catch.

## Reporting, gating, and the trim invariant

- **Report:** `repro_report.md` per cohort — the three diff tables (matched /
  only-in-produced / only-in-reference), overall PASS/FAIL, and provenance (code
  SHA, snapshot path, resolved real-input paths, fMRIPrep version).
- **Gating:** `reproduce_cohort.py` is the on-demand driver; the pytest wrapper
  runs it and **auto-skips** (via `pytest.importorskip`-style guards on the real
  input paths + snapshot) when inputs are absent, so it runs on Sherlock and skips
  in portable CI. The existing synthetic e2e test is unchanged.
- **Trim-before-fMRIPrep invariant:** the harness asserts, for each kept func scan,
  that the trimmed BOLD sidecar carries `NumberOfVolumesDiscardedByUser=7` **and**
  the matching fMRIPrep confounds-TSV row count equals the trimmed volume count
  (proves fMRIPrep saw trimmed data and did not double-discard). It also checks the
  fMRIPrep invocation carries `--dummy-scans 0`.

## Testing the harness (TDD)

Red-first unit tests on tiny synthetic fixtures:
- `snapshot.load_inventory` — JSON → spec adapter (session/acq ordering, echoes).
- `stage_metrics` — symlink correctness; sidecar/trim presence.
- `lev2_select` — min_runs floor, events/rest filtering, contrast expansion.
- `canonical` — provenance stripping; set extraction from a sample lockfile.
- `report` — diff rendering + PASS/FAIL logic.
The Sherlock e2e (`test_reproduce_cohort.py`) runs the real chain and auto-skips
when real inputs are absent.

## Prerequisites & sequencing

This harness asserts against the **regenerated** lockfiles, so:
1. validation `lev1_outliers.csv` completes (cohort QC, running 2026-06-27).
2. Recompile **both** lockfiles with all 5 generators (incl. `lev1_outlier`);
   review the exclusion-set diff vs the committed (stale) locks; commit the
   regenerated lockfiles + re-rendered `.bidsignore` (de-annex discovery's so a
   real copy is committed).
3. Capture the Flywheel inventory snapshots (one-time, needs auth).
4. Build + run this harness — which then guarantees the whole chain reproduces.

The harness is the durable verification that step 2's recompile is reproducible.

## Out of scope (YAGNI)

- Real GLM/fMRIPrep execution (stubs only; selection is modeled deterministically).
- A portable hermetic version with committed real-data fixtures (the synthetic
  harness already covers portable logic; this one is Sherlock-gated by design).
- Reproducing derivative *content* (only filenames + the exclusion/lev2 *sets*).
- Auto-capturing the Flywheel snapshot in CI (one-time manual capture; committed).
