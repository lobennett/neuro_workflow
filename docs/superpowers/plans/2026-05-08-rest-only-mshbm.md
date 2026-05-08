# Rest-Only MSHBM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--rest-only` mode to the `prep-mshbm` pipeline + analysis script so the discovery cohort's resting-state data can be prepped for MSHBM without requiring task GLM residuals; operate the existing `mshbm` pipeline against the user's fork of Buckner's `PrecisionNetworkMapping` to produce per-subject networks viewable in Connectome Workbench.

**Architecture:** Three additive changes — `--rest-only` flag in both the pipeline and the analysis script, with `--glm-dir` becoming optional. The task-residual code paths in `process_subject()` are wrapped with `if not rest_only:` (no removal). Template's hard-coded `--glm-dir`/`--residuals-space` move into the existing `extra_flags` mechanism so they render only when applicable. Operational `mshbm` submission uses `--mshbm-dir /home/users/logben/network_glm/PrecisionNetworkMapping`.

**Tech Stack:** Python 3.13, argparse, str.format() templating, pytest. SLURM, MATLAB (downstream MSHBM, untouched).

**Spec:** `docs/superpowers/specs/2026-05-08-rest-only-mshbm-design.md`

---

## File map

| File | Change |
|---|---|
| `tests/analysis/mshbm/__init__.py` | Create empty |
| `tests/analysis/mshbm/test_run.py` | Create — 4 tests for argparse + main validation + process_subject gating |
| `src/neuro_workflow/analysis/mshbm/run.py` | Add `--rest-only` arg; make `--glm-dir` optional; validate in `main()`; gate task-residual block in `process_subject()` |
| `src/neuro_workflow/pipelines/prep_mshbm.py` | Add `--rest-only`; make `--glm-dir` optional; validate in `build_context`; thread conditional flags into `extra_flags` |
| `src/neuro_workflow/templates/prep_mshbm.sbatch` | Drop hard-coded `--glm-dir`, `--residuals-space`; let everything optional flow through `{extra_flags}` |
| `tests/pipelines/test_prep_mshbm.py` | Update existing assertions; add 4 new tests |

---

## Task 1: Scaffold `tests/analysis/mshbm/test_run.py`

**Files:**
- Create: `tests/analysis/mshbm/__init__.py`
- Create: `tests/analysis/mshbm/test_run.py`

- [ ] **Step 1.1: Create empty `__init__.py`**

```bash
mkdir -p /home/users/logben/neuro_workflow/tests/analysis/mshbm
touch /home/users/logben/neuro_workflow/tests/analysis/mshbm/__init__.py
```

- [ ] **Step 1.2: Create scaffold test file**

Create `/home/users/logben/neuro_workflow/tests/analysis/mshbm/test_run.py`:

```python
"""Tests for src/neuro_workflow/analysis/mshbm/run.py."""
from __future__ import annotations

import pytest


def test_get_parser_importable():
    """Smoke test: the analysis script's get_parser is importable."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    assert parser is not None
```

- [ ] **Step 1.3: Run; expect PASS**

```bash
module load uv
uv run pytest tests/analysis/mshbm/test_run.py -v
```

Expected: 1 passed.

- [ ] **Step 1.4: Commit**

```bash
git add tests/analysis/mshbm/__init__.py tests/analysis/mshbm/test_run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(mshbm): scaffold tests/analysis/mshbm/ with import smoke

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `--rest-only` arg + make `--glm-dir` optional in analysis script (TDD)

**Files:**
- Modify: `src/neuro_workflow/analysis/mshbm/run.py`
- Modify: `tests/analysis/mshbm/test_run.py`

- [ ] **Step 2.1: Append failing tests**

Append to `tests/analysis/mshbm/test_run.py`:

```python
def test_parser_accepts_rest_only_flag():
    """`--rest-only` flag is registered and parses to True when present."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        "--subj-id", "s03",
        "--fmriprep-dir", "/tmp",
        "--rest-only",
    ])
    assert args.rest_only is True
    assert args.glm_dir is None


def test_parser_glm_dir_now_optional():
    """`--glm-dir` is no longer required at argparse level."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        "--subj-id", "s03",
        "--fmriprep-dir", "/tmp",
        "--rest-only",
    ])
    assert args.glm_dir is None


def test_parser_glm_dir_still_accepted():
    """Backwards-compat: `--glm-dir` still parses when supplied."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        "--subj-id", "s03",
        "--glm-dir", "/oak/lev1",
        "--fmriprep-dir", "/tmp",
    ])
    assert args.glm_dir == "/oak/lev1"
    assert args.rest_only is False
```

- [ ] **Step 2.2: Run; expect FAIL**

```bash
uv run pytest tests/analysis/mshbm/test_run.py::test_parser_accepts_rest_only_flag -v
```

Expected: FAIL with argparse complaining about either unrecognized `--rest-only` OR missing required `--glm-dir`.

- [ ] **Step 2.3: Edit `analysis/mshbm/run.py`**

Find the `--glm-dir` block in `get_parser()` (around line 725-728):

```python
    parser.add_argument(
        '--glm-dir', type=str, required=True,
        help='GLM results directory containing sub-s*/task-*/task_residuals/',
    )
```

Replace with:

```python
    parser.add_argument(
        '--glm-dir', type=str, default=None,
        help='GLM results directory containing sub-s*/task-*/task_residuals/. '
             'Required unless --rest-only is set.',
    )
```

Find the end of the `parser.add_argument` block (just before `return parser`, around line 757) and add a new arg:

```python
    parser.add_argument(
        '--rest-only', action='store_true', default=False,
        help='Skip task-residual discovery + processing. Only rest BOLD '
             'is projected to fsaverage6. Mutually exclusive with --glm-dir.',
    )
```

- [ ] **Step 2.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/mshbm/test_run.py -v
```

Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/run.py tests/analysis/mshbm/test_run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(mshbm): add --rest-only arg; make --glm-dir optional in analysis script

argparse-level changes only; runtime validation and gating of task-residual
processing follow in next commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Validate args in `main()` — both-or-neither error (TDD)

**Files:**
- Modify: `src/neuro_workflow/analysis/mshbm/run.py`
- Modify: `tests/analysis/mshbm/test_run.py`

- [ ] **Step 3.1: Append failing tests**

Append to `tests/analysis/mshbm/test_run.py`:

```python
def test_main_errors_when_neither_rest_only_nor_glm_dir(monkeypatch, capsys):
    """`main()` exits with a clear error when neither --rest-only nor --glm-dir is set."""
    from neuro_workflow.analysis.mshbm import run as mshbm_run

    monkeypatch.setattr(
        "sys.argv",
        ["mshbm.run", "--subj-id", "s03", "--fmriprep-dir", "/tmp"],
    )
    with pytest.raises(SystemExit) as exc_info:
        mshbm_run.main()
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "rest-only" in (captured.err + captured.out).lower()


def test_main_errors_when_both_rest_only_and_glm_dir(monkeypatch, capsys):
    """`main()` exits with a clear error when both --rest-only and --glm-dir are set."""
    from neuro_workflow.analysis.mshbm import run as mshbm_run

    monkeypatch.setattr(
        "sys.argv",
        [
            "mshbm.run", "--subj-id", "s03",
            "--fmriprep-dir", "/tmp",
            "--glm-dir", "/oak/lev1",
            "--rest-only",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        mshbm_run.main()
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "rest-only" in (captured.err + captured.out).lower()
    assert "glm-dir" in (captured.err + captured.out).lower()
```

- [ ] **Step 3.2: Run; expect FAIL**

```bash
uv run pytest tests/analysis/mshbm/test_run.py::test_main_errors_when_neither_rest_only_nor_glm_dir -v
```

Expected: FAIL (currently `main()` would proceed to `process_subject` and raise some other error like FileNotFoundError, or succeed-then-fail with a different message).

- [ ] **Step 3.3: Add validation in `main()`**

Edit `src/neuro_workflow/analysis/mshbm/run.py`. Find `def main()` (around line 761) and locate the line right after `args = parser.parse_args()`. Insert validation before the logging setup:

```python
def main() -> int:
    parser = get_parser()
    args = parser.parse_args()

    # Validation: exactly one of --rest-only / --glm-dir must be set.
    if args.rest_only and args.glm_dir:
        parser.error(
            "--rest-only and --glm-dir are mutually exclusive; pick one."
        )
    if not args.rest_only and not args.glm_dir:
        parser.error(
            "must supply either --rest-only or --glm-dir (one is required)."
        )

    level = logging.DEBUG if args.verbose else logging.INFO
    # ... rest of main unchanged ...
```

- [ ] **Step 3.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/mshbm/test_run.py -v
```

Expected: 6 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/run.py tests/analysis/mshbm/test_run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(mshbm): validate --rest-only / --glm-dir mutual exclusion in main()

parser.error() at main() entry catches misuse early. Pipeline-level
validation in build_context follows.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Gate task-residual processing in `process_subject` (TDD)

**Files:**
- Modify: `src/neuro_workflow/analysis/mshbm/run.py`
- Modify: `tests/analysis/mshbm/test_run.py`

- [ ] **Step 4.1: Append failing test**

Append to `tests/analysis/mshbm/test_run.py`:

```python
def test_process_subject_rest_only_skips_task_residual_discovery(
    tmp_path, monkeypatch,
):
    """When rest_only=True, task-residual discovery + processing are skipped.

    Mock the four task-residual functions to track calls; assert they're not
    invoked. Mock the rest-discovery + ensure_fsaverage6 paths to no-op so
    process_subject runs cleanly.
    """
    from neuro_workflow.analysis.mshbm import run as mshbm_run

    # FreeSurfer subjects dir must exist for process_subject to proceed
    fmriprep_dir = tmp_path / "fmriprep"
    (fmriprep_dir / "sourcedata" / "freesurfer").mkdir(parents=True)
    output_dir = tmp_path / "out"

    task_residual_calls: list[str] = []
    monkeypatch.setattr(
        mshbm_run, "discover_task_residuals_volume",
        lambda *a, **k: task_residual_calls.append("vol") or [],
    )
    monkeypatch.setattr(
        mshbm_run, "discover_task_residuals_surface",
        lambda *a, **k: task_residual_calls.append("surf") or [],
    )
    monkeypatch.setattr(
        mshbm_run, "process_volume_residuals",
        lambda *a, **k: task_residual_calls.append("proc_vol") or 0,
    )
    monkeypatch.setattr(
        mshbm_run, "process_surface_residuals",
        lambda *a, **k: task_residual_calls.append("proc_surf") or 0,
    )

    # Stub rest paths to no-op so the function returns cleanly.
    monkeypatch.setattr(mshbm_run, "ensure_fsaverage6", lambda *a, **k: None)
    monkeypatch.setattr(mshbm_run, "discover_rest_bold_fsaverage6", lambda *a, **k: [])
    monkeypatch.setattr(mshbm_run, "discover_rest_bold_surface", lambda *a, **k: [])
    monkeypatch.setattr(mshbm_run, "discover_rest_bold_volume", lambda *a, **k: [])

    errors = mshbm_run.process_subject(
        subject="sub-s03",
        glm_dir=None,
        fmriprep_dir=fmriprep_dir,
        output_dir=output_dir,
        residuals_space="surface",
        rest_fmriprep_dir=None,
        sessions=None,
        rest_only=True,
    )

    assert errors == 0
    assert task_residual_calls == [], (
        f"task-residual functions called when rest_only=True: {task_residual_calls}"
    )
```

- [ ] **Step 4.2: Run; expect FAIL**

```bash
uv run pytest tests/analysis/mshbm/test_run.py::test_process_subject_rest_only_skips_task_residual_discovery -v
```

Expected: FAIL — `process_subject` doesn't accept `rest_only` kwarg yet (TypeError) or task-residual fns get called.

- [ ] **Step 4.3: Edit `process_subject`**

In `src/neuro_workflow/analysis/mshbm/run.py`, find `def process_subject(...)` (around line 608). Add `rest_only: bool = False` to the signature:

```python
def process_subject(
    subject: str,
    glm_dir: Path | None,
    fmriprep_dir: Path,
    output_dir: Path,
    residuals_space: str = 'surface',
    rest_fmriprep_dir: Path | None = None,
    sessions: set[str] | None = None,
    rest_only: bool = False,
) -> int:
```

Note: also change `glm_dir: Path` to `glm_dir: Path | None` to reflect the new optional nature.

Find the task-residual block (around lines 636-660). Wrap it with `if not rest_only:`:

```python
    errors = 0

    # --- Task residuals -> fsaverage6 ---
    if not rest_only:
        if residuals_space == 'surface':
            # fsnative GIFTI -> fsaverage6 (mri_surf2surf)
            residual_files = discover_task_residuals_surface(glm_dir, subject)
            residual_files = filter_by_sessions(residual_files, sessions)
            errors += process_surface_residuals(
                residual_files, subject, subjects_dir, subj_output,
            )
        else:
            # Volumetric (MNI or T1w) -> fsaverage6
            anat_dir = find_anat_dir(fmriprep_dir, subject)
            transform = None
            t1w_ref = None
            if residuals_space == 'MNI':
                transform = find_mni_to_t1w_transform(anat_dir)
                t1w_ref_fullres = find_t1w_reference(anat_dir)
                t1w_ref = create_lowres_reference(t1w_ref_fullres, subj_output)

            residual_files = discover_task_residuals_volume(glm_dir, subject)
            residual_files = filter_by_sessions(residual_files, sessions)
            errors += process_volume_residuals(
                residual_files, subject, subjects_dir, subj_output,
                residuals_space, transform, t1w_ref,
            )

    # --- Rest BOLD -> fsaverage6 ---
    # ... rest unchanged ...
```

Update the call to `process_subject()` at the end of `main()` (around line 789-797) to pass the new kwarg:

```python
    errors = process_subject(
        subject=subject,
        glm_dir=Path(args.glm_dir) if args.glm_dir else None,
        fmriprep_dir=Path(args.fmriprep_dir),
        output_dir=Path(args.output_dir),
        residuals_space=args.residuals_space,
        rest_fmriprep_dir=rest_fmriprep_dir,
        sessions=sessions,
        rest_only=args.rest_only,
    )
```

- [ ] **Step 4.4: Run tests; expect PASS**

```bash
uv run pytest tests/analysis/mshbm/test_run.py -v
```

Expected: 7 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/run.py tests/analysis/mshbm/test_run.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(mshbm): gate task-residual processing in process_subject when rest_only=True

Wraps the task-residual discovery + processing block with `if not rest_only:`.
glm_dir param now Optional[Path]. Existing task+rest path unchanged when
rest_only=False.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update `prep_mshbm` pipeline + template atomically (TDD)

**Files:**
- Modify: `src/neuro_workflow/pipelines/prep_mshbm.py`
- Modify: `src/neuro_workflow/templates/prep_mshbm.sbatch`
- Modify: `tests/pipelines/test_prep_mshbm.py`

- [ ] **Step 5.1: Append failing tests**

Append to `tests/pipelines/test_prep_mshbm.py`:

```python
def test_prep_mshbm_rest_only_renders_flag(tmp_path):
    """When --rest-only is set, the rendered sbatch passes --rest-only and omits --glm-dir."""
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\nsub-02\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir=None,
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=True,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "--rest-only" in script
    assert "--glm-dir" not in script
    assert "--fmriprep-dir \"/oak/fmriprep\"" in script


def test_prep_mshbm_glm_dir_only_renders_glm_flag(tmp_path):
    """Backwards-compat: --glm-dir without --rest-only renders --glm-dir + --residuals-space."""
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )
    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "--glm-dir \"/oak/lev1\"" in script
    assert "--residuals-space surface" in script
    assert "--rest-only" not in script


def test_prep_mshbm_neither_flag_errors(tmp_path):
    """build_context errors when neither rest-only nor glm-dir set."""
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir=None,
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=False,
        nthreads=None, mem_gb=None, time=None,
    )
    with pytest.raises(SystemExit):
        p.build_context("test_ds", dataset_config, args)


def test_prep_mshbm_both_flags_errors(tmp_path):
    """build_context errors when both rest-only and glm-dir set."""
    subs = tmp_path / "subs.txt"
    subs.write_text("sub-01\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=True,
        nthreads=None, mem_gb=None, time=None,
    )
    with pytest.raises(SystemExit):
        p.build_context("test_ds", dataset_config, args)
```

Add `import pytest` to the top of `tests/pipelines/test_prep_mshbm.py` if not already imported (the existing file uses pytest fixtures via `tmp_path` argument but doesn't currently `import pytest`). Add the import at the top.

- [ ] **Step 5.2: Run; expect FAIL**

```bash
uv run pytest tests/pipelines/test_prep_mshbm.py -v 2>&1 | tail -20
```

Expected: at least the 4 new tests fail (current pipeline doesn't accept `rest_only` arg → AttributeError).

- [ ] **Step 5.3: Edit pipeline `add_cli_args` + `build_context`**

In `src/neuro_workflow/pipelines/prep_mshbm.py`:

Update `add_cli_args` — replace the `--glm-dir` line and add `--rest-only`:

```python
    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--glm-dir", required=False, default=None,
                            help="Level-1 GLM results directory (required unless --rest-only is set)")
        parser.add_argument("--fmriprep-dir", required=True, help="fMRIPrep derivatives directory")
        parser.add_argument("--rest-fmriprep-dir", default=None, help="Separate fMRIPrep directory for rest BOLD (optional)")
        parser.add_argument("--output-dir", required=True, help="Output directory for MSHBM surface inputs")
        parser.add_argument("--residuals-space", default="surface", choices=["surface", "MNI", "T1w"], help="Space of task residuals (default: surface)")
        parser.add_argument("--rest-only", action="store_true", default=False,
                            help="Skip task-residual prep; rest BOLD only (mutually exclusive with --glm-dir)")
        parser.add_argument("--sessions", nargs="+", default=None, help="Only process these sessions (optional)")
        parser.add_argument("--nthreads", type=int, default=None, help=f"CPUs per task (default: {self.default_resources['nthreads']})")
        parser.add_argument("--mem-gb", type=int, default=None, help=f"Memory in GB (default: {self.default_resources['mem_gb']})")
        parser.add_argument("--time", default=None, help=f"SLURM time limit (default: {self.default_resources['time']})")
```

Update `build_context` to validate + thread `--rest-only`/`--glm-dir`/`--residuals-space` through `extra_flags`:

```python
    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        # Validate: exactly one of --rest-only / --glm-dir must be set.
        if args.rest_only and args.glm_dir:
            sys.exit(
                "Error: --rest-only and --glm-dir are mutually exclusive; pick one."
            )
        if not args.rest_only and not args.glm_dir:
            sys.exit(
                "Error: must supply either --rest-only or --glm-dir (one is required)."
            )

        subjects = load_subjects(dataset_config["subjects_file"])

        output_dir = Path(args.output_dir)
        log_dir = output_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        subject_list_file = log_dir / "subject_list.txt"
        subject_list_file.write_text("\n".join(subjects) + "\n")

        resources = resolve_resources(args, self.default_resources)

        # Build extra flags: includes --glm-dir / --residuals-space / --rest-only / etc.
        extra_flags = []
        if args.rest_only:
            extra_flags.append("--rest-only")
        else:
            # Task+rest mode: --glm-dir and --residuals-space apply
            extra_flags.append(f'--glm-dir "{args.glm_dir}"')
            extra_flags.append(f"--residuals-space {args.residuals_space}")
        if args.rest_fmriprep_dir:
            extra_flags.append(f"--rest-fmriprep-dir {args.rest_fmriprep_dir}")
        if args.sessions:
            extra_flags.append("--sessions " + " ".join(args.sessions))

        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "n_subjects": len(subjects),
            "nthreads": resources["nthreads"],
            "mem_gb": resources["mem_gb"],
            "time": resources["time"],
            "partition": dataset_config["partition"],
            "log_dir": str(log_dir),
            "mail_line": mail_line,
            "subject_list_file": str(subject_list_file),
            "fmriprep_dir": args.fmriprep_dir,
            "output_dir": str(output_dir),
            "extra_flags": " ".join(extra_flags),
            "neuro_workflow_dir": str(Path(__file__).resolve().parents[3]),
        }
```

Add `import sys` at the top of the file if not already present (it should be, but verify).

Note: removed `glm_dir` and `residuals_space` from the returned context dict because the template no longer references them as standalone substitutions.

- [ ] **Step 5.4: Edit `prep_mshbm.sbatch` template**

Replace `src/neuro_workflow/templates/prep_mshbm.sbatch` with:

```bash
#!/bin/bash
#SBATCH -J prep_mshbm_{dataset_name}
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem={mem_gb}G
#SBATCH --time={time}
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

SUBJ_ID="$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" "{subject_list_file}")"

module load biology freesurfer/8.1.0
module load biology ants/2.4.0
module load uv

uv --directory "{neuro_workflow_dir}" run python -m neuro_workflow.analysis.mshbm.run \
    --subj-id "$SUBJ_ID" \
    --fmriprep-dir "{fmriprep_dir}" \
    --output-dir "{output_dir}" {extra_flags}
```

Differences from the prior version: the standalone `--glm-dir` and `--residuals-space` lines are gone (they now flow through `{extra_flags}`).

- [ ] **Step 5.5: Update existing tests in `test_prep_mshbm.py`**

The existing test `test_prep_mshbm_build_context` (around line 25) and `test_prep_mshbm_build_context_with_extras` (around line 67) and `test_prep_mshbm_render_full_template` (around line 101) will likely fail because the Namespace fixtures lack the new `rest_only` field.

Update the three test fixtures' `Namespace(...)` blocks to include `rest_only=False`:

For `test_prep_mshbm_build_context` (line 36-46):

```python
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )
```

Then update the assertion block (around lines 50-58). The old assertions referenced `ctx["glm_dir"]`, `ctx["residuals_space"]`; those keys no longer exist in the context dict. Replace with assertions on `ctx["extra_flags"]`:

```python
    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["n_subjects"] == 3
    assert ctx["nthreads"] == 1
    assert ctx["mem_gb"] == 64
    assert ctx["time"] == "24:00:00"
    assert ctx["fmriprep_dir"] == "/oak/fmriprep"
    assert "--glm-dir \"/oak/lev1\"" in ctx["extra_flags"]
    assert "--residuals-space surface" in ctx["extra_flags"]
    assert "--rest-only" not in ctx["extra_flags"]
    assert ctx["mail_line"] == ""
```

For `test_prep_mshbm_build_context_with_extras` (line 78-88), add `rest_only=False`:

```python
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir="/oak/rest_fmriprep",
        output_dir=str(tmp_path / "out"),
        residuals_space="MNI",
        sessions=["ses-01", "ses-02"],
        rest_only=False,
        nthreads=4,
        mem_gb=128,
        time="48:00:00",
    )
```

For `test_prep_mshbm_render_full_template` (line 113-123), add `rest_only=False`:

```python
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "out"),
        residuals_space="surface",
        sessions=None,
        rest_only=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )
```

The existing assertions (`"--glm-dir \"/oak/lev1\"" in script` and `"--residuals-space surface" in script`) should still pass because the strings still appear in the rendered script — just inside `{extra_flags}` now.

- [ ] **Step 5.6: Run tests; expect PASS**

```bash
uv run pytest tests/pipelines/test_prep_mshbm.py tests/analysis/mshbm/test_run.py tests/test_all_templates_render.py -v 2>&1 | tail -20
```

Expected: all green.

- [ ] **Step 5.7: Run full pipeline + analysis suites for regression**

```bash
uv run pytest tests/pipelines/ tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 5.8: Commit**

```bash
git add src/neuro_workflow/pipelines/prep_mshbm.py \
        src/neuro_workflow/templates/prep_mshbm.sbatch \
        tests/pipelines/test_prep_mshbm.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(prep-mshbm): wire --rest-only flag through pipeline + template

- add_cli_args: --rest-only flag; --glm-dir now optional
- build_context: validate (both/neither error); --glm-dir / --residuals-space /
  --rest-only flow through extra_flags
- template: drop hard-coded --glm-dir / --residuals-space; rely on {extra_flags}
- existing tests updated to add rest_only=False to fixtures

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Operational verification (post-merge, manual)

**Files:** none (operational only)

- [ ] **Step 6.1: Submit prep-mshbm for discovery**

```bash
module load uv
uv run neuro-run submit prep-mshbm discovery \
    --rest-only \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/mshbm_inputs_discovery
```

Expected: `Submitted batch job XXXXXXX` printed; SLURM array of 5 tasks (one per discovery subject) queued.

- [ ] **Step 6.2: Wait + verify output**

After the array completes, spot-check sub-s03's output:

```bash
ls /scratch/users/logben/mshbm_inputs_discovery/sub-s03/ | head -10
ls /scratch/users/logben/mshbm_inputs_discovery/sub-s03/ | wc -l
```

Expected: 24 files (12 sessions × 2 hemispheres) named `{lh,rh}_ses-{N}_task-rest_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz`.

- [ ] **Step 6.3: Submit mshbm**

```bash
uv run neuro-run submit mshbm discovery \
    --surface-inputs-dir /scratch/users/logben/mshbm_inputs_discovery \
    --output-dir /scratch/users/logben/mshbm_output_discovery \
    --mshbm-dir /home/users/logben/network_glm/PrecisionNetworkMapping
```

Expected: SLURM job submitted. Walltime hours (MATLAB MSHBM is heavy).

- [ ] **Step 6.4: After completion, locate output `.dscalar.nii` files**

```bash
find /scratch/users/logben/mshbm_output_discovery -name '*.dscalar.nii' | head -10
```

Expected: per-subject network label files in the `Params_sub-s03_sub-s10_sub-s19_sub-s29_sub-s43/` subdirectory tree.

- [ ] **Step 6.5: Open in Connectome Workbench for visual review**

Manual step — open `wb_view` and load one or two `.dscalar.nii` files alongside an fsaverage6 surface; sanity-check that the parcellation looks like Buckner's published 15-network atlas.

- [ ] **Step 6.6: No commit needed unless a problem is found.**

---

# Self-Review

**Spec coverage:**
- Goal 1 (`--rest-only` flag in pipeline + analysis script) → Tasks 2, 5
- Goal 2 (clear error if neither/both set) → Tasks 3, 5
- Goal 3 (operate `mshbm` with `--mshbm-dir <fork path>`) → Task 6
- Goal 4 (per-subject network output viewable in Workbench) → Task 6
- Goal 5 (existing task+rest path unchanged) → Task 4 (gating preserves old code paths) + Task 5 (existing tests still pass)

**Type consistency:** `rest_only` (snake_case bool) used consistently across analysis script, pipeline `Namespace`, and tests. `--rest-only` (kebab-case CLI flag) used consistently in argparse declarations and rendered sbatch.

**Placeholder scan:** no TBD / "implement later" / generic guidance. Each step has the exact code to add or change. Step 5.5 specifies exact line ranges (approximate) and what to change in each existing test.

**Risk notes:**
- Task 5's atomic 3-file change is bigger than typical. Splitting it would create broken intermediate states (template references context keys that don't exist yet). Atomic is correct.
- Test 4.1 monkeypatches several module-level functions; relies on the existing `process_subject` calling them by name. If `process_subject` is refactored to call them differently, the test would silently pass while breaking the actual gating. Mitigated by being a TDD test — failure mode is "test passes but bug exists" only after future refactors, not today.
- The user's fork at `/home/users/logben/network_glm/PrecisionNetworkMapping` is the location passed to `--mshbm-dir`. The `mshbm` pipeline's CLI default points at a sibling-of-neuro_workflow path that does not exist on this system. Task 6 includes the explicit `--mshbm-dir` flag to override the default.
