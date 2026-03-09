# Flywheel BIDSify Module Design

**Date:** 2026-03-09
**Status:** Approved

## Overview

A Python module added to `neuro_workflow` that uses the `flywheel-sdk` to pull NIfTI/JSON data from the `r01network` Flywheel project, resolve subject label inconsistencies, and write a clean BIDS dataset with correct naming, session ordering, and fieldmap metadata.

## Module Structure

```
src/neuro_workflow/bidsify/
    __init__.py
    config.py          # acquisition label -> BIDS name mapping, constants
    flywheel_query.py  # query FW project, enumerate subjects/sessions/acquisitions
    file_selector.py   # select correct NIfTI/JSON from duplicate gear outputs
    bids_writer.py     # download files, rename to BIDS, patch sidecars
    run.py             # orchestration: query -> select -> write
```

## CLI Integration

New subcommand on the existing `neuro-run` CLI:

```bash
neuro-run bidsify <sample> \
  --output-dir /scratch/users/logben/discovery_BIDS \
  --subjects s03 s10 s19 s29 s43 \
  --flywheel-project r01network \
  [--overwrite]
```

New optional dependency group in `pyproject.toml`:

```toml
bidsify = ["flywheel-sdk>=17.0"]
```

Container rebuilt with `.[lev1,qa,bidsify]`.

## Acquisition Label -> BIDS Name Mapping

Single source of truth in `config.py`. Maps every known Flywheel acquisition label to its BIDS output.

### Base tasks (func/)

| Flywheel label | BIDS task name |
|---|---|
| `task-rest_bold` | `rest` |
| `task-cuedTS_bold` | `cuedTS` |
| `task-directedForgetting_bold` | `directedForgetting` |
| `task-flanker_bold` | `flanker` |
| `task-goNogo_bold` | `goNogo` |
| `task-nBack_bold` | `nBack` |
| `task-shapeMatching_bold` | `shapeMatching` |
| `task-shapeMaching_bold` | `shapeMatching` (typo fix) |
| `task-spatialTS_bold` | `spatialTS` |
| `task-stopSignal_bold` | `stopSignal` |
| `task_stopSignal_bold` | `stopSignal` (underscore variant) |

### Dual tasks (func/)

| Flywheel label | BIDS task name |
|---|---|
| `directed_forgetting_w_flanker_bold` | `directedForgettingWFlanker` |
| `stop_signal_w_directed_forgetting_bold` | `stopSignalWDirectedForgetting` |
| `stop_signal_w_flanker_bold` | `stopSignalWFlanker` |
| `task-stop_signal_with_directed_forgetting_bold` | `stopSignalWDirectedForgetting` |
| `task-stop_with_df_bold` | `stopSignalWDirectedForgetting` |
| `task-stop_with_flanker_bold` | `stopSignalWFlanker` |

Additional dual task names may appear in validation subjects and will be added to the map as encountered. Unknown labels raise a warning and are skipped.

### Fieldmap (fmap/)

| Flywheel label | BIDS output |
|---|---|
| `fmap-fieldmap` | `fieldmap.nii.gz` + `magnitude.nii.gz` |

### Anatomical (anat/)

| Flywheel label | BIDS suffix | acq label |
|---|---|---|
| `T1w MPRAGE PROMO` | `T1w` | `MPRAGEPromo` |
| `NEW Sag_MPRAGE_T1` | `T1w` | `SagMPRAGE` |
| `T2w CUBE PROMO .8mm sag` | `T2w` | `CubePromo` |

### Diffusion (dwi/)

| Flywheel label | dir | acq | PhaseEncodingDirection |
|---|---|---|---|
| `DTI_pe0_g105` | `AP` | `g105` | `j` |
| `DTI_pe1_g105` | `PA` | `g105` | `j-` |
| `DTI_pe1_g71` | `PA` | `g71` | `j-` |

### Skipped acquisitions

| Flywheel label | Reason |
|---|---|
| `3Plane Loc SSFSE` | Localizer |
| `GE HOS FOV28` / `_1` / `_2` | Shim |

## Session Ordering

1. Query all sessions for a subject from Flywheel (including alias labels)
2. Sort by `session.timestamp` ascending
3. Assign `ses-01` through `ses-XX` sequentially
4. All sessions included (no cutoff filtering)

## File Selection from Duplicate Gear Outputs

Each acquisition may have multiple NIfTI/JSON files from different dcm2niix gear runs.

### Selection strategy

1. Group files by type (NIfTI, JSON, bval, bvec)
2. For multi-echo bold: select files matching `_e{1,2,3}` pattern
3. For single-output acquisitions (T1w, fmap, DTI): select base files
4. When duplicates exist: prefer the file with the most recent `created` timestamp
5. Verification: if multiple copies exist, compare file sizes. If sizes differ, log warning. If sizes match, proceed with newest.

### File patterns by modality

| Modality | NIfTI pattern | Sidecar pattern |
|---|---|---|
| bold (multi-echo) | `*_e{1,2,3}.nii.gz` | `*_e{1,2,3}*.json` |
| fieldmap | `*_fieldmap.nii.gz` | `*_fieldmap.json` |
| magnitude | base `*.nii.gz` (no `_fieldmap`) | base `*.json` |
| T1w / T2w | `*.nii.gz` (single) | `*.json` |
| DTI | `*.nii.gz` | `*.json` + `*.bval` + `*.bvec` |

## BIDS Output Structure

Output directory: specified by `--output-dir`.

```
{output_dir}/
    dataset_description.json
    README.md
    sub-s03/
        ses-01/
            func/
                sub-s03_ses-01_task-rest_run-1_echo-1_bold.nii.gz
                sub-s03_ses-01_task-rest_run-1_echo-1_bold.json
                sub-s03_ses-01_task-rest_run-1_echo-2_bold.nii.gz
                ...
            fmap/
                sub-s03_ses-01_run-1_fieldmap.nii.gz
                sub-s03_ses-01_run-1_fieldmap.json
                sub-s03_ses-01_run-1_magnitude.nii.gz
        ses-04/
            anat/
                sub-s03_ses-04_acq-MPRAGEPromo_T1w.nii.gz
                sub-s03_ses-04_acq-MPRAGEPromo_T1w.json
            func/
            fmap/
        ses-14/
            anat/
                sub-s03_ses-14_acq-SagMPRAGE_T1w.nii.gz
            fmap/
    sourcedata/
        reconciliation.json
        bidsify_log.json
```

### Run numbering

Each task within a session gets `run-1`. If a task appears multiple times in the same session, increment to `run-2`, etc.

### Sidecar patching (B0FieldIdentifier / B0FieldSource)

- Fieldmap JSON: `"B0FieldIdentifier": "sub-{sub}_ses-{ses}_run-{run}_fieldmap"`
- Every BOLD JSON in that session: `"B0FieldSource": "sub-{sub}_ses-{ses}_run-{run}_fieldmap"`

One fieldmap per session applies to all BOLD runs in that session.

### dataset_description.json

```json
{
    "Name": "Network Discovery Sample",
    "BIDSVersion": "1.10.0",
    "DatasetType": "raw",
    "Authors": ["Patrick Bissett", "Russell Poldrack", "Logan Bennett"],
    "GeneratedBy": [
        {
            "Name": "neuro-workflow bidsify",
            "Version": "0.2.0"
        }
    ]
}
```

## Subject Reconciliation

### Configuration

Version-controlled file at `src/neuro_workflow/bidsify/reconciliation_config.json`:

```json
{
    "flywheel_project": "r01network",
    "subject_aliases": {
        "s19-2": "s19",
        "s29-2": "s29",
        "s43-2": "s43"
    },
    "skip_subjects": ["n01", "ex26207"],
    "samples": {
        "discovery": ["s03", "s10", "s19", "s29", "s43"],
        "validation": [
            "s76", "s247", "s214", "s216", "s222", "s250", "s286", "s295",
            "s297", "s300", "s320", "s321", "s336", "s373", "s394", "s415",
            "s432", "s480", "s180", "s599", "s645", "s823", "s874", "s956",
            "s968", "s1035", "s1057", "s1058", "s1127", "s1134", "s1165",
            "s1175", "s1178", "s1189", "s1258", "s1266", "s1267", "s1270",
            "s1273", "s1292", "s1314", "s1320", "s1326", "s1338", "s1351",
            "s1391", "s1399", "s1402", "s1408", "s1445", "s1481", "s1486"
        ]
    }
}
```

### Reconciliation algorithm

For each subject:

1. Collect sessions from all Flywheel labels (main + aliases from config)
2. Sort by timestamp -> assign sequential `ses-XX`
3. Cross-validate against scan tracking CSV:
   - Match CSV dates to Flywheel timestamps (+-1 day tolerance)
   - Extra Flywheel sessions not in tracking: flagged as warnings, still included
   - Tracking sessions not on Flywheel: flagged as missing
4. Cross-validate against Google Calendar CSV as secondary confirmation
5. Generate `sourcedata/reconciliation.json` with full provenance

### Key decisions

- No manual approval gate -- runs end-to-end, warnings are logged but don't block
- All sessions included -- extra sessions become additional ses-XX entries
- Reconciliation config is version-controlled
- Idempotent -- same Flywheel state produces same output

### Known variant resolutions (discovery)

| Variant label | Canonical subject | Rationale |
|---|---|---|
| `s19-2` | `s19` | Scan tracking + calendar confirm s19 scan 3 on 2020-12-04 |
| `s29-2` | `s29` | Calendar shows "s29 scan ??" on 2021-03-05, makeup session |
| `s43-2` | `s43` | Scan tracking + calendar confirm s43 scan 1 on 2020-11-12 |

## Error Handling

- **Unknown acquisition label:** Warning, skip acquisition, continue. Summary at end.
- **Missing expected files:** Error, skip entire acquisition. No partial writes.
- **Duplicate file size mismatch:** Warning, use newest, flag for review.
- **Missing fieldmap in session:** Warning. BOLD sidecars skip B0FieldSource.
- **Flywheel API errors:** Retry once on transient (5xx/timeout). Fail on auth errors.
- **Output directory exists:** Requires `--overwrite` flag or fails.

## Logging

Structured JSON log at `{output_dir}/sourcedata/bidsify_log.json`:

- Timestamp of run
- Flywheel session label -> BIDS session mapping per subject
- Every file downloaded: FW source path, BIDS destination, file size, gear run timestamp
- All warnings/skips/mismatches

## Validation

BIDS validator run via container:

```bash
# Pull once
sbatch pull_image.sh  # (add bids-validator pull)

# Validate
apptainer run bids-validator_2.4.1.sif /scratch/users/logben/discovery_BIDS
```

## Execution

Can run interactively or as SLURM job for large downloads. Flywheel API key read from `~/.config/flywheel/user.json` (auto-bound on Sherlock).

## Duplicate acquisition handling

- Same task appears twice in a session (e.g., s43 ses-08 has two `task-directedForgetting_bold`): take the later one by timestamp (successful retry after failed first attempt)
- Same task across sessions: each session gets its own `run-1`
