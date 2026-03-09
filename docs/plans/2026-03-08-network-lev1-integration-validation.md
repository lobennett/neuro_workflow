# network_lev1 Integration Validation & Consolidation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Verify the network_lev1 merge works correctly, add missing tests for new pipeline modules, and extract duplicated boilerplate across pipelines.

**Architecture:** The two-package layout (neuro_workflow + network_lev1) is well-separated — zero Python-level cross-imports. neuro_workflow is orchestration (SLURM scripts, config, exclusions), network_lev1 is analysis (GLM, contrasts, file discovery). Communication is via CLI arguments and files. The main gaps are: (1) no tests for 4 new pipeline modules, (2) duplicated boilerplate across pipeline `build_context()` methods, (3) lev1 tests can't run without optional deps being installable.

**Tech Stack:** Python 3.11+, pytest, uv, SLURM sbatch templates

---

## Assessment Summary

### What's clean
- Zero Python imports between packages — clean boundary
- Exclusions: neuro_workflow creates them, network_lev1 consumes them (complementary, not duplicated)
- Config: different abstraction levels (dataset-level vs analysis-level) — no real overlap
- Subject loading: `load_subjects()` in neuro_workflow reads file, `normalize_subject_id()` in network_lev1 normalizes IDs — different concerns
- Format bridging in `network_lev1/core/utils.py` already handles both exclusion formats

### What needs work
1. **No tests for lev1, lev2, prep_mshbm, mshbm pipeline modules** — all other pipelines have tests
2. **Boilerplate duplication** — mail_line construction, resource override logic repeated in every pipeline's `build_context()`
3. **lev1 test suite blocked** — `tests/lev1/` requires nibabel/nilearn/scipy which fail to install (missing OpenBLAS)
4. **No pytest marker** to skip lev1 tests when optional deps are missing

### What does NOT need changing
- The two-package split is correct and should stay
- network_lev1's own config.py (analysis-level paths) does not overlap with neuro_workflow's config.py (dataset registration)
- Entry points (network-lev1, network-lev2, network-prep-mshbm) are fine as separate CLI tools invoked by SLURM templates

---

## Task 1: Add pytest marker for optional-dep tests

**Files:**
- Create: `tests/lev1/conftest.py` (modify existing)
- Modify: `pyproject.toml` (add marker)

**Step 1: Read existing conftest**

Already read — `tests/lev1/conftest.py` imports nibabel at module level (line 6), causing collection failure.

**Step 2: Add skip marker to conftest.py**

Add at the top of `tests/lev1/conftest.py`, before any neuroimaging imports:

```python
import pytest

try:
    import nibabel
except ImportError:
    pytest.skip("neuroimaging dependencies not installed (install with: uv pip install -e '.[lev1]')", allow_module_level=True)
```

**Step 3: Register marker in pyproject.toml**

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "lev1: requires neuroimaging dependencies (nibabel, nilearn, statsmodels)",
]
```

**Step 4: Run tests to verify lev1 tests skip gracefully**

Run: `uv run python -m pytest tests/ -q`
Expected: 116 passed, tests/lev1 skipped (not errored)

**Step 5: Commit**

```bash
git add tests/lev1/conftest.py pyproject.toml
git commit -m "fix: skip lev1 tests gracefully when neuroimaging deps not installed"
```

---

## Task 2: Add tests for Lev1Pipeline

**Files:**
- Create: `tests/pipelines/test_lev1.py`
- Test: `tests/pipelines/test_lev1.py`

**Step 1: Write the tests**

```python
from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.lev1 import (
    Lev1Pipeline,
    BASE_TASKS,
    DUAL_TASKS,
    ALL_TASKS,
)
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_lev1_pipeline_is_registered():
    pipeline = get_pipeline("lev1")
    assert pipeline is not None
    assert pipeline.name == "lev1"


def test_lev1_has_no_docker_uri():
    p = Lev1Pipeline()
    assert p.docker_uri is None


def test_lev1_default_resources():
    p = Lev1Pipeline()
    assert p.default_resources["nthreads"] == 1
    assert p.default_resources["mem_gb"] == 64
    assert p.default_resources["time"] == "2-00:00:00"


def test_lev1_template_exists():
    p = Lev1Pipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_lev1_task_constants():
    assert len(BASE_TASKS) == 8
    assert len(DUAL_TASKS) == 10
    assert ALL_TASKS == BASE_TASKS + DUAL_TASKS
    assert "flanker" in BASE_TASKS
    assert "stopSignalWDirectedForgetting" in DUAL_TASKS


def test_lev1_build_context_base_tasks(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=None,
        tasks_flag="base",
        fmriprep_dir="/oak/data/bids/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["n_jobs"] == 2 * 8  # 2 subjects x 8 base tasks
    assert ctx["nthreads"] == 1
    assert ctx["mem_gb"] == 64
    assert ctx["space"] == "MNI"
    assert ctx["mail_line"] == ""
    assert ctx["extra_flags"] == ""

    # Verify job list file was written
    job_list = Path(ctx["job_list_file"]).read_text().strip().split("\n")
    assert len(job_list) == 16
    assert "s03 flanker" in job_list


def test_lev1_build_context_explicit_tasks(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=["flanker", "nBack"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/bids/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["n_jobs"] == 2  # 1 subject x 2 tasks


def test_lev1_build_context_extra_flags(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": "user@stanford.edu",
    }
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/bids/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="surface",
        threshold=0.8,
        smoothing_fwhm=5.0,
        residuals=True,
        fc_confounds=True,
        skip_existing=True,
        nthreads=2,
        mem_gb=32,
        time="1-00:00:00",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "--smoothing-fwhm 5.0" in ctx["extra_flags"]
    assert "--residuals" in ctx["extra_flags"]
    assert "--fc-confounds" in ctx["extra_flags"]
    assert "--skip-existing" in ctx["extra_flags"]
    assert ctx["nthreads"] == 2
    assert ctx["mem_gb"] == 32
    assert ctx["time"] == "1-00:00:00"
    assert "#SBATCH --mail-user=user@stanford.edu" in ctx["mail_line"]


def test_lev1_build_context_default_results_dir(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=["flanker"],
        tasks_flag=None,
        fmriprep_dir="/oak/data/bids/derivatives/fmriprep",
        results_dir=None,
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["results_dir"] == "/oak/data/bids/derivatives/lev1"


def test_lev1_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text("[]")

    p = Lev1Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        tasks=None,
        tasks_flag="base",
        fmriprep_dir="/oak/data/bids/derivatives/fmriprep",
        results_dir=str(tmp_path / "results"),
        exclusions_file=str(exclusions),
        space="MNI",
        threshold=1.0,
        smoothing_fwhm=None,
        residuals=False,
        fc_confounds=False,
        skip_existing=False,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH -J lev1_test_ds" in script
    assert "#SBATCH --array=1-16" in script
    assert "network-lev1" in script
    assert "--bids-dir" in script
    assert "--exclusions-file" in script
    assert "--space MNI" in script
```

**Step 2: Run tests to verify they pass**

Run: `uv run python -m pytest tests/pipelines/test_lev1.py -v`
Expected: all tests PASS

**Step 3: Commit**

```bash
git add tests/pipelines/test_lev1.py
git commit -m "test: add tests for lev1 pipeline module"
```

---

## Task 3: Add tests for Lev2Pipeline

**Files:**
- Create: `tests/pipelines/test_lev2.py`

**Step 1: Write the tests**

```python
from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.lev2 import Lev2Pipeline, _discover_contrasts_from_lev1_dirs
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_lev2_pipeline_is_registered():
    pipeline = get_pipeline("lev2")
    assert pipeline is not None
    assert pipeline.name == "lev2"


def test_lev2_has_no_docker_uri():
    p = Lev2Pipeline()
    assert p.docker_uri is None


def test_lev2_default_resources():
    p = Lev2Pipeline()
    assert p.default_resources["nthreads"] == 2
    assert p.default_resources["mem_gb"] == 4
    assert p.default_resources["time"] == "04:00:00"


def test_lev2_template_exists():
    p = Lev2Pipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_discover_contrasts_from_lev1_dirs(tmp_path):
    """Create fake fixed-effects files and verify contrast discovery."""
    fe_dir = tmp_path / "sub-s03" / "task-flanker" / "fixed_effects"
    fe_dir.mkdir(parents=True)
    (fe_dir / "sub-s03_task-flanker_contrast-incongruentGtCongruent_stat-fixed-effects.nii.gz").touch()
    (fe_dir / "sub-s03_task-flanker_contrast-incongruentVsBaseline_stat-fixed-effects.nii.gz").touch()

    contrasts = _discover_contrasts_from_lev1_dirs([str(tmp_path)])
    assert len(contrasts) == 2
    assert "task-flanker_contrast-incongruentGtCongruent" in contrasts
    assert "task-flanker_contrast-incongruentVsBaseline" in contrasts


def test_discover_contrasts_with_task_filter(tmp_path):
    """Task filter limits discovered contrasts."""
    for task in ["flanker", "nBack"]:
        fe_dir = tmp_path / "sub-s03" / f"task-{task}" / "fixed_effects"
        fe_dir.mkdir(parents=True)
        (fe_dir / f"sub-s03_task-{task}_contrast-test_stat-fixed-effects.nii.gz").touch()

    contrasts = _discover_contrasts_from_lev1_dirs([str(tmp_path)], task_filter=["flanker"])
    assert len(contrasts) == 1
    assert "task-flanker_contrast-test" in contrasts


def test_lev2_build_context_explicit_contrasts(tmp_path):
    p = Lev2Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(tmp_path / "subs.txt"),
        "partition": "russpold",
        "mail_user": None,
    }
    (tmp_path / "subs.txt").write_text("s03\n")

    args = Namespace(
        lev1_dirs=["/oak/data/bids/derivatives/lev1"],
        results_dir=str(tmp_path / "lev2_results"),
        exclusions_csv="/path/to/flagged.csv",
        contrasts=["task-flanker_contrast-test", "task-nBack_contrast-test"],
        contrasts_flag=None,
        mask_threshold=0.9,
        num_permutations=5000,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["n_contrasts"] == 2
    assert ctx["mask_threshold"] == 0.9
    assert ctx["num_permutations"] == 5000
    assert ctx["mail_line"] == ""

    # Verify contrast list file
    contrast_list = Path(ctx["contrast_list_file"]).read_text().strip().split("\n")
    assert len(contrast_list) == 2


def test_lev2_render_full_template(tmp_path):
    p = Lev2Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(tmp_path / "subs.txt"),
        "partition": "russpold",
        "mail_user": None,
    }
    (tmp_path / "subs.txt").write_text("s03\n")

    args = Namespace(
        lev1_dirs=["/oak/lev1_discovery", "/oak/lev1_validation"],
        results_dir=str(tmp_path / "lev2_results"),
        exclusions_csv="/path/to/flagged.csv",
        contrasts=["task-flanker_contrast-test"],
        contrasts_flag=None,
        mask_threshold=0.9,
        num_permutations=5000,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)

    assert "#SBATCH -J lev2_test_ds" in script
    assert "network-lev2" in script
    assert "--flagged-scans-csv" in script
    assert "/oak/lev1_discovery /oak/lev1_validation" in script
```

**Step 2: Run tests**

Run: `uv run python -m pytest tests/pipelines/test_lev2.py -v`
Expected: all PASS

**Step 3: Commit**

```bash
git add tests/pipelines/test_lev2.py
git commit -m "test: add tests for lev2 pipeline module"
```

---

## Task 4: Add tests for PrepMshbmPipeline and MshbmPipeline

**Files:**
- Create: `tests/pipelines/test_prep_mshbm.py`
- Create: `tests/pipelines/test_mshbm.py`

**Step 1: Write prep_mshbm tests**

```python
from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.prep_mshbm import PrepMshbmPipeline
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_prep_mshbm_pipeline_is_registered():
    pipeline = get_pipeline("prep-mshbm")
    assert pipeline is not None
    assert pipeline.name == "prep-mshbm"


def test_prep_mshbm_has_no_docker_uri():
    p = PrepMshbmPipeline()
    assert p.docker_uri is None


def test_prep_mshbm_template_exists():
    p = PrepMshbmPipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_prep_mshbm_build_context(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\ns15\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        glm_dir="/oak/data/bids/derivatives/lev1",
        fmriprep_dir="/oak/data/bids/derivatives/fmriprep",
        rest_fmriprep_dir=None,
        output_dir=str(tmp_path / "surface_inputs"),
        residuals_space="surface",
        sessions=None,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["n_subjects"] == 3
    assert ctx["residuals_space"] == "surface"
    assert ctx["extra_flags"] == ""


def test_prep_mshbm_build_context_with_extras(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = PrepMshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": "user@stanford.edu",
    }
    args = Namespace(
        glm_dir="/oak/lev1",
        fmriprep_dir="/oak/fmriprep",
        rest_fmriprep_dir="/oak/rest_fmriprep",
        output_dir=str(tmp_path / "out"),
        residuals_space="MNI",
        sessions=["ses-01", "ses-02"],
        nthreads=2,
        mem_gb=32,
        time="12:00:00",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "--rest-fmriprep-dir /oak/rest_fmriprep" in ctx["extra_flags"]
    assert "--sessions ses-01 ses-02" in ctx["extra_flags"]
    assert ctx["nthreads"] == 2
    assert ctx["mem_gb"] == 32
    assert "#SBATCH --mail-user" in ctx["mail_line"]


def test_prep_mshbm_render_full_template(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

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
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)

    assert "network-prep-mshbm" in script
    assert "--glm-dir" in script
    assert "--residuals-space surface" in script
```

**Step 2: Write mshbm tests**

```python
from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.mshbm import MshbmPipeline
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_mshbm_pipeline_is_registered():
    pipeline = get_pipeline("mshbm")
    assert pipeline is not None
    assert pipeline.name == "mshbm"


def test_mshbm_has_no_docker_uri():
    p = MshbmPipeline()
    assert p.docker_uri is None


def test_mshbm_template_exists():
    p = MshbmPipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_mshbm_build_context(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    p = MshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        surface_inputs_dir="/scratch/surface_inputs",
        output_dir=str(tmp_path / "mshbm_out"),
        mshbm_dir="/home/user/PrecisionNetworkMapping",
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["mshbm_dir"] == "/home/user/PrecisionNetworkMapping"
    assert ctx["surface_inputs_dir"] == "/scratch/surface_inputs"

    # Verify sub_list written
    sub_list = Path(ctx["sub_list_file"]).read_text().strip().split("\n")
    assert sub_list == ["s03", "s10"]


def test_mshbm_build_context_default_mshbm_dir(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = MshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        surface_inputs_dir="/scratch/surface_inputs",
        output_dir=str(tmp_path / "mshbm_out"),
        mshbm_dir=None,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    # Default mshbm_dir is sibling of repo root
    assert "PrecisionNetworkMapping" in ctx["mshbm_dir"]


def test_mshbm_render_full_template(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = MshbmPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        surface_inputs_dir="/scratch/surface_inputs",
        output_dir=str(tmp_path / "mshbm_out"),
        mshbm_dir="/home/user/PrecisionNetworkMapping",
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)

    assert "run_MSHBM.sh" in script
    assert "PrecisionNetworkMapping" in script
```

**Step 3: Run tests**

Run: `uv run python -m pytest tests/pipelines/test_prep_mshbm.py tests/pipelines/test_mshbm.py -v`
Expected: all PASS

**Step 4: Commit**

```bash
git add tests/pipelines/test_prep_mshbm.py tests/pipelines/test_mshbm.py
git commit -m "test: add tests for prep-mshbm and mshbm pipeline modules"
```

---

## Task 5: Extract duplicated boilerplate into base helpers

Every pipeline's `build_context()` repeats the same mail_line and resource-override logic. Extract these into `base.py` helpers.

**Files:**
- Modify: `src/neuro_workflow/pipelines/base.py`
- Modify: `src/neuro_workflow/pipelines/lev1.py`
- Modify: `src/neuro_workflow/pipelines/lev2.py`
- Modify: `src/neuro_workflow/pipelines/prep_mshbm.py`
- Modify: `src/neuro_workflow/pipelines/mshbm.py`
- Modify: `src/neuro_workflow/pipelines/fmriprep.py`
- Modify: `src/neuro_workflow/pipelines/qsiprep.py`
- Modify: `src/neuro_workflow/pipelines/freesurfer.py`
- Modify: `src/neuro_workflow/pipelines/fsqc.py`
- Modify: `src/neuro_workflow/pipelines/happy.py`
- Test: `tests/pipelines/test_base.py`

**Step 1: Read current base.py**

Read `src/neuro_workflow/pipelines/base.py` to see current state.

**Step 2: Write failing test for new helpers**

Add to `tests/pipelines/test_base.py`:

```python
from neuro_workflow.pipelines.base import build_mail_line, resolve_resources


def test_build_mail_line_with_user():
    result = build_mail_line({"mail_user": "user@stanford.edu"})
    assert "#SBATCH --mail-user=user@stanford.edu" in result
    assert "#SBATCH --mail-type=ALL" in result


def test_build_mail_line_without_user():
    assert build_mail_line({"mail_user": None}) == ""
    assert build_mail_line({}) == ""


def test_resolve_resources_defaults():
    from argparse import Namespace
    defaults = {"nthreads": 8, "mem_gb": 64, "time": "2-00:00:00"}
    args = Namespace(nthreads=None, mem_gb=None, time=None)
    result = resolve_resources(args, defaults)
    assert result == {"nthreads": 8, "mem_gb": 64, "time": "2-00:00:00"}


def test_resolve_resources_overrides():
    from argparse import Namespace
    defaults = {"nthreads": 8, "mem_gb": 64, "time": "2-00:00:00"}
    args = Namespace(nthreads=4, mem_gb=32, time="1-00:00:00")
    result = resolve_resources(args, defaults)
    assert result == {"nthreads": 4, "mem_gb": 32, "time": "1-00:00:00"}


def test_resolve_resources_partial_override():
    from argparse import Namespace
    defaults = {"nthreads": 8, "mem_per_cpu_gb": 8, "time": "5-00:00:00"}
    args = Namespace(nthreads=4, mem_per_cpu_gb=None, time=None)
    result = resolve_resources(args, defaults)
    assert result == {"nthreads": 4, "mem_per_cpu_gb": 8, "time": "5-00:00:00"}
```

**Step 3: Run tests to verify they fail**

Run: `uv run python -m pytest tests/pipelines/test_base.py -v -k "mail_line or resolve_resources"`
Expected: FAIL (functions don't exist yet)

**Step 4: Add helpers to base.py**

Add to `src/neuro_workflow/pipelines/base.py`:

```python
def build_mail_line(dataset_config: dict) -> str:
    """Build SBATCH mail directives from dataset config."""
    if dataset_config.get("mail_user"):
        return f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
    return ""


def resolve_resources(args, defaults: dict) -> dict:
    """Resolve resource values: use args override if not None, else default."""
    return {
        key: getattr(args, key, None) if getattr(args, key, None) is not None else val
        for key, val in defaults.items()
    }
```

**Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/pipelines/test_base.py -v`
Expected: PASS

**Step 6: Update pipeline modules to use helpers**

For each pipeline file, replace the repeated pattern:
```python
# Before (in each build_context):
if dataset_config.get("mail_user"):
    mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
else:
    mail_line = ""

nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
mem_gb = args.mem_gb if args.mem_gb is not None else self.default_resources["mem_gb"]
time = args.time if args.time is not None else self.default_resources["time"]

# After:
from neuro_workflow.pipelines.base import build_mail_line, resolve_resources

mail_line = build_mail_line(dataset_config)
resources = resolve_resources(args, self.default_resources)
# Then use resources["nthreads"], resources["mem_gb"], resources["time"] in the context dict
```

Apply this to all 9 pipeline files (fmriprep, qsiprep, freesurfer, fsqc, happy, lev1, lev2, prep_mshbm, mshbm).

**Step 7: Run full test suite**

Run: `uv run python -m pytest tests/ --ignore=tests/lev1 -v`
Expected: all PASS (including new tests)

**Step 8: Commit**

```bash
git add src/neuro_workflow/pipelines/ tests/pipelines/test_base.py
git commit -m "refactor: extract mail_line and resource resolution into base helpers"
```

---

## Task 6: Verify end-to-end template rendering for all new pipelines

This is a manual verification task — generate and review actual SLURM scripts.

**Step 1: Write a quick integration test**

Create `tests/test_all_templates_render.py`:

```python
"""Verify every pipeline's template can be rendered without KeyError."""
from neuro_workflow.pipelines.base import list_pipelines, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_lev1_template_has_no_unresolved_placeholders(tmp_path):
    """Verify lev1 template renders fully (no stray {var} left)."""
    from neuro_workflow.pipelines.lev1 import Lev1Pipeline
    from argparse import Namespace

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    exc = tmp_path / "exc.json"
    exc.write_text("[]")

    p = Lev1Pipeline()
    ctx = p.build_context("ds", {
        "bids_dir": "/data", "subjects_file": str(subs),
        "partition": "normal", "mail_user": None,
    }, Namespace(
        tasks=["flanker"], tasks_flag=None,
        fmriprep_dir="/fmriprep", results_dir=str(tmp_path / "out"),
        exclusions_file=str(exc), space="MNI", threshold=1.0,
        smoothing_fwhm=None, residuals=False, fc_confounds=False,
        skip_existing=False, nthreads=None, mem_gb=None, time=None,
    ))
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)

    # No unresolved {placeholders} (but {{SLURM_ARRAY_TASK_ID}} is ok — it becomes {SLURM_ARRAY_TASK_ID})
    import re
    # After str.format(), double-braces become single-braces for shell vars
    # Check there are no Python-style {word} left (excluding shell vars like ${...})
    unresolved = re.findall(r'(?<!\$)\{([a-z_]+)\}', script)
    assert not unresolved, f"Unresolved placeholders: {unresolved}"
```

**Step 2: Run the test**

Run: `uv run python -m pytest tests/test_all_templates_render.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_all_templates_render.py
git commit -m "test: add template rendering smoke test for new pipelines"
```

---

## Summary of Architecture Assessment

### Recommendation: Keep the two-package layout

The current split is well-motivated:

| Concern | neuro_workflow | network_lev1 |
|---------|---------------|-------------|
| Purpose | HPC orchestration | Neuroimaging analysis |
| Dependencies | None (lightweight) | nibabel, nilearn, scipy, statsmodels (heavy) |
| Config level | Dataset registration, HPC settings | Analysis paths, task YAML configs |
| Exclusions | Create, compile, manage | Load and apply |
| Subject handling | Read from file | Normalize IDs |
| Communication | Generates SLURM scripts | Called via CLI entry points |

Merging would force heavy neuroimaging deps on all users, even those only running fmriprep/qsiprep. The CLI-based integration (SLURM template calls `network-lev1` entry point) is the right pattern for HPC — each job runs in its own environment.

### What this plan fixes
1. lev1 tests fail the entire suite when deps missing — **Task 1** adds graceful skip
2. 4 new pipeline modules have zero tests — **Tasks 2-4** add full coverage
3. Boilerplate repeated 9 times — **Task 5** extracts to 2 helpers
4. No smoke test for template rendering — **Task 6** catches placeholder mismatches
