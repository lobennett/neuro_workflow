# neuro-workflow

A zero-dependency Python CLI for submitting neuroimaging pipeline SLURM array jobs. Register a dataset once, then submit parallel jobs for any supported pipeline with a single command.

## Installation

```bash
module load uv
cd /home/users/logben/neuro_workflow
uv pip install -e .
```

For QA commands (nilearn, nibabel, matplotlib, pandas, numpy, seaborn, img2pdf):

```bash
uv pip install -e ".[qa]"
```

For first-level GLM analysis (statsmodels, randomise-prep — requires Python ≥ 3.11):

```bash
uv pip install -e ".[lev1,qa]"
```

After installation, `neuro-run` is available from anywhere (as long as the venv is active or you use the full path `.venv/bin/neuro-run`).

## Quick Start

```bash
# 1. Register a dataset (pipeline-agnostic)
neuro-run add-dataset discovery \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402 \
  --subjects-file /home/users/logben/neuro_workflow/subs_discovery.txt \
  --partition russpold \
  --mail-user logben@stanford.edu

# 2. Preview the generated sbatch script for a pipeline
neuro-run show fmriprep discovery --version 25.2.4

# 3. Submit the job to SLURM
neuro-run submit fmriprep discovery --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k"
```

## Commands

### `neuro-run add-dataset <name>`

Registers a dataset in `~/.neuro_workflow/datasets.json`. Dataset registration is pipeline-agnostic — it only stores shared configuration. Pipeline-specific options are passed at submit time.

**Required arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Dataset name (positional, e.g., `discovery`, `validation`) |
| `--bids-dir` | Path to BIDS directory |
| `--subjects-file` | Path to text file with one subject ID per line |

**Optional arguments (with defaults):**

| Argument | Default | Description |
|----------|---------|-------------|
| `--partition` | `russpold` | SLURM partition |
| `--mail-user` | _(none)_ | Email for SLURM notifications |
| `--image-dir` | `/home/groups/russpold/singularity_images` | Directory for SIF images |
| `--templateflow-dir` | `/home/groups/russpold/templateflow` | TemplateFlow directory |

### `neuro-run show <pipeline> <name> [pipeline-flags]`

Renders the sbatch script for a dataset and pipeline, then prints it to stdout.

```bash
neuro-run show fmriprep discovery --version 25.2.4
neuro-run show --list
```

### `neuro-run submit <pipeline> <name> [pipeline-flags]`

Submits a SLURM array job. Checks/pulls the SIF image if needed, renders the template, and calls `sbatch`.

```bash
neuro-run submit fmriprep discovery --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos"
```

## Supported Pipelines

| Pipeline | Command | Description |
|----------|---------|-------------|
| `fmriprep` | `neuro-run submit fmriprep <dataset> --version <ver>` | fMRI preprocessing via fMRIPrep |
| `qsiprep` | `neuro-run submit qsiprep <dataset> --version <ver>` | DWI preprocessing via QSIPrep |
| `fsqc` | `neuro-run submit fsqc <dataset> --version <ver> --freesurfer-dir <dir>` | FreeSurfer quality control |
| `freesurfer` | `neuro-run submit freesurfer <dataset> --version <ver>` | Cortical reconstruction (deprecated, use fMRIPrep) |
| `happy` | `neuro-run submit happy <dataset> --version <ver>` | Cardiac signal extraction via rapidtide/happy |
| `lev1` | `neuro-run submit lev1 <dataset> --fmriprep-dir <dir> --base-tasks` | First-level GLM (subject × task array) |
| `lev2` | `neuro-run submit lev2 <dataset> --lev1-dirs <dir> --base-tasks ...` | Second-level group GLM via FSL randomise |
| `prep-mshbm` | `neuro-run submit prep-mshbm <dataset> --glm-dir <dir> --fmriprep-dir <dir> ...` | Prepare fsaverage6 surface inputs for MSHBM |
| `mshbm` | `neuro-run submit mshbm <dataset> --surface-inputs-dir <dir> --output-dir <dir>` | Precision network parcellation via MSHBM |

### Pipeline-Specific Options

**fmriprep:**
```bash
neuro-run submit fmriprep discovery --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2" \
  --fs-license ~/license.txt \
  --fmriprep-args "--no-submm-recon"
```

**qsiprep:**
```bash
neuro-run submit qsiprep discovery --version 1.1.1 \
  --output-resolution 1.5 \
  --fs-license ~/license.txt
```

**fsqc:**
```bash
neuro-run submit fsqc discovery --version 2.1.4 \
  --freesurfer-dir /oak/.../derivatives/freesurfer
```

**happy:**
```bash
neuro-run submit happy discovery --version 3.1.8
```

---

## First-Level GLM (`lev1`)

The `lev1` pipeline runs first-level GLM analysis for the Network R01 task battery. It submits a SLURM array job where each task processes one subject × task combination.

### Installation

The lev1 analysis code requires additional dependencies (statsmodels, randomise-prep):

```bash
module load uv
uv pip install -e ".[lev1,qa]"
```

### Prerequisites

Before submitting, compile exclusions for the dataset:

```bash
# Generate motion exclusions from fMRIPrep confounds
neuro-run exclusions generate motion discovery \
  --fmriprep-version 24.1.0rc2 \
  --fd-threshold 0.2

# Generate neg-events exclusions from event files
neuro-run exclusions generate neg-events discovery

# Import any hand-curated behavioral exclusions
neuro-run exclusions import behavioral discovery \
  --input-file /path/to/behavioral_exclusions.json

# Compile all sources into a single exclusions file
neuro-run exclusions compile discovery

# Review the summary
neuro-run exclusions show discovery
```

The compiled exclusions are saved to `~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json` and used automatically by `lev1` (and `lev2`). To use a custom exclusions file instead, pass `--exclusions-file`.

### Submitting lev1 jobs

```bash
# All base tasks, surface space, with FC-quality residuals for precision mapping
neuro-run submit lev1 discovery \
  --fmriprep-dir /oak/.../derivatives/fmriprep_24.1.0rc2 \
  --base-tasks \
  --space surface \
  --residuals \
  --fc-confounds

# Specific tasks, MNI space (volumetric)
neuro-run submit lev1 discovery \
  --fmriprep-dir /oak/.../derivatives/fmriprep_24.1.0rc2 \
  --tasks stopSignal flanker nBack \
  --space MNI

# Preview the sbatch script before submitting
neuro-run show lev1 discovery \
  --fmriprep-dir /oak/.../derivatives/fmriprep_24.1.0rc2 \
  --base-tasks \
  --space surface --residuals
```

Results are written to `{bids_dir}/derivatives/lev1/` by default (override with `--results-dir`).

### lev1 options

| Flag | Default | Description |
|------|---------|-------------|
| `--fmriprep-dir` | _(required)_ | fMRIPrep derivatives directory |
| `--tasks <name...>` | — | One or more specific task names |
| `--base-tasks` | — | All 8 base tasks |
| `--dual-tasks` | — | All 10 dual tasks |
| `--all` | — | All 18 tasks |
| `--results-dir` | `{bids_dir}/derivatives/lev1` | Output directory |
| `--exclusions-file` | compiled exclusions | Path to exclusions JSON (auto-detected) |
| `--space` | `MNI` | `MNI`, `T1w`, `surface`, `fsaverage6`, or `fsLR` |
| `--threshold` | `1.0` | Within-subject mask intersection threshold |
| `--smoothing-fwhm` | _(none)_ | Spatial smoothing in mm |
| `--residuals` | off | Compute task-regressed residuals |
| `--fc-confounds` | off | Regress global signal / WM / CSF from residuals |
| `--skip-existing` | off | Skip runs where output files already exist |
| `--nthreads` | `1` | CPUs per array task |
| `--mem-gb` | `64` | Memory per array task in GB |
| `--time` | `2-00:00:00` | SLURM time limit |

### Available tasks

**Base tasks (8):** cuedTS, directedForgetting, flanker, goNogo, nBack, shapeMatching, spatialTS, stopSignal

**Dual tasks (10):** directedForgettingWCuedTS, directedForgettingWFlanker, stopSignalWDirectedForgetting, stopSignalWFlanker, spatialTSWCuedTS, flankerWShapeMatching, cuedTSWFlanker, spatialTSWShapeMatching, nBackWShapeMatching, nBackWSpatialTS

### Output structure

Results land in `{results_dir}/sub-<id>/task-<name>/`:

```
derivatives/lev1/
└── sub-s03/
    └── task-flanker/
        ├── fixed_effects/        # Subject-level fixed-effects maps (.nii.gz or .func.gii)
        ├── indiv_contrasts/      # Per-run contrast estimates
        ├── task_residuals/       # Task-regressed residuals (if --residuals)
        ├── quality_control/      # VIF plots, design matrix figures
        ├── masks/                # Combined brain masks (volumetric only)
        └── simplified_events/    # Preprocessed event files
```

### Exclusions format

`--exclusions-file` accepts two formats interchangeably:

**neuro_workflow compiled format** (recommended — generated by `neuro-run exclusions compile`):
```json
[
  {"subject": "sub-s03", "session": "ses-01", "task": "task-flanker", "run": "run-1",
   "action": "exclude", "source": "motion", "reason": "FD > 0.2 in >20% of TRs"}
]
```

**Legacy keyed-dict format** (from `network_glm/data/exclusions.json`):
```json
{
  "fmriprep_exclusions": [
    {"subject": "sub-s03", "session": "ses-01", "task": "task-flanker", "run": "run-1"}
  ],
  "behavioral_exclusions": [
    {"subject": "sub-s03", "session": "ses-01", "task": "task-flanker", "run": "run-1",
     "metrics": {"total_rows": 100, "rows_to_keep": 20}}
  ]
}
```

Both formats produce identical exclusion behavior. The format is detected automatically.

## QA Commands

QA commands analyze preprocessed data. Most require QA extras: `uv pip install -e ".[qa]"`.

```bash
neuro-run qa <command> <dataset> [flags]
```

| Command | Description |
|---------|-------------|
| `neg-events` | Report event files with non-monotonic onsets |
| `breaks` | Analyze behavioral data for performance feedback at breaks |
| `global-signal` | Plot global signal from echo-2 BOLD data |
| `outlier-report` | VIF + outlier analysis with figures and summary CSVs |
| `reliability` | Create MP4 movies showing fMRI reliability across sessions |

### Examples

```bash
# Check for non-monotonic event file onsets
neuro-run qa neg-events discovery

# Analyze behavioral breaks data
neuro-run qa breaks discovery \
  --behavioral-dir /oak/.../behavioral \
  --output-dir /oak/.../qa_results

# Global signal plots
neuro-run qa global-signal discovery --output-dir /tmp/gs_figs

# Outlier report
neuro-run qa outlier-report discovery \
  --lev1-dirs /oak/.../lev1_discovery /oak/.../lev1_validation \
  --exclusions-file /oak/.../exclusions.json \
  --output-dir /tmp/outlier_report

# Reliability movies
neuro-run qa reliability discovery \
  --fmriprep-version 24.1.0rc2 \
  --output-dir /tmp/reliability_movies
```

## Exclusions Management

The exclusions module tracks which scans to exclude or trim, organized by source (motion, neg-events, behavioral) with manual override support.

```bash
# Generate exclusions from a source
neuro-run exclusions generate motion discovery \
  --fmriprep-version 24.1.0rc2 \
  --fd-threshold 0.2

neuro-run exclusions generate neg-events discovery

# Compile all sources + overrides into a final list
neuro-run exclusions compile discovery

# Show exclusion summary
neuro-run exclusions show discovery

# Import an external exclusion list
neuro-run exclusions import behavioral discovery \
  --input-file /path/to/behavioral_exclusions.json
```

**Storage:** All exclusion data is stored in `~/.neuro_workflow/exclusions/<dataset>/`:
- `sources/motion.json` — motion exclusions
- `sources/neg_events.json` — neg-events trim/exclude entries
- `overrides.json` — manual force-include / force-exclude entries
- `compiled_exclusions.json` — final compiled list

**Override file format** (edit `~/.neuro_workflow/exclusions/<dataset>/overrides.json`):
```json
[
  {
    "subject": "sub-s05",
    "session": "ses-01",
    "task": "task-rest",
    "run": "run-1",
    "action": "force-include",
    "reason": "Borderline but acceptable after visual QC"
  }
]
```

## How It Works

### Subjects File

A plain text file with one subject ID per line (no `sub-` prefix):

```
s03
s10
s19
```

Each line becomes one SLURM array task.

### Config File

All dataset configs are stored in `~/.neuro_workflow/datasets.json`:

```json
{
  "discovery": {
    "bids_dir": "/oak/.../discovery_BIDS_20250402",
    "subjects_file": "/home/users/logben/neuro_workflow/subs_discovery.txt",
    "partition": "russpold",
    "mail_user": "logben@stanford.edu",
    "image_dir": "/home/groups/russpold/singularity_images",
    "templateflow_dir": "/home/groups/russpold/templateflow"
  }
}
```

### Derived Paths

| Path | Value |
|------|-------|
| Image | `{image_dir}/{pipeline}_{version}.sif` |
| Derivatives | `{bids_dir}/derivatives/{pipeline}_{version}` |
| Work dir | `$SCRATCH/work/{pipeline}_{dataset_name}_{version}` |
| Logs | `{bids_dir}/derivatives/{pipeline}_{version}/logs/` |

## Package Structure

This repo uses a two-package `src/` layout: `neuro_workflow` is the CLI and orchestration layer; `network_lev1` is the analysis library it calls.

```
neuro_workflow/
├── pyproject.toml
├── src/
│   ├── neuro_workflow/           # CLI + submission layer
│   │   ├── core/
│   │   │   ├── config.py         # ~/.neuro_workflow/datasets.json management
│   │   │   ├── exclusions.py     # scan exclusion schema, compile, query API
│   │   │   ├── image.py          # apptainer image existence check and pull
│   │   │   └── slurm.py          # sbatch template rendering and job submission
│   │   ├── exclusions/
│   │   │   ├── base.py           # ExclusionGenerator protocol and registry
│   │   │   ├── behavioral.py     # behavioral exclusion stub
│   │   │   ├── motion.py         # motion exclusions from fmriprep confounds
│   │   │   └── neg_events.py     # neg-events exclusions from event file onsets
│   │   ├── pipelines/
│   │   │   ├── base.py           # Pipeline protocol and registry
│   │   │   ├── fmriprep.py
│   │   │   ├── fsqc.py
│   │   │   ├── freesurfer.py     # (deprecated)
│   │   │   ├── happy.py
│   │   │   ├── lev1.py           # first-level GLM pipeline
│   │   │   ├── lev2.py           # second-level GLM pipeline
│   │   │   ├── mshbm.py          # precision network parcellation
│   │   │   ├── prep_mshbm.py     # MSHBM surface input prep
│   │   │   └── qsiprep.py
│   │   ├── qa/
│   │   │   ├── base.py           # QaCommand protocol and registry
│   │   │   ├── breaks.py
│   │   │   ├── fieldmap_check.py
│   │   │   ├── global_signal.py
│   │   │   ├── neg_events.py
│   │   │   ├── outlier_report.py
│   │   │   └── reliability.py
│   │   ├── templates/
│   │   │   ├── fmriprep.sbatch
│   │   │   ├── fsqc.sbatch
│   │   │   ├── freesurfer.sbatch
│   │   │   ├── happy.sbatch
│   │   │   ├── lev1.sbatch
│   │   │   ├── lev2.sbatch
│   │   │   ├── mshbm.sbatch
│   │   │   ├── prep_mshbm.sbatch
│   │   │   └── qsiprep.sbatch
│   │   └── cli.py
│   └── network_lev1/             # GLM analysis library
│       ├── config.py
│       ├── core/                 # utils, task_utils
│       ├── io/                   # file_discovery
│       ├── processing/           # design, glm, contrasts, fixed_effects, residuals, …
│       ├── task_config/          # per-task YAML configs + loader
│       ├── run_lev1.py           # entry point → network-lev1
│       ├── run_lev2.py           # entry point → network-lev2
│       └── prepare_mshbm_inputs.py  # entry point → network-prep-mshbm
└── tests/
    ├── test_cli.py
    └── lev1/                     # network_lev1 test suite
```

## Running Tests

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run pytest tests/ -v
```
