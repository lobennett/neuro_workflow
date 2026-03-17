# Merge network_lev1 into neuro_workflow.analysis

**Date:** 2026-03-10
**Status:** Approved

## Problem

The codebase has two packages under `src/`: `neuro_workflow` and `network_lev1`. This obfuscates the codebase and creates an awkward cross-package dependency (outlier_report.py imports from network_lev1). Consolidating into a single package with a clear `analysis/` sub-package provides better organization.

## Approach

Big-bang move: relocate all `network_lev1` code into `neuro_workflow/analysis/` in one pass, update all imports, remove the old package.

## Module Layout

```
src/neuro_workflow/analysis/
├── __init__.py
├── config.py                 # Config dataclass (from network_lev1/config.py)
├── task_config/              # shared YAML configs + loader
│   ├── loader.py
│   └── tasks/*.yaml
├── core/                     # shared utilities
│   ├── task_utils.py
│   └── utils.py
├── io/                       # shared file discovery
│   └── file_discovery.py
├── lev1/
│   ├── __init__.py
│   ├── run.py                # entry point (from run_lev1.py)
│   └── processing/           # all 10 processing modules as-is
├── lev2/
│   ├── __init__.py
│   └── run.py                # entry point (from run_lev2.py)
└── mshbm/
    ├── __init__.py
    └── run.py                # entry point (from prepare_mshbm_inputs.py)
```

## Import Rewiring

All `from network_lev1.X` imports become `from neuro_workflow.analysis.X`. Mechanical find-and-replace across:

- All source files as they move into `src/neuro_workflow/analysis/`
- All 12 test files under `tests/lev1/`
- `src/neuro_workflow/qa/outlier_report.py` (cross-package import)

No shims or re-exports.

## Entry Points & SLURM Templates

Remove standalone entry points from `pyproject.toml`:

```toml
# Remove:
network-lev1 = "network_lev1.run_lev1:main"
network-lev2 = "network_lev1.run_lev2:main"
network-prep-mshbm = "network_lev1.prepare_mshbm_inputs:main"
```

Update SLURM templates to use `python -m`:

- `lev1.sbatch`: `network-lev1` → `uv run python -m neuro_workflow.analysis.lev1.run`
- `lev2.sbatch`: `network-lev2` → `uv run python -m neuro_workflow.analysis.lev2.run`
- `prep_mshbm.sbatch`: `network-prep-mshbm` → `uv run python -m neuro_workflow.analysis.mshbm.run`

## Cross-Package Import Fix

`src/neuro_workflow/qa/outlier_report.py`:

```python
# Before:
from network_lev1.core.utils import load_exclusions
# After:
from neuro_workflow.analysis.core.utils import load_exclusions
```

## Test Migration

- Move `tests/lev1/*.py` → `tests/analysis/lev1/`
- Update all imports from `network_lev1.*` → `neuro_workflow.analysis.*`
- Add `tests/analysis/__init__.py` and `tests/analysis/lev1/__init__.py`

## Cleanup

- Delete `src/network_lev1/` after move is complete
- `discovery_wm/` and `network-behavior-qc/` directories **cannot** be deleted (only small portions were ported to events pipeline)

## Dependencies

The `lev1` optional dependency group in `pyproject.toml` stays as-is (statsmodels, randomise-prep).
