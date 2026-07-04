# Repo cleanup — make neuro_workflow a real SWE project

**Date:** 2026-07-04 · **Status:** approved (brainstorm) · **Scope:** moderate.

## Goal
Turn `neuro_workflow` into a lean, well-documented, conventionally-managed software
project now that the pipeline has run end-to-end (Flywheel→lev2) with exclusions and
per-stage steps captured. Consolidate/trim docs to an essential set, fix stale run
instructions, remove working-tree clutter, and establish branch/PR conventions.
Analysis-result docs and heavy analysis code stay out of core (they live in
`network_analysis`); new results (MSHBM, etc.) go on their own branches/repos.

## Premise corrections (from the cleanup inventory — important)
1. **`src/neuro_workflow/qa/reliability_movies.py` is NOT dead and is NOT the
   Kendrick-Kay algorithm.** It is a thin subprocess wrapper around the `brm` CLI from
   the extracted `bold-reliability-movies` package (pinned `tag=v0.1.3` in
   `pyproject.toml`, `qa` extra). This is already the modular design we want — the
   algorithm is external, core only calls it. **Keep it.**
2. **No MSHBM / prevalence / parcellation / XCP-D duplication.** That code is fully
   extracted to `network_analysis`; `src/neuro_workflow/analysis/` has only
   `core/io/lev1/lev2/task_config`. Nothing to de-duplicate. The only live cross-repo
   edge is `network_analysis` importing `neuro_workflow.core.slurm` and
   `pipelines.base` — treat those as **public API; do not break them**.
3. **`src/` has no dead modules** (every module has ≥1 importer). The cleanup is docs,
   run-instructions, conventions, and working-tree clutter — not `src/` surgery.

## End-state: essential repo
- **`src/neuro_workflow/`** — unchanged (`analysis, bidsify, cli, core, events,
  exclusions, pipelines, qa, templates, testing`). `core.slurm` + `pipelines.base`
  documented as the public surface `network_analysis` consumes.
- **`docs/` essential set (8):** `ARCHITECTURE.md`, `CONFIG.md`, `DATASETS.md`,
  `PIPELINE-WALKTHROUGH.md` (primary Flywheel→lev2 run doc), `PROVENANCE-AND-EXCLUSIONS.md`
  (authoritative exclusions + provenance), `RUNBOOK.md` (per-stage SLURM launch, pruned),
  `SCAN-NOTES.md`, `REFERENCES.md`.
  - **Fold in + delete:** `WORKFLOW.md` → PIPELINE-WALKTHROUGH (keep a short quick-ref
    section if useful); `PROVENANCE.md` (run-manifest schema) → a section of
    PROVENANCE-AND-EXCLUSIONS.
  - **Move to `network_analysis`:** `PARCELLATION-COMPARISON.md` (TM-vs-MSHBM analysis
    result — belongs with the analysis code, not core).
  - **Delete from `main` (retain in git history):** `docs/archive/`, `docs/audits/`.
    `docs/superpowers/` specs/plans for **still-in-flight** work (Oak re-execution) stay
    until that finalizes, then are removed too.
- **`scripts/`:** keep the documented pipeline scripts (`trim_bold`, `reconcile_sessions`,
  `migrate_behavioral`, `migrate_archive`, `capture_fw_inventory`, `reproduce_cohort`,
  `exclusion_gate`, `lev1_outliers`, `qa_report`, `check_tr`, `fmriprep_preflight`,
  `build_xcpd_view`, `dataset_stats`). **Archive/remove after Oak finalize** the audit
  one-offs (`recompile_delta.py`, `remove_orphan_derivatives.py`, `reconcile_audit.py`?,
  `audit_events_vs_task_configs.py`, `audit_subject_flywheel_vs_bids.py`) — each `verify`
  not-in-use before deleting.
- **Working tree:** delete the ~35 untracked root scratch files (`.*_*.out`, ad-hoc
  `.sbatch`/`.py`); add gitignore rules so they don't recur.

## Delivery: stacked conventional PRs off `main`
Taxonomy: branches `fix|feat|refactor|docs|chore|test/<slug>`; PR titles `FIX:`/`FEAT:`/
`REFACTOR:`/`DOCS:`/`CHORE:`/`TEST:` (Conventional-Commits style). Each PR small + reviewable.

- **PR0 — land pending work.** Merge `repro-harness-2026-06` (already pushed; contains
  PROVENANCE-AND-EXCLUSIONS, DATASETS, PIPELINE-WALKTHROUGH, the doc consolidation
  commit) into `main` so the stack bases on current truth. (Gated on the git-sync hold /
  iProc campaign — see Risks.)
- **PR1 — `docs/consolidate`** (DOCS:): fold WORKFLOW+PROVENANCE into their supersets and
  delete them; move PARCELLATION-COMPARISON to network_analysis; delete `docs/archive/`
  + `docs/audits/`; repoint all doc-links; update CLAUDE.md doc list + `ARCHITECTURE.md`.
- **PR2 — `docs/run-instructions`** (DOCS:): fix stale `RUNBOOK.md` §2.3/2.6/2.7/2.9
  (XCP-D/prep-mshbm/mshbm/prevalence reference deleted templates) → replace bodies with
  one-line pointers to `network_analysis`; add an XCP-D run pointer; verify every stage
  (bidsify→trim→reconcile/migrate→events→fMRIPrep→XCP-D→lev1→lev1-outlier→lev2→QA) has a
  current runnable command in PIPELINE-WALKTHROUGH + RUNBOOK.
- **PR3 — `chore/repo-conventions`** (CHORE:): add `CONTRIBUTING.md` (branch/PR taxonomy,
  commit trailer, review flow), `.github/PULL_REQUEST_TEMPLATE.md`; delete untracked
  scratch files + extend `.gitignore` (`*.out` scratch, ad-hoc sbatch).
- **PR4 — `chore/scripts-tidy`** (CHORE:, AFTER Oak finalize): archive/remove the retired
  one-off scripts; keep the documented pipeline scripts.

## Extraction decisions (moderate appetite)
- **iProc scatter drivers** (`scripts/iproc_scatter.py`, `iproc_tedana_scatter.py`,
  `iproc_parallel_run.py`, `iproc_ingest_fmriprep_fs.sh`) — **zero coupling** to
  neuro_workflow (stdlib only); the cleanest extraction candidate → a future
  `iproc-scatter` uv-installable tool. **Deferred to a follow-up** (the tedana controller
  is running now and must stay byte-identical; extract when idle). Recorded here; not in
  this stack.
- **QA report** — leave in core (reverse-coupled: `exclusions/*` import `qa.decisions`,
  `qa.metrics`). Revisit only if that edge is severed first.
- **Exclusions engine** — leave in core (the pipeline's decision spine).

## Out of scope
Any `src/` restructuring; MSHBM/analysis result docs (separate branches/repos); the
iProc extraction; `network_analysis`'s own stale back-imports (that repo's problem).

## Risks / sequencing
- **Git-sync hold:** `~/neuro_workflow` (controller checkout) must not be disrupted while
  the iProc tedana campaign runs. Do this work in the scratch worktree / on branches;
  PR0's merge-to-main and PR4 wait until the campaign + Oak finalize complete.
- **Public API:** do not remove/rename `core.slurm` or `pipelines.base` (network_analysis
  depends on them).
- **`docs/superpowers/` in-flight specs** stay until Oak re-execution finalizes.

## Success criteria
- `docs/` reduced to the 8 essential files; no dangling doc-links; RUNBOOK has a current
  command for every stage (in-repo or a pointer to network_analysis).
- `CONTRIBUTING.md` + PR template define the branch/PR taxonomy; repo root free of
  untracked scratch.
- No `src/` behavior change; test suite still green; `network_analysis` still imports
  cleanly from `neuro_workflow`.
- Delivered as the small conventional PR stack above.
