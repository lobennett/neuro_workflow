# Behavioral Events Pipeline Design

**Goal:** Create BIDS event files from raw behavioral data, run QC to flag/exclude bad scans, and trim NIfTIs for tasks where participants stopped responding.

**Tech Stack:** Python 3.13, nibabel (for NIfTI trimming), pandas, existing neuro_workflow CLI and exclusions system.

---

## Overview

Three CLI commands under `neuro-run events` plus a one-shot rename script:

1. **`scripts/rename_behavioral_to_sourcedata.py`** — One-time migration: standardize raw behavioral CSV filenames from `raw_cleaned/` to BIDS `sourcedata/` layout
2. **`neuro-run events create <dataset>`** — Generate BIDS `_events.tsv` files from sourcedata CSVs
3. **`neuro-run events qc <dataset>`** — Compute behavioral QC metrics, produce exclusion entries for the existing exclusions system, and identify tasks needing trimming
4. **`neuro-run events trim <dataset>`** — Trim NIfTIs to match behavioral cutoff, write to derivatives

---

## Script: Rename Behavioral Data

**Script:** `scripts/rename_behavioral_to_sourcedata.py`

**Input:** `/oak/stanford/groups/russpold/data/network_grant/behavioral_data/raw_cleaned/`
- 46 active subject folders
- Two CSV naming patterns:
  - BIDS-style (early subjects): `sub-s03_ses-1_task-go-nogo_desc-raw.csv`
  - Descriptive (most subjects): `stop_signal_single_task_network__fmri_results.csv`
- Sessions 1-12, single and dual tasks
- Skips `dropped_subjects/`, `exclusions/`, `pretouch/`, and practice files

**Output:** `/oak/stanford/groups/russpold/data/network_grant/behavioral_data/sourcedata/`
```
sourcedata/
└── sub-s03/
    └── ses-01/
        └── beh/
            └── sub-s03_ses-01_task-stopSignal_beh.csv
```

**Logic:**
- Maps both naming patterns to canonical camelCase task names using the same mapping as `config.py` (e.g., `stop_signal` -> `stopSignal`, `cued_task_switching` -> `cuedTS`)
- Zero-pads sessions (`ses-1` -> `ses-01`)
- Copies files (preserves originals in `raw_cleaned/`)
- Logs mapping from old path to new path for provenance

---

## Command: `neuro-run events create <dataset>`

**Purpose:** Generate BIDS `_events.tsv` files from behavioral CSVs.

**Input:**
- Sourcedata behavioral CSVs (`--behavioral-dir`)
- BIDS func directory (from dataset config, to match task/run combos to existing NIfTIs)

**Output:** Event files written directly into BIDS directory:
```
{bids_dir}/sub-s03/ses-01/func/sub-s03_ses-01_task-stopSignal_run-1_events.tsv
```

**Processing pipeline** (ported from `discovery_wm/events/`):
1. Read behavioral CSV
2. `get_neg_rt_correction()` — fix RT estimation errors from cumulative timing drift
3. `cal_time_elapsed()` — adjust times relative to fMRI trigger (`fmri_trigger_initial` row)
4. `add_choice_acc()` — compute binary accuracy column
5. `add_cols()` — select task-specific columns, construct `trial_type` from condition columns
6. `response_time_and_junk()` — task-specific cleanup (stop signal success/failure relabeling, go/nogo relabeling)
7. `set_default_event_cols()` — rename to BIDS columns (onset, duration, response_time), convert ms to seconds, filter onset > 0
8. `rename_cells()` — standardize trial_id labels per task
9. Detect performance feedback blocks, label as `break_with_performance_feedback`
10. Write TSV (tab-separated, `n/a` for missing values)

**Supported tasks (18):**
- 8 base: stopSignal, goNogo, flanker, nBack, cuedTS, spatialTS, directedForgetting, shapeMatching
- 10 dual: all pairwise combinations (stopSignalWFlanker, directedForgettingWCuedTS, etc.)

**CLI:**
```bash
neuro-run events create discovery --behavioral-dir /oak/.../behavioral_data/sourcedata
```

---

## Command: `neuro-run events qc <dataset>`

**Purpose:** Compute behavioral QC metrics, flag/exclude scans, identify tasks needing trimming.

**Input:**
- Sourcedata behavioral CSVs (`--behavioral-dir`)

**Output:**
1. **Exclusion entries** — registered as a `behavioral-qc` source in the existing exclusions system (`neuro-run exclusions compile` picks them up automatically)
2. **Trim list** — `{bids_dir}/sourcedata/behavioral_qc/trim_list.json` with subject/session/task/cutoff info
3. **QC summary CSVs** — `{bids_dir}/sourcedata/behavioral_qc/{task}_qc.csv` with per-subject metrics

**QC metrics** (ported from `network-behavior-qc`):
- Accuracy, RT, omission rate, commission rate (all tasks)
- Stop signal: go_rt, stop_success rate, SSRT, SSD stats
- Go/nogo: go_acc, nogo_acc
- N-back: per-load match/mismatch accuracy (1-back, 2-back only; 3-back excluded from exclusion criteria)

**Exclusion thresholds** (from `network-behavior-qc/globals.py`):
- Stop signal: stop_success outside [0.25, 0.75], go_rt > 1000ms (fMRI)
- Go/nogo: dual rule — (go_acc <= 0.75 OR nogo_acc <= 0.2) AND (go_acc <= 0.5 OR nogo_acc <= 0.5)
- N-back: dual rule — (match <= 0.2 AND mismatch <= 0.75) AND (match <= 0.5 AND mismatch <= 0.5)
- Other tasks: accuracy < 0.55 OR omission_rate > 0.25

**Trimming detection:**
- Detects RT tail cutoff (last N=10 test trials all non-responses)
- If cutoff is before halfway point of test trials: exclude (too much data lost)
- Otherwise: add to trim list with cutoff onset time

**Integration with exclusions system:**
- Produces entries in the same format as `motion` and `neg-events` generators
- Each exclusion has: subject, session, task, run, action (exclude), source (behavioral-qc), reason

**CLI:**
```bash
neuro-run events qc discovery --behavioral-dir /oak/.../behavioral_data/sourcedata
```

---

## Command: `neuro-run events trim <dataset>`

**Purpose:** Trim NIfTIs to match behavioral cutoff for tasks where participants stopped responding.

**Input:**
- Trim list from `events qc` (`{bids_dir}/sourcedata/behavioral_qc/trim_list.json`)
- BIDS func NIfTIs

**Output:** Trimmed NIfTIs in derivatives:
```
{bids_dir}/derivatives/trimmed/
└── sub-s03/
    └── ses-01/
        └── func/
            ├── sub-s03_ses-01_task-stopSignal_run-1_echo-1_desc-trimmed_bold.nii.gz
            ├── sub-s03_ses-01_task-stopSignal_run-1_echo-1_desc-trimmed_bold.json
            └── ...
```

**Logic:**
1. Read trim list
2. For each entry, find corresponding NIfTI(s) in BIDS func dir
3. Calculate volume cutoff: `floor(onset_cutoff / TR)`
4. Truncate NIfTI to that number of volumes using nibabel
5. Copy and patch JSON sidecar (update NumVolumes if present)
6. Write to `derivatives/trimmed/` with `desc-trimmed` entity

**CLI:**
```bash
neuro-run events trim discovery
```

---

## Module Structure

```
src/neuro_workflow/events/
├── __init__.py
├── create.py          # event file generation (ported from discovery_wm)
├── utils.py           # shared event processing utilities (ported from discovery_wm)
├── qc.py              # behavioral QC metrics + exclusion criteria
├── qc_globals.py      # thresholds and task definitions
└── trim.py            # NIfTI trimming

scripts/
└── rename_behavioral_to_sourcedata.py
```

**New exclusion generator:**
```
src/neuro_workflow/exclusions/behavioral_qc.py  # integrates with existing exclusions system
```

**Dependencies:** pandas, nibabel (add to `[events]` optional dependency group in pyproject.toml)

---

## Data Flow

```
raw_cleaned/                    (original behavioral CSVs)
    ↓ [scripts/rename_behavioral_to_sourcedata.py]  (one-time)
sourcedata/                     (standardized BIDS layout)
    ↓ [neuro-run events create]
{bids_dir}/.../func/*_events.tsv    (BIDS event files)
    ↓ [neuro-run events qc]
    ├→ exclusions system            (behavioral-qc source → compile → lev1)
    ├→ QC summary CSVs              (per-task metrics)
    └→ trim_list.json               (tasks needing trimming)
        ↓ [neuro-run events trim]
        └→ derivatives/trimmed/     (truncated NIfTIs with desc-trimmed)
```
