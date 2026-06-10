# Codebase Simplification + Full Provenance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slim `neuro_workflow` to one narrative (Flywheel→lev2), make BIDS→lev2 re-derivable with machine-readable provenance, collapse the exclusion ledgers into one generated source, move tasks/contrasts/thresholds to versioned config, dedupe pipelines, and add an end-to-end synthetic test — behavior-preservingly.

**Architecture:** A phased sequence of independently-mergeable PRs in an isolated git worktree. Downstream/alternative subsystems (MSHBM, prevalence, parcellation-reliability, XCP-D) extract to a new `network_analysis` repo; iProc tooling extracts to `external/iProc` (deferred until the running tedana controller is idle). The core keeps `bidsify/events/exclusions/pipelines/qa/analysis(lev1,lev2,core,io)/core`.

**Tech Stack:** Python 3.11, `uv`, pytest, nilearn, nibabel, BIDS, SLURM, Apptainer.

**Spec:** `docs/superpowers/specs/2026-06-09-codebase-simplification-provenance-design.md`

**Decisions in force:** D1 core-only/full-extraction · D2 provenance level-B · D3 single generated exclusions source · D4 behavior-preserving (science deferred) · D5 E2E synthetic chain · D6 config = tasks+contrasts+thresholds · D7 dedupe via base classes · D8 isolated worktree, iProc-script move deferred. Extraction destination: **new `network_analysis` repo**.

**Branch strategy:** long-lived `refactor/simplify-provenance` branch in a worktree, accumulating PR0–PR7, one reviewed merge at the end. The *running controller uses the main checkout* — the worktree never touches its files.

**Global guardrails (apply to every task):**
- Run `uv run pytest -q` (core suite) after each task; it must stay green. Use `module load uv` first on Sherlock.
- Never `mv`/`rm` `scripts/iproc_tedana_scatter.py` or `scripts/iproc_scatter.py` until the controller (job `28601240`) is idle (`squeue -u logben | grep -c iproc_ted` == 0).
- Behavior-preserving: if a change would alter a rendered sbatch or a scientific output, stop and route it to the audit workstream.

---

## PR0 — Protect & set up the worktree

**Files:**
- Modify (git tracking only): the 8 untracked `scripts/*` + untracked `docs/*` files
- No source edits

- [ ] **Step 1: Snapshot current state**

Run: `cd /home/users/logben/neuro_workflow && git status --short && git rev-parse --abbrev-ref HEAD`
Expected: branch `prevalence-viz-2026-05-17`; a list of ` M` and `??` entries. Record the `??` (untracked) set.

- [ ] **Step 2: Track the untracked scripts so the running controller's script cannot be lost**

```bash
git add scripts/iproc_ingest_fmriprep_fs.sh scripts/iproc_parallel_run.py \
        scripts/iproc_tedana_scatter.py scripts/mshbm_convert_task_residuals.py \
        scripts/mshbm_inputs_from_fmriprep.py scripts/mshbm_inputs_from_iproc.py \
        scripts/mshbm_inputs_from_iproc_denoised.py scripts/mshbm_minsize_cleanup.py \
        scripts/mshbm_from_xcpd.py scripts/mshbm_postprocess_du2025.py \
        src/neuro_workflow/analysis/mshbm/minsize.py tests/analysis/mshbm/test_minsize.py
# Only add paths that exist; drop any that 'git status' did not list as untracked.
git commit -m "chore: track untracked iProc/MSHBM scripts before refactor (no behavior change)"
```
Expected: a commit containing only the previously-untracked files. The controller's live file is now in git history.

- [ ] **Step 3: Verify the controller's script is intact and committed**

Run: `git log --oneline -1 -- scripts/iproc_tedana_scatter.py && test -f scripts/iproc_tedana_scatter.py && echo OK`
Expected: a commit hash + `OK`. (Do NOT touch this file again until the controller is idle.)

- [ ] **Step 4: Create the isolated worktree + branch off current HEAD**

```bash
git worktree add ../neuro_workflow_refactor -b refactor/simplify-provenance
cd ../neuro_workflow_refactor
```
Expected: a new working tree at `../neuro_workflow_refactor` on `refactor/simplify-provenance`, including all recent work. All subsequent PRs happen here; the original checkout (and its running scripts) is untouched.

- [ ] **Step 5: Baseline the test suite in the worktree**

Run: `module load uv >/dev/null 2>&1; uv run pytest -q 2>&1 | tail -5`
Expected: the current pass count recorded as the green baseline. If anything fails on a clean checkout, fix or document before proceeding.

- [ ] **Step 6: Commit a refactor-branch marker**

```bash
git commit --allow-empty -m "chore: start refactor/simplify-provenance worktree"
```

---

## PR1 — Prune dead code & extract downstream subsystems to `network_analysis`

**Files:**
- Delete: `src/neuro_workflow/behavioral_archive/`, root `subjects_*.txt` (11), `docs/DuEtAl2025Neuron.pdf`, `docs/HBM-43-3311.pdf`
- Create: `docs/REFERENCES.md`, new repo `~/network_analysis/`
- Move (to new repo): `src/neuro_workflow/analysis/{mshbm,prevalence,parcellation_reliability}/`, `src/neuro_workflow/pipelines/{xcpd,mshbm,prep_mshbm}.py`, `src/neuro_workflow/templates/{xcpd,mshbm,prep_mshbm}.sbatch`, `scripts/{mshbm_*,prevalence_*,xcpd_preflight}.py`, and their tests
- Modify: `.gitignore`, the pipeline registry, `cli.py` (drop extracted subcommands), `pyproject.toml` (drop extracted deps if any), `README.md`/`docs/ARCHITECTURE.md`

- [ ] **Step 1: Delete the empty package dir**

```bash
git rm -r src/neuro_workflow/behavioral_archive
uv run pytest -q 2>&1 | tail -3
```
Expected: green (it had no importers). Commit: `git commit -m "chore: remove empty behavioral_archive package"`.

- [ ] **Step 2: Confirm root subject lists are unreferenced, then delete**

Run: `grep -rn "subjects_discovery\|subjects_validation\|subjects_phase\|subjects_pooled\|subjects_rdoc\|subjects_xcpd" src tests scripts --include='*.py' | grep -v '\.txt:' | head`
Expected: no code references (they are passed as CLI args, superseded by `config/pipeline_config.json`). If any code references them, STOP and convert that call-site first.

```bash
git rm subjects_*.txt
git commit -m "chore: remove root subject-list txt files (superseded by config/pipeline_config.json)"
```

- [ ] **Step 3: Gitignore the PDFs and add a references pointer**

Add to `.gitignore`:
```
# Copyrighted reference PDFs — not redistributed
docs/*.pdf
```
Create `docs/REFERENCES.md`:
```markdown
# References

PDFs are not committed (copyright). Obtain from the publisher:
- Du et al. 2025, *Neuron* — precision functional mapping from task residuals. (was docs/DuEtAl2025Neuron.pdf)
- HBM 43:3311 — (was docs/HBM-43-3311.pdf)
```
```bash
git rm --cached docs/DuEtAl2025Neuron.pdf docs/HBM-43-3311.pdf 2>/dev/null || true
git add .gitignore docs/REFERENCES.md
git commit -m "docs: gitignore reference PDFs, add REFERENCES.md"
```

- [ ] **Step 4: Scaffold the new `network_analysis` repo**

```bash
cd ~ && uv init network_analysis --package && cd network_analysis
git init -q 2>/dev/null; git add -A; git commit -q -m "chore: scaffold network_analysis repo"
mkdir -p src/network_analysis tests
```
Expected: a uv-managed package at `~/network_analysis`. (Add the `lobennett/network_analysis` GitHub remote later; not required to proceed.)

- [ ] **Step 5: Map the import edges before moving anything**

Run from the worktree:
```bash
grep -rn "from neuro_workflow.analysis.\(mshbm\|prevalence\|parcellation_reliability\)\|import.*\(mshbm\|prevalence\|xcpd\|prep_mshbm\)" src/neuro_workflow --include='*.py' \
  | grep -vE "analysis/(mshbm|prevalence|parcellation_reliability)/|pipelines/(xcpd|mshbm|prep_mshbm)\.py"
```
Expected: the list of CORE files that import the to-be-extracted code (registry + cli are expected; anything else must be evaluated). Also note what the extracted code imports FROM core (`analysis.core`, `analysis.io`, `core.*`) — those become `network_analysis` dependencies on `neuro_workflow` (add `neuro_workflow` as a path/git dependency in `network_analysis/pyproject.toml`).

- [ ] **Step 6: Move MSHBM (history-preserving if `git filter-repo` is available, else copy)**

Preferred (preserves history):
```bash
# in a throwaway clone, filter the mshbm paths, then add as remote to network_analysis
```
Pragmatic fallback (no history):
```bash
cp -r src/neuro_workflow/analysis/mshbm ~/network_analysis/src/network_analysis/mshbm
cp src/neuro_workflow/pipelines/{mshbm,prep_mshbm}.py ~/network_analysis/src/network_analysis/pipelines/ 2>/dev/null
cp src/neuro_workflow/templates/{mshbm,prep_mshbm}.sbatch ~/network_analysis/templates/ 2>/dev/null
cp scripts/mshbm_*.py ~/network_analysis/scripts/
cp -r tests/analysis/mshbm ~/network_analysis/tests/mshbm
```
Then in `neuro_workflow`:
```bash
git rm -r src/neuro_workflow/analysis/mshbm src/neuro_workflow/pipelines/mshbm.py \
         src/neuro_workflow/pipelines/prep_mshbm.py tests/analysis/mshbm
git rm src/neuro_workflow/templates/mshbm.sbatch src/neuro_workflow/templates/prep_mshbm.sbatch 2>/dev/null || true
git rm scripts/mshbm_*.py
```

- [ ] **Step 7: Drop MSHBM from the pipeline registry + CLI, verify green**

Edit the pipeline registry (`src/neuro_workflow/pipelines/__init__.py` or `base.py` registry) to stop importing/registering `mshbm` and `prep_mshbm`; remove their `cli.py` subcommand wiring. Then:
Run: `uv run pytest -q 2>&1 | tail -5 && uv run neuro-run --help 2>&1 | grep -iE 'mshbm|prep' || echo "no mshbm in CLI — good"`
Expected: tests green; `neuro-run --help` no longer lists mshbm/prep_mshbm. Commit: `git commit -m "refactor: extract MSHBM to network_analysis repo"`.

- [ ] **Step 8: Move prevalence + parcellation_reliability (same pattern as Steps 6–7)**

```bash
cp -r src/neuro_workflow/analysis/prevalence ~/network_analysis/src/network_analysis/prevalence
cp -r src/neuro_workflow/analysis/parcellation_reliability ~/network_analysis/src/network_analysis/parcellation_reliability
cp scripts/prevalence_*.py ~/network_analysis/scripts/
cp -r tests/analysis/prevalence tests/analysis/parcellation_reliability ~/network_analysis/tests/ 2>/dev/null
git rm -r src/neuro_workflow/analysis/prevalence src/neuro_workflow/analysis/parcellation_reliability \
         tests/analysis/prevalence tests/analysis/parcellation_reliability
git rm scripts/prevalence_*.py
```
Remove any prevalence CLI wiring. Run: `uv run pytest -q 2>&1 | tail -5`. Expected: green. Commit: `git commit -m "refactor: extract prevalence + parcellation_reliability to network_analysis"`.

- [ ] **Step 9: Move XCP-D**

```bash
cp src/neuro_workflow/pipelines/xcpd.py ~/network_analysis/src/network_analysis/pipelines/
cp src/neuro_workflow/templates/xcpd.sbatch ~/network_analysis/templates/
cp scripts/xcpd_preflight.py ~/network_analysis/scripts/
cp tests/pipelines/test_xcpd.py ~/network_analysis/tests/ 2>/dev/null
git rm src/neuro_workflow/pipelines/xcpd.py src/neuro_workflow/templates/xcpd.sbatch \
       scripts/xcpd_preflight.py tests/pipelines/test_xcpd.py
```
Remove xcpd from the registry/CLI. Run: `uv run pytest -q 2>&1 | tail -5 && uv run neuro-run --help`. Expected: green; CLI lists only `fmriprep, freesurfer, qsiprep, happy, fsqc, lev1, lev2`. Commit: `git commit -m "refactor: extract XCP-D pipeline to network_analysis"`.

- [ ] **Step 10: Get `network_analysis` to import + collect tests**

In `~/network_analysis`: add `neuro_workflow` as a dependency (`uv add --editable /home/users/logben/neuro_workflow` or a git dep), fix the moved modules' imports (`neuro_workflow.analysis.mshbm` → `network_analysis.mshbm`, keep `neuro_workflow.analysis.core/io` imports pointing at the dependency).
Run: `cd ~/network_analysis && uv run python -c "import network_analysis" && uv run pytest -q 2>&1 | tail -5`
Expected: imports resolve; moved tests collect (passing is a follow-up in that repo, not a blocker for the core PR).

- [ ] **Step 11: Note iProc deferral + update docs**

Add to the plan tracker / `docs/RUNBOOK.md`: "iProc scripts (`scripts/iproc_*`) extraction to `external/iProc` deferred until controller `28601240` idle." Update `docs/ARCHITECTURE.md` and `README.md` to drop the extracted subsystems from the core map (full doc consolidation is PR7). Commit: `git commit -m "docs: note iProc extraction deferral; trim architecture map"`.

- [ ] **Step 12: Final PR1 verification**

Run: `uv run pytest -q 2>&1 | tail -5 && uv run neuro-run --help` and confirm `src/neuro_workflow/analysis/` contains only `core io lev1 lev2`.
Expected: green; lean `analysis/`. PR1 complete.

---

## PR2–PR7 — Task-level index (each expanded into its own detailed plan when its predecessors land)

> Detailed bite-sized plans for these are written just-in-time, because each depends on the structure the previous PR lands (writing them in full now would be guesswork — forbidden by the no-placeholder rule).

**PR2 — Dedupe pipelines + split CLI (behavior-preserving)**
- Extract `ContainerPipeline` base from the shared `build_context` of fmriprep/freesurfer/qsiprep/happy/fsqc (version check, resolve_resources, count_subjects, image_path, work_dir, mail_line); each concrete pipeline declares only image + command + resource defaults.
- Extract `LocalAnalysisPipeline` base for lev1/lev2 (job-list + exclusions-file resolution).
- Split `cli.py` (376 LOC) → `cli/` package: parser assembly + dispatch + per-subsystem handler modules.
- **New test (replaces ~11 tautological pipeline tests):** one meta-test that every registered pipeline renders its sbatch against a fixture context and the rendered text is byte-identical to a committed golden file (regression-proof behavior preservation).

**PR3 — Config-as-code (tasks + contrasts + thresholds)**
- `config/tasks/*.yaml` (regressors + contrast formulas) with a load-time **contrast-formula validator** (symbolic parse: every contrast references declared regressors; well-formed) + per-formula unit tests.
- `config/datasets/<dataset>.yaml`: subject list, `session_map`/offsets, `BASE_TASKS`/`DUAL_TASKS` (de-hardcode from `pipelines/lev1.py`), all thresholds (motion FD/prop, behavioral omission/RT/stop-acc, lev1 VIF). `events/qc.py`, `confounds.py`, outlier generator read from here.
- `config_version` hash helper (consumed by PR4).
- Tests: contrast validation fails loudly on a planted typo; threshold round-trip; multiverse variant resolves to a distinct `config_version`.

**PR4 — Provenance (level B)**
- `core/provenance.py::write_run_manifest()` (code SHA+dirty, uv.lock hash, tool versions, exclusions-source SHA, config_version, args, timestamp, host/jobid, input-file manifest).
- lev1/lev2 emit BIDS `dataset_description.json` + per-output input manifest; lev2 reads inputs' manifests instead of the `_desc-belowMinRuns` substring.
- Clean-tree enforcement (`--allow-dirty` override).
- Tests: manifest round-trips; lev2 resolves inputs via manifest on a fixture; dirty-tree refusal.

**PR5 — Single exclusions source + flywheel→BIDS provenance**
- Committed `data/exclusions/<dataset>_exclusions.json` (resolved scan-level ledger, unifying `collection` + runtime sources).
- `neuro-run exclusions render-bidsignore` / `render-md` (stamped DO-NOT-EDIT) + `query <scan>`; `session_map` codified and read by events/lev1; `neuro-run provenance query <sub>`.
- Tests (fail-loud): on-disk `.bidsignore`/`EXCLUSIONS.md` == rendered output; `query` returns all stages for a known excluded scan; split-session subject maps to correct BIDS session.

**PR6 — Simulation + test consolidation**
- `core/cmd.py::run_command()` external-binary seam with `--simulate` (record + synthesize outputs).
- `testing/synthetic.py` factory (tiny NIfTIs, planted-contrast events, synthetic confounds).
- `tests/e2e/` synthetic bidsify→events→exclusions→lev1→lev2 asserting planted-effect recovery.
- Real lev2 group-stat test; remove the leftover tautological tests; ensure `tests/qa/fixtures/` is used or removed.

**PR7 — Docs / onboarding**
- `README.md` flywheel→lev2 narrative + quickstart (incl. simulate); regenerate `WORKFLOW.md`, `ARCHITECTURE.md`; new `PROVENANCE.md`; merge `PIPELINE.md`/`RUNBOOK.md` into `WORKFLOW.md`; archive `docs/superpowers/{plans,specs}` pairs under `archive/` + index; fold `AUDIT-sub-s03.md`/`SURFACE-*.md` into `SUBJECT-STATUS.md`.

**Post-sequence (gated on controller idle):** extract `scripts/iproc_*` to `external/iProc`.

**Separate spec (not this plan):** the scientific audit — events + lev1 correctness, session-offset enforcement end-to-end, trim/salvage tagging, dummy-scan seam, threshold defensibility, stale `surface_data.py` anat fallback.

---

## Self-Review

- **Spec coverage:** D1 (PR1 + iProc deferral), D2 (PR4), D3 (PR5), D4 (science deferred — explicit), D5 (PR6), D6 (PR3), D7 (PR2), D8 (PR0 + guardrails). Structure §4 = PR1 end-state. Success criteria §11 map to PR4/PR5/PR3/PR6/PR1 tasks. All covered.
- **Placeholder scan:** PR0/PR1 steps contain concrete commands + expected output. PR2–PR7 are intentionally index-level (just-in-time detailing is stated, not a hidden TODO).
- **Type/name consistency:** `write_run_manifest`, `run_command`, `ContainerPipeline`, `LocalAnalysisPipeline`, `config_version`, `<dataset>_exclusions.json` used consistently across spec and plan.
- **Risk note:** PR1 Step 5 (import-edge mapping) gates the moves; the green core suite + (later) green e2e prove the core no longer depends on extracted code.
