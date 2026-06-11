# Lev2 Flagged-Scans Cleanup — design

**Date:** 2026-05-07
**Status:** Draft, ready for review
**Scope:** Project C, slice C3 — delete the broken `--flagged-scans-csv` filter from lev2. Out of scope: C0 (audit trail), end-to-end exclusion-flow doc.

---

## Context

`neuro_workflow.analysis.lev2.run.filter_flagged_scans` (lines 55-116) was added before this round of audits. It's intended to drop fixed-effects files corresponding to flagged scans listed in a CSV (`--flagged-scans-csv`). Two problems:

1. **The filter does not do what it claims.** The CSV's `subject_label` column is documented as `"sub-s03_ses-02_run-1"` (per-scan, with session and run). The filter builds substrings like `"sub-s03_ses-02_run-1_task-cuedTS"` and substring-matches against fixed-effects filenames. Fixed-effects filenames are `sub-s03_task-cuedTS_contrast-X_rtmodel-RTDur_stat-fixed-effects.nii.gz` — they don't contain `ses-02_run-1` because sessions are already aggregated in fixed effects. The substring never matches. The filter prints `Excluded 0 flagged files` regardless of CSV contents.
2. **The work this filter is supposed to do is already done elsewhere.** The exclusion chain (`.bidsignore` → fmriprep skips → lev1 honors `compiled_exclusions.json` → fixed-effects skip-or-tag) covers every meaningful lev2-relevant case:
    - Whole-subject exclusion (every session bad) → lev1 zero-files guard produces no fixed-effects file → lev2 doesn't see it.
    - Most-sessions excluded (`n_runs < min_runs`) → C2's `_desc-belowMinRuns` tag → C2's filter in `discover_input_files` drops it at lev2.
    - Per-scan exclusion at lev1 already happened before fixed-effects was computed; sessions are aggregated, so per-scan filtering at lev2 is meaningless.

This spec deletes the dead filter. Lev2 keeps only the `_desc-belowMinRuns` filter from C2 — the only meaningful group-level guard.

---

## Goals

1. Delete `filter_flagged_scans` function from `src/neuro_workflow/analysis/lev2/run.py`.
2. Delete the `--flagged-scans-csv` argparse argument and its call site / print line.
3. Drop the `import pandas as pd` if no other usage remains in the file.
4. Update `src/neuro_workflow/pipelines/lev2.py` and the lev2 sbatch template to drop the `flagged_scans_csv` field everywhere it's threaded through.
5. Update `tests/pipelines/test_lev2.py` to drop any reference to the removed arg.
6. Existing tests (`tests/analysis/lev2/test_run.py::test_discover_input_files_filters_below_min_runs` and the rest of `tests/pipelines/test_lev2.py`) keep passing.

## Non-goals

- Adding `--exclusions-file` to lev2 (rejected during brainstorming as redundant — the chain already covers all meaningful cases).
- Adding a new CSV-from-JSON converter (similarly redundant).
- Backward compatibility for saved sbatch scripts that pass `--flagged-scans-csv ...` — those scripts were already producing misleading output, and there's no external API surface in this repo to preserve.

---

## Architecture

Pure deletion. No new components or interfaces.

```
src/neuro_workflow/analysis/lev2/run.py     ← delete function + arg + call + import
src/neuro_workflow/pipelines/lev2.py        ← drop flagged_scans_csv plumbing
src/neuro_workflow/templates/lev2.sh.j2     ← drop --flagged-scans-csv line (verify path)
tests/pipelines/test_lev2.py                ← drop any flagged_scans_csv references
```

The implementer should grep for `flagged_scans_csv` and `flagged-scans-csv` across the repo at implementation time and remove every reference. The list above is what the snapshot grep showed; if more turn up at implementation time (e.g., a separate templates dir), drop those too.

---

## Data flow

Before:

```
neuro-run submit lev2 <ds> --contrast X --flagged-scans-csv /path/foo.csv ...
                        ↓ rendered into sbatch ↓
python -m neuro_workflow.analysis.lev2.run \
    --contrast X --flagged-scans-csv /path/foo.csv --level1-dirs ...
                        ↓
discover_input_files (drops _desc-belowMinRuns)
                        ↓
filter_flagged_scans (does nothing; misleading "Excluded 0 flagged files")
                        ↓
run_level2_analysis
```

After:

```
neuro-run submit lev2 <ds> --contrast X ...      (--flagged-scans-csv removed)
                        ↓ rendered into sbatch ↓
python -m neuro_workflow.analysis.lev2.run --contrast X --level1-dirs ...
                        ↓
discover_input_files (drops _desc-belowMinRuns)
                        ↓
run_level2_analysis
```

---

## Error handling + edge cases

- **No new error paths.** Just removing code.
- **Loosens validation**: `--flagged-scans-csv` was `required=True`. Removing it means a caller that omits it succeeds (correct — the arg was meaningless).
- **Backward compat with saved sbatch scripts**: a saved script that still passes `--flagged-scans-csv ...` will hit argparse's `unrecognized arguments` error. Acceptable for this repo — there's no external user with sbatch artifacts.
- **The `pandas` import**: grep `pd.` and `pandas` in `lev2/run.py` before deleting; if any other usage remains, keep the import. The snapshot read showed `filter_flagged_scans` was the only consumer, but verify at implementation time.
- **Lev2 sbatch fixture in pipeline test**: if the test currently passes a `--flagged-scans-csv` value to keep the old required arg satisfied, drop both the arg and the fixture line. If the test asserts the arg appears in the rendered output, delete that assertion.

---

## Tests

No new tests. Verification by existing tests + smoke checks:

1. `tests/analysis/lev2/test_run.py::test_discover_input_files_filters_below_min_runs` — must still pass; `discover_input_files` is unchanged.
2. `tests/pipelines/test_lev2.py` — full file must still pass after the pipeline-side delete. Implementer adjusts assertions if any reference the removed arg.
3. CLI smoke: `uv run python -m neuro_workflow.analysis.lev2.run --help` no longer lists `--flagged-scans-csv`.
4. Module import smoke: `uv run python -c "from neuro_workflow.analysis.lev2 import run"` succeeds. (Catches a stray pandas reference if the import was deleted but a `pd.` survived.)
5. Full broader suite: `uv run pytest tests/analysis/ tests/pipelines/ -q --tb=line` — green.

---

## Code-style guardrails

- Pure deletion, no refactor. No moving things around just because we're touching the file.
- One commit per artifact (analysis/lev2/run.py changes, pipeline changes, template change, test change). Or one commit if the changes are tightly coupled and tested together — the implementer's call.
- No replacement docstring or commented-out "see PR #X" stubs. If code is gone, it's gone.
- If the lev2 sbatch template lives in a path other than `src/neuro_workflow/templates/lev2.sh.j2`, the implementer reads `pipelines/lev2.py` to find the actual template path.

---

## Open questions / decisions deferred to implementation

1. **Exact template file path**: the implementer locates the rendered template by reading `pipelines/lev2.py:build_context` and following the `template_name` reference.
2. **Whether the pipeline test test_lev2.py asserts on rendered command contents**: the implementer reads the test, drops references, runs the test.
3. **Whether removing the `import pandas as pd` is safe**: grep first; if pandas is used outside the deleted function, keep the import.
