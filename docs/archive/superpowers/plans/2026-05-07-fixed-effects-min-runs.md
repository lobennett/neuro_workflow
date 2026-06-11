# Fixed-Effects min_runs Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unenforced `_desc-highExclusion` tag (>50% relative rule, never honored by lev2) with an enforced absolute `min_runs` floor (default 2, configurable). Lev2 honors a new `_desc-belowMinRuns` tag by filtering tagged files out of its input glob.

**Architecture:** Three-point change. `FixedEffectsAnalyzer` gains a `min_runs` constructor parameter; the existing inline filename construction is extracted into a `_build_base_filename` method that applies `_desc-belowMinRuns` when `n_runs < min_runs`. `lev1/run.py` gains a `--min-runs INT` CLI arg threaded through to `compute_subject_fixed_effects`. `lev2/run.py:discover_input_files` filters its glob result with one comprehension. All `high_exclusion` plumbing is deleted.

**Tech Stack:** Python 3.13, nilearn (existing), nibabel (existing), pytest (TDD), argparse, glob.

**Spec:** `docs/superpowers/specs/2026-05-07-fixed-effects-min-runs-design.md`

---

## Naming clarifications vs. the spec

The spec uses `SubjectFixedEffectsAnalyzer` and `gather_files_for_contrast`; the actual code uses `FixedEffectsAnalyzer` (`src/neuro_workflow/analysis/lev1/processing/fixed_effects.py:21`) and `discover_input_files` (`src/neuro_workflow/analysis/lev2/run.py:116`). This plan uses the actual names.

---

## Task 1: Scaffold tests/analysis/lev1/test_fixed_effects.py

Create the test file with one smoke test confirming the analyzer is importable. Establishes the file for subsequent TDD.

**Files:**
- Create: `tests/analysis/lev1/test_fixed_effects.py`

- [ ] **Step 1.1: Create the file**

```python
"""Tests for src/neuro_workflow/analysis/lev1/processing/fixed_effects.py."""
from __future__ import annotations


def test_fixed_effects_analyzer_importable():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert a.subject_id == 'sub-x'
    assert a.task_name == 'flanker'
```

- [ ] **Step 1.2: Run; expect PASS**

```bash
module load uv
uv run pytest tests/analysis/lev1/test_fixed_effects.py -v
```

Expected: 1 passed.

- [ ] **Step 1.3: Commit**

```bash
git add tests/analysis/lev1/test_fixed_effects.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(lev1): scaffold test_fixed_effects with import smoke

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `min_runs` constructor parameter (TDD)

**Files:**
- Modify: `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`
- Modify: `tests/analysis/lev1/test_fixed_effects.py`

- [ ] **Step 2.1: Append failing test**

Append to `tests/analysis/lev1/test_fixed_effects.py`:

```python
def test_min_runs_constructor_param_defaults_to_2():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert a.min_runs == 2


def test_min_runs_constructor_param_is_settable():
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker', min_runs=3)
    assert a.min_runs == 3
```

- [ ] **Step 2.2: Run; expect FAIL on AttributeError**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py::test_min_runs_constructor_param_defaults_to_2 -v
```

Expected: FAIL with `AttributeError: 'FixedEffectsAnalyzer' object has no attribute 'min_runs'`.

- [ ] **Step 2.3: Add `min_runs` to `__init__`**

Edit `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`. Find the `__init__` signature (currently lines 24-32) and add `min_runs: int = 2` after `high_exclusion: bool = False`:

```python
def __init__(
    self,
    subject_id: str,
    task_name: str,
    mask_img: Optional[Union[str, Path]] = None,
    high_exclusion: bool = False,
    min_runs: int = 2,
    hemisphere: Optional[str] = None,
    surface_space: str = 'fsnative',
):
```

In the body of `__init__` (currently around lines 47-53), add `self.min_runs = min_runs` after `self.high_exclusion = high_exclusion`:

```python
self.subject_id = subject_id
self.task_name = task_name
self.mask_img = mask_img
self.high_exclusion = high_exclusion
self.min_runs = min_runs
self.hemisphere = hemisphere
self.surface_space = surface_space
self.contrast_results = {}
```

Update the docstring `Args:` section to include `min_runs: Minimum runs required to compute a non-tagged fixed-effects map (default: 2).` and remove the `high_exclusion: Whether >50% of runs were excluded` line — we'll be deleting `high_exclusion` later but the docstring update keeps the file clean now. Actually leave the `high_exclusion` doc line in place for now; Task 9 cleans it up.

- [ ] **Step 2.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py -v
```

Expected: 3 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/processing/fixed_effects.py tests/analysis/lev1/test_fixed_effects.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(lev1): add min_runs param to FixedEffectsAnalyzer

Default 2. Constructor only — application in save_fixed_effects_maps
follows in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Extract `_build_base_filename` and apply `_desc-belowMinRuns` tag (TDD)

Replace the inline filename construction at `fixed_effects.py:284-286` with a private method that uses `self.min_runs` and `self.contrast_results[contrast_name]['n_runs']` to decide whether to include the new tag. Drops the old `_desc-highExclusion` tag entirely.

**Files:**
- Modify: `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`
- Modify: `tests/analysis/lev1/test_fixed_effects.py`

- [ ] **Step 3.1: Append failing tests**

Append to `tests/analysis/lev1/test_fixed_effects.py`:

```python
def test_build_base_filename_no_tag_at_floor():
    """n_runs == min_runs (=2 default) -> no _desc-belowMinRuns substring."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-s03', 'flanker', min_runs=2)
    a.contrast_results['incongruent-congruent'] = {
        'n_runs': 2, 'fixed_effect': None, 'fixed_variance': None,
        'fixed_stat': None, 'input_files': {'effects': [], 'variances': []},
    }
    fname = a._build_base_filename('incongruent-congruent')
    assert '_desc-belowMinRuns' not in fname
    assert 'sub-s03' in fname
    assert 'task-flanker' in fname
    assert 'contrast-incongruent-congruent' in fname
    assert '_rtmodel-RTDur' in fname
    assert '_stat-fixed-effects' in fname


def test_build_base_filename_tags_below_floor():
    """n_runs < min_runs -> filename includes _desc-belowMinRuns_."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-s10', 'flanker', min_runs=2)
    a.contrast_results['response_time'] = {
        'n_runs': 1, 'fixed_effect': None, 'fixed_variance': None,
        'fixed_stat': None, 'input_files': {'effects': [], 'variances': []},
    }
    fname = a._build_base_filename('response_time')
    # Substring includes the trailing '_' so the filter is order-tolerant.
    assert '_desc-belowMinRuns_' in fname


def test_build_base_filename_min_runs_is_configurable():
    """min_runs=3 with n_runs=2 -> tagged."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-s19', 'cuedTS', min_runs=3)
    a.contrast_results['cue_switch_cost'] = {
        'n_runs': 2, 'fixed_effect': None, 'fixed_variance': None,
        'fixed_stat': None, 'input_files': {'effects': [], 'variances': []},
    }
    assert '_desc-belowMinRuns_' in a._build_base_filename('cue_switch_cost')
```

- [ ] **Step 3.2: Run; expect FAIL on AttributeError**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py::test_build_base_filename_no_tag_at_floor -v
```

Expected: FAIL with `AttributeError: 'FixedEffectsAnalyzer' object has no attribute '_build_base_filename'`.

- [ ] **Step 3.3: Implement `_build_base_filename` and rewire `save_fixed_effects_maps`**

In `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`, add a new method to the `FixedEffectsAnalyzer` class (place it after `compute_fixed_effects_contrast` and before `save_fixed_effects_maps`). Use the actual class indentation (4 spaces):

```python
    def _build_base_filename(self, contrast_name: str) -> str:
        """Construct the BIDS-style base filename for this contrast's saved maps.

        Applies the `_desc-belowMinRuns` tag when this contrast's n_runs is
        below `self.min_runs`. The tag substring includes the trailing
        underscore so downstream lev2 filtering can use a substring match.
        """
        if self.hemisphere is not None:
            hemi_tag = f'_hemi-{self.hemisphere}'
            space_tag = f'_space-{self.surface_space}'
        else:
            hemi_tag = ''
            space_tag = ''

        n_runs = self.contrast_results[contrast_name]['n_runs']
        below_min = n_runs < self.min_runs
        below_min_tag = '_desc-belowMinRuns' if below_min else ''

        return (
            f'{self.subject_id}{hemi_tag}{space_tag}'
            f'_task-{self.task_name}'
            f'_contrast-{contrast_name}'
            f'_rtmodel-RTDur{below_min_tag}'
            f'_stat-fixed-effects'
        )
```

In `save_fixed_effects_maps`, replace the inline filename block (currently lines 274-286) with a call to the new method plus a log warning when below the floor. The full block to replace is:

```python
        # Determine file extension and hemisphere tag
        if self.hemisphere is not None:
            file_ext = '.func.gii'
            hemi_tag = f'_hemi-{self.hemisphere}'
            space_tag = f'_space-{self.surface_space}'
        else:
            file_ext = '.nii.gz'
            hemi_tag = ''
            space_tag = ''

        if base_filename is None:
            high_excl_tag = '_desc-highExclusion' if self.high_exclusion else ''
            base_filename = f'{self.subject_id}{hemi_tag}{space_tag}_task-{self.task_name}_contrast-{contrast_name}_rtmodel-RTDur{high_excl_tag}_stat-fixed-effects'
```

The replacement:

```python
        # Determine file extension (hemisphere/space tags are now in _build_base_filename)
        file_ext = '.func.gii' if self.hemisphere is not None else '.nii.gz'

        if base_filename is None:
            base_filename = self._build_base_filename(contrast_name)
            n_runs = self.contrast_results[contrast_name]['n_runs']
            if n_runs < self.min_runs:
                logger.warning(
                    'tagged %s/task-%s/contrast-%s as _desc-belowMinRuns: '
                    'n_runs=%d (min_runs=%d)',
                    self.subject_id, self.task_name, contrast_name,
                    n_runs, self.min_runs,
                )
```

- [ ] **Step 3.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py -v
```

Expected: 6 passed (1 import smoke + 2 from Task 2 + 3 from Task 3).

- [ ] **Step 3.5: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/processing/fixed_effects.py tests/analysis/lev1/test_fixed_effects.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(lev1): apply _desc-belowMinRuns tag in fixed-effects filenames

Extract filename construction into _build_base_filename. When this
contrast's n_runs is below the configured min_runs, the saved
NIfTI filename includes the _desc-belowMinRuns substring (lev2 will
filter on it). Drops the prior _desc-highExclusion tag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Plumb `min_runs` through `compute_subject_fixed_effects` (TDD)

The module-level helper `compute_subject_fixed_effects` (around `fixed_effects.py:400-440`) constructs the analyzer and currently doesn't take `min_runs`. Add the parameter so callers can configure it.

**Files:**
- Modify: `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`
- Modify: `tests/analysis/lev1/test_fixed_effects.py`

- [ ] **Step 4.1: Append failing test**

Append to `tests/analysis/lev1/test_fixed_effects.py`:

```python
def test_compute_subject_fixed_effects_accepts_min_runs(tmp_path):
    """The module-level helper accepts and threads `min_runs` to the analyzer."""
    from neuro_workflow.analysis.lev1.processing import fixed_effects as fe

    captured = {}
    real_init = fe.FixedEffectsAnalyzer.__init__

    def spy_init(self, *args, **kwargs):
        captured['min_runs'] = kwargs.get('min_runs', None)
        # Avoid actually running the analysis: raise after capturing.
        raise RuntimeError('stop after capture')

    fe.FixedEffectsAnalyzer.__init__ = spy_init
    try:
        try:
            fe.compute_subject_fixed_effects(
                'sub-x', 'flanker',
                contrast_dir=tmp_path, output_dir=tmp_path,
                min_runs=4,
            )
        except RuntimeError:
            pass
    finally:
        fe.FixedEffectsAnalyzer.__init__ = real_init

    assert captured['min_runs'] == 4
```

- [ ] **Step 4.2: Run; expect FAIL with TypeError**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py::test_compute_subject_fixed_effects_accepts_min_runs -v
```

Expected: FAIL with `TypeError: compute_subject_fixed_effects() got an unexpected keyword argument 'min_runs'`.

- [ ] **Step 4.3: Add `min_runs` parameter**

In `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`, find `def compute_subject_fixed_effects(...)` (around line 400). Add `min_runs: int = 2` after `high_exclusion: bool = False`:

```python
def compute_subject_fixed_effects(
    subject_id: str,
    task_name: str,
    contrast_dir: Path,
    output_dir: Path,
    mask_img: Optional[Union[str, Path]] = None,
    exclusions: Optional[Set[str]] = None,
    high_exclusion: bool = False,
    min_runs: int = 2,
    hemisphere: Optional[str] = None,
    surface_space: str = 'fsnative',
) -> Dict[str, Dict[str, Path]]:
```

Pass `min_runs` to the analyzer construction call (around line 437):

```python
    analyzer = FixedEffectsAnalyzer(
        subject_id, task_name, mask_img, high_exclusion,
        min_runs=min_runs, hemisphere=hemisphere,
        surface_space=surface_space,
    )
```

Update the docstring `Args:` section to include `min_runs: Minimum runs threshold passed to the analyzer (default 2).`.

- [ ] **Step 4.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py -v
```

Expected: 7 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/processing/fixed_effects.py tests/analysis/lev1/test_fixed_effects.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(lev1): plumb min_runs through compute_subject_fixed_effects helper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add `--min-runs` CLI flag in `lev1/run.py` (TDD)

Add the CLI argument with default 2 and a positivity guard.

**Files:**
- Modify: `src/neuro_workflow/analysis/lev1/run.py`
- Modify: `tests/analysis/lev1/test_fixed_effects.py` (or create a separate test file — keeping it consolidated for plan brevity)

- [ ] **Step 5.1: Append failing tests**

Append to `tests/analysis/lev1/test_fixed_effects.py`:

```python
def test_lev1_cli_accepts_min_runs_flag():
    """Parsing `--min-runs 3` produces args.min_runs == 3."""
    from neuro_workflow.analysis.lev1.run import get_parser
    parser = get_parser()
    # Provide the other required args minimally; --min-runs is the only field
    # under test. Use --help-style fields that always parse.
    args = parser.parse_args([
        '--subj_id', 'sub-x', '--task_name', 'flanker',
        '--bids_dir', '/tmp', '--space', 'MNI152NLin2009cAsym',
        '--exclusions-file', '/tmp/excl.json',
        '--min-runs', '3',
    ])
    assert args.min_runs == 3


def test_lev1_cli_min_runs_default_is_2():
    """Omitting --min-runs leaves the default of 2."""
    from neuro_workflow.analysis.lev1.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        '--subj_id', 'sub-x', '--task_name', 'flanker',
        '--bids_dir', '/tmp', '--space', 'MNI152NLin2009cAsym',
        '--exclusions-file', '/tmp/excl.json',
    ])
    assert args.min_runs == 2


def test_lev1_cli_min_runs_must_be_positive():
    """`--min-runs 0` aborts via SystemExit."""
    import pytest as _pytest
    from neuro_workflow.analysis.lev1.run import get_parser
    parser = get_parser()
    with _pytest.raises(SystemExit):
        parser.parse_args([
            '--subj_id', 'sub-x', '--task_name', 'flanker',
            '--bids_dir', '/tmp', '--space', 'MNI152NLin2009cAsym',
            '--exclusions-file', '/tmp/excl.json',
            '--min-runs', '0',
        ])
```

Note: the exact set of "other required args" depends on `get_parser()`'s actual definitions. If the test fixture's argument list is incomplete and `parser.parse_args` aborts before reaching the `--min-runs` validation, the implementer should adjust to match the parser's actual required positional / flagged args. Read `get_parser` in `src/neuro_workflow/analysis/lev1/run.py` to confirm.

- [ ] **Step 5.2: Run; expect FAIL on unknown argument**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py::test_lev1_cli_accepts_min_runs_flag -v
```

Expected: FAIL with `error: unrecognized arguments: --min-runs 3`.

- [ ] **Step 5.3: Add the CLI flag**

In `src/neuro_workflow/analysis/lev1/run.py`, find the `get_parser()` function and add the flag near the other lev1-config flags. Then add a positivity check after `parse_args`. The exact location depends on the file's structure; the implementer reads `get_parser()` (likely defined near `def get_parser()` and consumed in `main()`).

Add to the parser:

```python
    parser.add_argument(
        '--min-runs',
        type=int,
        default=2,
        help='Minimum runs required to compute a non-tagged fixed-effects map. '
             'Below this threshold, the saved map is tagged _desc-belowMinRuns '
             'and lev2 will filter it out (default: 2).',
    )
```

After `args = parser.parse_args()` in `main()`, add validation:

```python
    if args.min_runs < 1:
        parser.error('--min-runs must be >= 1')
```

If the validation lands in a place where `parser` is out of scope, the implementer can `raise SystemExit('--min-runs must be >= 1')` to keep the test happy.

- [ ] **Step 5.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py -v
```

Expected: 10 passed.

- [ ] **Step 5.5: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/run.py tests/analysis/lev1/test_fixed_effects.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(lev1): add --min-runs CLI flag (default 2, must be >= 1)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Wire `--min-runs` to `compute_subject_fixed_effects` call sites in `lev1/run.py`

Both call sites at `src/neuro_workflow/analysis/lev1/run.py:601` and `:609` (where `compute_subject_fixed_effects(...)` is invoked) need `min_runs=args.min_runs` threaded through.

**Files:**
- Modify: `src/neuro_workflow/analysis/lev1/run.py`

- [ ] **Step 6.1: Add `min_runs=args.min_runs` to both calls**

In `src/neuro_workflow/analysis/lev1/run.py`, find the two `compute_subject_fixed_effects(...)` invocations (around lines 601-606 and 609-613). Each currently passes `high_exclusion=high_exclusion_subject`. Add `min_runs=args.min_runs` adjacent. Example:

```python
        if is_surface_space(args.space):
            surface_space = resolve_surface_space(args.space)
            for hemisphere in ['L', 'R']:
                logger.info('Fixed effects for hemisphere %s...', hemisphere)
                results = compute_subject_fixed_effects(
                    args.subj_id, args.task_name, dirs['indiv_contrasts'],
                    dirs['fixed_effects'], mask_img=None, exclusions=exclusions,
                    high_exclusion=high_exclusion_subject,
                    min_runs=args.min_runs,
                    hemisphere=hemisphere,
                    surface_space=surface_space,
                )
                logger.info('Fixed effects: %d contrasts (hemi-%s)', len(results), hemisphere)
        else:
            results = compute_subject_fixed_effects(
                args.subj_id, args.task_name, dirs['indiv_contrasts'],
                dirs['fixed_effects'], combined_mask_path, exclusions,
                high_exclusion=high_exclusion_subject,
                min_runs=args.min_runs,
            )
            logger.info('Fixed effects: %d contrasts', len(results))
```

(`high_exclusion=...` stays for now; Task 9 deletes it cleanly.)

- [ ] **Step 6.2: Run the broader lev1 test suite; expect no regression**

```bash
uv run pytest tests/analysis/lev1/ -q --tb=line 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 6.3: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(lev1): thread min_runs through to fixed-effects call sites

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Lev2 filters `_desc-belowMinRuns` files (TDD)

`discover_input_files` at `src/neuro_workflow/analysis/lev2/run.py:116` globs all `*_stat-fixed-effects.nii.gz` files. Filter out any path containing `_desc-belowMinRuns_`.

**Files:**
- Create: `tests/analysis/lev2/__init__.py`
- Create: `tests/analysis/lev2/test_run.py`
- Modify: `src/neuro_workflow/analysis/lev2/run.py`

- [ ] **Step 7.1: Create test scaffold**

Create the directory `tests/analysis/lev2/` if it doesn't exist; add an empty `__init__.py`. Create `tests/analysis/lev2/test_run.py`:

```python
"""Tests for src/neuro_workflow/analysis/lev2/run.py."""
from __future__ import annotations
from pathlib import Path


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'')


def test_discover_input_files_filters_below_min_runs(tmp_path):
    """Files containing _desc-belowMinRuns_ are dropped from the result."""
    from neuro_workflow.analysis.lev2.run import discover_input_files

    lev1_dir = tmp_path / 'lev1'
    contrast_name = 'task-flanker_contrast-incongruent-congruent'
    common = f'{contrast_name}_rtmodel-RTDur'

    # Two untagged (kept), two tagged (dropped).
    _touch(lev1_dir / 'sub-s03' / 'ses-01' / 'fixed_effects'
           / f'sub-s03_{common}_stat-fixed-effects.nii.gz')
    _touch(lev1_dir / 'sub-s10' / 'ses-01' / 'fixed_effects'
           / f'sub-s10_{common}_stat-fixed-effects.nii.gz')
    _touch(lev1_dir / 'sub-s19' / 'ses-01' / 'fixed_effects'
           / f'sub-s19_{common}_desc-belowMinRuns_stat-fixed-effects.nii.gz')
    _touch(lev1_dir / 'sub-s29' / 'ses-01' / 'fixed_effects'
           / f'sub-s29_{common}_desc-belowMinRuns_stat-fixed-effects.nii.gz')

    files = discover_input_files([lev1_dir], contrast_name)

    assert len(files) == 2
    subjects = {Path(f).name.split('_')[0] for f in files}
    assert subjects == {'sub-s03', 'sub-s10'}
    for f in files:
        assert '_desc-belowMinRuns_' not in f
```

- [ ] **Step 7.2: Run; expect FAIL (returns 4 files instead of 2)**

```bash
uv run pytest tests/analysis/lev2/test_run.py -v
```

Expected: FAIL with assertion mismatch on `len(files) == 2`.

- [ ] **Step 7.3: Implement the filter**

In `src/neuro_workflow/analysis/lev2/run.py`, modify `discover_input_files` (currently around lines 116-141). The current body iterates `level1_dirs`, globs, and extends `all_files`. Add the filter inside the loop and a single summary print after:

```python
def discover_input_files(level1_dirs: List[Path], contrast_name: str) -> List[str]:
    """
    Discover input files for a specific contrast from multiple level1 output directories.

    Files tagged `_desc-belowMinRuns_` (subjects whose fixed-effects came
    from fewer than `min_runs` retained sessions, see lev1 design 2026-05-07)
    are filtered out automatically.

    Args:
        level1_dirs: List of paths to level1 output directories
        contrast_name: Task_contrast name (e.g., 'task-flanker_contrast-incongruent-congruent')

    Returns:
        List of paths to fixed effects files for this contrast (excluding
        _desc-belowMinRuns_ files).
    """
    all_files: List[str] = []
    n_dropped = 0

    for level1_dir in level1_dirs:
        pattern = (
            level1_dir
            / 'sub-*'
            / '*'
            / 'fixed_effects'
            / f'*{contrast_name}_rtmodel-*_stat-fixed-effects.nii.gz'
        )
        files = glob.glob(str(pattern))
        kept = [f for f in files if '_desc-belowMinRuns_' not in f]
        n_dropped += len(files) - len(kept)
        all_files.extend(kept)

    if n_dropped:
        print(
            f'discover_input_files: dropped {n_dropped} '
            f'_desc-belowMinRuns files for contrast {contrast_name}'
        )

    return sorted(all_files)
```

- [ ] **Step 7.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/lev2/test_run.py -v
```

Expected: 1 passed.

- [ ] **Step 7.5: Commit**

```bash
git add tests/analysis/lev2/__init__.py tests/analysis/lev2/test_run.py src/neuro_workflow/analysis/lev2/run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(lev2): filter _desc-belowMinRuns files from discover_input_files

Group analysis now automatically excludes subjects whose lev1
fixed-effects came from fewer than min_runs retained sessions
(tagged in lev1 by the corresponding C2 changes).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Delete `high_exclusion` plumbing (constructor, function, call sites, summary)

All `high_exclusion`-related code is now dead — the new tag derives from `n_runs` and `min_runs`. Remove it.

**Files:**
- Modify: `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`
- Modify: `src/neuro_workflow/analysis/lev1/run.py`
- Modify: `src/neuro_workflow/analysis/core/utils.py`
- Modify: `tests/analysis/lev1/test_fixed_effects.py`

- [ ] **Step 8.1: Append regression test for absent attribute**

Append to `tests/analysis/lev1/test_fixed_effects.py`:

```python
def test_no_high_exclusion_attribute():
    """Regression: high_exclusion plumbing must stay deleted."""
    from neuro_workflow.analysis.lev1.processing.fixed_effects import (
        FixedEffectsAnalyzer,
    )
    a = FixedEffectsAnalyzer('sub-x', 'flanker')
    assert not hasattr(a, 'high_exclusion'), (
        'FixedEffectsAnalyzer should not carry a high_exclusion attribute'
    )
```

- [ ] **Step 8.2: Run; expect FAIL because the attribute still exists**

```bash
uv run pytest tests/analysis/lev1/test_fixed_effects.py::test_no_high_exclusion_attribute -v
```

Expected: FAIL with assertion `should not carry a high_exclusion attribute`.

- [ ] **Step 8.3: Delete `high_exclusion` from `FixedEffectsAnalyzer.__init__`**

In `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py`:

- Remove the `high_exclusion: bool = False,` parameter from the `__init__` signature.
- Remove the `self.high_exclusion = high_exclusion` assignment in the body.
- Remove the `high_exclusion: Whether >50% of runs were excluded` line from the `Args:` docstring.

- [ ] **Step 8.4: Delete `high_exclusion` from `compute_subject_fixed_effects`**

In the same file, find `def compute_subject_fixed_effects(...)`:

- Remove `high_exclusion: bool = False,` parameter.
- Remove the `high_exclusion: Whether >50% of runs were excluded` line from the docstring.
- Remove `high_exclusion` from the `analyzer = FixedEffectsAnalyzer(...)` call. Resulting call:

```python
    analyzer = FixedEffectsAnalyzer(
        subject_id, task_name, mask_img,
        min_runs=min_runs, hemisphere=hemisphere,
        surface_space=surface_space,
    )
```

- [ ] **Step 8.5: Delete `high_exclusion_subject` and the `count_subject_exclusions` call in `lev1/run.py`**

In `src/neuro_workflow/analysis/lev1/run.py`:

- Remove the `count_subject_exclusions` import on line 16 (or leave it if `count_subject_exclusions` itself is still used — verify by searching for further calls; given the only reference at line 569 will be removed, the import becomes dead).
- Remove the `exclusion_summary = count_subject_exclusions(...)` block (lines 569-577) including the surrounding logger.info / logger.warning lines that reference `exclusion_summary`.
- Remove the `high_exclusion_subject = exclusion_summary['high_exclusion']` and `if high_exclusion_subject: logger.warning(...)` lines (~579-581).
- Remove the `high_exclusion=high_exclusion_subject,` argument from the two `compute_subject_fixed_effects(...)` calls (~601-606 and ~609-613).
- Keep the `discovered_runs / subject_excluded_runs / total_expected_runs` computation only if it has any other use; if it was only feeding into `count_subject_exclusions`, delete it too.

After this edit, the function that wraps fixed-effects no longer mentions `high_exclusion` anywhere.

- [ ] **Step 8.6: Drop `high_exclusion` from `count_subject_exclusions` return**

In `src/neuro_workflow/analysis/core/utils.py`:

- Remove the `high_exclusion = exclusion_rate > 0.5` line (~264).
- Remove the `'high_exclusion': high_exclusion,` field from the returned dict (~271).
- Update the docstring's `Returns:` section to drop the `high_exclusion` field.

If grep shows `count_subject_exclusions` has zero remaining callers after Step 8.5, delete the function entirely. Otherwise keep it (it still provides useful exclusion-rate diagnostics).

- [ ] **Step 8.7: Run all lev1 tests; expect PASS**

```bash
uv run pytest tests/analysis/lev1/ tests/analysis/lev2/ -q --tb=line 2>&1 | tail -5
```

Expected: all green. The new regression test from Step 8.1 must pass.

- [ ] **Step 8.8: Confirm no stragglers**

```bash
# Should print nothing — no surviving references in src/.
uv run python - <<'EOF'
import subprocess
out = subprocess.run(
    ['grep', '-rn', '-w', 'high_exclusion',
     'src/neuro_workflow/'],
    capture_output=True, text=True,
)
print('STDOUT:', out.stdout or '(empty — clean)')
EOF
```

Expected: `(empty — clean)`. If any references remain, fix them before committing.

- [ ] **Step 8.9: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/processing/fixed_effects.py \
        src/neuro_workflow/analysis/lev1/run.py \
        src/neuro_workflow/analysis/core/utils.py \
        tests/analysis/lev1/test_fixed_effects.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(lev1): delete high_exclusion plumbing

The unenforced _desc-highExclusion tag is fully replaced by the
n_runs<min_runs / _desc-belowMinRuns mechanism. Drop the now-dead
high_exclusion parameter from FixedEffectsAnalyzer and
compute_subject_fixed_effects, the high_exclusion field from
count_subject_exclusions's return, and the corresponding plumbing in
lev1/run.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Full test suite + lint sanity check

**Files:** None (verification only).

- [ ] **Step 9.1: Run the full analysis test suite**

```bash
uv run pytest tests/analysis/ tests/exclusions/ tests/qa/ -q --tb=line 2>&1 | tail -5
```

Expected: all green. Note any unrelated failures and surface them — don't paper over them.

- [ ] **Step 9.2: Confirm `--min-runs` shows up in the CLI help**

```bash
uv run python -m neuro_workflow.analysis.lev1.run --help 2>&1 | grep -A 2 'min-runs'
```

Expected: a help block including `--min-runs INT` with the description and default 2.

- [ ] **Step 9.3: No commit needed unless the verification surfaces a fix.**

---

## Task 10: Operational verification (post-merge, manual)

After the PR merges to main, re-run discovery lev1 to overwrite orphan `_desc-highExclusion` files. Validation lev1 has not run, so no migration there.

- [ ] **Step 10.1: Re-run discovery lev1**

```bash
# From the repo root, with the latest main checked out.
# The exact submission command depends on the dataset registration; use the
# same flags previous runs used (see CLAUDE.md / SLURM `.err` files in logs/).
module load uv
uv run neuro-run submit lev1 discovery \
    --exclusions-file ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json \
    --overwrite
```

Use the existing `--mni-template` / `--mni-res` defaults (per the lev1 audit memory: `MNI152NLin6Asym` + `--mni-res 2`). `--min-runs` will default to 2.

- [ ] **Step 10.2: Spot-check tagged outputs**

After the array job finishes:

```bash
find /scratch/users/logben/lev1_discovery -name '*_desc-belowMinRuns_*' | head -5
find /scratch/users/logben/lev1_discovery -name '*_desc-highExclusion_*'
```

The first command may return some files (subjects with <2 retained sessions for some `(task, contrast)`); the second must return nothing — all `_desc-highExclusion` files should have been overwritten with `_desc-belowMinRuns` or untagged equivalents.

- [ ] **Step 10.3: Run lev2 on the rerun outputs and confirm the filter prints**

```bash
uv run python -m neuro_workflow.analysis.lev2.run \
    --contrast task-flanker_contrast-incongruent-congruent \
    --level1-dirs /scratch/users/logben/lev1_discovery \
    --output-dir /tmp/lev2_smoke 2>&1 | grep -i 'belowMinRuns'
```

If any `_desc-belowMinRuns` files exist, the line `discover_input_files: dropped N _desc-belowMinRuns files for contrast ...` should appear in the output.

- [ ] **Step 10.4: No commit needed unless the verification surfaces a fix.**

---

# Self-Review

**Spec coverage:**
- Goal 1 (replace relative >50% rule with absolute `min_runs<2` floor): Tasks 2-3.
- Goal 2 (lev2 honors floor): Task 7.
- Goal 3 (new `_desc-belowMinRuns` tag, drop old `_desc-highExclusion`): Tasks 3 (apply), 8 (delete plumbing).
- Goal 4 (`--min-runs` CLI, default 2): Task 5.
- Goal 5 (one stderr WARNING per tagged contrast, no manifest): Task 3, Step 3.3 (`logger.warning`).
- Goal 6 (re-run discovery after merge): Task 10.
- Edge case `n_runs == 0` (existing zero-files guard): no code change required, covered implicitly.
- Edge case `min_runs <= 0`: Task 5 Step 5.3 + tests at Step 5.1.
- Edge case mixed orphan tags: Task 10 Step 10.2 verifies.

**Type consistency:** parameter names are consistent (`min_runs` everywhere, never `min_n` or `min_n_runs`). Tag substring is `_desc-belowMinRuns_` everywhere (lev1 emits, lev2 filters with the same string).

**Placeholder scan:** no TBD / TODO / "implement later" / generic "add error handling". The one judgment call (Task 8.6 — delete `count_subject_exclusions` if no callers, else keep) is concrete: implementer greps and decides at implementation time. Step 5.3's note about adjusting required-args in the test fixture is a debugging hint, not a placeholder — the implementation is fully specified.

**Risk notes:**
- Tasks 5 and 6 split a small change across two commits. Could be combined; kept apart so each commit is reviewable in isolation.
- Task 8 is large but tightly scoped to one concept (deleting the dead `high_exclusion` plumbing).
