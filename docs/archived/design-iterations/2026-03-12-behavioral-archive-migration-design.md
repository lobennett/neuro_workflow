# Behavioral Data Archive Migration Design

**Date:** 2026-03-12

**Goal:** Migrate and organize behavioral data from archive directory into properly structured, BIDS-formatted sourcedata locations. Includes mTurk (separate sample), out-of-scanner behavior, and survey data (discovery/validation only).

---

## Overview

Three types of behavioral data currently exist in `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/`:

1. **mTurk** — separate sample, not part of neuroimaging cohort
2. **out_of_scanner** — behavioral data from discovery/validation subjects collected outside scanner
3. **survey_data** — prescan survey data from discovery/validation subjects

These will be migrated to three separate locations with BIDS-formatted filenames:

- `/oak/stanford/groups/russpold/data/network_grant/mTurk/sub-XXX/` (all subjects)
- `/oak/stanford/groups/russpold/data/network_grant/sourcedata/out_scanner_behavior/sub-XXX/` (discovery/validation only)
- `/oak/stanford/groups/russpold/data/network_grant/sourcedata/survey_data/sub-XXX/` (discovery/validation only)

Concurrently, the existing pipeline script will be updated to use `in_scanner_behavior` instead of `behavioral_data` to clarify the distinction.

---

## Architecture

### **Main Script:** `scripts/migrate_archive_behavioral_data.py`

Unified Python script handling all three data types:

1. **Sample Validation** — Load discovery/validation subject lists from config
2. **Filename Normalization** — Convert archive names to BIDS camelCase format
3. **Data Migration** — Copy files to destinations with filtering
4. **Reporting** — Generate console summary + JSON report of migration results

**CLI:**
```bash
python scripts/migrate_archive_behavioral_data.py \
  --archive-dir /oak/.../behavioral_data \
  --sourcedata-dir /oak/.../sourcedata \
  --mturk-dir /oak/.../mTurk \
  --dry-run  # optional: preview without copying
```

---

## Filename Normalization

### **Task Name Mapping**

Convert snake_case archive names to BIDS camelCase, removing excess variants:

| Archive Name | BIDS Output |
|---|---|
| `go_nogo_with_shape_matching` | `goNogoWShapeMatching` |
| `directed_forgetting_single_task_network` | `directedForgetting` |
| `n_back_with_predictable_task_switching` | `nBackWPredictableTaskSwitching` |
| `stop_signal_with_directed_forgetting` | `stopSignalWDirectedForgetting` |
| `flanker_single_task_network` | `flanker` |
| `shape_matching_with_cued_task_switching` | `shapeMatchingWCuedTaskSwitching` |

**Stripping rules:**
- Remove `_single_task_network`, `_single_task`, `_network` suffixes
- Keep `_with_` pairings (dual-task combinations are meaningful)

### **Output Filename Format**

```
Input:  s247_go_nogo_with_shape_matching.csv
Output: sub-s247_task-goNogoWShapeMatching_behavior.csv

Input:  flanker_single_task_network_s528.csv
Output: sub-s528_task-flanker_behavior.csv

Input:  prescan_1.json (survey)
Output: sub-s247_prescan-01_survey.json (with zero-padded run number)
```

---

## Data Migration & Filtering

### **Sample Validation**

Load discovery and validation sample lists from `config/behavioral_session_mapping.json` to determine which subjects are in the neuroimaging cohort.

- **mTurk:** Copy ALL files (entirely separate sample)
- **out_of_scanner & survey_data:** Copy only for subjects in discovery OR validation

### **Directory Structure**

```
Archive → Destination:

mTurk/all_data/s528/*.csv
  → /oak/.../mTurk/sub-s528/

out_of_scanner/s247/*.csv
  → /oak/.../sourcedata/out_scanner_behavior/sub-s247/
  (only if s247 in discovery or validation)

survey_data/prescan_surveys/raw/s247/*.json
  → /oak/.../sourcedata/survey_data/sub-s247/
  (only if s247 in discovery or validation)
```

### **Copy Logic**

- Create destination directories as needed (with proper permissions)
- Normalize filename during copy
- Skip if file already exists (log as skipped)
- Handle exceptions gracefully (permission errors, disk space, etc.)

---

## Reporting & Logging

### **Console Summary**

Output migration statistics:
- Files migrated per data type
- Subjects in archive but NOT in discovery/validation (with file counts)
- Subjects in discovery/validation but missing from archive
- Normalization issues or file conflicts

### **JSON Report File**

Save detailed report to `sourcedata/behavioral_migration_report.json`:
- Timestamp and summary counts
- Lists of missing data (subjects not in sample, subjects missing from archive)
- Skipped files with reasons

### **Logging**

Use Python logging module:
- `INFO`: Migration progress, file counts
- `WARNING`: Subjects not in sample, missing subjects, filename issues
- `ERROR`: File I/O failures, permissions, etc.

---

## Pipeline Update: `rename_behavioral_to_sourcedata.py`

Update existing script to reflect new directory naming:

**Change:**
```python
# OLD:
output_dir = output_dir / "behavioral_data" / f"sub-{subject}"

# NEW:
output_dir = output_dir / "in_scanner_behavior" / f"sub-{subject}"
```

**Rationale:** Clarifies that this pipeline handles in-scanner behavioral task data, distinct from out-of-scanner behavior and survey data.

**CLI unchanged:**
```bash
python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/.../raw_cleaned \
    --output-dir /scratch/.../discovery_bids/sourcedata \
    --sample discovery
```

Script will now write to `sourcedata/in_scanner_behavior/`.

---

## Implementation Notes

1. **One-time script:** Designed as a one-time migration but written to be maintainable if re-runs are needed
2. **Idempotent:** Can be run multiple times safely (skips existing files)
3. **Dry-run mode:** `--dry-run` flag previews migration without copying
4. **Config reuse:** Leverages existing sample config from behavioral mapping work
5. **No breaking changes:** Existing pipeline continues to work; only output directory name changes

---

## Success Criteria

- ✅ All mTurk files copied to `/oak/.../mTurk/sub-XXX/` with BIDS-normalized names
- ✅ All out_of_scanner files for discovery/validation copied to `sourcedata/out_scanner_behavior/sub-XXX/`
- ✅ All survey_data for discovery/validation copied to `sourcedata/survey_data/sub-XXX/`
- ✅ Comprehensive report generated identifying missing subjects and orphaned files
- ✅ Existing pipeline updated to use `in_scanner_behavior` directory
- ✅ README/documentation updated to reflect new directory structure
