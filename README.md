# neuro-workflow

CLI for managing the full neuroimaging pipeline from raw data to statistical analysis, orchestrated through SLURM array jobs.

## Installation

```bash
module load uv
cd /home/users/logben/neuro_workflow
uv sync
```

Install optional dependency groups as needed:

```bash
uv pip install -e ".[bidsify]"   # Flywheel BIDSify
uv pip install -e ".[events]"    # Behavioral events pipeline
uv pip install -e ".[qa]"        # QA commands (nilearn, matplotlib, etc.)
uv pip install -e ".[lev1,qa]"   # First-level GLM analysis
uv pip install -e ".[all]"       # Everything above (lev1+qa+bidsify+events)
```

The bare `uv sync` install runs `show`/`add-dataset`/`submit` for dataset
registration, but `submit lev1/lev2/mshbm`, the `qa` subcommands, and
`python -m neuro_workflow.analysis.*` need the corresponding extra (or `[all]`).

After installation, use `uv run neuro-run` from the project directory, or `module load uv && neuro-run` if the venv is on your PATH.

## Documentation

This README is a summary; for the full picture start with
[`docs/PIPELINE-WALKTHROUGH.md`](docs/PIPELINE-WALKTHROUGH.md) (how to run a stage,
end to end) and [`docs/RUNBOOK.md`](docs/RUNBOOK.md) (how each SLURM job is launched).

| Doc | Purpose |
|-----|---------|
| [`docs/PIPELINE-WALKTHROUGH.md`](docs/PIPELINE-WALKTHROUGH.md) | Full ordered recipe, Flywheel → second-level models, with a quick-reference command list |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operational reference for launching each SLURM stage (partitions, resources, binds) |
| [`docs/PROVENANCE-AND-EXCLUSIONS.md`](docs/PROVENANCE-AND-EXCLUSIONS.md) | The exclusion framework (5 sources, compilation, lockfile, drift gate), run-manifest schema, clean-tree policy |
| [`docs/CONFIG.md`](docs/CONFIG.md) | `thresholds.yaml` and `battery.yaml` schema and usage |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Package structure and module reference |
| [`docs/DATASETS.md`](docs/DATASETS.md) | Orientation to the cohorts, task battery, and per-subject data budget |
| [`docs/SCAN-NOTES.md`](docs/SCAN-NOTES.md) | Raw data collection notes per subject (excluded/incomplete sessions) |
| [`docs/REFERENCES.md`](docs/REFERENCES.md) | Source papers referenced by the analysis (not committed; obtain from publisher) |

MSHBM parcellation, prevalence analysis, parcellation reliability, and XCP-D
denoising live in the separate [`network_analysis`](https://github.com/lobennett/network_analysis)
repository.

## Pipeline Progression

The workflow moves data through these stages:

```
1. BIDSify         Raw Flywheel data → BIDS dataset
2. Events          Behavioral CSVs → BIDS _events.tsv + behavioral QC + exclusions
3. Preprocessing   fMRIPrep, QSIPrep, FreeSurfer, happy
4. QA              Derivative quality checks (global signal, fieldmaps, reliability)
5. Exclusions      Compile motion + behavioral + manual exclusions
6. Analysis        First-level GLM → Second-level group stats → MSHBM parcellation
```

Each stage is described below in order.

---

## Stage 1: BIDSify

Pull NIfTI/JSON data from Flywheel and write a clean BIDS dataset. Processes subjects sequentially, handling subject label aliases, multi-echo BOLD selection, sequential session numbering, duplicate scan run-numbering, fieldmap sidecar patching, and physiological data download (cardiac/respiratory from gephysio gear).

### Prerequisites

- Flywheel API key configured (`~/.config/flywheel/user.json` or `FW_API_KEY`)
- `uv pip install -e ".[bidsify]"`

### Usage

Three samples are defined in `config/pipeline_config.json`: **discovery** (5 subjects), **validation** (41 subjects), and **excluded** (11 subjects).

```bash
# Submit BIDSify jobs (one per sample)
uv run neuro-run submit bidsify discovery \
  --output-dir /scratch/users/logben/discovery_BIDS --overwrite

uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_BIDS --overwrite

uv run neuro-run submit bidsify excluded \
  --output-dir /scratch/users/logben/excluded_BIDS --overwrite

# Pull specific subjects only
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/.../validation_BIDS --subjects s76 s247 --overwrite

# Run directly without SLURM (debugging)
uv run neuro-run bidsify discovery --output-dir /scratch/users/logben/discovery_BIDS
```

### Output

```
discovery_BIDS/
├── dataset_description.json
├── sub-s03/
│   ├── ses-01/
│   │   ├── anat/     # T1w, T2w (duplicates get run numbering)
│   │   ├── func/     # multi-echo BOLD + physio (cardiac/respiratory)
│   │   ├── fmap/     # fieldmap + magnitude
│   │   └── dwi/      # DWI + bval/bvec
│   └── ses-02/
├── sub-s10/
└── sourcedata/
    ├── reconciliation.json
    ├── bidsify_log.json
    └── session_timestamps.tsv
```

Physio files are stored in `func/` as:
- `sub-*_ses-*_task-*_recording-cardiac_physio.tsv.gz` + `.json` (cardiac waveform, 100 Hz)
- `sub-*_ses-*_task-*_recording-respiratory_physio.tsv.gz` + `.json` (respiratory waveform, 25 Hz)

Physiological data (gephysio gear outputs) are automatically detected and downloaded from Flywheel session analyses. They are downloaded and converted to BIDS format but not trimmed during bidsify.

### Configuration

- `config/pipeline_config.json` — sample lists, subject aliases, skip lists, Flywheel session overrides
- `src/neuro_workflow/bidsify/config.py` — acquisition label to BIDS mappings
- `config/behavioral_session_mapping.json` — behavioral data session pairing (used by events pipeline)

---

## Stage 2: Behavioral Events

Create BIDS `_events.tsv` files from raw behavioral CSVs, run behavioral QC to flag exclusions, and trim NIfTIs for participants who stopped responding mid-run.

### Prerequisites

- `uv pip install -e ".[events]"`

### Workflow

```
raw_cleaned/                         (original behavioral CSVs)
    | scripts/rename_behavioral_to_sourcedata.py   (one-time migration)
sourcedata/                          (standardized BIDS layout)
    | neuro-run events create
{bids_dir}/.../func/*_events.tsv     (BIDS event files)
    | neuro-run events qc
    |→ exclusions/sources/behavioral-qc.json
    |→ trim_list.json
        | neuro-run events trim
        |→ derivatives/trimmed/      (truncated NIfTIs)
```

### Commands

```bash
# One-time: copy raw CSVs to BIDS sourcedata layout (config-driven)
python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/.../behavioral_data/raw_cleaned \
    --output-dir /scratch/.../discovery_bids/sourcedata/behavioral \
    --sample discovery \
    --dry-run

# Session mappings are defined in config/behavioral_session_mapping.json
# Generated by scripts/generate_behavioral_mapping.py, then hand-corrected

# Create BIDS event files from sourcedata
neuro-run events create discovery --behavioral-dir /oak/.../sourcedata

# Run behavioral QC (generates exclusion entries + trim list)
neuro-run events qc discovery --behavioral-dir /oak/.../sourcedata

# Trim NIfTIs for participants flagged by QC
neuro-run events trim discovery
```

The QC step saves exclusions to `~/.neuro_workflow/exclusions/discovery/sources/behavioral-qc.json` and a trim list to `{bids_dir}/sourcedata/behavioral_qc/trim_list.json`.

### Directory Structure

Behavioral data is organized into three separate locations:

1. **in_scanner_behavior** — Behavioral task data collected during fMRI scanning (discovery/validation subjects only)
   - Source: `scripts/rename_behavioral_to_sourcedata.py`
   - Location: `sourcedata/in_scanner_behavior/sub-XXX/`

2. **out_scanner_behavior** — Behavioral data collected outside scanner (discovery/validation subjects only)
   - Source: `scripts/migrate_archive_behavioral_data.py` (one-time migration)
   - Location: `sourcedata/out_scanner_behavior/sub-XXX/`

3. **survey_data** — Prescan survey responses (discovery/validation subjects only)
   - Source: `scripts/migrate_archive_behavioral_data.py` (one-time migration)
   - Location: `sourcedata/survey_data/sub-XXX/`

4. **mTurk** — Behavioral data from separate mTurk sample (all subjects)
   - Source: `scripts/migrate_archive_behavioral_data.py` (one-time migration)
   - Location: `mTurk/sub-XXX/`

### Known Data Issues

Session-level data issues are documented in `config/behavioral_session_mapping.json` (irreconcilable runs, skipped sessions) and [`docs/SCAN-NOTES.md`](docs/SCAN-NOTES.md) (operator notes for excluded and incomplete subjects).

---

## One-Time Archive Migration

Behavioral data from the archive directory must be migrated once to organize it into the proper structure above. This is done via:

```bash
python scripts/migrate_archive_behavioral_data.py \
    --archive-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data \
    --sourcedata-dir /oak/stanford/groups/russpold/data/network_grant/sourcedata \
    --mturk-dir /oak/stanford/groups/russpold/data/network_grant/mTurk \
    --config config/behavioral_session_mapping.json \
    --dry-run  # optional: preview without copying
```

This script:
- Validates subjects against discovery/validation sample lists
- Normalizes filenames to BIDS camelCase format
- Copies files to appropriate locations
- Generates a report of migration statistics and missing data

---

## Stage 3: Preprocessing

Submit containerized preprocessing pipelines as SLURM array jobs. Each subject gets its own array task.

```bash
# fMRIPrep
neuro-run submit fmriprep discovery --version 25.2.4 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k"

# QSIPrep
neuro-run submit qsiprep discovery --version 1.1.1 \
  --output-resolution 1.5

# happy (cardiac signal extraction)
neuro-run submit happy discovery --version 3.1.8

# FreeSurfer QC
neuro-run submit fsqc discovery --version 2.1.4 \
  --freesurfer-dir /oak/.../derivatives/freesurfer
```

### Supported pipelines

| Pipeline | Description |
|----------|-------------|
| `fmriprep` | fMRI preprocessing |
| `qsiprep` | DWI preprocessing |
| `happy` | Cardiac signal extraction via rapidtide |
| `fsqc` | FreeSurfer quality control |
| `freesurfer` | Cortical reconstruction (deprecated — use fMRIPrep) |

All pipelines pull their Apptainer/Singularity image automatically if not present in `--image-dir`.

---

## Stage 4: QA

Quality checks on preprocessed derivatives. Requires `uv pip install -e ".[qa]"`.

```bash
neuro-run qa <command> <dataset> [flags]
```

| Command | Description |
|---------|-------------|
| `neg-events` | Report event files with non-monotonic onsets |
| `breaks` | Analyze behavioral data for performance feedback breaks |
| `global-signal` | Plot global signal from echo-2 BOLD data |
| `fieldmap-check` | Verify fieldmap/BOLD correspondence |

Cohort lev1 VIF/outlier reporting and reliability movies are produced by the
QA report (`scripts/qa_report.py`, using `neuro_workflow.qa.lev1_outliers` and
`neuro_workflow.qa.reliability_movies`), not by standalone `neuro-run qa`
subcommands.

### Examples

```bash
neuro-run qa neg-events discovery
neuro-run qa global-signal discovery --output-dir /tmp/gs_figs
```

---

## Stage 5: Exclusions

Compile scan-level exclusions from multiple sources before running analysis. Each source generates entries independently; `compile` merges them with manual overrides.

```bash
# Generate motion exclusions from fMRIPrep confounds
neuro-run exclusions generate motion discovery \
  --fmriprep-version 24.1.0rc2 --fd-threshold 0.2

# Generate neg-events exclusions
neuro-run exclusions generate neg-events discovery

# Behavioral exclusions are generated automatically by `events qc` (Stage 2)

# Compile all sources into a single file
neuro-run exclusions compile discovery

# Review
neuro-run exclusions show discovery
```

### Storage

All exclusion data lives in `~/.neuro_workflow/exclusions/<dataset>/`:

| File | Contents |
|------|----------|
| `sources/motion.json` | Motion-based exclusions |
| `sources/neg_events.json` | Neg-events trim/exclude entries |
| `sources/behavioral-qc.json` | Behavioral QC exclusions (from Stage 2) |
| `overrides.json` | Manual force-include / force-exclude entries |
| `compiled_exclusions.json` | Final compiled list used by analysis |

### Manual overrides

Edit `~/.neuro_workflow/exclusions/<dataset>/overrides.json`:

```json
[
  {
    "subject": "sub-s05", "session": "ses-01", "task": "task-rest", "run": "run-1",
    "action": "force-include",
    "reason": "Borderline but acceptable after visual QC"
  }
]
```

---

## Stage 6: Analysis

### First-level GLM (`lev1`)

Runs subject-level GLM for the task battery. Submits a SLURM array job with one task per subject x task combination.

```bash
# Surface space with FC-quality residuals
neuro-run submit lev1 discovery \
  --fmriprep-dir /oak/.../derivatives/fmriprep_24.1.0rc2 \
  --base-tasks --space surface --residuals --fc-confounds

# Volumetric MNI, specific tasks
neuro-run submit lev1 discovery \
  --fmriprep-dir /oak/.../derivatives/fmriprep_24.1.0rc2 \
  --tasks stopSignal flanker nBack --space MNI

# Preview
neuro-run show lev1 discovery \
  --fmriprep-dir /oak/.../derivatives/fmriprep_24.1.0rc2 \
  --base-tasks --space surface --residuals
```

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--fmriprep-dir` | _(required)_ | fMRIPrep derivatives directory |
| `--tasks` | — | Specific task names |
| `--base-tasks` | — | All 8 base tasks |
| `--dual-tasks` | — | All 10 dual tasks |
| `--all` | — | All 18 tasks |
| `--results-dir` | `{bids_dir}/derivatives/lev1` | Output directory |
| `--exclusions-file` | compiled | Exclusions JSON (auto-detected from Stage 5) |
| `--space` | `MNI` | `MNI`, `T1w`, `surface`, `fsaverage6`, or `fsLR` |
| `--threshold` | `1.0` | Within-subject mask intersection |
| `--smoothing-fwhm` | _(none)_ | Spatial smoothing in mm |
| `--residuals` | off | Compute task-regressed residuals |
| `--fc-confounds` | off | Regress global signal / WM / CSF from residuals |
| `--skip-existing` | off | Skip runs with existing outputs |

#### Tasks

**Base (8):** cuedTS, directedForgetting, flanker, goNogo, nBack, shapeMatching, spatialTS, stopSignal

**Dual (10):** directedForgettingWCuedTS, directedForgettingWFlanker, stopSignalWDirectedForgetting, stopSignalWFlanker, spatialTSWCuedTS, flankerWShapeMatching, cuedTSWFlanker, spatialTSWShapeMatching, nBackWShapeMatching, nBackWSpatialTS

#### Output

```
derivatives/lev1/sub-s03/task-flanker/
├── fixed_effects/        # Subject-level fixed-effects maps
├── indiv_contrasts/      # Per-run contrast estimates
├── task_residuals/       # Task-regressed residuals (if --residuals)
├── quality_control/      # VIF plots, design matrix figures
├── masks/                # Combined brain masks (volumetric only)
└── simplified_events/    # Preprocessed event files
```

### Second-level GLM (`lev2`)

Group-level analysis via FSL randomise. One array task per contrast.

```bash
neuro-run submit lev2 discovery \
  --lev1-dirs /oak/.../lev1_discovery \
  --results-dir /oak/.../lev2_discovery \
  --base-tasks
```

### MSHBM Parcellation

Precision network parcellation. Two steps: prepare fsaverage6 surface inputs, then run MSHBM.

```bash
# Prepare surface inputs from lev1 residuals + rest BOLD
neuro-run submit prep-mshbm discovery \
  --glm-dir /oak/.../lev1_discovery \
  --fmriprep-dir /oak/.../fmriprep

# Run MSHBM
neuro-run submit mshbm discovery \
  --surface-inputs-dir /scratch/.../surface_inputs \
  --output-dir /scratch/.../mshbm_output
```

---

## Reference

### Sample Configuration

Samples (discovery, validation, excluded) and Flywheel settings are defined in `config/pipeline_config.json`. All commands reference samples by name. Runtime dataset paths (BIDS dir, partition, image dir) are stored in `~/.neuro_workflow/datasets.json` and registered via `neuro-run add-dataset`.

### Derived Paths

| Path | Value |
|------|-------|
| Image | `{image_dir}/{pipeline}_{version}.sif` |
| Derivatives | `{bids_dir}/derivatives/{pipeline}_{version}` |
| Work dir | `$SCRATCH/work/{pipeline}_{dataset}_{version}` |
| Logs | `{bids_dir}/derivatives/{pipeline}_{version}/logs/` |

### Package Structure

```
src/neuro_workflow/
├── cli.py                     # Entry point (neuro-run)
├── bidsify/                   # Stage 1: Flywheel → BIDS
├── events/                    # Stage 2: Behavioral events + QC
│   ├── create.py              #   _events.tsv generation
│   ├── utils.py               #   Shared event utilities
│   ├── qc.py                  #   Behavioral QC + exclusion criteria
│   ├── qc_globals.py          #   QC thresholds
│   └── trim.py                #   NIfTI trimming
├── pipelines/                 # Stage 3: SLURM submission templates
│   ├── fmriprep.py
│   ├── qsiprep.py
│   ├── happy.py
│   ├── fsqc.py
│   ├── lev1.py, lev2.py       # Analysis submission
│   ├── prep_mshbm.py, mshbm.py
│   └── bidsify.py
├── qa/                        # Stage 4: Quality checks
├── exclusions/                # Stage 5: Exclusion management
│   ├── motion.py
│   ├── neg_events.py
│   └── behavioral.py
├── analysis/                  # Stage 6: Analysis library
│   ├── config.py
│   ├── core/                  #   Shared utilities
│   ├── io/                    #   File discovery
│   ├── task_config/           #   Per-task YAML configs
│   ├── lev1/                  #   First-level GLM
│   │   ├── run.py
│   │   └── processing/        #   Design, GLM, contrasts, residuals, etc.
│   ├── lev2/                  #   Second-level group stats
│   │   └── run.py
│   └── mshbm/                 #   MSHBM surface input prep
│       └── run.py
├── templates/                 # sbatch templates
└── core/                      # Config, image management, SLURM utils
```

### Running Tests

```bash
module load uv
uv run pytest tests/ -v
```
