# Merge network_lev1 into neuro_workflow.analysis — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate `src/network_lev1` into `src/neuro_workflow/analysis/` so the project has one package.

**Architecture:** Big-bang move of all network_lev1 code into neuro_workflow/analysis/, mechanical import rewriting, SLURM template updates, and test migration. No behavioral changes.

**Tech Stack:** Python, pytest, uv, SLURM sbatch templates

---

### Task 1: Create analysis package skeleton

**Files:**
- Create: `src/neuro_workflow/analysis/__init__.py`
- Create: `src/neuro_workflow/analysis/lev1/__init__.py`
- Create: `src/neuro_workflow/analysis/lev2/__init__.py`
- Create: `src/neuro_workflow/analysis/mshbm/__init__.py`

**Step 1: Create the directory structure and empty init files**

```bash
mkdir -p src/neuro_workflow/analysis/lev1 src/neuro_workflow/analysis/lev2 src/neuro_workflow/analysis/mshbm
touch src/neuro_workflow/analysis/__init__.py
touch src/neuro_workflow/analysis/lev1/__init__.py
touch src/neuro_workflow/analysis/lev2/__init__.py
touch src/neuro_workflow/analysis/mshbm/__init__.py
```

**Step 2: Verify the package is importable**

Run: `module load uv && uv run python -c "import neuro_workflow.analysis; print('ok')"`
Expected: `ok`

**Step 3: Commit**

```bash
git add src/neuro_workflow/analysis/
git commit -m "feat(analysis): create analysis package skeleton"
```

---

### Task 2: Move shared modules (config, core, io, task_config)

**Files:**
- Move: `src/network_lev1/config.py` → `src/neuro_workflow/analysis/config.py`
- Move: `src/network_lev1/core/task_utils.py` → `src/neuro_workflow/analysis/core/task_utils.py`
- Move: `src/network_lev1/core/utils.py` → `src/neuro_workflow/analysis/core/utils.py`
- Move: `src/network_lev1/io/file_discovery.py` → `src/neuro_workflow/analysis/io/file_discovery.py`
- Move: `src/network_lev1/task_config/loader.py` → `src/neuro_workflow/analysis/task_config/loader.py`
- Move: `src/network_lev1/task_config/tasks/*.yaml` → `src/neuro_workflow/analysis/task_config/tasks/*.yaml`

**Step 1: Copy files to new locations**

```bash
# Shared modules
cp src/network_lev1/config.py src/neuro_workflow/analysis/config.py

mkdir -p src/neuro_workflow/analysis/core
cp src/network_lev1/core/task_utils.py src/neuro_workflow/analysis/core/task_utils.py
cp src/network_lev1/core/utils.py src/neuro_workflow/analysis/core/utils.py

mkdir -p src/neuro_workflow/analysis/io
cp src/network_lev1/io/file_discovery.py src/neuro_workflow/analysis/io/file_discovery.py

mkdir -p src/neuro_workflow/analysis/task_config/tasks
cp src/network_lev1/task_config/loader.py src/neuro_workflow/analysis/task_config/loader.py
cp src/network_lev1/task_config/tasks/*.yaml src/neuro_workflow/analysis/task_config/tasks/
```

**Step 2: Update imports in the copied files**

In `src/neuro_workflow/analysis/core/task_utils.py`, change:
```python
# Line 5:
from network_lev1.task_config.loader import get_task_parameters
# →
from neuro_workflow.analysis.task_config.loader import get_task_parameters
```

No other shared modules have internal cross-imports.

**Step 3: Verify the shared modules import correctly**

Run: `module load uv && uv run python -c "from neuro_workflow.analysis.config import Config; from neuro_workflow.analysis.task_config.loader import get_task_parameters; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add src/neuro_workflow/analysis/
git commit -m "feat(analysis): move shared modules (config, core, io, task_config)"
```

---

### Task 3: Move processing modules

**Files:**
- Move: all 10 files from `src/network_lev1/processing/` → `src/neuro_workflow/analysis/lev1/processing/`

The 10 processing modules: `confounds.py`, `contrasts.py`, `design.py`, `events.py`, `fixed_effects.py`, `glm.py`, `masks.py`, `quality_control.py`, `residuals.py`, `surface_data.py`

**Step 1: Copy processing files**

```bash
mkdir -p src/neuro_workflow/analysis/lev1/processing
cp src/network_lev1/processing/*.py src/neuro_workflow/analysis/lev1/processing/
```

**Step 2: Update imports in all processing files**

Each file has `from network_lev1.` imports that must become `from neuro_workflow.analysis.`. Here are all the changes:

`src/neuro_workflow/analysis/lev1/processing/confounds.py` line 9:
```python
from neuro_workflow.analysis.task_config.loader import DUMMY_SCANS
```

`src/neuro_workflow/analysis/lev1/processing/contrasts.py` line 12:
```python
from neuro_workflow.analysis.task_config.loader import get_task_contrasts
```

`src/neuro_workflow/analysis/lev1/processing/design.py` line 10:
```python
from neuro_workflow.analysis.task_config.loader import get_regressor_config
```

`src/neuro_workflow/analysis/lev1/processing/events.py` line 22:
```python
from neuro_workflow.analysis.task_config.loader import DUMMY_SCANS, TR
```

`src/neuro_workflow/analysis/lev1/processing/fixed_effects.py` line 12:
```python
from neuro_workflow.analysis.lev1.processing.surface_data import (
```

`src/neuro_workflow/analysis/lev1/processing/fixed_effects.py` line 16:
```python
from neuro_workflow.analysis.task_config.loader import get_task_contrasts
```

`src/neuro_workflow/analysis/lev1/processing/glm.py` line 12:
```python
from neuro_workflow.analysis.task_config.loader import TR
```

`src/neuro_workflow/analysis/lev1/processing/surface_data.py` line 18:
```python
from neuro_workflow.analysis.task_config.loader import DUMMY_SCANS
```

**Step 3: Verify processing modules import correctly**

Run: `module load uv && uv run python -c "from neuro_workflow.analysis.lev1.processing.glm import fit_run_glm; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/processing/
git commit -m "feat(analysis): move lev1 processing modules"
```

---

### Task 4: Move entry point modules (lev1, lev2, mshbm)

**Files:**
- Move: `src/network_lev1/run_lev1.py` → `src/neuro_workflow/analysis/lev1/run.py`
- Move: `src/network_lev1/run_lev2.py` → `src/neuro_workflow/analysis/lev2/run.py`
- Move: `src/network_lev1/prepare_mshbm_inputs.py` → `src/neuro_workflow/analysis/mshbm/run.py`

**Step 1: Copy entry point files**

```bash
cp src/network_lev1/run_lev1.py src/neuro_workflow/analysis/lev1/run.py
cp src/network_lev1/run_lev2.py src/neuro_workflow/analysis/lev2/run.py
cp src/network_lev1/prepare_mshbm_inputs.py src/neuro_workflow/analysis/mshbm/run.py
```

**Step 2: Rewrite all imports in lev1/run.py**

In `src/neuro_workflow/analysis/lev1/run.py`, replace all `from network_lev1.` imports (lines 12-51):

```python
from neuro_workflow.analysis.config import Config
from neuro_workflow.analysis.core.task_utils import detect_sample_type, get_expected_sessions
from neuro_workflow.analysis.core.utils import (
    check_behavioral_trim_threshold,
    count_subject_exclusions,
    load_exclusions,
    load_exclusions_by_type,
    normalize_subject_id,
)
from neuro_workflow.analysis.io.file_discovery import FileFinder
from neuro_workflow.analysis.lev1.processing.confounds import get_fc_confounds, load_and_process_confounds
from neuro_workflow.analysis.lev1.processing.contrasts import (
    compute_run_contrasts,
    filter_contrasts_for_dropped_columns,
)
from neuro_workflow.analysis.lev1.processing.design import create_design_matrix
from neuro_workflow.analysis.lev1.processing.events import (
    add_junk_trials,
    load_bold_data_with_dummy_removal,
    preprocess_events,
    save_simplified_events,
)
from neuro_workflow.analysis.lev1.processing.fixed_effects import compute_subject_fixed_effects
from neuro_workflow.analysis.lev1.processing.glm import (
    fit_run_glm,
    handle_zero_variance_columns,
    validate_glm_inputs,
)
from neuro_workflow.analysis.lev1.processing.masks import MaskProcessor
from neuro_workflow.analysis.lev1.processing.quality_control import run_quality_control
from neuro_workflow.analysis.lev1.processing.residuals import process_run_residuals, process_surface_residuals
from neuro_workflow.analysis.lev1.processing.surface_data import (
    SurfaceGLM,
    find_freesurfer_subjects_dir,
    get_surface_scan_info,
    load_surface_data,
    plot_surface_stat_map,
    smooth_surface_gifti,
)
from neuro_workflow.analysis.task_config.loader import get_task_contrasts, get_task_parameters
```

lev2/run.py has no `network_lev1` imports — leave as-is.

mshbm/run.py has no `network_lev1` imports — leave as-is.

**Step 3: Verify entry points import correctly**

Run: `module load uv && uv run python -c "from neuro_workflow.analysis.lev1.run import main; print('ok')"`
Expected: `ok`

Run: `module load uv && uv run python -c "from neuro_workflow.analysis.lev2.run import main; print('ok')"`
Expected: `ok`

Run: `module load uv && uv run python -c "from neuro_workflow.analysis.mshbm.run import main; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add src/neuro_workflow/analysis/lev1/run.py src/neuro_workflow/analysis/lev2/run.py src/neuro_workflow/analysis/mshbm/run.py
git commit -m "feat(analysis): move lev1, lev2, mshbm entry points"
```

---

### Task 5: Update SLURM templates

**Files:**
- Modify: `src/neuro_workflow/templates/lev1.sbatch:17`
- Modify: `src/neuro_workflow/templates/lev2.sbatch:17`
- Modify: `src/neuro_workflow/templates/prep_mshbm.sbatch:18`

**Step 1: Update lev1.sbatch**

Change line 17 from:
```bash
uv --directory "{neuro_workflow_dir}" run network-lev1 \
```
to:
```bash
uv --directory "{neuro_workflow_dir}" run python -m neuro_workflow.analysis.lev1.run \
```

**Step 2: Update lev2.sbatch**

Change line 17 from:
```bash
uv --directory "{neuro_workflow_dir}" run network-lev2 \
```
to:
```bash
uv --directory "{neuro_workflow_dir}" run python -m neuro_workflow.analysis.lev2.run \
```

**Step 3: Update prep_mshbm.sbatch**

Change line 18 from:
```bash
uv --directory "{neuro_workflow_dir}" run network-prep-mshbm \
```
to:
```bash
uv --directory "{neuro_workflow_dir}" run python -m neuro_workflow.analysis.mshbm.run \
```

**Step 4: Verify templates render correctly**

Run: `module load uv && uv run python -c "from pathlib import Path; t = Path('src/neuro_workflow/templates/lev1.sbatch').read_text(); assert 'python -m neuro_workflow.analysis.lev1.run' in t; print('ok')"`
Expected: `ok`

**Step 5: Commit**

```bash
git add src/neuro_workflow/templates/lev1.sbatch src/neuro_workflow/templates/lev2.sbatch src/neuro_workflow/templates/prep_mshbm.sbatch
git commit -m "feat(analysis): update SLURM templates to use new module paths"
```

---

### Task 6: Update cross-package import in outlier_report.py

**Files:**
- Modify: `src/neuro_workflow/qa/outlier_report.py:33`

**Step 1: Update the import**

Change line 33 from:
```python
from network_lev1.core.utils import load_exclusions
```
to:
```python
from neuro_workflow.analysis.core.utils import load_exclusions
```

**Step 2: Verify it imports**

Run: `module load uv && uv run python -c "from neuro_workflow.qa.outlier_report import OutlierReportQa; print('ok')"`
Expected: `ok`

**Step 3: Commit**

```bash
git add src/neuro_workflow/qa/outlier_report.py
git commit -m "fix(qa): update outlier_report import to use analysis package"
```

---

### Task 7: Remove standalone entry points from pyproject.toml

**Files:**
- Modify: `pyproject.toml:9-11`

**Step 1: Remove the three standalone entry points**

In `pyproject.toml`, remove these lines (9-11):
```toml
network-lev1 = "network_lev1.run_lev1:main"
network-lev2 = "network_lev1.run_lev2:main"
network-prep-mshbm = "network_lev1.prepare_mshbm_inputs:main"
```

The `[project.scripts]` section should only contain:
```toml
[project.scripts]
neuro-run = "neuro_workflow.cli:main"
```

**Step 2: Sync the project**

Run: `module load uv && uv sync`

**Step 3: Verify neuro-run still works**

Run: `module load uv && uv run neuro-run --help`
Expected: Help text with no errors.

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(analysis): remove standalone entry points from pyproject.toml"
```

---

### Task 8: Migrate tests

**Files:**
- Move: `tests/lev1/conftest.py` → `tests/analysis/lev1/conftest.py`
- Move: all 13 test files from `tests/lev1/` → `tests/analysis/lev1/`
- Create: `tests/analysis/__init__.py`
- Create: `tests/analysis/lev1/__init__.py`

**Step 1: Create test directories and copy files**

```bash
mkdir -p tests/analysis/lev1
touch tests/analysis/__init__.py
touch tests/analysis/lev1/__init__.py
cp tests/lev1/*.py tests/analysis/lev1/
```

**Step 2: Update imports in all test files**

Use find-and-replace in each file under `tests/analysis/lev1/`: change all `from network_lev1.` to `from neuro_workflow.analysis.`. The specific files and their import lines:

`test_config.py` line 5: `from neuro_workflow.analysis.config import Config`

`test_confounds.py` line 5: `from neuro_workflow.analysis.lev1.processing.confounds import get_fc_confounds`

`test_core.py` line 7: `from neuro_workflow.analysis.core.utils import (`

`test_design.py` line 7: `from neuro_workflow.analysis.lev1.processing.design import create_design_matrix, create_regressor`

`test_file_discovery.py` line 5: `from neuro_workflow.analysis.io.file_discovery import FileFinder`

`test_processing_events.py` line 7: `from neuro_workflow.analysis.lev1.processing.events import (`

`test_processing_masks.py` line 8: `from neuro_workflow.analysis.lev1.processing.masks import MaskProcessor`

`test_surface_fixed_effects.py` line 10: `from neuro_workflow.analysis.lev1.processing.surface_data import (`

`test_surface_glm_spaces.py` lines 7-10:
```python
from neuro_workflow.analysis.io.file_discovery import FileFinder
from neuro_workflow.analysis.lev1.processing.confounds import get_fc_confounds
from neuro_workflow.analysis.lev1.processing.fixed_effects import FixedEffectsAnalyzer
from neuro_workflow.analysis.lev1.processing.surface_data import SurfaceGLM
```

`test_surface_residuals.py` line 8: `from neuro_workflow.analysis.lev1.processing.surface_data import SurfaceGLM`

`test_task_config.py` line 5: `from neuro_workflow.analysis.task_config.loader import (`

`test_task_utils.py` line 7: `from neuro_workflow.analysis.core.task_utils import (`

`test_vol2fsaverage.py`: Check if it has `network_lev1` imports and update accordingly.

**Step 3: Run the migrated tests**

Run: `module load uv && uv run pytest tests/analysis/lev1/ -v`
Expected: All tests pass (same results as before).

**Step 4: Commit**

```bash
git add tests/analysis/
git commit -m "test(analysis): migrate lev1 tests to tests/analysis/lev1/"
```

---

### Task 9: Delete old network_lev1 package and tests/lev1

**Files:**
- Delete: `src/network_lev1/` (entire directory)
- Delete: `tests/lev1/` (entire directory)

**Step 1: Run full test suite first to confirm nothing breaks**

Run: `module load uv && uv run pytest tests/ -v --ignore=tests/lev1`
Expected: All tests pass (the old tests/lev1 is ignored since we have the migrated copy).

**Step 2: Delete old directories**

```bash
rm -rf src/network_lev1
rm -rf tests/lev1
```

**Step 3: Verify no remaining references to network_lev1**

Run: `grep -r "network_lev1" src/ tests/ --include="*.py"`
Expected: No output (no remaining references).

**Step 4: Run full test suite**

Run: `module load uv && uv run pytest tests/ -v`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove old network_lev1 package and tests/lev1"
```
