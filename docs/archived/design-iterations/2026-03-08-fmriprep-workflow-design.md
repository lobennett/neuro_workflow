# Design: fmriprep-workflow

A zero-dependency Python package for submitting fMRIPrep SLURM array jobs from anywhere.

## Problem

Running fMRIPrep across datasets (discovery, validation) requires manually editing sbatch scripts, environment files, and subjects lists. The current approach works but is brittle: paths are scattered across files, flags are embedded in scripts, and adding a new dataset means copying and editing multiple files.

## Solution

A `fmriprep-run` CLI backed by per-dataset JSON configuration. Register a dataset once, then submit jobs with a single command.

```bash
fmriprep-run add-dataset discovery \
  --bids-dir /oak/.../discovery_BIDS_20250402 \
  --subjects-file /home/users/logben/freesurfer/subs_discovery.txt \
  --fmriprep-version 24.1.0rc2 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels"

fmriprep-run submit discovery
```

## Package Structure

```
fmriprep-workflow/
├── pyproject.toml
├── src/fmriprep_workflow/
│   ├── __init__.py
│   ├── cli.py                  # argparse subcommands
│   ├── config.py               # ~/.fmriprep_workflow/ management
│   ├── image.py                # apptainer pull logic
│   ├── submit.py               # sbatch generation + submission
│   └── templates/
│       └── fmriprep.sbatch     # sbatch template with placeholders
```

Managed with `uv` (`module load uv && uv pip install -e .`). No external dependencies — pure stdlib.

## CLI Commands

### `fmriprep-run add-dataset <name>`

Registers a dataset in `~/.fmriprep_workflow/datasets.json`.

**Required arguments:**
- `--bids-dir` — path to BIDS directory
- `--subjects-file` — path to text file with one subject ID per line
- `--fmriprep-version` — fMRIPrep version tag (e.g., `24.1.0rc2`)

**Optional arguments (with defaults):**
- `--output-spaces` — fMRIPrep output spaces string
- `--fmriprep-args` — additional fMRIPrep flags as a single string
- `--partition` — SLURM partition (default: `russpold`)
- `--nthreads` — CPUs per task (default: `8`)
- `--mem-per-cpu-gb` — memory per CPU in GB (default: `8`)
- `--time` — SLURM time limit (default: `5-00:00:00`)
- `--image-dir` — where SIF images live (default: `/home/groups/russpold/singularity_images`)
- `--templateflow-dir` — templateflow bind path (default: `/home/groups/russpold/templateflow`)
- `--fs-license` — FreeSurfer license file (default: `~/license.txt`)
- `--bids-filter-file` — optional BIDS filter JSON
- `--mail-user` — email for SLURM notifications

Creates `~/.fmriprep_workflow/` and `datasets.json` if they don't exist. Overwrites an existing dataset entry with a warning. Warns (but does not block) if `--bids-dir` or `--subjects-file` paths don't exist, since filesystems may not be mounted.

### `fmriprep-run submit <name>`

1. Reads dataset config from JSON
2. Counts lines in subjects file to set `--array=1-N`
3. Checks if `{image_dir}/fmriprep_{version}.sif` exists; pulls with `apptainer pull` if missing
4. Renders the sbatch template with all values
5. Writes rendered script to a temp file and runs `sbatch`
6. Prints the SLURM job ID

### `fmriprep-run show <name>`

Prints the rendered sbatch script without submitting. Useful for review.

### `fmriprep-run show --list`

Lists all registered datasets with their BIDS directories.

## Dataset JSON Format

Stored at `~/.fmriprep_workflow/datasets.json`:

```json
{
  "discovery": {
    "bids_dir": "/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402",
    "subjects_file": "/home/users/logben/freesurfer/subs_discovery.txt",
    "fmriprep_version": "24.1.0rc2",
    "output_spaces": "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat",
    "fmriprep_args": "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels",
    "partition": "russpold",
    "nthreads": 8,
    "mem_per_cpu_gb": 8,
    "time": "5-00:00:00",
    "image_dir": "/home/groups/russpold/singularity_images",
    "templateflow_dir": "/home/groups/russpold/templateflow",
    "fs_license": "~/license.txt",
    "bids_filter_file": null,
    "mail_user": null
  }
}
```

**Defaults** are baked into `config.py`:

```python
DEFAULTS = {
    "partition": "russpold",
    "nthreads": 8,
    "mem_per_cpu_gb": 8,
    "time": "5-00:00:00",
    "image_dir": "/home/groups/russpold/singularity_images",
    "templateflow_dir": "/home/groups/russpold/templateflow",
    "fs_license": "~/license.txt",
    "bids_filter_file": None,
    "mail_user": None,
}
```

When reading a dataset config, missing optional fields are filled from defaults.

## sbatch Template

Located at `src/fmriprep_workflow/templates/fmriprep.sbatch`. A real bash script with `{placeholders}` filled by `str.format()`:

```bash
#!/bin/bash
#SBATCH -J fmriprep_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
#SBATCH --mail-user={mail_user}
#SBATCH --mail-type=ALL

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file})

FMRIPREP_IMG="{image_path}"

apptainer run --cleanenv \
  -B {bids_dir}:/data \
  -B {templateflow_dir}:/templateflow \
  -B {work_dir}:/work \
  -B {config_bind}:/config \
  "$FMRIPREP_IMG" \
  /data {derivs_dir} participant \
  --participant-label "$subject" \
  -w /work \
  --nthreads {nthreads} \
  --mem_mb {mem_mb} \
  --output-spaces {output_spaces} \
  --fs-license-file {fs_license_container} \
  {bids_filter_arg} \
  {fmriprep_args} \
  --verbose

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
```

## Derived Paths

Computed at submit time, not stored in config:

| Path | Value |
|------|-------|
| `image_path` | `{image_dir}/fmriprep_{version}.sif` |
| `derivs_dir` | `{bids_dir}/derivatives/fmriprep_{version}` |
| `work_dir` | `$SCRATCH/work/fmriprep_{dataset_name}_{version}` |
| `log_dir` | `{bids_dir}/derivatives/fmriprep_{version}/logs` |
| `mem_mb` | `nthreads * mem_per_cpu_gb * 1000 * 0.9` (90% buffer) |
| `fs_license_container` | Resolved from `fs_license` with `~` expanded |
| `config_bind` | Directory containing `bids_filter_file` if set |
| `bids_filter_arg` | `--bids-filter-file /config/{filename}` if set, empty string otherwise |

## Image Pull Logic

In `image.py`:

1. Compute expected path: `{image_dir}/fmriprep_{version}.sif`
2. If file exists, return path
3. If not, run: `apptainer pull {path} docker://nipreps/fmriprep:{version}`
4. Exit with error if pull fails

This runs at `submit` time, before sbatch generation.

## Setup

```bash
module load uv
cd /path/to/fmriprep-workflow
uv pip install -e .
```

Then from anywhere:

```bash
# Register datasets
fmriprep-run add-dataset discovery \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402 \
  --subjects-file /home/users/logben/freesurfer/subs_discovery.txt \
  --fmriprep-version 24.1.0rc2 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels"

fmriprep-run add-dataset validation \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/validation_BIDS \
  --subjects-file /home/users/logben/freesurfer/subs_validation.txt \
  --fmriprep-version 24.1.0rc2 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels"

# Preview
fmriprep-run show discovery

# Submit
fmriprep-run submit discovery
```
