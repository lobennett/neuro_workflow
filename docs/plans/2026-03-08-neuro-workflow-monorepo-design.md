# Design: neuro-workflow Monorepo

## Problem

Running neuroimaging pipelines (fMRIPrep, MRIQC, QSIPrep, FreeSurfer QC) on a SLURM cluster requires duplicated boilerplate across many standalone scripts and repos. BIDS paths, subject lists, SLURM configs, container image management, and file discovery are reimplemented in each project. QA scripts, lineage tracking (poldrackwrap), and GLM analysis (network_glm) all need the same BIDS directory information but have no shared infrastructure.

## Decision

Expand the existing `fmriprep-workflow` into a **monorepo** (`neuro-workflow`) with a shared core and pipeline-specific plugins. GLM analysis stays in its own repo but imports the BIDS discovery module.

### Why monorepo over shared library + separate repos

- On HPC (Sherlock), managing multiple packages with version dependencies via editable installs is painful.
- The shared concerns (BIDS paths, SLURM submission, image pulling) are tightly coupled in practice.
- A single `uv pip install -e .` gives access to everything.

## Package Structure

```
neuro-workflow/
├── pyproject.toml
├── src/neuro_workflow/
│   ├── __init__.py
│   ├── cli.py                    # Unified CLI entry point (neuro-run)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Dataset registry (~/.neuro_workflow/datasets.json)
│   │   ├── slurm.py              # Template rendering + sbatch submission
│   │   ├── image.py              # Apptainer image check + pull
│   │   ├── bids.py               # BIDS file discovery utilities
│   │   └── lineage.py            # Optional JSON sidecar job tracking
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── base.py               # Pipeline protocol
│   │   ├── fmriprep.py           # fMRIPrep pipeline definition
│   │   ├── mriqc.py              # MRIQC pipeline definition
│   │   ├── qsiprep.py            # QSIPrep pipeline definition
│   │   └── fsqc.py               # FreeSurfer QC pipeline definition
│   ├── qa/                       # QA scripts (figures, checks)
│   │   └── __init__.py
│   └── templates/
│       ├── fmriprep.sbatch
│       ├── mriqc.sbatch
│       ├── qsiprep.sbatch
│       └── fsqc.sbatch
├── tests/
│   ├── test_config.py
│   ├── test_slurm.py
│   ├── test_image.py
│   ├── test_bids.py
│   └── pipelines/
│       └── test_fmriprep.py
└── docs/
```

## CLI Design

```bash
# Register a dataset (pipeline-agnostic)
neuro-run add-dataset discovery \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402 \
  --subjects-file subs_discovery.txt

# Submit a pipeline against a dataset
neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation"

# Submit a different pipeline against the same dataset
neuro-run submit mriqc discovery --version 24.1.0

# Preview the generated sbatch script
neuro-run show fmriprep discovery --version 25.2.4

# List registered datasets
neuro-run show --list

# Run QA
neuro-run qa motion-plots discovery --pipeline fmriprep --version 25.2.4
```

## Dataset Configuration

Stored at `~/.neuro_workflow/datasets.json`. Contains only dataset-level concerns:

```json
{
  "discovery": {
    "bids_dir": "/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402",
    "subjects_file": "/home/users/logben/neuro-workflow/subs_discovery.txt",
    "partition": "russpold",
    "mail_user": "logben@stanford.edu"
  }
}
```

Pipeline-specific flags (version, output spaces, extra args) are passed at submit time, not stored in the dataset config. SLURM resource defaults (nthreads, memory, time) live in each pipeline module and can be overridden at submit time.

## Pipeline Plugin Pattern

Each pipeline implements a protocol:

```python
class Pipeline(Protocol):
    name: str                    # "fmriprep", "mriqc", etc.
    docker_uri: str              # "docker://nipreps/fmriprep"
    template_name: str           # "fmriprep.sbatch"
    default_resources: dict      # {"nthreads": 8, "mem_per_cpu_gb": 8, "time": "5-00:00:00"}

    def add_cli_args(self, parser: ArgumentParser) -> None:
        """Add pipeline-specific args to the submit subcommand."""

    def build_context(self, dataset_config: dict, args: Namespace) -> dict:
        """Build the template context dict from dataset config + CLI args."""
```

Adding a new pipeline requires:
1. Write `pipelines/newpipeline.py` implementing the protocol
2. Write `templates/newpipeline.sbatch` with placeholders
3. Register it in the pipeline registry (dict mapping name to class)

No changes to core code or CLI plumbing needed.

## Core Modules

### `core/config.py`

Dataset registry management. Functions: `save_dataset()`, `get_dataset()`, `load_datasets()`. Stores defaults for shared SLURM settings (partition, image directory, templateflow directory).

### `core/slurm.py`

Generalized template rendering and sbatch submission. Takes a template path + context dict, renders with `str.format()`, writes to temp file, runs `sbatch`. Used by all pipelines.

### `core/image.py`

Apptainer image management. Takes a Docker URI + version, checks for SIF at `{image_dir}/{name}_{version}.sif`, pulls if missing. Parameterized for any container, not just fMRIPrep.

### `core/bids.py`

BIDS file discovery utilities. High-value shared module:

- `find_bold_files(bids_dir, subject, session, task, space, extension)`
- `find_echo_files(bids_dir, subject, session, task)` — multi-echo discovery
- `find_confounds(derivatives_dir, subject, session, task)`
- `find_masks(derivatives_dir, subject, session, task, space)`
- `count_subjects(subjects_file)` / `load_subjects(subjects_file)`

This replaces ad-hoc file discovery across scattered scripts. `network_glm` can import this module directly.

### `core/lineage.py`

Optional job tracking via JSON sidecars. When `--track` is passed to `submit`, writes a JSON file to `{derivatives}/logs/{subject}_{pipeline}_{job_id}.json` with timestamps, exit codes, and SLURM metadata. Zero dependencies. MongoDB backend can be added later as an optional feature (replaces poldrackwrap).

## QA Scripts

Live in `neuro_workflow/qa/`. Invoked via `neuro-run qa <script-name> <dataset>`. Use dataset config for BIDS paths and `core/bids.py` for file discovery. Outputs go to `{bids_dir}/derivatives/{pipeline}_{version}/qa/`.

## GLM Relationship

`network_glm` stays in its own repo. It adds `neuro-workflow` as a dependency to import `neuro_workflow.core.bids` for file discovery. It can also read `~/.neuro_workflow/datasets.json` for BIDS directory paths. The GLM repo may adopt the same dataset configuration pattern independently.

## Dependencies

- **Core**: Zero external dependencies (stdlib only)
- **QA module**: Optional deps — nibabel, matplotlib (declared as extras in pyproject.toml)
- **Python**: >=3.9

## Migration Phases

### Phase 1: Rename + restructure

- Rename `fmriprep_workflow` to `neuro_workflow`
- Move existing code into `core/` (config, image, slurm)
- Extract fMRIPrep-specific logic into `pipelines/fmriprep.py`
- CLI becomes `neuro-run` with `submit fmriprep` syntax
- All existing tests continue to pass

### Phase 2: Add BIDS discovery

- Build `core/bids.py` with tested file discovery functions
- Port file discovery logic from `network_glm` into this module

### Phase 3: Add pipelines

- Add mriqc, qsiprep, fsqc pipeline modules + templates
- Port scattered standalone scripts

### Phase 4: QA scripts

- Move QA/figure scripts into `qa/` module
- Wire up `neuro-run qa` subcommand

### Phase 5: Lineage (optional)

- Add JSON sidecar tracking in `core/lineage.py`
- Deprecate poldrackwrap

Each phase is independently shippable.
