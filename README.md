# neuro-workflow

A zero-dependency Python CLI for submitting neuroimaging pipeline SLURM array jobs. Register a dataset once, then submit parallel jobs for any supported pipeline with a single command.

## Installation

```bash
module load uv
cd /home/users/logben/fmriprep-workflow
uv pip install -e .
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

Registers a dataset in `~/.fmriprep_workflow/datasets.json`. If the dataset name already exists, it is overwritten. Dataset registration is pipeline-agnostic -- it only stores shared configuration. Pipeline-specific options (version, output spaces, extra flags) are passed at submit time.

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

### `neuro-run show <pipeline> <name> --version <ver>`

Renders the sbatch script for a dataset and pipeline, then prints it to stdout. Use this to review what will be submitted before running `submit`.

```bash
neuro-run show fmriprep discovery --version 25.2.4
```

### `neuro-run show --list`

Lists all registered datasets and their BIDS directories.

### `neuro-run submit <pipeline> <name> --version <ver> [pipeline-specific flags]`

Submits a SLURM array job for the named dataset and pipeline:

1. Reads the dataset config from `~/.fmriprep_workflow/datasets.json`
2. Counts subjects in the subjects file to set `--array=1-N`
3. Checks if the pipeline image exists at `{image_dir}/{pipeline}_{version}.sif`; if not, pulls it with `apptainer pull`
4. Renders the sbatch template with all config values and pipeline-specific flags
5. Writes the script to a temp file and submits with `sbatch`

Example:

```bash
neuro-run submit fmriprep discovery --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos"
```

## How It Works

### Subjects File

A plain text file with one subject ID per line (no `sub-` prefix):

```
s03
s10
s19
s29
s43
```

Each line becomes one SLURM array task. The array index maps to the line number.

### Config File

All dataset configs are stored in `~/.fmriprep_workflow/datasets.json`. You can edit this file directly or use `add-dataset` to manage it. The config is pipeline-agnostic:

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

Pipeline-specific options (version, output spaces, extra flags) are supplied at `submit` or `show` time rather than stored in the config.

### Derived Paths

These are computed automatically at submit time:

| Path | Value |
|------|-------|
| Image | `{image_dir}/{pipeline}_{version}.sif` |
| Derivatives | `{bids_dir}/derivatives/{pipeline}_{version}` |
| Work dir | `$SCRATCH/work/{pipeline}_{dataset_name}_{version}` |
| Logs | `{bids_dir}/derivatives/{pipeline}_{version}/logs/` |

### Image Pulling

If the SIF image doesn't exist at the expected path, `submit` automatically pulls it:

```
apptainer pull {image_dir}/{pipeline}_{version}.sif docker://nipreps/{pipeline}:{version}
```

### Adding a New Dataset

To register a new BIDS directory:

```bash
neuro-run add-dataset my_new_study \
  --bids-dir /oak/stanford/groups/russpold/data/my_new_study_BIDS \
  --subjects-file /path/to/my_subjects.txt \
  --mail-user logben@stanford.edu
```

Then submit with any supported pipeline:

```bash
neuro-run submit fmriprep my_new_study --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation"
```

## Extensible Pipeline Architecture

neuro-workflow is designed to support multiple neuroimaging pipelines. Each pipeline is a module under `src/neuro_workflow/pipelines/` that defines its own CLI flags, sbatch template, and image source. Currently supported:

- **fmriprep** -- functional MRI preprocessing via [fMRIPrep](https://fmriprep.org)

Planned pipelines include mriqc, qsiprep, and fsqc. Adding a new pipeline requires creating a pipeline module that inherits from the base pipeline class and providing an sbatch template.

## Package Structure

```
fmriprep-workflow/
├── pyproject.toml
├── src/neuro_workflow/
│   ├── core/
│   │   ├── config.py        # ~/.fmriprep_workflow/datasets.json management
│   │   ├── image.py         # apptainer image existence check and pull
│   │   └── slurm.py         # sbatch template rendering and job submission
│   ├── pipelines/
│   │   ├── base.py          # base pipeline class
│   │   └── fmriprep.py      # fMRIPrep pipeline definition and CLI flags
│   ├── templates/
│   │   └── fmriprep.sbatch  # SLURM sbatch template with placeholders
│   └── cli.py               # argparse entry point (add-dataset, show, submit)
└── tests/
    ├── test_cli.py
    ├── test_config.py
    ├── test_image.py
    └── test_submit.py
```

## Running Tests

```bash
cd /home/users/logben/fmriprep-workflow
module load uv
uv run pytest tests/ -v
```
