# Fixed-Effects min_runs Floor — design

**Date:** 2026-05-07
**Status:** Draft, ready for review
**Scope:** Project C, slice C2 — replace the unenforced `_desc-highExclusion` tag with an enforced absolute `min_runs` floor honored by lev2. Out of scope: qa_report decisions plumbing (C1), lev2 `--exclusions-file` symmetry (C3), end-to-end exclusion-flow doc.

---

## Context

Today, lev1 fixed-effects sets a filename suffix `_desc-highExclusion` when more than 50% of a `(subject, task)`'s expected sessions are excluded (`src/neuro_workflow/analysis/core/utils.py:264`, applied at `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py:285-286`). The tag is not honored by lev2 (`src/neuro_workflow/analysis/lev2/run.py:131-141` globs all `*_stat-fixed-effects.nii.gz`). Lev1 also has no `min_runs` guard — `if not effect_files` (line 194) is the only check, so a 1-of-5 fixed-effects map silently enters group analysis with a tag nobody reads.

This is a real data-integrity gap surfaced by the post-merge audit of PR #5. Project C addresses several related exclusion-flow issues; this slice fixes the most acute one.

---

## Goals

1. Replace the unenforced relative rule (`exclusion_rate > 0.5`) with an enforced absolute floor (`n_runs < min_runs`, default `min_runs=2`).
2. Lev2 honors the floor automatically by filtering out tagged files from its input glob.
3. New, descriptive tag: `_desc-belowMinRuns`. The old `_desc-highExclusion` and all of its plumbing are deleted.
4. `min_runs` is configurable via `--min-runs INT` on `neuro-run submit lev1`, default 2.
5. One stderr WARNING line per tagged `(subject, task)` is the audit trail. No new manifest files.
6. Discovery lev1 is re-run after merge to overwrite orphan `_desc-highExclusion` files. Validation lev1 has not run yet, so no migration is needed there.

## Non-goals

- Qa_report decisions plumbing (Project C, slice C1).
- Adding a `--exclusions-file` arg to lev2 (Project C, slice C3).
- A `--include-low-n` override flag on lev2 (YAGNI; if a researcher wants a low-N map, they can inspect it manually outside the pipeline).
- A queryable TSV manifest of tagged subjects (YAGNI; SLURM `.err` is the existing audit pattern).

---

## Architecture

The change is mechanical at three points: lev1 fixed-effects (apply the tag), lev1 CLI (accept the flag and thread it through), lev2 (filter the glob result). The deleted `high_exclusion` plumbing nets a small code reduction.

```
src/neuro_workflow/analysis/lev1/processing/fixed_effects.py     ← edit
src/neuro_workflow/analysis/lev1/run.py                          ← edit
src/neuro_workflow/analysis/core/utils.py                        ← edit (delete dead code)
src/neuro_workflow/analysis/lev2/run.py                          ← edit
tests/analysis/lev1/test_fixed_effects.py                        ← create or extend
tests/analysis/lev2/test_run.py                                  ← create or extend
```

Each unit has one clear responsibility:
- **fixed_effects.py**: decides whether a saved map is tagged based on its own state (`n_runs`, `min_runs`) and emits a WARNING when tagging.
- **lev1/run.py**: surfaces `min_runs` at the CLI and passes it to the analyzer.
- **lev2/run.py**: filters tagged files out of group analysis input via a substring check.

The policy is encoded in the filename. There is no parallel state in `~/.neuro_workflow/` to keep in sync.

---

## Data flow

```
[lev1 per-run effects + variances]
            ↓
SubjectFixedEffectsAnalyzer.compute_fixed_effects_contrast(...)
   - len(effect_files) → contrast_results[contrast_name]['n_runs']
            ↓
SubjectFixedEffectsAnalyzer.save_fixed_effects_maps(...)
   - if n_runs < self.min_runs:
        filename includes "_desc-belowMinRuns"
        log.warning("tagged sub-X/task-Y as _desc-belowMinRuns: n=N (min=M)")
   - else: untagged
            ↓
[lev1 fixed_effects/sub-X/.../*.nii.gz files on disk]
            ↓
gather_files_for_contrast(level1_dirs, contrast_name)   # lev2/run.py
   - glob.glob(*_stat-fixed-effects.nii.gz)
   - filter: drop any path containing "_desc-belowMinRuns_"
   - print(f"...filtered {n_filtered} below-min-runs files")
            ↓
run_level2_analysis(input_files, ...)   # untagged only
            ↓
[lev2 group analysis honors the floor automatically]
```

**Idempotency:** rerunning lev1 with the same `--min-runs` produces identical filenames. Changing `--min-runs` on a rerun overwrites the previous tag/no-tag state correctly.

---

## Tag placement

The new tag goes between `rtmodel-RTDur` and `_stat-fixed-effects`, mirroring the prior `high_excl_tag` position:

```
sub-s03_task-flanker_contrast-incongruent-congruent_rtmodel-RTDur_desc-belowMinRuns_stat-fixed-effects.nii.gz
```

Lev2's filter uses the substring `_desc-belowMinRuns_` so it is order-tolerant: any future entity additions before or after the tag are fine.

---

## Components

### `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`

- Drop `self.high_exclusion` attribute (currently set in `__init__`, used at line 285-286).
- Add `min_runs: int = 2` parameter to the `SubjectFixedEffectsAnalyzer` constructor; store as `self.min_runs`.
- In `save_fixed_effects_maps`, after computing `base_filename`:
  ```python
  n_runs = self.contrast_results[contrast_name]['n_runs']
  below_min = n_runs < self.min_runs
  if base_filename is None:
      tag = '_desc-belowMinRuns' if below_min else ''
      base_filename = f'{self.subject_id}{hemi_tag}{space_tag}_task-{self.task_name}_contrast-{contrast_name}_rtmodel-RTDur{tag}_stat-fixed-effects'
  if below_min:
      logger.warning(
          'tagged %s/task-%s/contrast-%s as _desc-belowMinRuns: n_runs=%d (min=%d)',
          self.subject_id, self.task_name, contrast_name, n_runs, self.min_runs,
      )
  ```
- Existing zero-files guard at line 194 (`if not effect_files`) is unchanged.

### `src/neuro_workflow/analysis/lev1/run.py`

- Add CLI arg:
  ```python
  parser.add_argument('--min-runs', type=int, default=2,
                      help='Minimum number of runs required to compute a non-tagged fixed-effects map (default: 2).')
  ```
- Validate: if `args.min_runs < 1`, `parser.error('--min-runs must be >= 1')`.
- Pass `min_runs=args.min_runs` to `SubjectFixedEffectsAnalyzer(...)`.
- Delete the call site that computed and threaded `high_exclusion` through (around lines 579-612). Verify no other callers; if any remain, drop them too.

### `src/neuro_workflow/analysis/core/utils.py`

- `count_subject_exclusions` returns `high_exclusion` and `exclusion_rate` (line 264). The function may have other useful callers (e.g., reporting) — grep before deciding.
- If `high_exclusion` is no longer consumed anywhere: drop the field from the return.
- If the function as a whole is unused elsewhere: delete it. Grep results inform the choice at implementation time.

### `src/neuro_workflow/analysis/lev2/run.py`

- In `gather_files_for_contrast` (line ~120-141), after `files = glob.glob(str(pattern))`:
  ```python
  filtered = [f for f in files if '_desc-belowMinRuns_' not in f]
  n_filtered = len(files) - len(filtered)
  if n_filtered:
      print(f'gather_files_for_contrast: filtered {n_filtered} _desc-belowMinRuns files for {contrast_name}')
  all_files.extend(filtered)
  ```

---

## Error handling + edge cases

- **`n_runs == 0`** (every session excluded): existing guard at `fixed_effects.py:194` short-circuits — no file written, nothing to tag. No code change.
- **`min_runs <= 0`**: argparse-validated; `parser.error` exits with a clear message.
- **`min_runs > expected_sessions`** (e.g. `--min-runs 5` on a 2-session dual task): every subject for that task gets tagged, lev2 finds zero files, group analysis prints "No input files found" and returns. Not an error — the researcher set an impossible floor and the system says so.
- **Mixed old + new tags during migration window**: the new lev2 filter only matches `_desc-belowMinRuns_`. Pre-existing `_desc-highExclusion` files are *still included* by lev2 (same as before C2 — there was never enforcement). Mitigated by re-running discovery lev1 immediately after merge so no orphans remain. Validation lev1 has not run, so no orphans there.
- **Logging volume**: one WARNING line per tagged `(subject, task, contrast)` triple. Worst case `n_subjects × n_tasks × n_contrasts ≈ 46 × 8 × ~5 = 1840` lines if every subject/task/contrast hit the floor — fine.

---

## Tests

`tests/analysis/lev1/test_fixed_effects.py` (extend or create):

1. **`test_tagged_when_below_min_runs`** — analyzer with 1 effect file + 1 variance file, `min_runs=2`, save. Assert filename contains `_desc-belowMinRuns_`.
2. **`test_untagged_at_min_runs_floor`** — 2 effect files, `min_runs=2`. Assert no `belowMinRuns` substring.
3. **`test_min_runs_is_configurable`** — 2 effect files, `min_runs=3`. Assert tagged.
4. **`test_no_high_exclusion_attribute`** — instantiate analyzer; assert `not hasattr(analyzer, 'high_exclusion')` so the deleted plumbing stays gone.

`tests/analysis/lev2/test_run.py` (extend or create):

5. **`test_gather_excludes_belowMinRuns_files`** — tmp dir with 4 fake fixed-effects NIfTIs (2 tagged with `_desc-belowMinRuns_`, 2 not). Call `gather_files_for_contrast`. Assert exactly the 2 untagged are returned.

CLI test (lightweight, in `tests/analysis/lev1/test_run.py` or nearest existing):

6. **`test_lev1_run_accepts_min_runs_flag`** — parse CLI with `--min-runs 3`; assert namespace has `min_runs == 3`.
7. **`test_min_runs_must_be_positive`** — parse with `--min-runs 0`; assert `SystemExit`.

**Operational verification (post-merge):**

- Re-run discovery lev1 (`uv run neuro-run submit lev1 discovery ...`); spot-check that any `(subject, task)` with <2 retained sessions is tagged.
- Run lev2 with the rerun outputs; confirm log line `gather_files_for_contrast: filtered N _desc-belowMinRuns files`.

---

## Code-style guardrails

- TDD throughout: failing test first, then implementation.
- Each commit: one conceptual change + its test. Frequent commits.
- No retroactive abstractions — no "policy registry", no overridable filter hooks. The filter is one comprehension.
- `min_runs=2` is the default in two places only: the CLI parser (canonical) and the analyzer constructor (test ergonomics). Tests construct the analyzer directly and rely on the constructor default; production runs always go through the CLI. No third copy.
- Delete `count_subject_exclusions` or its `high_exclusion` field — don't leave dead fields.

---

## Open questions / decisions deferred to implementation

1. **Whether `count_subject_exclusions` has remaining consumers**: implementer greps and decides whether to drop the function or just the `high_exclusion` field.
2. **Exact line numbers in lev1/run.py for the call-site removal**: the design points at lines 579-612 based on a snapshot read; the implementer reads the file at implementation time and removes the actual range.
3. **Test file paths**: the design names `tests/analysis/lev1/test_fixed_effects.py` and `tests/analysis/lev2/test_run.py`. If these don't exist, the implementer creates them with `__init__.py` next to existing test layouts.
