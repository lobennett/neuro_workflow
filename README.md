# fmriprep-workflow

A zero-dependency Python CLI for submitting fMRIPrep SLURM array jobs. Register a dataset once, then submit parallel jobs with a single command.

## Installation

```bash
module load uv
cd /home/users/logben/freesurfer/fmriprep-workflow
uv pip install -e .
```

After installation, `fmriprep-run` is available from anywhere (as long as the venv is active or you use the full path `.venv/bin/fmriprep-run`).

## Quick Start

```bash
# 1. Register a dataset
fmriprep-run add-dataset discovery \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402 \
  --subjects-file /home/users/logben/freesurfer/subs_discovery.txt \
  --fmriprep-version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels" \
  --mail-user logben@stanford.edu

# 2. Preview the generated sbatch script
fmriprep-run show discovery

# 3. Submit the job to SLURM
fmriprep-run submit discovery
```

## Commands

### `fmriprep-run add-dataset <name>`

Registers a dataset in `~/.fmriprep_workflow/datasets.json`. If the dataset name already exists, it is overwritten.

**Required arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Dataset name (positional, e.g., `discovery`, `validation`) |
| `--bids-dir` | Path to BIDS directory |
| `--subjects-file` | Path to text file with one subject ID per line |
| `--fmriprep-version` | fMRIPrep version tag (e.g., `25.2.4`) |

**Optional arguments (with defaults):**

| Argument | Default | Description |
|----------|---------|-------------|
| `--output-spaces` | _(none)_ | fMRIPrep output spaces |
| `--fmriprep-args` | _(none)_ | Additional fMRIPrep flags as a single string |
| `--partition` | `russpold` | SLURM partition |
| `--nthreads` | `8` | CPUs per task |
| `--mem-per-cpu-gb` | `8` | Memory per CPU in GB |
| `--time` | `5-00:00:00` | SLURM time limit |
| `--image-dir` | `/home/groups/russpold/singularity_images` | Directory for SIF images |
| `--templateflow-dir` | `/home/groups/russpold/templateflow` | TemplateFlow directory |
| `--fs-license` | `~/license.txt` | FreeSurfer license file |
| `--bids-filter-file` | _(none)_ | BIDS filter JSON file |
| `--mail-user` | _(none)_ | Email for SLURM notifications |

### `fmriprep-run show <name>`

Renders the sbatch script for a dataset and prints it to stdout. Use this to review what will be submitted before running `submit`.

### `fmriprep-run show --list`

Lists all registered datasets and their BIDS directories.

### `fmriprep-run submit <name>`

Submits an fMRIPrep SLURM array job for the named dataset:

1. Reads the dataset config from `~/.fmriprep_workflow/datasets.json`
2. Counts subjects in the subjects file to set `--array=1-N`
3. Checks if the fMRIPrep image exists at `{image_dir}/fmriprep_{version}.sif`; if not, pulls it with `apptainer pull ... docker://nipreps/fmriprep:{version}`
4. Renders the sbatch template with all config values
5. Writes the script to a temp file and submits with `sbatch`

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

All dataset configs are stored in `~/.fmriprep_workflow/datasets.json`. You can edit this file directly or use `add-dataset` to manage it. Example:

```json
{
  "discovery": {
    "bids_dir": "/oak/.../discovery_BIDS_20250402",
    "subjects_file": "/home/users/logben/freesurfer/subs_discovery.txt",
    "fmriprep_version": "25.2.4",
    "output_spaces": "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat",
    "fmriprep_args": "--no-submm-recon --skip-bids-validation ...",
    "mail_user": "logben@stanford.edu"
  }
}
```

Any optional fields you omit are filled from defaults at runtime (see the defaults table above).

### Derived Paths

These are computed automatically at submit time:

| Path | Value |
|------|-------|
| Image | `{image_dir}/fmriprep_{version}.sif` |
| Derivatives | `{bids_dir}/derivatives/fmriprep_{version}` |
| Work dir | `$SCRATCH/work/fmriprep_{dataset_name}_{version}` |
| Logs | `{bids_dir}/derivatives/fmriprep_{version}/logs/` |
| Memory (MB) | `nthreads * mem_per_cpu_gb * 1000 * 0.9` (90% buffer below SLURM limit) |

### Image Pulling

If the SIF image doesn't exist at the expected path, `submit` automatically pulls it:

```
apptainer pull /home/groups/russpold/singularity_images/fmriprep_{version}.sif docker://nipreps/fmriprep:{version}
```

### Adding a New Dataset

To adapt this to a new BIDS directory with the same processing flags:

```bash
fmriprep-run add-dataset my_new_study \
  --bids-dir /oak/stanford/groups/russpold/data/my_new_study_BIDS \
  --subjects-file /path/to/my_subjects.txt \
  --fmriprep-version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels" \
  --mail-user logben@stanford.edu
```

Then `fmriprep-run submit my_new_study`.

## Package Structure

```
fmriprep-workflow/
├── pyproject.toml
├── src/fmriprep_workflow/
│   ├── cli.py           # argparse entry point (add-dataset, show, submit)
│   ├── config.py         # ~/.fmriprep_workflow/datasets.json management
│   ├── image.py          # apptainer image existence check and pull
│   ├── submit.py         # sbatch template rendering and job submission
│   └── templates/
│       └── fmriprep.sbatch  # SLURM sbatch template with placeholders
└── tests/
    ├── test_cli.py
    ├── test_config.py
    ├── test_image.py
    └── test_submit.py
```

## Running Tests

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
module load uv
uv run pytest tests/ -v
```
