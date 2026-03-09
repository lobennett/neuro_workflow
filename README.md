# neuro-workflow

A zero-dependency Python CLI for submitting neuroimaging pipeline SLURM array jobs. Register a dataset once, then submit parallel jobs for any supported pipeline with a single command.

## Installation

```bash
module load uv
cd /home/users/logben/fmriprep-workflow
uv pip install -e .
```

For QA commands that require nilearn, nibabel, matplotlib, pandas, numpy, seaborn, and img2pdf:

```bash
uv pip install -e ".[qa]"
```

After installation, `neuro-run` is available from anywhere (as long as the venv is active or you use the full path `.venv/bin/neuro-run`).

## Quick Start

```bash
# 1. Register a dataset (pipeline-agnostic)
neuro-run add-dataset discovery \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402 \
  --subjects-file /home/users/logben/fmriprep-workflow/subs_discovery.txt \
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
    "subjects_file": "/home/users/logben/fmriprep-workflow/subs_discovery.txt",
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

```
fmriprep-workflow/
├── pyproject.toml
├── src/neuro_workflow/
│   ├── core/
│   │   ├── config.py         # ~/.neuro_workflow/datasets.json management
│   │   ├── exclusions.py     # scan exclusion schema, compile, query API
│   │   ├── image.py          # apptainer image existence check and pull
│   │   └── slurm.py          # sbatch template rendering and job submission
│   ├── exclusions/
│   │   ├── base.py           # ExclusionGenerator protocol and registry
│   │   ├── behavioral.py     # behavioral exclusion stub
│   │   ├── motion.py         # motion exclusions from fmriprep confounds
│   │   └── neg_events.py     # neg-events exclusions from event file onsets
│   ├── pipelines/
│   │   ├── base.py           # Pipeline protocol and registry
│   │   ├── fmriprep.py       # fMRIPrep pipeline
│   │   ├── fsqc.py           # FSQC pipeline
│   │   ├── freesurfer.py     # FreeSurfer pipeline (deprecated)
│   │   ├── happy.py          # Happy/rapidtide pipeline
│   │   └── qsiprep.py        # QSIPrep pipeline
│   ├── qa/
│   │   ├── base.py           # QaCommand protocol and registry
│   │   ├── breaks.py         # behavioral breaks QA
│   │   ├── global_signal.py  # global signal plots
│   │   ├── neg_events.py     # non-monotonic event file detection
│   │   ├── outlier_report.py # VIF + outlier analysis
│   │   └── reliability.py    # fMRI reliability movies
│   ├── templates/
│   │   ├── fmriprep.sbatch
│   │   ├── fsqc.sbatch
│   │   ├── freesurfer.sbatch
│   │   ├── happy.sbatch
│   │   └── qsiprep.sbatch
│   └── cli.py                # argparse entry point
└── tests/
```

## Running Tests

```bash
cd /home/users/logben/fmriprep-workflow
module load uv
uv run pytest tests/ -v
```
