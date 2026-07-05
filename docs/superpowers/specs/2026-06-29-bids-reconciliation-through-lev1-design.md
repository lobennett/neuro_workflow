# Reconcile + datalad-commit reproducible BIDS through lev1 — design

**Date:** 2026-06-29
**Author:** Logan Bennett (logben@stanford.edu)
**Status:** proposed (pre-implementation)
**Branch:** `repro-harness-2026-06`

## Goal

End state: final **datalad-committed** BIDS datasets on `$SCRATCH` for **discovery**,
**validation**, and **excluded**, fully reproducible from the pipeline **through
first-level model exclusions**. Understand every divergence between the live scratch
datasets + their derivatives and what the current codebase produces, reconcile them,
rerun lev1 + anything else needed, and commit.

Out of scope today: lev2 group analyses, XCP-D, iProc/MSHBM, prevalence (rerun later
off the reconciled base).

## Context: the directory architecture

Per cohort on scratch (e.g. `/scratch/users/logben/discovery_bids`):
- The **full BIDS dataset** (all scans; datalad/git-annex).
- `derivatives/fmriprep_25.2.4_input` — a **symlink view**: the `.bidsignore`-filtered
  subset that fMRIPrep actually ran on (via `--bids-dir-override`).
- `derivatives/fmriprep_25.2.4` — fMRIPrep output (derivatives still land in the
  registered dataset).
- `derivatives/lev1_surface`, `xcp_d_*`, `iproc*` — downstream (out of scope today).

Oak holds only **stale snapshots** (`discovery_BIDS_20250402`, `validation_BIDS`) — not
the live copies. The live datasets are on scratch.

## Divergence axes (what "diverged" means)

1. **BIDS files** — the reproduce harness already proved scans/structure/trim reproduce
   from the Flywheel inventory snapshot; events 99.4% identical (s10 ses-02 shapeMatching
   + s43 ses-11 SSwFlanker corrected this cycle). Effectively reconciled. Accepted as
   harness-proven (no byte-level re-bidsify).
2. **`.bidsignore` / exclusions** — recompiled with the per-contrast lev1_outlier code +
   the behavioral roster fix; lockfiles committed (discovery 44, validation 142). The
   rendered `.bidsignore` is a **verified clean superset** (nothing un-excluded).
3. **Symlink views** — `fmriprep_25.2.4_input` was built from the OLD `.bidsignore` → now
   stale (includes scans the new `.bidsignore` excludes).
4. **lev1 outputs** — computed under old exclusions/events.

**Rerun classes:** events-changed scans need a full per-run GLM (events feed the design
matrix); exclusion-changed cells need only **fixed-effects recombination** (per-run
`indiv_contrasts` are unchanged) — fast. Per-run VIF is stable across FE-only reruns, so
no re-QA → re-compile loop (except events-changed scans, whose VIF is re-checked).

## Confirmed decisions

- **`.bidsignore`:** de-annex → committed as a git-tracked plain file (diff-able, harness
  reads it directly, clones don't need annex-get).
- **fMRIPrep orphans** (derivatives for now-excluded scans): **leave in place + record**;
  lev1/lev2 honor exclusions so they never feed models. Non-destructive.
- **Dual-task lev1** (s43 ses-11 SSwFlanker): **defer** — events corrected/committed; lev1
  runs later when dual-task YAML configs are finalized. Today covers single-task only.
- **lev1 rerun mode:** **fixed-effects-only** for exclusion-changed cells if `lev1.run`
  supports it, else full-GLM those cells.

## Staged reconciliation pipeline (Approach A: audit-first, targeted)

Each stage is idempotent + logged; annex-careful (regenerate → `git annex add`, never
write through a symlink); `datalad save` scoped to explicit paths.

**Stage 0 — Divergence audit (read-only).** Per cohort, enumerate:
(a) symlink-view membership vs new `.bidsignore` keep-set → `{in-view-but-now-excluded,
keep-but-not-in-view}`; (b) fMRIPrep outputs vs keep-set → orphans / missing;
(c) lev1 affected cells = events-changed scans ∪ exclusion-changed `(subject,task)`.
Output: a divergence report + exact rerun worklists. Nothing mutated.

**Stage 1 — `.bidsignore` sync.** Write the rendered `.bidsignore` (clean superset) into
each dataset as a de-annexed git-tracked file; `datalad save` that path.

**Stage 2 — Rebuild symlink views.** Regenerate `fmriprep_25.2.4_input` from the new
keep-set so it matches the committed exclusions; newly-excluded scans drop out.

**Stage 3 — fMRIPrep (targeted).** Expected **0 reruns** (set only grew; events don't feed
fMRIPrep). Newly-included scans (expected none) → run fMRIPrep. Orphans → leave + record.

**Stage 4 — lev1 (targeted).** Events-changed → full GLM (s10 done; s43 deferred).
Exclusion-changed `(subject,task)` → FE-only rerun with the new `compiled_exclusions`
(per-contrast + behavioral). Re-QA only events-changed scans' VIF.

**Stage 5 — datalad commit + provenance.** Commit discovery / validation / excluded BIDS
on scratch (BIDS + de-annexed `.bidsignore` + rebuilt view + pinned fMRIPrep + reconciled
lev1). Record code SHA + exclusion lockfile + fMRIPrep version in the commit/provenance.
Set datasets read-only.

**Stage 6 — Reproducibility proof.** Add the per-contrast model to
`testing/reproduce/lev2_select.py` (canonical already handles `exclude-contrast`); run
`reproduce_cohort {discovery,validation}` → PASS. That PASS is the standing guarantee.

**Excluded dataset.** `excluded_bids` (11 fully-excluded subjects) is not in the lev1
pipeline; reconcile = verify the roster + `datalad save`/commit. Minimal.

## Units (each independently testable)

- `divergence_audit` — pure read; emits the report + worklists (Stage 0).
- view rebuild — regenerate the `.bidsignore`-filtered symlink tree (Stage 2).
- lev1 FE-only path — confirm/exercise fixed-effects-only rerun (Stage 4).
- datalad commit wrapper — scoped, annex-careful commit of each dataset (Stage 5).
- harness `lev2_select` per-contrast model + `reproduce_cohort` PASS (Stage 6).

## Risks / mitigations

- **Annex corruption** (prior incident): never write through annex symlinks; always
  regenerate → `git annex add`; verify object integrity post-write.
- **HOME quota** (recurring): keep compiled/exclusions reads light; commit small; the
  recompile already wrote `compiled_exclusions.json`.
- **FE-only unsupported:** fall back to full-GLM the affected cells (still targeted).
- **VIF drift on events-changed scans:** re-QA s10 shapeMatching; if its per-contrast
  exclusions change, re-compile + re-render before the final commit.

## Out of scope (YAGNI)

- Byte-level re-bidsify from Flywheel (harness proves equivalence).
- fMRIPrep full rerun (no preprocessing inputs changed).
- lev2 / XCP-D / iProc / MSHBM / prevalence reruns.
