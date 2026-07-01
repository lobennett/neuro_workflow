# Full Flywheel→lev2 Re-execution to Oak — Design

- **Date:** 2026-06-30
- **Status:** Approved (design); implementation plan to follow
- **Branch context:** work continues on `repro-harness-2026-06` (merged refactor + reproduce harness) at `/scratch/users/logben/neuro_workflow_refactor`
- **Supersedes/extends:** the pending "RECON Stage 5/7" finalization — instead of committing the scratch datasets in place, we produce fresh, version-controlled, read-only datasets on Oak via a full pipeline re-execution.

## 1. Purpose

Produce the **final, permanent, version-controlled, read-only BIDS datasets on Oak** (discovery, validation, excluded) **and** prove the pipeline is **fully executable end-to-end from Flywheel through second-level models**, by actually re-running it. This is the ultimate exercise of the codebase: a clean-slate re-execution whose primary scientific guarantee is that **exclusions are correctly mapped and respected at every stage**.

The datasets currently live on `$SCRATCH` (90-day purge, not backed up). Oak is purchased, backed-up, permanent. The reproducible *core* of each dataset is **the raw BIDS tree + the compiled exclusion lockfile** — everything downstream (fMRIPrep, lev1, lev2) is regenerable and is *not* the version-controlled artifact.

## 2. Goals / Non-goals

**Goals**
- Fresh BIDS datasets on Oak (discovery/validation/excluded), datalad-tracked, annex-locked, read-only.
- A single, internally-consistent, clean-SHA exclusion lockfile per cohort covering **all five sources** (behavioral, collection, qa_decisions, motion, lev1_outlier).
- Exclusions changed **only deliberately**, with evidence, gated by human sign-off at the stage where each source's evidence first exists.
- A demonstrable end-to-end run: live Flywheel pull → BIDS → fMRIPrep → lev1 (surface) → lev2, plus a `reproduce_cohort` **PASS** re-pointed at the Oak datasets.
- **Zero overwrite/deletion of anything already on Oak.**

**Non-goals**
- Byte-reproducibility of fMRIPrep derivatives (explicitly accepted as non-reproducible/regenerable).
- Dual-task lev1/lev2 (all 10 dual-task YAMLs are placeholders → **base-tasks-only** this pass; documented follow-on).
- Migrating iProc (33 TB) or other non-core derivatives to Oak.

## 3. Key decisions (settled with the user)

| Decision | Choice | Rationale |
|---|---|---|
| Primary goal | Permanent Oak artifact **+** full executability proof | The ultimate goal of the codebase |
| Flywheel→BIDS | **Live pull + drift guard** | Honest end-to-end proof, anchored so exclusion keys can't silently drift |
| Task scope | **Base tasks only (8)** | Faithful reproduction of the current validated science |
| Exclusion drift | **Recompute + mandatory diff-review gate** | Clean slate with zero silent drift |
| Compute timing | **Concurrent on russpold, medium throttle** | iProc campaign finishing soon; medium throttle shares nodes |
| Dataset naming | **Fresh Oak datalad datasets**, repoint registry; keep scratch read-only cross-check until Oak PASSes | Preserves a fallback; no premature deletion |
| Compute I/O | Work-dir on `$SCRATCH`; outputs to scratch then `rsync`→Oak | Sherlock policy: heavy job I/O on scratch, not Lustre-Oak |
| Derivatives placement | BIDS raw annexed+committed; `derivatives/` = plain read-only files | Keeps annex from re-hashing terabytes of regenerable output |
| **Oak safety** | **Never overwrite/delete existing Oak content** | Explicit user directive |

## 4. Why the design is staged (the ordering constraint)

The five exclusion sources become knowable at different stages:

- **Pre-fMRIPrep** (knowable right after BIDS): `behavioral` (reads `sourcedata` CSVs), `collection` (static committed file), `qa_decisions` (human QA TSV).
- **Requires fMRIPrep**: `motion` (reads `*_desc-confounds_timeseries.tsv`).
- **Requires lev1**: `lev1_outlier` (reads cohort-QC `lev1_outliers.csv`).

Therefore a "commit the exclusions at the Flywheel→BIDS point" is only *partially* possible. The design layers exclusions as their evidence appears, with a datalad commit and a diff-gate at each layer. This is exactly "exclusions respected at each stage," done honestly.

Enforcement is **key-based, not `.bidsignore`-based**: lev1's `runner.process_single_run` skips a run iff `sub_ses_task-T_run` is in the compiled set; `.bidsignore`/`EXCLUSIONS.md` are renders of the same lockfile. The exclusion set is compiled by dataset **name** and is fully **path-independent** — moving to Oak cannot change *what* is excluded.

## 5. Architecture — staged pipeline with per-stage commits + gates

```
Stage 0  Pre-flight & provenance freeze          (no compute)
Stage 1  Flywheel→BIDS (live + Drift Gate)       → datalad commit #1 (raw BIDS + pre-fMRIPrep exclusions)
Stage 2  fMRIPrep                                → Exclusion Gate A (motion) → datalad commit #2
Stage 3  lev1 surface (8 base tasks) + cohort QC → Exclusion Gate B (lev1_outlier) → datalad commit #3 (FINAL lockfile)
Stage 4  lev2 (base-task contrasts, surf+vol)    → rsync derivatives→Oak
Stage 5  Reproduce certification (Oak)           → reproduce_cohort PASS
Stage 6  Finalize                                → datalad save → git annex lock → chmod read-only
```

### Stage 0 — Pre-flight & provenance freeze (no compute)
1. **Commit untracked determinism artifacts**: `data/repro/fw_inventory_{discovery,validation}.json`, the `qc_decisions.tsv` and `lev1_outliers.csv` reference inputs.
2. **Pin `flywheel-sdk`** — install from `uv.lock` (not a fresh pyproject `>=17.0` resolve) so the live pull/query behaves identically; rebuild `neuro_workflow.sif` only if required, from the lockfile.
3. **Verify apptainer binds `/oak`** into the container (`apptainer exec neuro_workflow.sif ls /oak`); if not, add `-B /oak:/oak` to `templates/bidsify.sbatch`. *Highest-risk item for the critical Flywheel→BIDS-to-Oak step.*
4. **Add `--bids-dir` / `--out-root` CLI flags** (or equivalent) to the hardcoded-`/scratch` operational scripts: `reproduce_cohort.py` (`_COHORT_PATHS`), `recompile_delta.py`, `reconcile_audit.py`, `remove_orphan_derivatives.py` — so the whole reconcile+verify chain can target Oak without source edits.
5. **`datalad create` fresh datasets on Oak** (annex, MD5E backend, `.gitattributes` mirroring `excluded_bids`) at the new paths (§6); register Oak paths in `~/.neuro_workflow/datasets.json` (new dataset entries; scratch entries retained for cross-check).
6. **Assert Oak write targets are empty/new** before any stage runs (no-overwrite guardrail, §6).

### Stage 1 — Flywheel→BIDS (live pull + Drift Gate) → **datalad commit #1**
1. **Capture a fresh `fw_inventory`** via `capture_fw_inventory.py` and **diff it against the committed snapshot** (`data/repro/fw_inventory_<cohort>.json`).
   - **Drift Gate:** any changed/added/removed acquisition, or any change that would renumber `ses-NN` (session timestamps/counts), **halts** for human review. ses-NN is derived by ascending timestamp, so drift here is the primary threat to exclusion-key stability.
2. **Live `bidsify`** → `trim_bold` → **reuse the committed reconciliation manifests** (`config/manifests/reconciliation_{cohort}.tsv`); re-run `reconcile_sessions.py` only to surface *genuinely-new* `pending` rows for review (do **not** blindly regenerate — that resets human decisions to pending).
3. `migrate_behavioral` into **this dataset's own** `sourcedata/in_scanner_behavior` (reads `_archive/.../raw_cleaned` **read-only**) → `events create` + `events qc` → BIDS-validate.
4. Compile the **pre-fMRIPrep exclusions** (behavioral + collection + qa_decisions) → render `.bidsignore` + `EXCLUSIONS.md`.
5. **datalad commit #1** = raw BIDS + partial exclusion lockfile. *This is the "state at the Flywheel→BIDS point."*

> **Cohort scope for Stages 2–5:** the **excluded** cohort (11 fully-excluded subjects) is a **BIDS-only artifact** — it receives Stages 0/1/6 (create → Flywheel→BIDS → commit → read-only) but **not** fMRIPrep/lev1/lev2/reproduce. Stages 2–5 apply to **discovery + validation** only.

### Stage 2 — fMRIPrep → **Exclusion Gate A + datalad commit #2**
1. Submit fMRIPrep (25.2.4) as a SLURM array on **russpold, medium throttle** (e.g. `%4`–`%8`), **24 CPU / 160 GB** (template defaults 8 CPU/64 GB would OOM vs observed ~95–113 GB MaxRSS), work-dir on `$SCRATCH`. Output-spaces: **match production** (MNI2009c res-1 + MNI6Asym res-2 + fsaverage + fsnative + T1w + func) so xcp_d + volume-lev2 remain feasible.
2. `rsync` derivatives → Oak `derivatives/fmriprep_25.2.4/` (plain files); rebuild `fmriprep_25.2.4_input` + `xcp_d_26.0.2_input` symlink views (drop `.bidsignore`'d scan-keys).
3. Recompile exclusions **adding motion** → **Exclusion Gate A** (§7): diff new motion set vs committed lockfile; any add/drop halts with FD/DVARS evidence for sign-off.
4. **datalad commit #2** = exclusion lockfile now includes motion.

### Stage 3 — lev1 surface (8 base tasks) + cohort QC → **Exclusion Gate B + datalad commit #3**
1. Run **lev1 surface** for the 8 base tasks (`--base-tasks`), reading BIDS events + fMRIPrep fsaverage6 GIFTI via `FileFinder`; scan-level + per-contrast exclusions honored from the compiled lockfile; `min_runs=2` (`_desc-belowMinRuns` tagging).
2. Run cohort QC → `lev1_outliers.csv`.
3. Recompile exclusions **adding lev1_outlier** → **Exclusion Gate B**: diff vs committed; sign-off on any change.
4. **datalad commit #3** = **final** exclusion lockfile (all 5 sources, single clean SHA) + final `.bidsignore` + `EXCLUSIONS.md`.

### Stage 4 — lev2 (base-task contrasts) 
- Run lev2 for base-task contrasts, **surface** (sign-flip permutation, seeded) and **volume** (FSL randomise — verify seed support, else prefer surface for reproducibility). `rsync` outputs → Oak. Prevalence dashboards are a cheap post-lev2 follow-on.

### Stage 5 — Reproduce certification (Oak)
- Re-point `reproduce_cohort` (`--bids-dir`/`--out-root`, from Stage 0) at the **Oak** datasets → run → require **PASS** on all three diffs (filenames / exclusion-set / lev2-eligible). This certifies the Oak datasets reproduce from the frozen snapshot + real inputs.

### Stage 6 — Finalize
- Per cohort, **in a Slurm job with a verified annex** (git-annex is absent on the login node; group datalad module is broken; use the user-local `datalad`):
  `datalad save` final state → `git annex lock` (collapse unlocked working copies to symlinks, matching `excluded_bids`) → **`chmod` read-only last** (files `r--r--…`, dirs `dr-xr-…`).
- Derivatives under `derivatives/` are chmod'd read-only as plain files (not annex-committed).
- Write `docs/.../REEXECUTION-RUN-LOG.md` + a provenance manifest: live-pull date, code SHA, config_version, exclusion lockfile SHA, and the reproduce PASS certificate.
- Retire the scratch datasets **only after** the Oak reproduce PASSes.

## 6. Oak layout & no-overwrite guardrails

**New, non-colliding target paths** (nothing legacy is touched):
```
/oak/stanford/groups/russpold/data/network_grant/bids/discovery
/oak/stanford/groups/russpold/data/network_grant/bids/validation
/oak/stanford/groups/russpold/data/network_grant/bids/excluded
```
- These sit **beside** the legacy `discovery_BIDS_20250402/`, `validation_BIDS/`, and the shared `sourcedata/` — none of which is written, moved, or deleted.
- Each new dataset is **self-contained**: its own `sourcedata/in_scanner_behavior` (migrated fresh from the read-only `_archive/.../raw_cleaned`), so the shared `network_grant/sourcedata/` is never rewritten.
- **Guardrail:** Stage 0 asserts each Oak target directory is empty/new before proceeding; any pipeline write path resolving to an existing legacy tree is a hard error.
- Oak has ample room (~101 TB / ~15.7 M inodes free); raw BIDS is ~20 GB/cohort, fMRIPrep ~3.4 TB — comfortably fits.

## 7. Exclusion diff-review gate (the critical mechanism)

A small gate utility (extending `testing/reproduce/canonical.py`) runs after each recompile:
1. Compute `compiled_to_keyset(new_compiled)` and `compiled_to_keyset(committed_lockfile)`.
2. If the **symmetric difference is empty** → adopt + `datalad save` automatically.
3. If **non-empty** → **non-zero exit** + a `exclusion_gate_report_<cohort>_<stage>.md`: each added/dropped scan-key with its evidence (motion: mean-FD / prop-FD>0.5 / prop-std_dvars>1.5; lev1_outlier: VIF / outlier-voxel stats). The pipeline **halts**; the user reviews and signs off; only then is the new set adopted + committed.

This guarantees exclusions change **only deliberately, with evidence, at the stage where the evidence first exists** — and never silently from fMRIPrep numerical drift.

## 8. Path retarget / config changes (summary)

- **`~/.neuro_workflow/datasets.json`** (machine-local): add Oak dataset entries (`bids_dir` → Oak paths). Retain scratch entries for cross-check.
- **`config/pipeline_config.json`**: **no change** (path-free; drives rosters/aliases/overrides by name).
- **`templates/bidsify.sbatch`**: add `-B /oak:/oak` if not auto-mounted.
- **Operational scripts** (`reproduce_cohort.py`, `recompile_delta.py`, `reconcile_audit.py`, `remove_orphan_derivatives.py`): add `--bids-dir`/`--out-root`.
- **Work dirs** stay on `$SCRATCH` (`fmriprep.py` already reads `$SCRATCH`).
- **Container image / templateflow** on `/home/groups/russpold`: no change.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Flywheel content drift renumbers `ses-NN` → orphaned exclusion keys | **Drift Gate** (Stage 1): fresh snapshot diffed vs committed before any write |
| Fresh reconcile resets human manifest decisions to `pending` | **Reuse committed manifests**; re-review only genuinely-new pending rows |
| Fresh fMRIPrep perturbs motion/lev1_outlier exclusions | **Exclusion Gates A/B** with evidence + sign-off; nothing adopted silently |
| `flywheel-sdk` floating dep changes pull behavior | **Pin from `uv.lock`** in Stage 0 |
| `/oak` not bound into apptainer → bidsify write fails | **Verify/patch bind** in Stage 0 |
| Overwriting legacy Oak content | New non-colliding paths + Stage-0 empty-target assertion + read-only-source reads |
| datalad save hangs on hundreds of ~150 MB NIfTIs; annex unavailable on login node | **Run save in a Slurm job** with verified user-local annex; lock before chmod |
| Heavy Lustre-Oak I/O during 24 h jobs | Compute on `$SCRATCH`, `rsync`→Oak via DTN |
| fMRIPrep template defaults OOM (64 GB vs ~113 GB) | Submit 24 CPU / 160 GB explicitly |
| iProc campaign contention on russpold | **Medium array throttle**; iProc finishing soon |
| Volume-lev2 randomise non-deterministic if seed unsupported | Verify randomise seed support; else prefer surface lev2 |

## 10. Success criteria

1. Three Oak datasets exist at the new paths, datalad-committed, annex-locked, read-only; nothing legacy on Oak altered.
2. A single clean-SHA exclusion lockfile per cohort covering all five sources; every exclusion change signed off with evidence.
3. `reproduce_cohort` re-pointed at Oak → **PASS** (filenames / exclusion-set / lev2-eligible) for discovery **and** validation.
4. lev1 (8 base tasks) + lev2 (base-task contrasts) outputs present on Oak for both analysis cohorts.
5. `REEXECUTION-RUN-LOG.md` + provenance manifest records the live-pull date, SHAs, and PASS certificate.
6. Synthetic e2e test suite green (regression safety net).

## 11. Follow-ons (out of scope this pass)

- **Dual-task modeling**: author the 10 real dual-task regressor/contrast YAMLs (from the reference design) → run lev1/lev2 for the dual tasks. Blocked on science-config decisions.
- **Prevalence dashboards** regenerated from the Oak lev2 surface outputs.
- **Retire/purge scratch datasets** once the Oak reproduce PASSes.
- Optionally extend `reproduce_cohort` with a byte-level BIDS lineage check vs the live pull (currently a content sanity-diff).
