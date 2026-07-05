# Repo Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `neuro_workflow` into a lean, CI-gated, conventionally-managed RSE project: add the engineering substrate (CI + lint + license + contributor docs), consolidate docs to an essential set, and fix stale run instructions.

**Architecture:** A stack of small, conventionally-labeled PRs. PR1 lands the CI/standards substrate first so every later PR is gated; PR2–PR3 are docs. No `src/` behavior changes. Work happens in the scratch worktree and pushes to `lobennett/neuro_workflow`.

**Tech Stack:** Python 3.11, `uv` (deps + `uv run`), `pytest` (~570-test core suite), `ruff` (lint+format), `pre-commit`, GitHub Actions, hatchling build.

**Spec:** `docs/superpowers/specs/2026-07-04-repo-cleanup-design.md`

---

## Sequencing & base-branch reality (read first)

- **Base branch.** `main` lacks the recent doc work; the current truth is `repro-harness-2026-06` (pushed). Cleanup branches are cut **from `repro-harness-2026-06`**. PR0 (below) merges that to `main`; PR1–PR3 rebase onto `main` once PR0 lands.
- **Gated steps (do NOT run yet):**
  - **PR0 — merge `repro-harness-2026-06` → `main`.** Blocked by the git-sync hold (iProc tedana campaign must finish; `~/neuro_workflow` controller checkout must not be disrupted). Human-coordinated when the campaign completes.
  - **PR4 — `chore/scripts-tidy`.** Blocked until the Oak re-execution finalizes (the `verify`-marked one-off scripts are still in use). Not planned in task detail here; a short follow-up.
- **Where to run.** Author changes in `/scratch/users/logben/neuro_workflow_refactor`. `ruff` can run on the login node (fast); the **pytest core suite runs via CI** (GitHub Actions) — do not run ~570 tests on the login node. `module load uv/0.9.5` before any `uv` command.
- **Public API guard.** Never remove/rename `src/neuro_workflow/core/slurm.py` or `src/neuro_workflow/pipelines/base.py` — `network_analysis` imports them.

---

## PR1 — `chore/ci-and-standards`

Branch: `chore/ci-and-standards` off `repro-harness-2026-06`. PR title: `CHORE: CI, lint, license, and contributor standards`.

### Task 1: Branch + delete untracked scratch clutter

**Files:** none tracked; removes ~35 untracked root files; modifies `.gitignore`.

- [ ] **Step 1: Create the branch**

```bash
cd /scratch/users/logben/neuro_workflow_refactor
git checkout repro-harness-2026-06 && git pull
git checkout -b chore/ci-and-standards
```

- [ ] **Step 2: List the untracked scratch files (confirm before deleting)**

Run: `git status --porcelain | grep '^??' | grep -vE 'docs/|src/|tests/'`
Expected: the root `.*_*.out`, ad-hoc `.stage*.sbatch`, `.orphan_reasons.py`, `.real_recompile.py`, `.lev1_s10sm*`, etc. Confirm none are tracked (all lines start with `??`).

- [ ] **Step 3: Delete the untracked scratch files**

```bash
git status --porcelain | awk '/^\?\?/{print $2}' \
  | grep -E '^\.[a-z].*_[0-9]+\.(out|err)$|^\.stage.*\.sbatch$|^\.(orphan_reasons|real_recompile)\.py$|^\.lev1_s10sm' \
  | xargs -r rm -f
```

- [ ] **Step 4: Extend `.gitignore`** — append:

```gitignore
# SLURM/scratch captures at repo root (never tracked)
/.*_[0-9]*.out
/.*_[0-9]*.err
/.stage*.sbatch
/.*.tmp.py
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "CHORE: ignore root SLURM/scratch captures; remove untracked clutter"
```

### Task 2: Add ruff config + format the codebase

**Files:** Modify `pyproject.toml`; reformat `src/`, `tests/`, `scripts/`.

- [ ] **Step 1: Add `[tool.ruff]` to `pyproject.toml`** (append near the other `[tool.*]` blocks):

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["docs/archive", "external"]

[tool.ruff.lint]
# Conservative starting set — expand later once clean.
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]  # line length handled by the formatter, not the linter
```

- [ ] **Step 2: See the current lint violation surface (informational)**

Run: `module load uv/0.9.5 && uv run ruff check . --statistics`
Expected: a list of rule counts. Note the total — this scopes Step 4.

- [ ] **Step 3: Apply the formatter (large mechanical diff, its own commit)**

Run: `uv run ruff format .`
Expected: "N files reformatted".

- [ ] **Step 4: Commit the format pass separately**

```bash
git add -A
git commit -m "STYLE: apply ruff format across the codebase"
```

- [ ] **Step 5: Auto-fix safe lint issues, then hand-fix the rest**

Run: `uv run ruff check . --fix`
Then re-run `uv run ruff check .`. For any remaining violations: fix the code, OR (only if a rule is genuinely inappropriate for this codebase) add a targeted `# noqa: <RULE>` with a reason, OR narrow `select` in `pyproject.toml`. Do NOT blanket-ignore.
Expected end state: `uv run ruff check .` exits 0.

- [ ] **Step 6: Commit the lint fixes**

```bash
git add -A
git commit -m "FIX: resolve ruff lint findings (E/F/I/UP/B)"
```

### Task 3: Add the CI workflow

**Files:** Create `.github/workflows/ci.yml`.

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"
          enable-cache: true
      - name: Sync (all extras)
        run: uv sync --all-extras
      - name: Ruff lint
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Core test suite
        run: uv run pytest tests/ --ignore=tests/analysis -q
```

- [ ] **Step 2: Validate the YAML locally**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
Expected: `yaml ok`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "CHORE: add CI (uv sync + ruff lint/format + core pytest suite)"
```

- [ ] **Step 4: Note** — the real verification is CI running on the PR. After pushing (Task 8), confirm the `ci` check passes on the PR; if `uv sync --all-extras` pulls a dep that fails on GH (e.g. a heavy optional), pare the sync to the extras the core suite actually needs and re-push.

### Task 4: Add LICENSE

**Files:** Create `LICENSE`; modify `pyproject.toml`.

- [ ] **Step 1: DECISION GATE — confirm the license with the PI.** Default recommendation: **BSD-3-Clause** (common for Poldrack-lab / research pipelines). Do not guess silently; if unconfirmed, open the PR with a note and leave this task's commit for last.

- [ ] **Step 2: Write `LICENSE`** with the chosen SPDX text (BSD-3-Clause: standard template, `Copyright (c) 2026, Russell Poldrack Lab, Stanford University`).

- [ ] **Step 3: Set the license in `pyproject.toml`** under `[project]`:

```toml
license = "BSD-3-Clause"
```

- [ ] **Step 4: Commit**

```bash
git add LICENSE pyproject.toml
git commit -m "CHORE: add BSD-3-Clause LICENSE"
```

### Task 5: Add CITATION.cff

**Files:** Create `CITATION.cff`.

- [ ] **Step 1: Write `CITATION.cff`**

```yaml
cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: "neuro-workflow: a BIDS-to-second-level fMRI pipeline"
authors:
  - family-names: Bennett
    given-names: Logan
  - name: "Russell Poldrack Lab, Stanford University"
repository-code: "https://github.com/lobennett/neuro_workflow"
license: BSD-3-Clause
version: "0.2.0"
```

- [ ] **Step 2: Validate**

Run: `uv run python -c "import yaml; yaml.safe_load(open('CITATION.cff')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add CITATION.cff
git commit -m "CHORE: add CITATION.cff"
```

### Task 6: Add pre-commit config

**Files:** Create `.pre-commit-config.yaml`.

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/codespell-project/codespell
    rev: v2.3.0
    hooks:
      - id: codespell
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

- [ ] **Step 2: Sanity-run against all files**

Run: `uv run pre-commit run --all-files` (add `pre-commit` to the dev dependency-group in `pyproject.toml` if not resolvable).
Expected: hooks pass (ruff already applied in Task 2; fix any codespell/whitespace hits and re-commit).

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml pyproject.toml
git commit -m "CHORE: add pre-commit (ruff, codespell, whitespace hooks)"
```

### Task 7: Add CONTRIBUTING.md + PR template

**Files:** Create `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`.

- [ ] **Step 1: Write `CONTRIBUTING.md`** documenting:
  - Branch prefixes: `fix/`, `feat/`, `refactor/`, `docs/`, `chore/`, `test/`.
  - PR titles: Conventional-Commits style — `FIX:`, `FEAT:`, `REFACTOR:`, `DOCS:`, `CHORE:`, `TEST:`.
  - Commit trailer: `Co-Authored-By:` line convention (from CLAUDE.md).
  - Dev setup: `module load uv && uv sync --all-extras`; run tests `uv run pytest tests/ --ignore=tests/analysis`; lint `uv run ruff check . && uv run ruff format --check .`; `pre-commit install`.
  - Note: `tests/analysis` needs extra deps/HPC data and is excluded from CI.
  - Note: on Sherlock never run pytest on the login node — use `srun`/`sbatch`.

- [ ] **Step 2: Write `.github/PULL_REQUEST_TEMPLATE.md`**

```markdown
## Summary

<!-- what & why -->

## Type
- [ ] FIX  - [ ] FEAT  - [ ] REFACTOR  - [ ] DOCS  - [ ] CHORE  - [ ] TEST

## Checklist
- [ ] Branch named `<type>/<slug>`; PR title `TYPE: ...`
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] Core suite green (`uv run pytest tests/ --ignore=tests/analysis`) or CI green
- [ ] Docs updated if behavior/commands changed
- [ ] No change to public API (`core.slurm`, `pipelines.base`) without noting downstream `network_analysis`
```

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md .github/PULL_REQUEST_TEMPLATE.md
git commit -m "DOCS: add CONTRIBUTING.md and PR template (branch/PR taxonomy)"
```

### Task 8: Push + open PR1

- [ ] **Step 1: Push**

```bash
git push -u origin chore/ci-and-standards
```

- [ ] **Step 2: Open the PR** (base `main` if PR0 has landed, else `repro-harness-2026-06`)

```bash
module load system gh
gh pr create --repo lobennett/neuro_workflow \
  --base repro-harness-2026-06 --head chore/ci-and-standards \
  --title "CHORE: CI, lint, license, and contributor standards" \
  --body "Adds CI (ruff + core pytest), ruff config + format pass, pre-commit, LICENSE, CITATION.cff, CONTRIBUTING + PR template; removes root scratch clutter. First in the cleanup stack so later PRs are gated. 🤖 Generated with Claude Code"
```

- [ ] **Step 3: Confirm the `ci` check is green on the PR** before merging. Fix + push until green.

---

## PR2 — `docs/consolidate`

Branch: `docs/consolidate` off PR1's tip (or `main` after PR1 merges). PR title: `DOCS: consolidate to the essential doc set`.

### Task 9: Fold WORKFLOW.md and PROVENANCE.md into their supersets

**Files:** Modify `docs/PIPELINE-WALKTHROUGH.md`, `docs/PROVENANCE-AND-EXCLUSIONS.md`; delete `docs/WORKFLOW.md`, `docs/PROVENANCE.md`.

- [ ] **Step 1:** Read `docs/WORKFLOW.md`. Port any content **not** already in `PIPELINE-WALKTHROUGH.md` into a new "## Quick reference (Steps 1–14)" section at the top of `PIPELINE-WALKTHROUGH.md` (terse stage list). Do not duplicate the full recipe.
- [ ] **Step 2:** Read `docs/PROVENANCE.md` (run-manifest schema + clean-tree policy). Add its content as a "## Run-manifest schema & clean-tree policy" section of `PROVENANCE-AND-EXCLUSIONS.md`.
- [ ] **Step 3:** `git rm docs/WORKFLOW.md docs/PROVENANCE.md`.
- [ ] **Step 4:** Grep for links to the deleted docs and repoint them:

Run: `grep -rn "WORKFLOW.md\|PROVENANCE.md" docs/ CLAUDE.md README.md --include='*.md' | grep -v PROVENANCE-AND-EXCLUSIONS | grep -v PIPELINE-WALKTHROUGH`
Fix each hit to point at the new section/doc. (Leave `EXCLUSIONS.md`-as-rendered-artifact refs alone.)

- [ ] **Step 5: Commit**

```bash
git add -A docs/ CLAUDE.md README.md
git commit -m "DOCS: fold WORKFLOW + PROVENANCE into PIPELINE-WALKTHROUGH + PROVENANCE-AND-EXCLUSIONS"
```

### Task 10: Move PARCELLATION-COMPARISON.md to network_analysis

**Files:** `git rm docs/PARCELLATION-COMPARISON.md` (neuro_workflow); add it to `network_analysis/docs/`.

- [ ] **Step 1:** Copy the file to the network_analysis repo:

```bash
mkdir -p /scratch/users/logben/network_analysis/docs
cp docs/PARCELLATION-COMPARISON.md /scratch/users/logben/network_analysis/docs/
```

- [ ] **Step 2:** In `network_analysis`, commit it on a `docs/` branch:

```bash
cd /scratch/users/logben/network_analysis
git checkout -b docs/parcellation-comparison
git add docs/PARCELLATION-COMPARISON.md
git commit -m "DOCS: import TM-vs-MSHBM parcellation comparison from neuro_workflow"
git push -u origin docs/parcellation-comparison
```

- [ ] **Step 3:** Back in neuro_workflow, remove it + repoint any links:

```bash
cd /scratch/users/logben/neuro_workflow_refactor
git rm docs/PARCELLATION-COMPARISON.md
grep -rn "PARCELLATION-COMPARISON" docs/ CLAUDE.md README.md --include='*.md'
```
Repoint hits to note it now lives in network_analysis.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "DOCS: move PARCELLATION-COMPARISON (analysis result) to network_analysis"
```

### Task 11: Delete docs/archive and docs/audits from main

**Files:** `git rm -r docs/archive docs/audits`.

- [ ] **Step 1:** Confirm nothing in the shipped docs links INTO archive/audits as a live reference:

Run: `grep -rn "docs/archive\|docs/audits" docs/*.md CLAUDE.md README.md`
Expected: only historical mentions; repoint/remove any that present them as current.

- [ ] **Step 2:** Remove them (retained in git history):

```bash
git rm -r docs/archive docs/audits
git commit -m "DOCS: remove dev-history archive/ and audits/ from shipped tree (kept in git history)"
```

### Task 12: Make README the navigational hub

**Files:** Modify `README.md`.

- [ ] **Step 1:** Add/refresh a "## Documentation" section listing the 8 essential docs with one-line purposes and links: `ARCHITECTURE`, `CONFIG`, `DATASETS`, `PIPELINE-WALKTHROUGH`, `PROVENANCE-AND-EXCLUSIONS`, `RUNBOOK`, `SCAN-NOTES`, `REFERENCES`. Ensure install + "run a stage" pointers exist and point at PIPELINE-WALKTHROUGH/RUNBOOK.
- [ ] **Step 2:** Update the CLAUDE.md "Authoritative Documentation" list to the 8-doc set (already partially done for PROVENANCE-AND-EXCLUSIONS; ensure WORKFLOW/PROVENANCE/PARCELLATION entries are gone).
- [ ] **Step 3: Verify no dangling doc-links**

Run: `for f in $(grep -rohE '\bdocs/[A-Za-z0-9_-]+\.md' docs/ README.md CLAUDE.md | sort -u); do test -e "$f" || echo "DANGLING: $f"; done`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "DOCS: make README the navigational hub; sync CLAUDE.md doc list"
```

- [ ] **Step 5: Push + open PR2**

```bash
git push -u origin docs/consolidate
gh pr create --repo lobennett/neuro_workflow --base repro-harness-2026-06 --head docs/consolidate \
  --title "DOCS: consolidate to the essential doc set" --body "Fold WORKFLOW+PROVENANCE; move PARCELLATION-COMPARISON to network_analysis; remove archive/audits; README as hub. 🤖 Generated with Claude Code"
```

---

## PR3 — `docs/run-instructions`

Branch: `docs/run-instructions` off PR2's tip. PR title: `DOCS: current run instructions for every stage`.

### Task 13: Fix stale RUNBOOK sections (moved-out stages)

**Files:** Modify `docs/RUNBOOK.md`.

- [ ] **Step 1:** In `RUNBOOK.md`, replace the BODIES of §2.3 (XCP-D), §2.6 (prep-mshbm), §2.7 (mshbm), §2.9 (prevalence) — which reference `templates/{xcpd,prep_mshbm,mshbm}.sbatch` that no longer exist here — with a one-line pointer each:

> **Moved.** This stage now lives in the `network_analysis` repo (`lobennett/network_analysis`). See its `templates/<stage>.sbatch` and `neuro-run submit <stage>` there.

- [ ] **Step 2: Verify no RUNBOOK command references a deleted template**

Run: `grep -nE "templates/(xcpd|mshbm|prep_mshbm)" docs/RUNBOOK.md`
Expected: no output (only prose pointers remain).

- [ ] **Step 3: Commit**

```bash
git add docs/RUNBOOK.md
git commit -m "DOCS: RUNBOOK — replace moved-out stage bodies (XCP-D/MSHBM/prevalence) with network_analysis pointers"
```

### Task 14: Verify per-stage run coverage end-to-end

**Files:** Modify `docs/PIPELINE-WALKTHROUGH.md` and/or `docs/RUNBOOK.md` as gaps require.

- [ ] **Step 1:** For each core stage, confirm a current runnable command exists (in PIPELINE-WALKTHROUGH or RUNBOOK): bidsify, trim, reconcile, migrate, events, fMRIPrep, **XCP-D (pointer)**, lev1, lev1-outlier, lev2, QA report. Build a checklist and mark each ✔/gap.
- [ ] **Step 2:** For the one identified gap (XCP-D run pointer in PIPELINE-WALKTHROUGH C2, which only covers `build_xcpd_view.py`), add a one-line note that the XCP-D run itself is executed via `network_analysis`.
- [ ] **Step 3:** Confirm every referenced template exists in `templates/`:

Run: `for t in bidsify fmriprep lev1 lev2; do test -e templates/$t.sbatch && echo "ok $t" || echo "MISSING $t"; done`
Expected: all ok.

- [ ] **Step 4: Commit + push + open PR3**

```bash
git add -A docs/
git commit -m "DOCS: verify + fill per-stage run instructions (add XCP-D run pointer)"
git push -u origin docs/run-instructions
gh pr create --repo lobennett/neuro_workflow --base repro-harness-2026-06 --head docs/run-instructions \
  --title "DOCS: current run instructions for every stage" --body "Fix stale RUNBOOK moved-out sections; ensure every stage has a current command or pointer. 🤖 Generated with Claude Code"
```

---

## PR0 (gated) & PR4 (gated) — not planned in task detail

- **PR0 — merge `repro-harness-2026-06` → `main`.** Execute when the iProc campaign finishes and the git-sync hold lifts: standard PR/merge, then rebase PR1–PR3 onto `main` and switch their `--base` to `main`.
- **PR4 — `chore/scripts-tidy`.** After Oak re-execution finalizes: `git rm` the confirmed-retired one-offs (`recompile_delta.py`, `remove_orphan_derivatives.py`, `audit_events_vs_task_configs.py`, `audit_subject_flywheel_vs_bids.py`; `verify` `reconcile_audit.py`), keep documented pipeline scripts. One small CHORE: PR.

---

## Self-Review

**Spec coverage:** PR1 (CI, ruff, pre-commit, LICENSE, CITATION, CONTRIBUTING, PR template, scratch cleanup) → Tasks 1–8 ✔. PR2 (fold WORKFLOW/PROVENANCE, move PARCELLATION-COMPARISON, delete archive/audits, README hub) → Tasks 9–12 ✔. PR3 (stale RUNBOOK, per-stage coverage) → Tasks 13–14 ✔. PR0/PR4 gated + documented ✔. iProc-extraction precondition + `core.slurm`/`pipelines.base` guard noted ✔. Success criteria (CI gate, standards present, docs consolidated, no src change) all map to tasks ✔.

**Placeholder scan:** LICENSE choice is a real DECISION GATE (Task 4 Step 1), not a lazy placeholder — flagged for PI confirmation with a default. All file contents are provided inline. No "TBD"/"handle edge cases".

**Type/name consistency:** branch names, PR titles, and the `tests/ --ignore=tests/analysis` gate are used identically across CI (Task 3), CONTRIBUTING (Task 7), PR template (Task 7), and success criteria. ruff `select` set is consistent between `pyproject.toml` (Task 2) and pre-commit (Task 6, via the ruff hook).
