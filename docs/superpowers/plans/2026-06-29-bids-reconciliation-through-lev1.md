# BIDS Reconciliation Through lev1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the live scratch BIDS datasets + their derivative chain to the current codebase + recompiled exclusions, rerun only what diverged through lev1, and datalad-commit reproducible discovery/validation/excluded datasets.

**Architecture:** Audit-first, targeted (Approach A). A read-only divergence audit produces exact rerun worklists; then `.bidsignore` sync → rebuild symlink views → targeted fMRIPrep (expected none) → targeted lev1 (FE-only for exclusion-changed, full-GLM for events-changed) → reproduce PASS → datalad commit. No new BIDS generation (harness-proven).

**Tech Stack:** Python (uv), pytest, SLURM (`sbatch -p russpold --wait`), git-annex 8.20210622, datalad, the `neuro_workflow` package on branch `repro-harness-2026-06` in worktree `/scratch/users/logben/neuro_workflow_refactor`.

**Environment rules:** Never run Python on the login node — use `sbatch -p russpold --wait` with `module load uv` + `export UV_CACHE_DIR=/scratch/users/logben/.uv_cache`. Annex-careful: never write through an annex symlink; regenerate → `git annex add` (git-annex at `/share/software/user/open/git-annex/8.20210622`). `datalad save` scoped to explicit paths (datasets carry pre-existing dirty state). Watch HOME quota (write small).

---

## Task 1: Divergence audit (read-only) — Stage 0

**Files:**
- Create: `scripts/reconcile_audit.py`
- Test: `tests/analysis/e2e/test_reconcile_audit.py`

Produces, per cohort, the exact divergences + rerun worklists. Pure read; nothing mutated.

- [ ] **Step 1: Write the failing test for the membership-diff helper**

```python
# tests/analysis/e2e/test_reconcile_audit.py
def test_view_membership_diff_flags_now_excluded_and_newly_included(tmp_path):
    from scripts.reconcile_audit import view_membership_diff
    view_scans = {"sub-s10/ses-02/func/sub-s10_ses-02_task-shapeMatching_run-1",
                  "sub-s10/ses-01/func/sub-s10_ses-01_task-cuedTS_run-1"}      # old view
    keep_scans = {"sub-s10/ses-02/func/sub-s10_ses-02_task-shapeMatching_run-1",
                  "sub-s10/ses-05/func/sub-s10_ses-05_task-goNogo_run-1"}      # new keep-set
    now_excluded, newly_included = view_membership_diff(view_scans, keep_scans)
    assert now_excluded == {"sub-s10/ses-01/func/sub-s10_ses-01_task-cuedTS_run-1"}
    assert newly_included == {"sub-s10/ses-05/func/sub-s10_ses-05_task-goNogo_run-1"}
```

- [ ] **Step 2: Run it, verify it fails** — `sbatch ... uv run pytest tests/analysis/e2e/test_reconcile_audit.py -q` → FAIL (import error).

- [ ] **Step 3: Implement `reconcile_audit.py`**

Core helpers (pure):
```python
def view_membership_diff(view_scans: set[str], keep_scans: set[str]) -> tuple[set, set]:
    """Return (now_excluded, newly_included) = (in view not in keep, in keep not in view)."""
    return view_scans - keep_scans, keep_scans - view_scans
```
Plus an `audit(cohort)` that, for `discovery`/`validation`, computes:
- **(a) view membership:** scan-keys present in `<bids>/derivatives/fmriprep_25.2.4_input` (walk `sub-*/ses-*/func/*_bold.nii.gz`, strip echo/suffix to a scan-key) vs the keep-set = full-BIDS bold scan-keys minus the new `.bidsignore` globs (reuse `scripts/fmriprep_preflight.py:parse_bidsignore` + `path_matches_any`).
- **(b) fMRIPrep outputs:** scan-keys with a `*_desc-confounds_timeseries.tsv` under `derivatives/fmriprep_25.2.4` vs keep-set → orphans (have fMRIPrep, now excluded) + missing (in keep-set, no fMRIPrep — expect none).
- **(c) lev1 affected cells:** events-changed scans (hardcode the two known: `sub-s10/ses-02/shapeMatching`, `sub-s43/ses-11/stopSignalWFlanker`) ∪ exclusion-changed `(subject,task)` = the `(subject, bare-task)` of every `exclude-contrast` entry + every NEW scan-level `exclude` entry in `compiled_exclusions.json` vs the committed `.bidsignore`.
Write a markdown report to `/scratch/users/logben/reconcile_audit_<cohort>.md` and a JSON worklist to `/scratch/users/logben/reconcile_worklist_<cohort>.json` with keys `now_excluded_from_view`, `newly_included`, `fmriprep_orphans`, `fmriprep_missing`, `lev1_events_changed`, `lev1_exclusion_changed_cells`.

- [ ] **Step 4: Run test, verify PASS.**

- [ ] **Step 5: Run the real audit** (both cohorts) via `sbatch ... uv run python scripts/reconcile_audit.py discovery validation`; read the two reports. **Confirm the expected shape:** `newly_included == []` and `fmriprep_missing == []` (set only grew). If either is non-empty, STOP and surface — it means fMRIPrep reruns are needed (Stage 3).

- [ ] **Step 6: Commit** — `git add scripts/reconcile_audit.py tests/analysis/e2e/test_reconcile_audit.py && git commit -m "feat(reconcile): divergence audit + rerun worklists (Stage 0)"`

---

## Task 2: `.bidsignore` sync (de-annexed) — Stage 1

**Files:**
- Modify (data, in each BIDS dataset): `/scratch/users/logben/{discovery,validation}_bids/.bidsignore`
- Inputs: `/scratch/users/logben/recompile_{discovery,validation}.bidsignore` (already rendered, verified clean superset)

Per cohort, in an `sbatch` job (git-annex on PATH):

- [ ] **Step 1: De-annex + replace + datalad save**, e.g. for discovery:

```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
cd /scratch/users/logben/discovery_bids
git rm --cached .bidsignore 2>/dev/null || true          # drop annex pointer from index
rm -f .bidsignore                                         # remove symlink
cp /scratch/users/logben/recompile_discovery.bidsignore .bidsignore   # plain file
printf '.bidsignore annex.largefiles=nothing\n' >> .gitattributes      # force git-track, not annex
git add .gitattributes .bidsignore
git config user.name "Logan Bennett"; git config user.email "logben@stanford.edu"
git commit -q -m "exclusions: sync .bidsignore to recompiled set (de-annexed, git-tracked)"
```

- [ ] **Step 2: Verify** `.bidsignore` is now a regular git-tracked file (`git -C <bids> ls-files --eol .bidsignore` shows a real blob, not annex symlink; `test -L .bidsignore` is false).

- [ ] **Step 3: Repeat for validation.**

- [ ] **Step 4: No worktree commit** (this is in the BIDS datasets, not the code repo).

---

## Task 3: Rebuild symlink views — Stage 2

**Files:** regenerates `/scratch/users/logben/{discovery,validation}_bids/derivatives/fmriprep_25.2.4_input/`

- [ ] **Step 1: Re-run the preflight view-builder** per cohort:

```bash
sbatch -p russpold --time=00:30:00 --mem=8G --wrap \
  "cd /scratch/users/logben/neuro_workflow_refactor && module load uv && \
   export UV_CACHE_DIR=/scratch/users/logben/.uv_cache && \
   uv run python scripts/fmriprep_preflight.py discovery --version 25.2.4" \
  --output=/scratch/users/logben/neuro_workflow_refactor/.preflight_disc_%j.out --wait
```
(then validation). `fmriprep_preflight.py` overwrites the `_input` view from the current `.bidsignore`.

- [ ] **Step 2: Verify** the rebuilt view no longer contains the `now_excluded_from_view` scans from the Task 1 worklist (grep the worklist scan-keys are absent under `_input/`), and every keep-set scan IS linked. Sanity: each subject still has a T1w (preflight checks this; confirm exit 0).

---

## Task 4: fMRIPrep reconcile (targeted) — Stage 3

- [ ] **Step 1: Confirm 0 reruns** from the Task 1 worklist: `newly_included == []` and `fmriprep_missing == []`. If true, no fMRIPrep runs. Record `fmriprep_orphans` in the audit report (left in place; lev1/lev2 honor exclusions).
- [ ] **Step 2: If non-empty** (unexpected): for each `newly_included`/`missing` scan, submit fMRIPrep via the existing pipeline (`uv run neuro-run submit fmriprep <cohort> --version 25.2.4 --bids-dir-override <view> --subjects <subj>`); otherwise skip. (Expected: skip.)

---

## Task 5: lev1 reconcile (targeted) — Stage 4

**Files:** writes under `/scratch/users/logben/lev1_{discovery,validation}/`; reads `~/.neuro_workflow/exclusions/<cohort>/compiled_exclusions.json` (already recompiled).

- [ ] **Step 1: Verify the FE-only path.** On ONE exclusion-changed single-task cell (e.g. `sub-s10 task-shapeMatching`, which has per-contrast exclusions), run lev1 with `--skip-existing` + the new exclusions and confirm it (a) skips the per-run GLM and (b) recomputes fixed-effects honoring `exclude-contrast` (i.e. a contrast that lost runs gets `_desc-belowMinRuns` or fewer input runs). If `--skip-existing` also skips fixed-effects, first `rm -rf <results>/sub-s10/task-shapeMatching/fixed_effects` to force recompute, then re-run.

```bash
sbatch -p russpold --time=01:00:00 --mem=32G --cpus-per-task=4 --wrap \
 "cd /scratch/users/logben/neuro_workflow_refactor && module load uv && export UV_CACHE_DIR=/scratch/users/logben/.uv_cache && \
  uv run python -m neuro_workflow.analysis.lev1.run --subj-id sub-s10 --task-name shapeMatching \
  --bids-dir /scratch/users/logben/discovery_bids \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --results-dir /scratch/users/logben/lev1_discovery \
  --exclusions-file \$HOME/.neuro_workflow/exclusions/discovery/compiled_exclusions.json \
  --space MNI --mni-template MNI152NLin6Asym --mni-res 2 --within-subject-threshold 1.0 \
  --skip-existing --allow-dirty" \
  --output=/scratch/users/logben/neuro_workflow_refactor/.lev1fe_%j.out --wait
```
Inspect: `find /scratch/users/logben/lev1_discovery/sub-s10/task-shapeMatching/fixed_effects -name '*belowMinRuns*'` and confirm the per-run `indiv_contrasts` mtimes did NOT change (GLM skipped).

- [ ] **Step 2: Build the affected-cell list** from `reconcile_worklist_<cohort>.json` `lev1_exclusion_changed_cells` (single-task only; dual-task deferred per spec). For discovery this is the shapeMatching subjects + any behavioral-excluded single-task cells; for validation likewise.

- [ ] **Step 3: Submit FE-only reruns** for all affected single-task `(subject,task)` cells as a small array (same invocation as Step 1, `--skip-existing`, per cell). Use `--wait` or poll `sacct`.

- [ ] **Step 4: Events-changed cells.** `sub-s10 ses-02 shapeMatching` lev1 was already re-run from corrected events (fixed-effects refreshed); just re-run it cleanly now (worktree is committed, so provenance writes succeed) WITHOUT `--skip-existing` to force a full GLM from the corrected events. `sub-s43 ses-11 stopSignalWFlanker` is dual-task → DEFER (events committed; lev1 later).

- [ ] **Step 5: Re-QA events-changed scans' VIF.** Re-run cohort QC (`neuro_workflow.qa.lev1_outliers`) over the updated `lev1_discovery` and diff the s10 shapeMatching per-contrast VIF rows vs the committed `lev1_outliers.csv`. If they changed enough to alter `strict_vif` firing, re-run the lev1_outlier generator + `compile_exclusions` + re-render `.bidsignore` (Task 2) + the affected FE rerun (Step 3) once more. If unchanged (expected — only events-changed scan's VIF could move), proceed.

---

## Task 6: Harness per-contrast model + reproduce PASS — Stage 6

**Files:**
- Modify: `src/neuro_workflow/testing/reproduce/lev2_select.py`
- Test: `tests/analysis/e2e/test_reproduce_units.py`

- [ ] **Step 1: Write a failing test** for per-contrast lev2 eligibility:

```python
def test_lev2_eligible_drops_contrast_excluded_below_min_runs(tmp_path):
    from neuro_workflow.testing.reproduce.lev2_select import lev2_eligible_set
    # 2 runs of shapeMatching for sub-s10, contrast DDS excluded on both runs ->
    # 0 surviving runs for (s10, shapeMatching, DDS) -> dropped from eligible set
    # (build a tiny BIDS+fmriprep stub + excluded_keys incl exclude-contrast)
    ...
    elig = lev2_eligible_set(bids_dir, fmriprep_dir, subjects=["sub-s10"],
                             tasks=["shapeMatching"], excluded_keys=keys, min_runs=2)
    assert ("sub-s10", "shapeMatching", "DDS") not in elig
    assert ("sub-s10", "shapeMatching", "SSS") in elig
```

- [ ] **Step 2: Run it, verify it fails.**

- [ ] **Step 3: Extend `lev2_select.lev2_eligible_set`** to accept the `exclude-contrast` keys: when expanding `(subject,task)` to `(subject,task,contrast)`, drop a contrast whose surviving runs (runs minus contrast-excluded runs for that contrast) fall below `min_runs`. Reuse `canonical.compiled_to_keyset`'s 7-tuple (contrast in slot 7).

- [ ] **Step 4: Run test, verify PASS; run full `tests/analysis/e2e/test_reproduce_units.py` (expect all pass).**

- [ ] **Step 5: Capture Flywheel snapshots** if not already present (`uv run python scripts/capture_fw_inventory.py discovery validation` — needs Flywheel auth; snapshots already at `data/repro/fw_inventory_*.json` from this cycle, so likely skip).

- [ ] **Step 6: Run `reproduce_cohort`** for both cohorts:
```bash
sbatch ... uv run python scripts/reproduce_cohort.py discovery --out /scratch/users/logben/repro_discovery
sbatch ... uv run python scripts/reproduce_cohort.py validation --out /scratch/users/logben/repro_validation
```
Iterate to **PASS** (exit 0). A FAIL prints the 3-diff (filenames / exclusion-set / lev2-set); fix the modeled side or the data until green.

- [ ] **Step 7: Commit** the harness change — `git add src/neuro_workflow/testing/reproduce/lev2_select.py tests/analysis/e2e/test_reproduce_units.py && git commit -m "feat(reproduce): per-contrast lev2 eligibility model; reproduce_cohort PASS"`

---

## Task 7: datalad commit + provenance — Stage 5 (after reproduce PASS)

For each of discovery / validation (in an `sbatch` job, git-annex on PATH):

- [ ] **Step 1: Stage the reconciled state** — `.bidsignore` (Task 2, already committed), rebuilt `_input` view, lev1 outputs are NOT in the BIDS dataset (they live in `/scratch/users/logben/lev1_*`, a separate location) — so the BIDS-dataset commit covers BIDS + `.bidsignore` + the `_input` view + any events.tsv changes (s10 shapeMatching re-key already datalad-saved). Run `datalad status` scoped to confirm what's uncommitted.

- [ ] **Step 2: `datalad save`** the reconciled paths with a provenance message recording code SHA (`git -C <worktree> rev-parse --short HEAD`), exclusion lockfile path, fMRIPrep version 25.2.4. Scope to explicit paths (do NOT sweep the pre-existing dirty `derivatives/` state unrelated to this reconcile — `datalad save <.bidsignore> <derivatives/fmriprep_25.2.4_input> <changed events>`).

- [ ] **Step 3: Excluded dataset** — verify `/scratch/users/logben/excluded_bids` holds the right 11-subject roster (`pipeline_config.json` excluded sample); `datalad save` it (no lev1 pipeline). 

- [ ] **Step 4: Set datasets read-only** (matching the project's post-update convention): `chmod -R a-w` on the three dataset trees (or the project's documented lock step).

- [ ] **Step 5: Update WORKFLOW.md / EXCLUSIONS.md** if counts changed (discovery 44 / validation 142 compiled), commit to the worktree.

---

## Self-review notes

- Spec Stage 5 (commit) is intentionally reordered AFTER Stage 6 (reproduce PASS) here — validate-then-commit.
- fMRIPrep rerun (Task 4) is conditional on the audit; expected to be a no-op.
- Dual-task lev1 (s43) is deferred per the confirmed decision; its events are already corrected/committed.
- The FE-only path (Task 5) has a fallback (delete fixed_effects dir to force recompute) if `--skip-existing` skips fixed-effects.
- Re-QA loop (Task 5 Step 5) guards against VIF drift on the one events-changed single-task scan; bounded (re-run generator+compile+render only if it actually changed).
