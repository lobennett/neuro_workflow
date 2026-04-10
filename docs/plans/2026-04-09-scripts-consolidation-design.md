# Scripts Consolidation Design

**Date:** 2026-04-09
**Status:** Approved

## Problem

The `scripts/` directory contains 10 scripts accumulated over several months. Two depend on deleted modules and are broken. Several others are superseded by planned work. The directory needs consolidation to three focused scripts with clear responsibilities.

## Decision

Delete all 10 existing scripts and `config/behavioral_session_mapping.json`. Replace with three new scripts:

1. `trim_bold.py` — trim 7 dummy BOLD volumes, update sidecar JSONs
2. `reconcile_sessions.py` — read-only analysis mapping raw behavioral to BIDS, producing a reviewable manifest
3. `migrate_behavioral.py` — consume reviewed manifest, copy/rename files to BIDS sourcedata

## Deleted Scripts

| Script | Reason |
|--------|--------|
| `analyze_bold_scans.py` | Broken — imports deleted `bids_validation` module |
| `post_process_bids.py` | Broken — imports deleted `trimming_orchestrator`, `exclusions_manifest` |
| `generate_behavioral_mapping.py` | Replaced by `reconcile_sessions.py` |
| `rename_behavioral_to_sourcedata.py` | Replaced by `migrate_behavioral.py` |
| `migrate_archive_behavioral_data.py` | Replaced by `migrate_behavioral.py` |
| `check_behavioral_bold_correspondence.py` | Replaced by `reconcile_sessions.py` |
| `check_bids_sourcedata_correspondence.py` | Replaced by `reconcile_sessions.py` |
| `resolve_behavioral_discrepancies.py` | Handled by manifest review workflow |
| `run_behavioral_migration.sh` | Replaced by two-step manifest workflow |
| `verify_bids_completion.sh` | No longer needed |

Also deleted:
- `config/behavioral_session_mapping.json` — replaced by reconciliation manifest TSVs
- Any `neuro_workflow.behavioral_archive.*` modules used only by deleted scripts

---

## Script 1: `trim_bold.py`

**Purpose:** Trim 7 dummy volumes from every functional NIfTI in a BIDS directory and update sidecar JSONs.

**Independent of the other two scripts. Can run at any time.**

### Interface

```bash
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
uv run python scripts/trim_bold.py /scratch/users/logben/validation_bids
```

### Behavior

1. Glob all `sub-*/ses-*/func/*_bold.nii.gz` in the given BIDS directory
2. For each NIfTI:
   - Load the matching sidecar JSON
   - **Idempotency check:** if `"NumberOfVolumesDiscardedByUser": 7` already present in the sidecar, skip this file
   - Load with nibabel, verify dim4 > 7
   - Slice off the first 7 volumes, overwrite the NIfTI in place
   - Update sidecar JSON: add `"NumberOfVolumesDiscardedByUser": 7`, update `"NumVolumes"` if present
3. Print summary: files trimmed, files skipped (already trimmed), files skipped (dim4 <= 7)

### Dependencies

- nibabel (already in project dependencies)
- No dependency on any `neuro_workflow` module

### Idempotency

Safe to run multiple times. The sidecar check (`NumberOfVolumesDiscardedByUser`) prevents double-trimming. A file is only trimmed if this field is absent from its sidecar JSON.

---

## Script 2: `reconcile_sessions.py`

**Purpose:** Read-only analysis that checks 1-to-1 correspondence between BIDS functional scans and raw behavioral CSVs. Produces a TSV manifest for human review (optionally Claude-assisted).

### Interface

```bash
uv run python scripts/reconcile_sessions.py \
    --raw-dir /oak/.../behavioral_data/raw_cleaned \
    --bids-dir /scratch/users/logben/discovery_bids \
    --scan-notes docs/SCAN-NOTES.md \
    --output reconciliation_discovery.tsv

uv run python scripts/reconcile_sessions.py \
    --raw-dir /oak/.../behavioral_data/raw_cleaned \
    --bids-dir /scratch/users/logben/validation_bids \
    --scan-notes docs/SCAN-NOTES.md \
    --output reconciliation_validation.tsv
```

### Behavior

1. **Scan BIDS func/**: extract (subject, session, task) tuples from `*_bold.nii.gz` filenames. Deduplicate across echoes and runs (a task in a session counts once regardless of how many echoes/runs exist). Record the absolute path to one representative BOLD file.
2. **Scan raw behavioral dir**: extract (subject, session, task) tuples from CSV filenames in `raw_cleaned/s*/ses-*/` AND `exclusions/s*/ses-*/`. Record absolute path to each CSV.
3. **Normalize task names**: map raw CSV naming conventions to BIDS camelCase (e.g., `go-nogo` -> `goNogo`, `shape_matching_with_cued_task_switching` -> `shapeMatchingWCuedTS`). This requires a lookup table covering all task naming patterns in the dataset.
4. **Direct match** on (subject, session, task). No session remapping or greedy algorithm.
5. **Enrich discrepancies**: for each unmatched row, check whether the same task for the same subject exists in any other session on the opposite side (the `same_task_other_sessions` column).
6. **Auto-populate notes**: if `--scan-notes` is provided, search for subject/session/task mentions and include relevant text.
7. **Write TSV manifest**.

### Output TSV Columns

| Column | Description |
|--------|-------------|
| `subject` | Subject label (e.g., `s03`) |
| `session` | BIDS session (e.g., `ses-01`) |
| `task` | BIDS task name (e.g., `goNogo`) |
| `status` | `matched`, `bold_without_behavioral`, `behavioral_without_bold` |
| `action` | `copy` (for matched rows), `pending` (for discrepancies) |
| `dest_session` | Target session for migration (defaults to source session; editable for remapping) |
| `raw_path` | Absolute path to the behavioral CSV (empty if none found) |
| `bold_path` | Absolute path to a representative BOLD NIfTI (empty if none found) |
| `same_task_other_sessions` | Cross-session context (e.g., `ses-02:behavioral_only`) |
| `notes` | Auto-populated from SCAN-NOTES.md if subject/session/task match found |

### Designed for Claude-Assisted Review

The TSV is self-contained: absolute paths, cross-session context, and scan notes are inline. The intended workflow is:

1. Run `reconcile_sessions.py` to produce the TSV
2. Open a Claude conversation with the TSV + `docs/SCAN-NOTES.md` + `manual_notes.md`
3. Ask Claude to review all `pending` rows and propose: `copy`, `copy` with `dest_session` override, `skip`, or `irreconcilable`
4. Review Claude's proposals, accept/reject, save the TSV
5. Feed the reviewed TSV to `migrate_behavioral.py`

### Read-Only

This script modifies nothing on disk. Its only output is the TSV file.

---

## Script 3: `migrate_behavioral.py`

**Purpose:** Consume the reviewed reconciliation manifest and copy raw behavioral CSVs to BIDS sourcedata, renaming to BIDS convention. Also handles out-of-scanner, survey, and mTurk data.

### Interface

```bash
uv run python scripts/migrate_behavioral.py \
    --manifest reconciliation_discovery.tsv \
    --raw-dir /oak/.../behavioral_data/raw_cleaned \
    --output-dir /oak/.../sourcedata \
    --sample discovery

uv run python scripts/migrate_behavioral.py \
    --manifest reconciliation_validation.tsv \
    --raw-dir /oak/.../behavioral_data/raw_cleaned \
    --output-dir /oak/.../sourcedata \
    --sample validation
```

### Behavior

**In-scanner behavioral** (manifest-driven):
1. Read the TSV manifest
2. For each row where `action = copy`:
   - Copy the file at `raw_path` to `{output-dir}/in_scanner_behavior/sub-{subject}/{dest_session}/beh/sub-{subject}_{dest_session}_task-{task}_beh.csv`
3. Skip rows where `action` is `skip`, `irreconcilable`, or `pending` (log them)
4. Fail if any rows are still `pending` (user must resolve all discrepancies first)

**Out-of-scanner behavioral:**
- Copy `practice/` and `pretouch/` subdirectories to `{output-dir}/out_scanner_behavior/sub-{subject}/`
- Rename to BIDS convention
- Filter to subjects present in the manifest

**Survey data:**
- Copy from `/oak/.../survey_data/*/raw/*/*` to `{output-dir}/survey_data/sub-{subject}/`
- Filter to subjects present in the manifest

**mTurk:**
- Copy from archive mTurk directory to `/oak/.../mTurk/sub-{subject}/`
- Not filtered by sample (all subjects)

### Output

- Copied and renamed files in BIDS sourcedata layout
- `{output-dir}/migration_report.json`: counts per category, list of copied files, list of skipped files with reasons

### Data Lineage

All files are copied, including those from `exclusions/`. Excluded scans are managed via `.bidsignore` after migration, preserving full data lineage in the BIDS directories.

---

## Workflow

```
trim_bold.py ─────────────────────────────────────────────────┐
  (independent, runs on BIDS dirs directly)                   │
                                                              │
reconcile_sessions.py ──→ TSV manifest                        │
       │                                                      │
       ▼                                                      │
  Claude-assisted review of pending rows                      │
       │                                                      │
       ▼                                                      │
migrate_behavioral.py ──→ files in BIDS sourcedata            │
       │                                                      │
       ▼                                                      │
  .bidsignore updated for excluded scans  ◄───────────────────┘
```

## Task Name Normalization Table

The reconciliation script needs a mapping from raw CSV task names to BIDS camelCase. Based on the existing dataset, the known patterns are:

| Raw CSV pattern(s) | BIDS task name |
|---------------------|----------------|
| `go-nogo`, `go_nogo` | `goNogo` |
| `stop-signal`, `stop_signal` | `stopSignal` |
| `directed-forgetting`, `directed_forgetting` | `directedForgetting` |
| `cued-task-switching`, `cued_task_switching` | `cuedTS` |
| `spatial-task-switching`, `spatial_task_switching` | `spatialTS` |
| `shape-matching`, `shape_matching` | `shapeMatching` |
| `n-back`, `n_back` | `nBack` |
| `flanker` | `flanker` |
| `rest` | `rest` |
| `go_nogo_with_flanker` | `goNogoWFlanker` |
| `stop_signal_with_flanker` | `stopSignalWFlanker` |
| `directed_forgetting_with_flanker` | `directedForgettingWFlanker` |
| `cued_task_switching_with_flanker`, `flanker_with_cued_task_switching` | `cuedTSWFlanker` / `flankerWCuedTS` |
| `shape_matching_with_cued_task_switching` | `shapeMatchingWCuedTS` |

This table will be validated against actual CSV filenames during implementation.
