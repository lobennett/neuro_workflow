# REFACTOR-PLAN.md — neuro_workflow

Prioritized, **SAFE** cleanup + refactor plan grounded in the 2026-05-31 read-only audit.

---

## HARD CONSTRAINT (read first)

A SLURM controller job runs **every 10 minutes**:

```bash
cd /home/users/logben/neuro_workflow && uv run python scripts/iproc_tedana_scatter.py submit ...
```

This controller is the single most important thing not to break. Verified facts that bound everything below:

- `scripts/iproc_tedana_scatter.py` imports **only the stdlib** (`argparse, csv, logging, re, subprocess, sys, pathlib, getpass`). It does **not** import `neuro_workflow`, does **not** import anything from `scripts/`, and `uv run python` only needs the package to remain *importable* (it never calls into it).
- Its manifest, logs, outputs, and scratch all live under `--scatter-root` / `--canonical-root`, which default to `/scratch/users/logben/discovery_bids/derivatives/iproc...` — **never** the repo `logs/` directory and **never** `scripts/__init__.pyc`.
- It depends, at most, on: (a) `scripts/iproc_tedana_scatter.py` itself existing and parsing, (b) `cd /home/users/logben/neuro_workflow` succeeding, (c) `uv run` resolving the `.venv` and an importable `neuro_workflow` package, and (d) `sbatch`/`squeue` on PATH.

**Therefore the only DO-NOW-forbidden actions are anything that touches:**
`scripts/iproc_tedana_scatter.py`, `pyproject.toml`, `src/neuro_workflow/` importability, the `.venv`, or the repo working directory's existence. Everything in section (1) below is provably outside that set.

This audit was strictly read-only. **Nothing has been edited, moved, renamed, or deleted.** The plan below is a set of recommendations, gated by phase.

---

## (1) DO-NOW — safe cleanups (provably unused by the running controller, easily reversible)

Each item is provably outside the controller's dependency set (per the verified facts above) and is trivially reversible (regenerated artifacts, `.gitignore` additions, or untracked files that can be re-created/restored). **None of these touch `scripts/iproc_tedana_scatter.py`, `pyproject.toml`, the importable `src/neuro_workflow` package, or the `.venv`.**

### 1.1 Remove stale on-disk Python 3.6 bytecode (`__pycache__` / stray `.pyc`)

The repo runs on Python 3.13 (`.venv`), but stale `cpython-36` bytecode and a stray `scripts/__init__.pyc` litter the tree. **None are tracked in git** (`git ls-files | grep -E '__pycache__|\.pyc$'` returns nothing — `__pycache__/` and `*.py[oc]` are already in `.gitignore`), so this is purely on-disk cruft.

```bash
find /home/users/logben/neuro_workflow/src -type d -name __pycache__ -prune -exec rm -rf {} +
rm -f /home/users/logben/neuro_workflow/src/neuro_workflow/__init__.pyc
rm -f /home/users/logben/neuro_workflow/scripts/__init__.pyc
```

- **Safety:** Bytecode is regenerated on next import; the controller never reads these paths (it reads `--scatter-root/logs`, not the repo). Does not touch `iproc_tedana_scatter.py` or the package source. Already gitignored, so no git state changes.
- **Poldrack principle:** Clean repo / no generated artifacts in the tree (Hygiene).
- **Risk:** none. **Reversibility:** trivial (Python regenerates on next `uv run`).
- **Correction to inventory:** the inventory referred to "tracked `__pycache__`/`.pyc`" — verification shows **none are tracked**; the cleanup is on-disk only.

### 1.2 Delete the orphaned `behavioral_archive/` directory (no tracked files, only py36 cruft)

`src/neuro_workflow/behavioral_archive/` was emptied of source in commit `6c5210f`. On disk it now contains **only** `__pycache__/*.cpython-36.pyc` (`__init__`, `sample_validation`). `git ls-files src/neuro_workflow/behavioral_archive/` returns nothing — there is no tracked code there.

```bash
rm -rf /home/users/logben/neuro_workflow/src/neuro_workflow/behavioral_archive
```

- **Safety:** Not a valid package (no `__init__.py`), not imported anywhere (verified: no references in `cli.py` or any module), not tracked in git. The controller imports only stdlib, so this cannot affect it. Because nothing tracked is removed, `neuro_workflow` importability is unchanged — but to be conservative, after deletion run `uv run python -c "import neuro_workflow"` to confirm (it will succeed; nothing imports this dir).
- **Poldrack principle:** Delete dead code (no commented-out / orphaned modules).
- **Risk:** very low. **Reversibility:** trivial — restorable from git history (commit `6c5210f`) if ever needed; the live content is only stale bytecode.

### 1.3 Add `.pytest_cache/` to `.gitignore`

`.pytest_cache/` (288K) is auto-generated test state, currently not explicitly ignored (only incidentally covered when nested). Add an explicit rule.

```bash
printf '\n# Pytest cache (auto-generated test state)\n.pytest_cache/\n' >> /home/users/logben/neuro_workflow/.gitignore
```

- **Safety:** `.gitignore` edits do not affect runtime, imports, the `.venv`, or the controller. `uv run` ignores `.gitignore`.
- **Poldrack principle:** Don't version generated artifacts.
- **Risk:** none. **Reversibility:** trivial (one line).

### 1.4 Ignore `*.err` SLURM stderr in `logs/`

`logs/.gitignore` ignores `*.log`, `*.out`, `slurm-*.out`, `*_logs/` but **not** `*.err`, so `logs/qa_report-25464293.err` and `logs/qa_report-25618195.err` show as untracked noise.

```bash
printf '*.err\n' >> /home/users/logben/neuro_workflow/logs/.gitignore
```

- **Safety:** The controller writes its `.err` files to `--scatter-root/logs` on `/scratch`, **not** the repo `logs/` (verified: `iproc_tedana_scatter.py:193,205`). Ignoring repo `logs/*.err` cannot touch controller output.
- **Poldrack principle:** Don't version generated artifacts.
- **Risk:** none. **Reversibility:** trivial.

### 1.5 Optionally clear stale repo `logs/` content (untracked, controller writes elsewhere)

The repo `logs/` holds ~163 untracked, stale SLURM outputs (lev1 smoke tests from May 7, `bidsify_logs/` from March, etc.), 5.3M total. **The running controller writes to `/scratch/.../scatter_combine_s10/logs`, never here** (verified). These are already gitignored (`*.out`, `*_logs/`), so this is disk-cleanup only and optional.

```bash
# Optional — frees ~5.3M; keep logs/.gitignore itself.
find /home/users/logben/neuro_workflow/logs -mindepth 1 ! -name '.gitignore' -delete
```

- **Safety:** None of these files are read or written by the controller; all are gitignored. The `.gitignore` is preserved by the `! -name` guard.
- **Poldrack principle:** Clean repo / reproducibility via fresh logs.
- **Risk:** very low (loses historical diagnostic logs only). **Reversibility:** logs are disposable; rerun jobs to regenerate. **Defer if you want to keep the lev1-smoke history.**

### 1.6 Decide on the two untracked reference PDFs in `docs/`

`docs/DuEtAl2025Neuron.pdf` (41M) and `docs/HBM-43-3311.pdf` (6M) are **untracked and not ignored** (verified: `git ls-files docs/*.pdf` → none; `git check-ignore` → no match). They permanently dirty `git status`. Pick one:

```bash
# Option A (recommended): keep locally, ignore reference PDFs, keep them out of history (they are 47M of binaries)
printf '\n# Reference papers (kept locally, not versioned)\ndocs/*.pdf\n' >> /home/users/logben/neuro_workflow/.gitignore
```

- **Safety:** `.gitignore`-only change; no runtime/import/controller impact. (Do **not** delete the PDFs — they are research references the user is reading.)
- **Poldrack principle:** Don't version large binaries / keep `git status` clean.
- **Risk:** none. **Reversibility:** trivial.
- **Note:** If the lab wants these versioned, use git-LFS instead — but that is an AFTER-jobs decision (touches more than `.gitignore`), not DO-NOW.

### 1.7 Commit the two stray untracked superpowers docs (status hygiene, no code)

`docs/superpowers/plans/2026-05-20-sub-s03-import-oak-t1w-and-freesurfer.md` and its `…-design.md` spec are untracked siblings of an otherwise fully-tracked plan/spec set. Staging them is a docs-only commit.

```bash
git add docs/superpowers/plans/2026-05-20-sub-s03-import-oak-t1w-and-freesurfer.md \
        docs/superpowers/specs/2026-05-20-sub-s03-import-oak-t1w-and-freesurfer-design.md
# commit only when the user asks (per repo commit policy)
```

- **Safety:** Markdown-only; no effect on package, `.venv`, or controller.
- **Poldrack principle:** Reproducible audit trail (design records tracked alongside their siblings).
- **Risk:** none. **Reversibility:** `git reset`.

> **DO-NOW boundary restated:** Items 1.1–1.7 touch only on-disk bytecode, an orphaned no-tracked-files directory, `.gitignore` files, disposable logs, and markdown. **None edits, moves, or renames `scripts/iproc_tedana_scatter.py`; none touches `pyproject.toml`, the importable `src/neuro_workflow` package, or the `.venv`.** The controller's next 10-minute invocation is unaffected.

---

## (2) AFTER iProc jobs finish — code-touching deletions / moves / consolidation

These either modify code, move files the controller might (now or later) depend on, or change importability. **Do not start any of these while `squeue` shows `iproc_ted_*` jobs queued/running or while the 10-minute controller is active.** Each requires re-running the test suite (`uv run pytest tests/ --ignore=tests/analysis -v` plus `tests/analysis` where extras are installed) and a `uv run python -c "import neuro_workflow"` smoke check before committing.

### 2.1 Bring the iProc / MSHBM / prevalence scripts under version control (RE-6)

12 untracked scripts (`iproc_*.py` ×3, `mshbm_*.py` ×4, `prevalence_*.py` ×5) — including the **running controller `iproc_tedana_scatter.py`** — are not in git. This is the highest-value AFTER item: an untracked controller can be lost with no recovery.

- **Action:** Once the controller stops, `git add scripts/iproc_*.py scripts/mshbm_*.py scripts/prevalence_*.py` and commit. **Do not `git add` `iproc_tedana_scatter.py` while it is the live controller** — adding a tracked file is harmless to execution, but reviewing/editing it during a run is not; wait for the campaign to finish so a stabilized version is committed.
- **Poldrack principle:** Everything in version control (RE-6); reproducibility.
- **Risk:** low (adding files). **Reversibility:** `git rm --cached`.

### 2.2 Fix the hardcoded username in `iproc_scatter.py` (RE-7)

`scripts/iproc_scatter.py:303,315` call `squeue -u logben` literally, whereas the controller (`iproc_tedana_scatter.py`) correctly uses `getpass.getuser()`. On any other account the scatter driver silently finds no active jobs and breaks idempotent re-submit / `afterok` chaining.

- **Action (AFTER, coordinated):** replace the two `'logben'` literals with `getpass.getuser()`. This file is **not** the running controller, but it is part of the same iProc campaign — edit only when no scatter/filter jobs are in flight.
- **Poldrack principle:** Portability / no hardcoded environment (RE-7).
- **Risk:** low (one-account-only behavior change). **Reversibility:** revert two lines.

### 2.3 Promote shared prevalence-viz logic into the package (RF-6)

Panel renderers are copy-pasted across `prevalence_dashboard.py`, `prevalence_subject_diagnostic.py`, `prevalence_instance_panel.py`; the 8 `MAIN_CELLS` (task, contrast) tuples are triplicated across `prevalence_by_instance_run.py`, `prevalence_instance_trend.py`, `prevalence_instance_panel.py`. Two scripts also import a private `_fetch_fsaverage6` (RF-1, information-hiding violation).

- **Action:** Promote a public panel renderer + `MAIN_CELLS` constant + a public `fetch_fsaverage6` into `src/neuro_workflow/analysis/prevalence/visualize.py`; have the scripts import them. Add a small mocked unit test (TE-1) when promoting.
- **Poldrack principle:** DRY (RF-6) + information hiding (RF-1).
- **Risk:** medium — **touches `src/neuro_workflow`** (importability surface), so strictly AFTER. Re-run `tests/analysis/prevalence` afterward.
- **Reversibility:** moderate (revert script imports + remove the new public symbols).

### 2.4 Confirm `behavioral_archive/` removal at the git level (if not done in 1.2)

If 1.2 was deferred, removing the on-disk dir AFTER is identical and equally safe; there is simply nothing tracked to `git rm`.

- **Poldrack principle:** Delete dead code.
- **Risk:** very low. **Reversibility:** git history.

### 2.5 Test-suite cleanups

- `tests/qa/fixtures/` is empty (`__init__.py` only) — either populate with intended fixtures or remove the empty dir.
- Add a minimal import/parse smoke test for the iProc controller (`tests/scripts/test_iproc_scatter.py`) so the most operationally critical script gains a guard (TE-1). **Write this AFTER** the controller version is final and committed (2.1), so the test pins the stabilized signature.
- **Poldrack principle:** Test the critical path (TE-1, TE-8).
- **Risk:** low. **Reversibility:** delete the test file.

---

## (3) DOCUMENTATION consolidation

Concrete merge plan to fold the sprawl (45 tracked docs + 2 untracked PDFs) into the structured authoritative set. All doc edits are content-only and carry **no runtime/controller risk**; they can technically be done anytime, but are grouped here as a deliberate pass rather than DO-NOW noise. Each merge is reversible via git history.

### 3.1 Promote `EXCLUSIONS-FLOW.md` to the authoritative set and update `CLAUDE.md`

`docs/EXCLUSIONS-FLOW.md` (2026-05-07) is equally authoritative for the exclusion system but is **not** listed in `CLAUDE.md`'s "4 authoritative files" block, which also predates it (CLAUDE.md last updated 2026-04-11).

- **Action:** In `CLAUDE.md` "Authoritative Documentation", add a 5th entry: `docs/EXCLUSIONS-FLOW.md — Exclusion system: sources, generators, compile + lockfile audit, lev1/lev2 honoring`. Update the "Last Updated" date.
- **Poldrack principle:** Accurate, discoverable documentation (DO-2).
- **Risk:** none. **Reversibility:** trivial.

### 3.2 Consolidate the per-subject / surface micro-docs into one living doc

Four tiny single-table docs (`AUDIT-sub-s03.md`, `SURFACE-DIAGNOSIS-discovery.md` 255 B, `SURFACE-FIX-STATUS.md` 207 B, and the s03 session-mapping table) describe per-subject status that belongs together.

- **Action:** Fold them into a single `docs/SUBJECT-STATUS.md` (one section per subject, with the FreeSurfer hole/KEEP-EXCLUDE table). Cross-link from `SCAN-NOTES.md`. Delete the four stubs.
- **Poldrack principle:** One source of truth per concern (CF-2 applied to docs); reduce sprawl.
- **Risk:** none (content move). **Reversibility:** git history.

### 3.3 Archive completed superpowers plans/specs after a retention window

34 paired plan/spec files (2026-04-24 → 2026-05-26) are frozen execution artifacts for *completed* projects. They are valuable history but are not active pipeline docs.

- **Action:** Move `docs/superpowers/plans/` and `docs/superpowers/specs/` under `docs/archive/superpowers/` (keep them tracked — they are the audit trail; do **not** delete). Add a one-line index `docs/archive/superpowers/README.md` listing feature → date → status. Keep the most recent in-flight ones in place if any project is still open.
- **Poldrack principle:** Separate active docs from frozen history; reproducible audit trail preserved.
- **Risk:** none (tracked moves). **Reversibility:** git history.

### 3.4 Add a `docs/REFERENCES.md` for the PDFs

After 1.6 ignores `docs/*.pdf`, add a one-line-per-paper `docs/REFERENCES.md` (title, DOI, relevance) so the bibliographic intent survives even though the binaries are not versioned.

- **Poldrack principle:** Document provenance of methods (DO-2).
- **Risk:** none. **Reversibility:** trivial.

### 3.5 Reconcile `WORKFLOW.md` vs `README.md` overlap (low priority)

Both describe pipeline stages; they are complementary (exact commands vs. narrative) and non-contradictory. Leave as-is but add a one-line pointer at the top of each to the other to make the split explicit.

- **Poldrack principle:** Discoverability; avoid silent duplication drift.
- **Risk:** none. **Reversibility:** trivial.

---

## (4) STRUCTURAL — repo organization

Higher-effort organization changes. **All are AFTER-iProc**, because they move files and/or change the source-of-truth that array jobs read.

### 4.1 Establish `config/pipeline_config.json` as the sole subject-list source of truth; relocate `subjects_*.txt`

12 `subjects_*.txt` files live at the repo root. 11 are already gitignored (`/subjects_*.txt`), and `subjects_discovery.txt` / `subjects_validation.txt` duplicate `config/pipeline_config.json`'s `samples` exactly; `*_xcpd.txt` variants are byte-identical copies.

- **Action:** Add a `neuro-run subjects export <sample> [--filter ...] --out <path>` helper that **generates** these lists from `config/pipeline_config.json` on demand, and write them to a non-root scratch location (e.g. `~/.neuro_workflow/subject_lists/`). Stop hand-maintaining root `.txt` files. The one tracked exception, `subjects_rdoc.txt`, should either move into `pipeline_config.json` as an `rdoc` sample or into `config/`.
- **Poldrack principle:** Single source of truth / configuration-as-code (CF-2, RE-6).
- **Risk:** **medium** — sbatch templates consume `{subjects_file}` via `sed`; any array job (including future iProc submissions if they ever read a subjects file) must point at the new location. **Strictly AFTER**, and re-register datasets in `~/.neuro_workflow/datasets.json`. Note the *current* tedana controller reads `units_manifest.tsv`, not a subjects file, so it is unaffected either way — but other pipelines are.
- **Reversibility:** moderate — re-emit the `.txt` files from config to roll back.

### 4.2 Add the missing `__init__.py` to four namespace dirs (ST-5)

`analysis/io/`, `analysis/core/`, `analysis/task_config/`, `analysis/lev1/processing/` lack `__init__.py` (PEP 420 implicit namespaces) while sibling analysis subpackages have them. Imports currently work, so this is consistency, not breakage.

- **Action:** add four empty `__init__.py`. Pure addition.
- **Poldrack principle:** Consistent package layout (ST-5).
- **Risk:** low — **touches `src/neuro_workflow`** packaging, so AFTER. Verify the wheel still bundles `tasks/*.yaml` and re-run `tests/analysis`.
- **Reversibility:** delete the four files.

### 4.3 Add an `all` extra and document the install matrix (RE-7)

The CLI works with no extras, but `submit lev1/lev2/mshbm`, the `qa` commands, and `python -m neuro_workflow.analysis.*` fail at import without `[lev1]`/`[qa]`/`[events]` installed. There is no aggregate extra and no per-subcommand install doc.

- **Action:** add `all = [lev1 + qa + bidsify + events]` to `pyproject.toml [project.optional-dependencies]`; document the required extra per subcommand in `README.md`.
- **Poldrack principle:** Reproducible environment / declared dependencies (RE-2, RE-7).
- **Risk:** **medium-by-policy** — this edits `pyproject.toml`, which is on the controller's critical surface (the controller's `uv run` resolves the package). Adding an *optional* extra does not change resolution of the existing `.venv`, but per the hard constraint **no `pyproject.toml` edits until the controller is idle.** Strictly AFTER; re-run `uv sync` and `uv run python -c "import neuro_workflow"`.
- **Reversibility:** revert the `pyproject.toml` hunk.

### 4.4 Convert `core/config.get_dataset()` from `sys.exit` to a raised exception (RF-4)

A library function calling `sys.exit(1)` couples core logic to process exit and hampers in-process reuse/testing. `cli.py` is its only caller.

- **Action:** raise `DatasetNotFoundError`; convert to `sys.exit` at the `cli.py` boundary.
- **Poldrack principle:** Library/CLI separation; testability (RF-4).
- **Risk:** low — touches `src/neuro_workflow/core/config.py`, so AFTER; re-run `tests/core` + `tests/test_cli.py`.
- **Reversibility:** revert the hunk.

---

## Quick reference: phase gating

| Phase | Touches code / imports? | Touches controller surface? | Safe while controller runs? |
|-------|--------------------------|------------------------------|------------------------------|
| (1) DO-NOW 1.1–1.7 | No (bytecode/dirs/.gitignore/docs only) | No | **Yes** |
| (2) AFTER 2.1–2.5 | Yes (scripts + `src/`) | 2.1/2.2 = iProc scripts | **No** |
| (3) DOCS 3.1–3.5 | No | No | Yes, but do as a deliberate pass |
| (4) STRUCTURAL 4.1–4.4 | Yes (`src/`, `pyproject.toml`, subject-list SoT) | 4.3 edits `pyproject.toml` | **No** |

**Verification gate for every section-2/4 item:** `uv run python -c "import neuro_workflow"` **and** the relevant `uv run pytest` target must pass before committing, and `squeue -u "$USER"` must show no live `iproc_ted_*` jobs.
