# Codebase Audit Report — `neuro_workflow` Monorepo

**Audit date:** 2026-05-31  **Repo:** `/home/users/logben/neuro_workflow`  **Branch:** `prevalence-viz-2026-05-17` (8 commits ahead of remote)
**Rubric:** Russ Poldrack RSE Scientific-Computing Monorepo Audit Rubric
**Constraint honored:** Strictly read-only. The iProc tedana SLURM controller (`scripts/iproc_tedana_scatter.py submit`, every 10 min) was verified to import **only the stdlib** (`argparse, csv, logging, re, subprocess, sys, pathlib`) — no `neuro_workflow` import. It is therefore insulated from every package-level recommendation below, and being untracked it cannot be touched by edits to tracked files. Nothing was edited, moved, or deleted.

---

## 1. Executive Summary

`neuro_workflow` is, at its core, a genuinely well-engineered scientific CLI. The `src/` package earns a high grade: a clean src-layout, a thin `neuro-run` entrypoint that dispatches to three consistent decorator/Protocol registries (pipelines, QA commands, exclusion generators), heavy analysis logic kept importable and invoked as `python -m neuro_workflow.analysis.<...>.run`, zero wildcard imports, dependencies declared with sensible extras, and an exact lockfile (`uv.lock`, tracked). The data-correctness scripts (`reconcile_sessions`, `migrate_behavioral`, `trim_bold`, the preflight/audit/render helpers) are backed by a real test suite. This is not a confusing codebase at its center.

**Why it nonetheless *feels* confusing** is almost entirely a *boundary and lifecycle* problem, not a core-design problem:

1. **Two parallel worlds with no signposting.** The polished, registry-driven `neuro-run` package world coexists with a second, completely separate **iProc world** (`scripts/iproc_*.py`) that is hand-orchestrated, never integrated into `neuro-run`, untracked in git, and undocumented outside docstrings. A reader cannot tell from the repo which world is "the pipeline" — and the *running production job* lives in the undocumented, untracked one.
2. **A large untracked surface masquerading as the working state.** 12 of the most active files (3 iProc drivers, 4 MSHBM scripts, 5 prevalence scripts) plus new source (`analysis/mshbm/minsize.py`) and its test are untracked. The repo on disk and the repo in git history diverge significantly, which violates the rubric's "code under version control" baseline (RE-6) and makes the codebase un-navigable for anyone but the author.
3. **`scripts/` has become a catch-all of two very different things.** Half are thin, tested CLI glue (correct per SP-5); half are stateful research orchestrators with no tests and hardcoded `/scratch` paths baked in as argparse defaults. They share a directory but not a quality bar.
4. **Docs sprawl + a "4 authoritative files" claim that is already false.** `CLAUDE.md` (last updated 2026-04-11) under-counts the authoritative set (omits `EXCLUSIONS-FLOW.md`) and points the README reader at three deleted scripts. 49 MB of docs (96% of it two untracked PDFs) and 34 superpowers plan/spec files blur the line between "how to run this" and "history."
5. **No correctness CI.** The only GitHub Actions workflow is `codespell.yml`. A strong local test suite is never run on a clean machine on push (TE-13 unmet), so "works on my machine" risk is real, compounded by `requires-python>=3.11` declared but only Python 3.13 actually exercised.

**The 3–5 highest-leverage fixes (all deferrable until after the tedana campaign; none touch the controller):**

- **A. Commit the untracked working set** (iProc drivers, MSHBM/prevalence scripts, `minsize.py` + its test). This single act closes the biggest source of confusion and the RE-6 gap. *(Do this carefully — `git add` of new files cannot affect the already-running, on-disk controller, but coordinate so you don't churn files mid-campaign.)*
- **B. Stand up a real pytest CI workflow** (TE-13) running the suite on 3.11 and 3.13 on every push, with optional extras installed. This is the single biggest reliability/portability win.
- **C. Split `scripts/` by quality tier and document the iProc world.** Add a `docs/IPROC.md` (or section) explaining the canonical-tree + scatter architecture and the 10-minute controller; tier scripts into "supported CLI glue" vs "research orchestration."
- **D. Tidy `.gitignore` and reconcile docs** — ignore `*.pdf`, `.pytest_cache/`, and `logs/*.err`; fix `CLAUDE.md`'s authoritative-files list and the README's three dead script references.
- **E. Parameterize hardcoded paths/usernames** — `iproc_scatter.py` hardcodes `'logben'` in `squeue` calls where its sibling controller correctly uses `getpass.getuser()`; analysis scripts bake `/scratch/users/logben/...` as defaults (CF-1).

---

## 2. Per-Area Scorecard

| Area | Grade | One-line verdict |
|------|-------|------------------|
| **Package** (`src/neuro_workflow`) | **B+** | Exemplary src-layout, thin-CLI/fat-library split, and consistent registries; minor namespace-package and importability-without-extras gaps. |
| **Scripts** (`scripts/`) | **B–** | Tested, well-documented data-correctness glue sits beside untracked, untested, path-hardcoded research orchestrators in the same folder. |
| **Tests** (`tests/`) | **B** | Strong, well-isolated unit coverage of the package core; weak on scripts (incl. the production controller), thin on lev2/prevalence entrypoints, and never run in CI. |
| **Docs** (`docs/`, README, CLAUDE.md) | **B–** | Excellent authoritative core + audit trail, undermined by stale claims, dead script references, an undocumented iProc world, and 47 MB of untracked PDFs. |
| **Config & Data** (`config/`, `data/`) | **B** | Clean single-source-of-truth cohort config and an auditable exclusion lockfile system; subject-list `.txt` sprawl and 9-day-stale lockfiles. |
| **Hygiene** (logs, work, .gitignore, tracking) | **C+** | `.gitignore` covers the basics but leaks PDFs/.err/.pytest_cache; large untracked working set; stale logs and a 69 MB `work/` scratch pile. |
| **Launch** (CLI → sbatch → container) | **A–** | Coherent, idempotent, fail-loud SLURM launch architecture with documented calibration; the iProc path is robust but lives entirely outside the `neuro-run` system. |

---

## 3. Per-Area Detail

### 3.1 Package — `src/neuro_workflow/` — **B+**

**What's good**
- **Standard src-layout package (ST-2).** `pyproject.toml` declares `neuro-workflow` 0.2.0, `[project.scripts] neuro-run = "neuro_workflow.cli:main"`, hatchling backend. Verified importable and that a wheel builds.
- **Exemplary entrypoint/library split (SP-1, RF-1).** `cli.py` parses args and dispatches; analysis stages run as `python -m neuro_workflow.analysis.lev1.run` from rendered sbatch templates. Reusable logic is importable and testable, not trapped in scripts.
- **Three consistent registries (ST-1, RF-1).** `pipelines/base.py`, `qa/base.py`, `exclusions/base.py` each use a `runtime_checkable` Protocol + explicit `register()`. Registration is triggered by explicit imports in `cli.py:19-42` — no hidden dynamic discovery, so registry contents are reviewable.
- **No God object (RF-2, RF-3).** Config lives in dataclasses (`analysis/config.py`); processing lives in standalone modules. `analysis/lev1/processing/` cleanly separates `design`, `confounds`, `contrasts`, `glm`, `masks`, `residuals`, `fixed_effects`, `quality_control`, `surface_data`.
- **Zero wildcard imports (SN-6);** dependencies declared with extras (RE-2); `uv.lock` present and tracked → **exact pinning satisfied (RE-3)**; audit helpers (`_git_sha`, `_jsonify`, `make_meta`, `load_dataset_subjects`) defined once in `exclusions/base.py` and *imported* by `core/exclusions.py` (no duplication — RF-6).

**What's wrong (with evidence)**
- **Four analysis dirs are implicit namespace packages — missing `__init__.py` (ST-5).** Verified missing in `analysis/io/`, `analysis/core/`, `analysis/task_config/`, `analysis/lev1/processing/`, while siblings `lev1/`, `lev2/`, `mshbm/`, `prevalence/` *have* them. Imports work under 3.13 (PEP 420) and the wheel bundles them, so this is a **consistency** flaw, not breakage. *Recommendation:* add four empty `__init__.py` — pure addition, cannot break the controller. Defer past this read-only window.
- **Package analysis/qa code cannot import without optional extras (RE-7).** `analysis/*` and `qa/report.py` import `nibabel/nilearn/statsmodels/pandas` at module top level, but those are confined to `[lev1]`/`[qa]`/`[events]` extras. A bare install gives a working CLI whose `submit lev1`/`qa` paths fail at import. No aggregate `all` extra exists and no per-subcommand install matrix is documented. *Recommendation:* add `all = [...]` extra + document required extra per subcommand.
- **`requires-python>=3.11` but only 3.13 is exercised (RE-3/RE-7).** Verified `.venv` is Python 3.13.2; the 3.11 floor is unvalidated. *Recommendation:* a CI matrix (see Tests) or narrow the floor.
- **A library function exits the process (RF-4).** `core/config.py:get_dataset()` calls `sys.exit(1)` on an unknown dataset. It fails loudly (good, GE-4/RE-15) but couples a core helper to process exit, hampering in-process reuse. Low priority; only `cli.py` calls it; the controller does not.

> Note: the inventory's "behavioral_archive/ and `__pycache__` are committed dead code, safe to delete" is **incorrect** — `git ls-files` shows nothing tracked there and `.gitignore` covers `__pycache__/` and `*.py[oc]`. There is no committed dead code to remove; the on-disk `__pycache__` (cpython-36) is purely local cruft.

### 3.2 Scripts — `scripts/` — **B–**

**What's good**
- **Scripts isolated from package (SP-5);** dependency strictly one-way (scripts → package; package never imports scripts).
- **Correctness-critical scripts are genuinely tested (TE-1, TE-8).** `tests/scripts/` covers `reconcile_sessions` (~21 KB of tests), `migrate_behavioral`, `trim_bold`, `fmriprep_preflight` (~12.5 KB), `audit_subject_flywheel_vs_bids`, `diagnose_high_hole_subjects`, `render_*`, `triage_surface_quality`. TDD effort was correctly concentrated where a wrong answer corrupts the dataset.
- **The iProc controller is robust (RE-9, RE-15, DO-5).** `subprocess.run(..., check=True)`, `set -e` in generated bash, removal of partial/OOM-killed tedana dirs before retry, output-existence skip checks (idempotent every cycle), `sbatch`-rejection caught and logged rather than crashing. Substantial module docstrings document scientific motivation and the "zero scientific divergence" / memory-calibration rationale.

**What's wrong (with evidence)**
- **A large untracked, untested research surface (RE-6, TE-1).** Verified untracked: `iproc_{tedana_scatter,scatter,parallel_run}.py`, `mshbm_{convert_task_residuals,minsize_cleanup}.py`, `prevalence_{by_instance_run,dashboard,instance_panel,instance_trend}.py`. No tests for any. These are recent (May 2026) and central to current work.
- **Hardcoded username breaks portability (RE-7).** `iproc_scatter.py` calls `squeue -u logben` (two sites), while its sibling controller `iproc_tedana_scatter.py` correctly uses `getpass.getuser()`. On any other account, `iproc_scatter.py`'s active-job detection silently finds nothing. *(Do NOT edit the controller; this is a different file.)*
- **Duplicated panel-plot logic (RF-6).** Surface-panel renderers reimplemented in `prevalence_dashboard.py`, `prevalence_subject_diagnostic.py`, and `prevalence_instance_panel.py`; the 8 `MAIN_CELLS` `(task, contrast)` tuples are copy-pasted across three prevalence scripts. *Recommendation:* promote a shared renderer + `MAIN_CELLS` into `analysis/prevalence/visualize.py`.
- **Scripts import a private package symbol (RF-1).** `prevalence_dashboard.py` and `prevalence_subject_diagnostic.py` do `from neuro_workflow.analysis.prevalence.visualize import _fetch_fsaverage6` — depending on a leading-underscore helper across the module boundary; an internal rename would silently break them. *Recommendation:* promote `_fetch_fsaverage6` to a public name.
- **Hardcoded `/scratch/users/logben/...` paths as argparse defaults (CF-1)** throughout the iProc/mshbm/prevalence scripts — single-machine assumptions baked in.

### 3.3 Tests — `tests/` — **B**

**What's good**
- **Layout mirrors `src/` (ST-1)** across 119 files / ~15,850 LOC, with strong concentration where it matters: `analysis/lev1/` (29 files) covers design-matrix rank/VIF guards, confound NaN-first-row, fixed-effects min-runs, surface vs volume branches, session-offset/cross-session anat.
- **Good isolation and gating (TE-10, TE-16).** Directory-scoped `conftest.py` fixtures (`temp_dir`, synthetic events, mock brain masks) are built locally; nibabel/statsmodels absence triggers clean module-level skips; data-dependent regression tests skip gracefully when real BIDS/fmriprep dirs are absent.
- **Parameterized rather than duplicated (TE-15)** — YAML contrast/event-alignment tests run over all 8 base tasks; posterior tests sweep `k, n, q`. Registry tests (`pipelines`/`qa`/`exclusions` `test_base.py`) are distinct, not redundant.
- **Real smoke/integration tests (TE-5)** — `test_all_templates_render.py` asserts no unresolved `{placeholder}` after rendering every pipeline template; `test_lev1_data_chain.py` is an end-to-end regression on minimal real data.

**What's wrong (with evidence)**
- **No correctness CI (TE-13).** Verified: `.github/workflows/` contains only `codespell.yml`. The suite never runs on a clean machine on push, across no Python versions. This is the single largest testing gap.
- **The production controller is untested (TE-1, TE-5).** `iproc_tedana_scatter.py` (runs every 10 min) and its siblings `iproc_scatter.py`/`iproc_parallel_run.py` have zero tests. *Recommendation (safe, additive):* extract `main()` into a testable function and add an import-smoke test under `tests/scripts/` — never delete or edit the controller.
- **Thin coverage of two analysis entrypoints.** `tests/analysis/lev2/` is a single scaffold `test_run.py`; `tests/analysis/prevalence/` has **no `test_run.py`** despite `prevalence/run.py` existing in src. The CLI driver layer of group analysis and prevalence is under-tested.
- **Empty `tests/qa/fixtures/`** (only `__init__.py`) — placeholder never populated (TE-12 partially unmet for QA).

### 3.4 Docs — `docs/`, `README.md`, `CLAUDE.md` — **B–**

**What's good**
- **Strong authoritative core (DO-1, DO-2).** `WORKFLOW.md` (exact reproducible commands, RE-1), `EXCLUSIONS.md`, `SCAN-NOTES.md`, `ARCHITECTURE.md`, plus `EXCLUSIONS-FLOW.md` document conventions, motivation, design, usage, and outputs. Cross-references between them are internally consistent.
- **Excellent audit trail (DO-2, RE-6).** `docs/audits/2026-05-06-lev1-base-task-audit.md` records bug fixes + smoke-test figures and cites its spec/plan; 34 dated superpowers plan/spec pairs document design→implementation for completed features.

**What's wrong (with evidence)**
- **`CLAUDE.md` is stale and under-counts authoritative docs (DO-1).** Claims "4 authoritative files" (last updated 2026-04-11) but omits `EXCLUSIONS-FLOW.md` (2026-05-07), which is equally authoritative for the exclusion system.
- **README points at three deleted scripts (DO-2).** `README.md` references `scripts/rename_behavioral_to_sourcedata.py`, `scripts/generate_behavioral_mapping.py`, and `scripts/migrate_archive_behavioral_data.py` — all removed in commit `6c5210f`. A reader following the README runs non-existent files.
- **The iProc world is undocumented outside docstrings (DO-2).** The single most operationally active subsystem — the canonical-tree + scatter architecture and the 10-minute controller — has no entry in any authoritative doc. *Recommendation:* add `docs/IPROC.md`.
- **47 MB of untracked reference PDFs (DM-3, hygiene).** `docs/DuEtAl2025Neuron.pdf` (41 MB) + `docs/HBM-43-3311.pdf` (6 MB) are untracked and **not** gitignored, so they permanently dirty `git status`. *Recommendation:* `.gitignore` `*.pdf` and add a one-line `docs/REFERENCES.md` with title/DOI.

### 3.5 Config & Data — `config/`, `data/` — **B**

**What's good**
- **Single source of truth for cohorts (CF-2).** `config/pipeline_config.json` defines discovery (5), validation (41), excluded (10), Flywheel aliases, skip lists, and session overrides, loaded by `bidsify/config.py:load_pipeline_config()`.
- **Auditable exclusion lockfiles (DO-9, RE-6, DM-13).** `data/exclusions/{discovery,validation}_lock.json` record which generators ran, when, under which git SHA (with `+dirty` flag), and entry counts — a real provenance trail. Reviewed TSV manifests version small text data in git correctly.
- **BIDS standard adopted throughout (DM-1, DM-2, SN-1)** — the field-standard organization scheme, strongly preferred over invention.

**What's wrong (with evidence)**
- **Subject-list `.txt` sprawl (SN-4, DM-13).** 12 `subjects_*.txt` at repo root (only `subjects_rdoc.txt` tracked; rest gitignored as operational scratch). Several are byte-identical duplicates (`subjects_discovery.txt` == `subjects_discovery_xcpd.txt`; validation likewise). The `.gitignore` comment correctly names `pipeline_config.json` as canonical, but the derived files have no single owner and risk drift.
- **Lockfiles 9 days stale; compiled at `+dirty` SHA (RE-1, DM-6).** `discovery_lock.json`/`validation_lock.json` were compiled 2026-05-22 under a dirty tree. Reproducibility of the exact exclusion set from a clean checkout is therefore not guaranteed.
- *(Inventory correction:* the claimed "24 KB `.env` containing a binary credential" is false — verified `.env` is **86 bytes**, correctly gitignored, holds a single `FW_API_KEY` line. Still a plaintext production credential on disk (DM-12) — rotate/move to a secret store eventually, but it is *not* in git.)

### 3.6 Hygiene — **C+**

**What's good**
- **`.gitignore` covers the essentials** — `.venv/`, `.env`, `__pycache__/`, `*.py[oc]`, `build/`, `work/`, `scratch/`, `.worktrees/`, `/subjects_*.txt`. `.venv` (842 MB) correctly excluded; `external/PrecisionNetworkMapping` is a proper submodule.
- **Controller logs are *not* in the repo** — verified the controller writes to `/scratch/.../scatter_combine_s10/logs`, so the repo's `logs/` is all safe-to-clear historical SLURM output (no live writer).

**What's wrong (with evidence)**
- **`.gitignore` gaps (hygiene).** Verified NOT ignored: `docs/*.pdf`, `.pytest_cache/`, `logs/*.err` (two untracked `qa_report-*.err`). These pollute `git status`.
- **Large divergence between disk and history (RE-6).** 12 active scripts + new source `analysis/mshbm/minsize.py` + `tests/analysis/mshbm/test_minsize.py` untracked. The new module+test are part of in-progress MSHBM work and should be committed together.
- **69 MB `work/` scratch pile + 5.3 MB stale `logs/`** — exploration PDFs, draft issue comments, `.bak` files, diagnostic PNGs. All gitignored or safe to clear, but it's clutter.

### 3.7 Launch — CLI → sbatch → container — **A–**

**What's good**
- **Coherent launch architecture (ST-7, ST-8).** `neuro-run submit <pipeline> <dataset>` → pipeline `build_context()` → `render_template()` (Jinja-style `.format`) → `submit_sbatch()`. 12 pipelines, 11 templates, conceptually distinct stages separated.
- **Containers pinned, never `latest` (RE-4, RE-5).** Verified fmriprep/xcpd require an explicit `--version` that resolves into a versioned `.sif` path (`fmriprep_{version}.sif`); no floating `latest`.
- **Idempotent, fail-loud, calibrated (RE-9, RE-15, DO-5).** Array throttling, per-subject work-dir cleanup, documented benign exit-1 workarounds for fmriprep#3634 and the XCP-D matplotlib quirk, and recorded memory/wall-time calibration in the iProc drivers.

**What's wrong (with evidence)**
- **iProc is not integrated into `neuro-run` (ST-1, ST-7).** The production pipeline runs via hand-invoked `scripts/iproc_*.py` against a canonical `/scratch` tree, entirely outside the otherwise-uniform launch system — the central reason the repo presents "two worlds." This is defensible (it wraps an external iProc codebase verbatim for scientific fidelity) but must be *documented* as a deliberate boundary.
- **Single-machine path assumptions (CF-1, RE-7)** in the launch scripts (hardcoded `/scratch/users/logben`, the `logben` username in `iproc_scatter.py`).

---

## 4. Cross-Cutting Themes

1. **The dominant problem is the package/research boundary, not core design (ST-1, ST-7, SP-5).** The `neuro-run` world is excellent; the iProc/MSHBM/prevalence research world is good code with poor lifecycle discipline (untracked, untested, undocumented, path-hardcoded). Confusion comes from these two worlds sharing one repo with no map between them. Highest leverage: commit the working set, document iProc, tier `scripts/`.

2. **Version control discipline lags code quality (RE-6, DM-13).** A repo whose *running production job* and *newest source module* are both untracked cannot satisfy the rubric's reproducibility baseline regardless of how clean the tracked code is. Committing the working set and tightening `.gitignore` is cheap and transformative.

3. **Testing is strong but unenforced and unevenly applied (TE-1, TE-13, TE-5).** Real, well-isolated tests exist for the package core and data-correctness scripts, but there is no pytest CI, the production controller and group/prevalence entrypoints are untested, and the 3.11 floor is unverified. The fix (CI matrix + a controller smoke test + lev2/prevalence entrypoint tests) is well-scoped.

4. **Documentation accuracy decays at the edges (DO-1, DO-2).** The authoritative core is excellent, but `CLAUDE.md` and `README.md` already contain false statements (miscount of authoritative files; three dead script references) and the most active subsystem is undocumented. Docs need a reconciliation pass and an iProc section.

5. **Single-machine assumptions throughout (CF-1, RE-7).** Hardcoded `/scratch/users/logben` paths and a literal `logben` username appear across scripts. Parameterizing via config/env (and `getpass.getuser()`) is the rubric's prescribed single-source-of-truth pattern and a prerequisite for any second operator.

**Sequencing note (constraint-safe):** Every recommendation above is deferrable until the tedana campaign completes. None edit, move, or delete `scripts/iproc_tedana_scatter.py`, `pyproject.toml`, `src/neuro_workflow` importability, or `.venv`. The two highest-leverage actions — committing untracked files and adding a CI workflow — are pure additions that the running, stdlib-only, on-disk controller cannot observe. When acting, coordinate `git add` timing so you are not churning files an in-flight `submit` cycle is reading.

**Relevant file paths (absolute):**
- Controller (do not edit): `/home/users/logben/neuro_workflow/scripts/iproc_tedana_scatter.py`
- Portability bug to fix later: `/home/users/logben/neuro_workflow/scripts/iproc_scatter.py` (hardcoded `logben`)
- Stale docs to reconcile: `/home/users/logben/neuro_workflow/CLAUDE.md`, `/home/users/logben/neuro_workflow/README.md`
- CI gap: `/home/users/logben/neuro_workflow/.github/workflows/` (only `codespell.yml`)
- Untracked working set to commit: `scripts/iproc_*.py`, `scripts/mshbm_*.py`, `scripts/prevalence_*.py`, `src/neuro_workflow/analysis/mshbm/minsize.py`, `tests/analysis/mshbm/test_minsize.py`
- Namespace-package dirs missing `__init__.py`: `src/neuro_workflow/analysis/{io,core,task_config,lev1/processing}/`
- `.gitignore` to tighten: ignore `docs/*.pdf`, `.pytest_cache/`, `logs/*.err`