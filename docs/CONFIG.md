# Config Reference

**Last updated:** 2026-06-09

This document covers the two config-as-code files that control study-level analysis behaviour. Both files are version-controlled; editing either produces a new `config_version()` hash recorded in every subsequent provenance manifest.

---

## config/thresholds.yaml

Single source of truth for all QC, motion, and lev1-outlier thresholds. Loaded at import by `neuro_workflow.core.thresholds` (`load_thresholds()`). There is no fallback to hardcoded defaults — if the file is missing the package raises at import.

### Sections

#### behavioral_qc

Controls in-scanner performance QC applied by `exclusions/behavioral.py` (via `events/qc.py`):

| Key | Default | Meaning |
|-----|---------|---------|
| `stop_success_acc_low_threshold` | 0.25 | Stop-signal: minimum stop-success accuracy |
| `stop_success_acc_high_threshold` | 0.75 | Stop-signal: maximum stop-success accuracy (ceiling exclusion) |
| `go_rt_threshold_fmri` | 1000 | Go RT (ms) above which the scan is excluded (single-task) |
| `go_rt_threshold_fmri_dual_task` | 1050 | Go RT threshold for dual-task sessions |
| `gonogo_go_acc_threshold_1` / `_2` | 0.75 / 0.5 | Go/Nogo: both conditions must be met for exclusion |
| `gonogo_nogo_acc_threshold_1` / `_2` | 0.2 / 0.5 | |
| `nback_*` | various | N-back: matched accuracy thresholds per level |
| `acc_threshold` | 0.55 | All other tasks: minimum accuracy |
| `omission_rate_threshold` | 0.25 | All tasks: maximum omission rate |
| `last_n_test_trials` | 10 | Trim detection: how many trailing trials to check |
| `summary_rows` | 4 | Trim detection: number of summary rows at end of CSV |

#### motion

Controls `exclusions/motion.py` argparse defaults (fmriprep confounds-based):

| Key | Default | Meaning |
|-----|---------|---------|
| `fd_threshold` | 0.2 | Mean framewise displacement (mm) threshold for resting-state |
| `proportion_fd_threshold` | 0.2 | Proportion of frames with FD > 0.5 for task scans |
| `proportion_dvars_threshold` | 0.2 | Proportion of frames with std_dvars > 1.5 |

#### lev1_outlier

Controls the VIF/outlier thresholds in `exclusions/lev1_outlier.py`:

| Key | Default | Meaning |
|-----|---------|---------|
| `combined_vif` | 10.0 | Combined rule: VIF >= this AND outlier_pct >= combined_outlier_pct |
| `combined_outlier_pct` | 10.0 | Combined rule: outlier percentage threshold |
| `strict_vif` | 15.0 | Strict VIF-only rule: VIF >= this → exclude regardless of outlier_pct |
| `strict_outlier_pct` | 15.0 | Strict outlier-only rule: outlier_pct >= this → exclude |

### Changing a threshold

Edit `config/thresholds.yaml`, commit the change, and rerun the relevant exclusion generator + compile step:

```bash
# After editing thresholds.yaml:
uv run neuro-run exclusions generate motion discovery
uv run neuro-run exclusions compile discovery
```

The new `config_version()` will be recorded in the next run manifest automatically.

---

## src/neuro_workflow/analysis/task_config/battery.yaml

Canonical ordered lists of the 8 base (single-task) and 10 dual-task paradigm names. Loaded by `analysis/task_config/loader.py`.

```yaml
base:
  - cuedTS
  - directedForgetting
  - flanker
  - goNogo
  - nBack
  - shapeMatching
  - spatialTS
  - stopSignal

dual:
  - directedForgettingWCuedTS
  - directedForgettingWFlanker
  - stopSignalWDirectedForgetting
  - stopSignalWFlanker
  - spatialTSWCuedTS
  - flankerWShapeMatching
  - cuedTSWFlanker
  - spatialTSWShapeMatching
  - nBackWShapeMatching
  - nBackWSpatialTS
```

### Python API

```python
from neuro_workflow.analysis.task_config.loader import (
    get_base_tasks,   # -> list of 8 base task names
    get_dual_tasks,   # -> list of 10 dual task names
    get_all_tasks,    # -> base + dual, 18 total
)
```

Order is canonical — lev1/lev2 flag resolution (`--all` / `--base-tasks` / `--dual-tasks`) depends on this order. Do not reorder without a behavior-preserving audit.

---

## Per-task YAML configs

Each of the 18 tasks has a YAML file in `src/neuro_workflow/analysis/task_config/tasks/<task>.yaml` defining its regressors and contrasts. Contrast formulas are validated at config-load time; a formula that references an undeclared regressor name raises `ContrastFormulaError` immediately rather than failing silently at GLM fit.

Placeholder YAMLs (dual-task configs with `regressors: null`) raise `TaskNotConfiguredError` when accessed, which signals that the config needs to be filled in before lev1 can run for that task.

---

## config/pipeline_config.json

Subject lists, session overrides, and Flywheel label aliases. Not part of the config-as-code / `config_version` hash — it describes the study sample and is not an analysis threshold.
