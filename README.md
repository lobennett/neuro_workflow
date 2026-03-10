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
```

After installation, use `uv run neuro-run` from the project directory, or `module load uv && neuro-run` if the venv is on your PATH.

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

Pull NIfTI/JSON data from Flywheel and write a clean BIDS dataset. Handles subject label aliases, multi-echo BOLD selection, sequential session numbering, and fieldmap sidecar patching.

### Prerequisites

- Flywheel API key configured (`~/.config/flywheel/user.json` or `FW_API_KEY`)
- `uv pip install -e ".[bidsify]"`

### Usage

```bash
# Register the dataset first
neuro-run add-dataset discovery \
  --bids-dir /oak/.../discovery_BIDS \
  --subjects-file subs_discovery.txt \
  --partition russpold \
  --mail-user logben@stanford.edu

# Submit BIDSify job
neuro-run submit bidsify discovery --output-dir /scratch/users/logben/discovery_BIDS

# Or run directly (no SLURM)
neuro-run bidsify discovery --output-dir /scratch/users/logben/discovery_BIDS

# Pull specific subjects
neuro-run submit bidsify validation --output-dir /scratch/.../validation_BIDS --subjects s76 s247

# Preview the sbatch script
neuro-run show bidsify discovery --output-dir /scratch/users/logben/discovery_BIDS
```

### Output

```
discovery_BIDS/
├── dataset_description.json
├── sub-s03/
│   ├── ses-01/
│   │   ├── anat/     # T1w, T2w
│   │   ├── func/     # multi-echo BOLD
│   │   ├── fmap/     # fieldmap + magnitude
│   │   └── dwi/      # DWI + bval/bvec
│   └── ses-02/
├── sub-s10/
└── sourcedata/
    ├── reconciliation.json
    └── bidsify_log.json
```

Configuration lives in `src/neuro_workflow/bidsify/reconciliation_config.json` (subject lists, aliases, skip lists) and `src/neuro_workflow/bidsify/config.py` (acquisition label → BIDS mappings).

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
# One-time: rename raw CSVs to BIDS sourcedata layout
python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/.../behavioral_data/raw_cleaned \
    --output-dir /oak/.../behavioral_data/sourcedata \
    --dry-run

# Create BIDS event files
neuro-run events create discovery --behavioral-dir /oak/.../sourcedata

# Run behavioral QC (generates exclusion entries + trim list)
neuro-run events qc discovery --behavioral-dir /oak/.../sourcedata

# Trim NIfTIs for participants flagged by QC
neuro-run events trim discovery
```

The QC step saves exclusions to `~/.neuro_workflow/exclusions/discovery/sources/behavioral-qc.json` and a trim list to `{bids_dir}/sourcedata/behavioral_qc/trim_list.json`.

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
| `outlier-report` | VIF + outlier analysis with figures and summary CSVs |
| `reliability` | Create MP4 movies showing fMRI reliability across sessions |

### Examples

```bash
neuro-run qa neg-events discovery
neuro-run qa global-signal discovery --output-dir /tmp/gs_figs
neuro-run qa outlier-report discovery \
  --lev1-dirs /oak/.../lev1_discovery \
  --exclusions-file /oak/.../exclusions.json \
  --output-dir /tmp/outlier_report
neuro-run qa reliability discovery \
  --fmriprep-version 24.1.0rc2 \
  --output-dir /tmp/reliability_movies
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
  --exclusions-csv /oak/.../exclusions.csv \
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

### Dataset Registration

Register a dataset once; all commands reference it by name.

```bash
neuro-run add-dataset <name> \
  --bids-dir <path> \
  --subjects-file <path> \
  [--partition russpold] \
  [--mail-user user@stanford.edu] \
  [--image-dir /home/groups/russpold/singularity_images] \
  [--templateflow-dir /home/groups/russpold/templateflow]
```

Configs are stored in `~/.neuro_workflow/datasets.json`.

### Subjects File

Plain text, one subject ID per line (no `sub-` prefix):

```
s03
s10
s19
```

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
