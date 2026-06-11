# Lev2 Flagged-Scans Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the broken `filter_flagged_scans` function and its `--flagged-scans-csv` / `--exclusions-csv` plumbing from lev2 (analysis script, pipeline, template, tests, README).

**Architecture:** Pure deletion. The chain (`.bidsignore` → fmriprep → lev1 honors `compiled_exclusions.json` → fixed-effects skip-or-tag → lev2 `_desc-belowMinRuns` filter from C2) already covers every meaningful case. The dead filter is removed without replacement.

**Tech Stack:** Python 3.13, argparse, jinja-style sbatch template, pytest.

**Spec:** `docs/superpowers/specs/2026-05-07-lev2-flagged-scans-cleanup-design.md`

---

## Affected files (snapshot grep, 2026-05-07)

| File | What references the dead arg |
|---|---|
| `src/neuro_workflow/analysis/lev2/run.py` | `filter_flagged_scans` function (lines 55-116), `import pandas as pd` (line 16, only used in this function), `--flagged-scans-csv` argparse (lines 239-244), call site + `Flagged scans CSV: ...` print (lines 261, 282-288) |
| `src/neuro_workflow/pipelines/lev2.py` | `--exclusions-csv` argparse arg (line 42), `exclusions_csv` field in `build_context` return (line 91) |
| `src/neuro_workflow/templates/lev2.sbatch` | `--flagged-scans-csv "{exclusions_csv}"` line in the rendered command |
| `tests/pipelines/test_lev2.py` | `exclusions_csv` in two `Namespace(...)` fixtures (lines 83, 127), `ctx["exclusions_csv"]` assertion (line 105), `assert "--flagged-scans-csv" in script` assertion (line 150) |
| `tests/test_all_templates_render.py` | `exclusions_csv="/flagged.csv"` in `test_lev2_template_renders` Namespace (line 89) |
| `README.md` | Example: `--exclusions-csv /oak/.../exclusions.csv \` (line 386) |

The implementer may grep for `flagged.scans.csv|flagged_scans_csv|exclusions_csv|exclusions-csv` after each task to confirm the expected references remain (or are gone).

---

## Task 1: Delete from `analysis/lev2/run.py`

Removes the dead filter function and its CLI arg from the analysis script. After this task, the script still works correctly when invoked (the arg is just gone), and the rendered sbatch still passes a flag the script no longer accepts — but no tests actually run the rendered sbatch, so all tests stay green. The pipeline + template cleanup follows in Task 2.

**Files:**
- Modify: `src/neuro_workflow/analysis/lev2/run.py`

- [ ] **Step 1.1: Read `src/neuro_workflow/analysis/lev2/run.py` and confirm pandas usage**

```bash
grep -n "pd\.\|import pandas" /home/users/logben/neuro_workflow/src/neuro_workflow/analysis/lev2/run.py
```

Expected: exactly one `import pandas as pd` and one `pd.read_csv(...)` inside `filter_flagged_scans`. If pandas is used anywhere else, do not delete the import in Step 1.4.

- [ ] **Step 1.2: Delete the `filter_flagged_scans` function**

In `src/neuro_workflow/analysis/lev2/run.py`, delete the entire function definition (currently lines ~55-116, the block starting `def filter_flagged_scans(input_files: ...)` and ending at the blank line before `def discover_input_files(...)`).

- [ ] **Step 1.3: Delete the `--flagged-scans-csv` argparse argument**

In the same file, locate `get_parser()` (around line 206) and delete the block:

```python
    parser.add_argument(
        '--flagged-scans-csv',
        type=str,
        required=True,
        help='Path to CSV file containing flagged scans to exclude from analysis',
    )
```

- [ ] **Step 1.4: Delete the call site and the print line in `main()`**

Locate `main()` (around line 248). Delete:

```python
    print(f'Flagged scans CSV: {args.flagged_scans_csv}')
```

(part of the header print block) and the call site:

```python
    # Filter out flagged scans using provided CSV file
    print(f'Filtering flagged scans using: {args.flagged_scans_csv}')
    input_files = filter_flagged_scans(input_files, args.flagged_scans_csv, args.contrast)
    
    if not input_files:
        print(f'ERROR: No input files remain after filtering flagged scans for contrast {args.contrast}')
        return 1
```

The post-filter empty-check goes too — there's already an empty-check after `discover_input_files` (around line 278) which now handles the only case where no files remain.

- [ ] **Step 1.5: Delete the pandas import (if no other use)**

If Step 1.1 confirmed `filter_flagged_scans` was the only consumer, delete:

```python
import pandas as pd
```

If anything else uses `pd.`, leave the import.

- [ ] **Step 1.6: Verify the module imports cleanly**

```bash
module load uv
uv run python -c "from neuro_workflow.analysis.lev2 import run; print('ok')"
```

Expected: `ok`. (If pandas was deleted incorrectly and a `pd.` reference survived, this would fail.)

- [ ] **Step 1.7: Verify no straggler references**

```bash
grep -n "flagged_scans_csv\|filter_flagged_scans\|flagged-scans-csv" /home/users/logben/neuro_workflow/src/neuro_workflow/analysis/lev2/run.py
```

Expected: empty (no matches).

- [ ] **Step 1.8: Run the lev2 analysis tests**

```bash
uv run pytest tests/analysis/lev2/ -v
```

Expected: 1 passed (`test_discover_input_files_filters_below_min_runs`). The C2 filter is unchanged.

- [ ] **Step 1.9: Run the broader analysis suite for regressions**

```bash
uv run pytest tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 1.10: Commit**

```bash
git add src/neuro_workflow/analysis/lev2/run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(lev2): delete broken filter_flagged_scans function

The filter substring-matched per-scan identifiers (sub-X_ses-Y_run-Z)
against fixed-effects filenames (sub-X_task-Y_contrast-Z), which never
match because fixed-effects aggregate sessions. The chain
(.bidsignore → fmriprep → lev1 → fixed-effects skip-or-tag → C2's
_desc-belowMinRuns filter in discover_input_files) covers every case
the dead filter pretended to handle.

Drops --flagged-scans-csv from the analysis script's CLI and the now-
unused pandas import. Pipeline + template + test cleanup follows in
the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Delete from pipeline + template + tests (atomic)

`pipelines/lev2.py`, `templates/lev2.sbatch`, `tests/pipelines/test_lev2.py`, and `tests/test_all_templates_render.py` are tightly coupled — changing the pipeline without updating the template and tests breaks the test suite. Single commit covering all four files.

**Files:**
- Modify: `src/neuro_workflow/pipelines/lev2.py`
- Modify: `src/neuro_workflow/templates/lev2.sbatch`
- Modify: `tests/pipelines/test_lev2.py`
- Modify: `tests/test_all_templates_render.py`

- [ ] **Step 2.1: Edit `src/neuro_workflow/pipelines/lev2.py`**

In `add_cli_args`, delete the line:

```python
        parser.add_argument("--exclusions-csv", required=True, help="Flagged scans CSV")
```

In `build_context`, delete the `"exclusions_csv"` line from the returned dict:

```python
            "exclusions_csv": args.exclusions_csv,
```

- [ ] **Step 2.2: Edit `src/neuro_workflow/templates/lev2.sbatch`**

Delete the line:

```
    --flagged-scans-csv "{exclusions_csv}" \
```

The trailing `\` continuation on the prior line should still be present (the previous line ends `--output-dir "{results_dir}" \`). After deletion, the next line should be `--mask-threshold {mask_threshold} \`. Confirm by re-reading the file.

- [ ] **Step 2.3: Edit `tests/pipelines/test_lev2.py`**

In `test_lev2_build_context_explicit_contrasts` (around line 72), remove these lines from the `Namespace(...)` fixture (around line 83):

```python
        exclusions_csv="/path/to/flagged.csv",
```

And remove the assertion (around line 105):

```python
    assert ctx["exclusions_csv"] == "/path/to/flagged.csv"
```

In `test_lev2_render_full_template` (around line 116), remove from the `Namespace(...)` fixture (around line 127):

```python
        exclusions_csv="/path/to/flagged.csv",
```

And remove the assertion (around line 150):

```python
    assert "--flagged-scans-csv" in script
```

- [ ] **Step 2.4: Edit `tests/test_all_templates_render.py`**

In `test_lev2_template_renders` (around line 84), remove from the `Namespace(...)` fixture (around line 89):

```python
        exclusions_csv="/flagged.csv",
```

- [ ] **Step 2.5: Verify no straggler references**

```bash
grep -rn "flagged.scans.csv\|flagged_scans_csv\|exclusions_csv\|exclusions-csv" /home/users/logben/neuro_workflow/src /home/users/logben/neuro_workflow/tests
```

Expected: empty (no matches anywhere in `src/` or `tests/`).

- [ ] **Step 2.6: Run pipeline tests**

```bash
uv run pytest tests/pipelines/test_lev2.py tests/test_all_templates_render.py::test_lev2_template_renders -v
```

Expected: all green. 7 tests in `test_lev2.py` plus the lev2 template-render test.

- [ ] **Step 2.7: Run full pipelines + analysis suites**

```bash
uv run pytest tests/pipelines/ tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 2.8: CLI smoke**

```bash
uv run python -m neuro_workflow.analysis.lev2.run --help 2>&1 | grep -i 'flagged\|exclusions' || echo '(no matches — clean)'
```

Expected: `(no matches — clean)`. The arg is gone.

```bash
uv run neuro-run show lev2 --help 2>&1 | grep -i 'exclusions-csv' || echo '(no matches — clean)'
```

Expected: `(no matches — clean)`.

- [ ] **Step 2.9: Commit**

```bash
git add src/neuro_workflow/pipelines/lev2.py \
        src/neuro_workflow/templates/lev2.sbatch \
        tests/pipelines/test_lev2.py \
        tests/test_all_templates_render.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(lev2): drop --exclusions-csv plumbing from pipeline + template

Removes the now-orphaned argument from the lev2 pipeline class, drops
the rendered --flagged-scans-csv line from the sbatch template, and
updates the pipeline + template-render tests to match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update README example

**Files:**
- Modify: `README.md`

- [ ] **Step 3.1: Edit `README.md`**

In the lev2 example block (around lines 382-388), delete the `--exclusions-csv` line:

```bash
neuro-run submit lev2 discovery \
  --lev1-dirs /oak/.../lev1_discovery \
  --results-dir /oak/.../lev2_discovery \
  --exclusions-csv /oak/.../exclusions.csv \
  --base-tasks
```

becomes:

```bash
neuro-run submit lev2 discovery \
  --lev1-dirs /oak/.../lev1_discovery \
  --results-dir /oak/.../lev2_discovery \
  --base-tasks
```

- [ ] **Step 3.2: Verify no straggler references in README**

```bash
grep -n "flagged.scans.csv\|exclusions-csv\|exclusions_csv" /home/users/logben/neuro_workflow/README.md
```

Expected: empty (no matches).

- [ ] **Step 3.3: Commit**

```bash
git add README.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(README): drop --exclusions-csv from lev2 example

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Final verification

**Files:** none (verification only).

- [ ] **Step 4.1: Repo-wide straggler grep**

```bash
grep -rn "flagged.scans.csv\|flagged_scans_csv\|exclusions_csv\|exclusions-csv" \
    /home/users/logben/neuro_workflow/src \
    /home/users/logben/neuro_workflow/tests \
    /home/users/logben/neuro_workflow/README.md \
    /home/users/logben/neuro_workflow/docs 2>&1 \
  | grep -v 'docs/superpowers/specs/' \
  | grep -v 'docs/superpowers/plans/' \
  || echo '(empty — clean)'
```

Expected: `(empty — clean)`. (The spec and plan documents reference the old names by design — they are excluded from this check.)

- [ ] **Step 4.2: Full broader test suite**

```bash
uv run pytest tests/ -q --tb=line --ignore=tests/analysis 2>&1 | tail -5
uv run pytest tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: both green. The split avoids the analysis-suite optional-dep issues.

- [ ] **Step 4.3: No commit unless something surfaces a fix.**

---

# Self-Review

**Spec coverage:**
- Goal 1 (delete `filter_flagged_scans`) → Task 1 Step 1.2.
- Goal 2 (delete `--flagged-scans-csv` arg + call site + print line) → Task 1 Steps 1.3, 1.4.
- Goal 3 (drop pandas import if no other usage) → Task 1 Step 1.5 (with the verify-first guard in Step 1.1).
- Goal 4 (drop pipeline + template plumbing) → Task 2 Steps 2.1, 2.2.
- Goal 5 (update pipeline test) → Task 2 Step 2.3.
- Goal 6 (existing tests pass) → Task 1 Steps 1.8-1.9, Task 2 Steps 2.6-2.7, Task 4 Step 4.2.
- README cleanup (mentioned in spec architecture but not numbered as a goal) → Task 3.
- `tests/test_all_templates_render.py` (mentioned as a snapshot finding in the affected-files table) → Task 2 Step 2.4.

**Type consistency:**
- `--exclusions-csv` (pipeline-side) and `--flagged-scans-csv` (script-side) names are used consistently across all referenced steps. The pipeline-side template variable is `{exclusions_csv}` (snake_case) — also consistent.

**Placeholder scan:** no TBD / "implement later" / generic guidance. Each step lists the exact text to remove and the exact verification command. Step 1.1's grep instruction is concrete (the implementer reads the output and decides whether to delete the import).

**Risk notes:**
- Task 2's atomic 4-file change is bigger than the typical bite-sized step. Splitting it would introduce broken-but-temporary states (e.g., template missing a placeholder while pipeline still passes one). Atomic is correct here.
- The `grep -v 'docs/superpowers/'` in Step 4.1 excludes the spec + plan documents, which legitimately reference the old names. If the implementer's grep flags those, that's expected.
