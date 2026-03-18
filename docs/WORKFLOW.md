# Complete neuro_workflow Pipeline: Flywheel → BIDS → Behavioral → Events → Preprocessing

**Last Updated:** 2026-03-17
**Status:** ✓ Phases 1-3 Complete, Phase 4-5 Ready
**Single Source of Truth:** This document supersedes individual phase guides.

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Phase 1: Bidsify (Flywheel → BIDS)](#phase-1-bidsify)
3. [Phase 2: Behavioral Data Migration](#phase-2-behavioral-data-migration)
4. [Phase 3: BOLD Trimming & Post-Processing](#phase-3-bold-trimming)
5. [Phase 4: Event File Generation](#phase-4-event-file-generation)
6. [Phase 5: Preprocessing (fMRIPrep & Tedana)](#phase-5-preprocessing)
7. [Troubleshooting Guide](#troubleshooting-guide)
8. [File Organization Reference](#file-organization-reference)
9. [Key Concepts](#key-concepts)
10. [Pipeline Checkpoints](#pipeline-checkpoints)

---

## Quick Reference

### Essential Commands

```bash
# Phase 1: Bidsify (convert Flywheel to BIDS)
uv run python -m neuro_workflow.cli bidsify discovery \
    --output-dir /scratch/users/logben/discovery_bids -v

uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/validation_bids -v

# Phase 2: Migrate behavioral data
uv run python scripts/generate_behavioral_mapping.py \
    --output-config config/behavioral_session_mapping.json -v

uv run python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/stanford/.../raw_cleaned \
    --output-dir /network_grant/sourcedata \
    --excluded-output-dir /network_grant/excluded_sourcedata \
    --mapping-file config/behavioral_session_mapping.json -v

uv run python scripts/migrate_archive_behavioral_data.py \
    --output-dir /network_grant/sourcedata \
    --excluded-sourcedata-dir /network_grant/excluded_sourcedata \
    --mturk-dir /network_grant/mTurk -v

# Phase 3: Trim BOLD files and sync physiological data
uv run python src/neuro_workflow/post_processing/post_process_bids.py \
    --bids-dir /scratch/users/logben/discovery_bids \
    --bids-dir /scratch/users/logben/validation_bids \
    --bids-dir /scratch/users/logben/excluded_bids -v
```

### Current Status by Phase

| Phase | Status | Output | Last Run |
|-------|--------|--------|----------|
| 1: Bidsify | ✓ Complete | 3 BIDS directories | 2026-03-14 |
| 2: Behavioral Migration | ✓ Complete | sourcedata + excluded_sourcedata | 2026-03-13 |
| 3: BOLD Trimming | ✓ Complete | Trimmed BOLD, sync'd physio | 2026-03-16 |
| 4: Event Generation | ⏳ Planned | events.tsv files | TBD |
| 5: Preprocessing | 📋 Ready | fMRIPrep output | TBD |

---

## Phase 1: Bidsify (Flywheel → BIDS)

### Purpose
Convert Flywheel acquisition data (stored as DICOMs + JSON metadata) into BIDS-compliant directory structure with proper sidecar files, subject/session organization, and validation.

### Prerequisites
- Flywheel SDK and credentials configured
- `uv` package manager installed
- `bids-validator` available (via Singularity or system)
- Write access to `/scratch/users/logben/`

### Configuration Files

**Location:** `config/reconciliation_config.json`

This file handles special cases and session overrides:

```json
{
  "session_overrides": {
    "s03": {
      "22752": "s10"
    },
    "s29": {
      "22424": null
    }
  },
  "excluded_subjects": {
    "s1165": "data quality issues",
    "s1178": "incomplete acquisition",
    "s1266": "participant withdrew",
    "s1320": "technical problem",
    "s214": "data quality",
    "s222": "incomplete",
    "s250": "participant withdrew",
    "s297": "technical problem",
    "s432": "data quality",
    "s823": "incomplete acquisition",
    "s968": "participant withdrew"
  }
}
```

### Running Bidsify by Sample

#### Discovery Sample (5 subjects)
```bash
cd /home/users/logben/neuro_workflow

uv run python -m neuro_workflow.cli bidsify discovery \
    --output-dir /scratch/users/logben/discovery_bids \
    -v

# Expected: ~57 GB, 1,307 files
# Time: ~45 minutes
```

#### Validation Sample (41 subjects)
```bash
cd /home/users/logben/neuro_workflow

uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/validation_bids \
    -v

# Expected: ~810 GB, 24,872 files
# Time: ~4-5 hours
```

#### Excluded Subjects (11 subjects)
```bash
cd /home/users/logben/neuro_workflow

# Manually specify excluded subjects
uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/excluded_bids \
    --subjects s1165 s1178 s1266 s1320 s214 s222 s250 s297 s432 s823 s968 \
    -v

# Expected: ~49 GB, 1,551 files
# Time: ~1 hour
```

### What Gets Created

For each BIDS directory:

```
├── sub-001/
│   ├── ses-01/
│   │   ├── anat/
│   │   │   ├── sub-001_ses-01_T1w.nii.gz
│   │   │   ├── sub-001_ses-01_T1w.json
│   │   │   └── ...
│   │   ├── func/
│   │   │   ├── sub-001_ses-01_task-rest_bold.nii.gz
│   │   │   ├── sub-001_ses-01_task-rest_bold.json
│   │   │   ├── sub-001_ses-01_task-rest_events.tsv  [Phase 4 adds this]
│   │   │   └── ...
│   │   ├── fmap/
│   │   │   └── ... (fieldmap files)
│   │   └── dwi/
│   │       └── ... (diffusion files)
│   └── ses-02/
│       └── ...
├── sourcedata/
│   ├── reconciliation.json       (subject/session mapping, warnings)
│   ├── bidsify_log.json          (download logs from Flywheel)
│   ├── behavioral_data/          (Phase 2 adds in-scanner behavioral CSVs)
│   ├── out_scanner_behavior/     (Phase 2 adds out-of-scanner data)
│   └── survey_data/              (Phase 2 adds surveys + demographics)
├── .bidsignore                   (files to exclude from validation)
├── .bids-validation/
│   └── analysis.json             (BOLD validation results)
├── CHANGES
├── README
├── participants.tsv
└── dataset_description.json
```

### Bidsify Features (March 2026 Updates)

#### Parallel Processing
- **Workers:** 4 parallel Flywheel API clients (reduced from 16 to avoid rate limiting)
- **Trade-off:** Slower overall (~4-5 hours for validation) but more reliable

#### Safe Sidecar Patching
- **Retry Logic:** 3 attempts to patch JSON sidecars
- **Handles:** Missing TR, Units metadata, malformed JSON
- **Failure Mode:** Logs error with full context, continues with others

#### Duplicate File Detection
- **Anatomical duplicates:** Multiple T1w/T2w/T2star in same session → marked for .bidsignore
- **Diffusion duplicates:** Multiple DWI/dwi sequences → marked for .bidsignore
- **3D BOLD files:** Detected and excluded from processing
- **Output:** `sourcedata/reconciliation.json` documents all duplicates

#### Physiological Error Handling
- **gephysio failures:** Non-fatal warnings (previously silent skips)
- **Cardiac/Respiratory:** Sync'd with BOLD in Phase 3
- **Output:** `sourcedata/reconciliation.json` warning logs

#### Session Reconciliation
- Reads `reconciliation_config.json` for session overrides
- Maps Flywheel acquisition IDs to standardized session labels
- Example: s03 acquisition 22752 → ses-10
- Excluded sessions mapped to null (skipped)

### Verification Steps

#### 1. Check BIDS Structure
```bash
# Count subjects and sessions
find /scratch/users/logben/discovery_bids -type d -name "sub-*" | wc -l
find /scratch/users/logben/discovery_bids -type d -name "ses-*" | wc -l

# Expected: Discovery = 5 subjects, multiple sessions per subject
```

#### 2. Validate with BIDS Validator
```bash
# Via Singularity (recommended)
singularity run -B /scratch/users/logben \
    /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
    /scratch/users/logben/discovery_bids

# Should show:
# - 0 critical errors
# - Some warnings (pre-existing JSON issues, etc.)
```

#### 3. Check Reconciliation Output
```bash
# View subject/session mapping
cat /scratch/users/logben/discovery_bids/sourcedata/reconciliation.json | \
    jq '.subjects | keys'

# View warnings about duplicates, failed physio, etc.
cat /scratch/users/logben/discovery_bids/sourcedata/reconciliation.json | \
    jq '.warnings' | head -50
```

#### 4. Examine .bidsignore
```bash
# Files marked for exclusion
cat /scratch/users/logben/discovery_bids/.bidsignore | head -20

# Should include duplicate anatomicals, DWI, 3D BOLDs, etc.
```

#### 5. Check BOLD Validation Results
```bash
# TR-based short scan detection (Phase 3 uses these results)
cat /scratch/users/logben/discovery_bids/.bids-validation/analysis.json | \
    jq '.short_scans'
```

### Common Issues and Solutions

#### Issue: "ModuleNotFoundError: No module named 'neuro_workflow'"
**Cause:** Using system Python instead of uv
**Solution:** Always use `uv run python`

```bash
# WRONG
python -m neuro_workflow.cli bidsify discovery ...

# CORRECT
uv run python -m neuro_workflow.cli bidsify discovery ...
```

#### Issue: Flywheel API Rate Limiting
**Cause:** Too many parallel workers (>4) hitting API simultaneously
**Symptom:** Random download timeouts, "connection refused" errors
**Solution:** Already fixed in 2026-03-14 update (reduced to 4 workers)

#### Issue: JSON Patching Failures on Specific Subjects
**Subjects:** s956, s1267, s1351
**Cause:** Corrupted JSON from Flywheel extraction or concurrent write conflicts
**Solution:** Retry logic (3 attempts) now in place; if still fails:
1. Check individual file: `cat /scratch/.../sub-XXX/.../file.json`
2. If malformed, manually correct
3. Rerun bidsify for affected subject

```bash
uv run python -m neuro_workflow.cli bidsify validation \
    --subjects s956 \
    --output-dir /scratch/users/logben/validation_bids \
    -v
```

#### Issue: Missing Physiological JSON Sidecars
**Cause:** gephysio analysis failed during acquisition
**Solution:** Now captured in `sourcedata/reconciliation.json` warnings
- Check which physio files failed: `jq '.warnings.physio_failures' reconciliation.json`
- These are expected for some acquisitions
- If needed, manually generate minimal JSON templates

#### Issue: 3D BOLD Files Not Detected
**Solution:** Already integrated into validation analysis (Phase 3 uses detection)
- Marked in `.bidsignore`
- Documented in `sourcedata/reconciliation.json`

---

## Phase 2: Behavioral Data Migration

### Purpose
Migrate behavioral data (in-scanner CSVs, out-of-scanner behavioral, surveys, demographics, mTurk) from archive storage into organized sourcedata structure alongside BIDS data.

### Prerequisites
- Completed Phase 1 (Bidsify) for all three samples
- BIDS directories with `sourcedata/reconciliation.json`
- Access to archive directories:
  - `/oak/stanford/.../raw_cleaned/` (in-scanner behavioral CSVs)
  - `/oak/stanford/.../` (out-of-scanner, surveys, demographics, mTurk)
- Write access to `/network_grant/` for output

### Key Concept: Sample-Filtered Migration

All behavioral data is **sample-filtered** based on `reconciliation.json`:
- Discovery subjects: Only discovery sample data migrated
- Validation subjects: Only validation sample data migrated
- Excluded subjects: Data routed to separate `excluded_sourcedata/` directory
- mTurk: No filtering (all subjects included)

### Configuration Files

**Location:** `config/behavioral_session_mapping.json`

Generated by Phase 2a, used by Phase 2b and 2c:

```json
{
  "subjects": {
    "s03": {
      "sample": "discovery",
      "excluded": false,
      "sessions": [
        {"bids_session": "s10", "raw_session": "22752", "run": 1},
        ...
      ]
    },
    "s1165": {
      "sample": "validation",
      "excluded": true,
      "reason": "data quality issues",
      "sessions": [...]
    },
    ...
  }
}
```

### Phase 2a: Generate Behavioral Mapping

**Script:** `scripts/generate_behavioral_mapping.py`
**Purpose:** Create static mapping of Flywheel sessions → raw behavioral sessions
**Run once:** Before first behavioral migration

```bash
cd /home/users/logben/neuro_workflow

uv run python scripts/generate_behavioral_mapping.py \
    --discovery-bids /scratch/users/logben/discovery_bids \
    --validation-bids /scratch/users/logben/validation_bids \
    --excluded-bids /scratch/users/logben/excluded_bids \
    --output-config config/behavioral_session_mapping.json \
    -v

# Expected output:
# - 5 discovery subjects
# - 41 validation subjects
# - 11 excluded subjects
```

#### Verification
```bash
# Check mapping structure
uv run python -c "
import json
with open('config/behavioral_session_mapping.json') as f:
    data = json.load(f)
    for sample in ['discovery', 'validation', 'excluded']:
        count = sum(1 for s in data['subjects'].values() if s['sample'] == sample)
        print(f'{sample}: {count} subjects')
"

# Expected: discovery: 5, validation: 41, excluded: 11
```

### Phase 2b: Rename In-Scanner Behavioral to Sourcedata

**Script:** `scripts/rename_behavioral_to_sourcedata.py`
**Purpose:** Copy in-scanner behavioral CSVs to BIDS sourcedata layout
**Output:** `/network_grant/sourcedata/behavioral_data/sub-XXX/ses-YY/beh/`

```bash
cd /home/users/logben/neuro_workflow

uv run python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/stanford/nsg/share/STUDYNAME/data/raw_cleaned \
    --output-dir /network_grant/sourcedata \
    --excluded-output-dir /network_grant/excluded_sourcedata \
    --mapping-file config/behavioral_session_mapping.json \
    -v

# Expected: ~223 files (discovery) + ~1,887 files (validation)
# + ~234 files (excluded) in separate directory
```

#### What Gets Created

```
/network_grant/sourcedata/behavioral_data/
├── sub-s03/
│   ├── ses-01/
│   │   └── beh/
│   │       ├── s03_ses-01_task-goNogo_beh.csv
│   │       ├── s03_ses-01_task-goNogo_beh.json   [Phase 4 adds]
│   │       └── ...
│   └── ses-s10/
│       └── beh/
│           └── ...
├── sub-s43/
│   └── ...
└── sub-sXXX/
    └── ...

/network_grant/excluded_sourcedata/behavioral_data/
├── sub-s1165/
│   └── ...
└── ...
```

#### Verification
```bash
# Count in-scanner behavioral files
find /network_grant/sourcedata/behavioral_data -type f -name "*.csv" | wc -l
# Expected: ~2,110 files (223 discovery + 1,887 validation)

find /network_grant/excluded_sourcedata/behavioral_data -type f -name "*.csv" | wc -l
# Expected: ~234 files (excluded subjects)
```

### Phase 2c: Migrate Archive Behavioral Data

**Script:** `scripts/migrate_archive_behavioral_data.py`
**Purpose:** Migrate out-of-scanner behavior, surveys, demographics, mTurk
**Output:** Multiple directories organized by data type

```bash
cd /home/users/logben/neuro_workflow

uv run python scripts/migrate_archive_behavioral_data.py \
    --archive-dir /oak/stanford/nsg/share/STUDYNAME/data \
    --output-dir /network_grant/sourcedata \
    --excluded-sourcedata-dir /network_grant/excluded_sourcedata \
    --mturk-dir /network_grant/mTurk \
    -v

# Expected:
# - Out-of-scanner: ~1,224 files (sample-filtered)
# - Survey data: ~552 files JSON/CSV (sample-filtered)
# - Demographics: ~61 files (sample-filtered)
# - mTurk: ~2,437 files (all subjects, not filtered)
```

#### What Gets Created

```
/network_grant/sourcedata/
├── behavioral_data/              [Phase 2b created]
│   └── sub-XXX/ses-YY/beh/*.csv
├── out_scanner_behavior/         [Phase 2c creates]
│   ├── sub-s03/
│   │   ├── out_scanner_beh_session1.csv
│   │   └── ...
│   └── ...
└── survey_data/                  [Phase 2c creates]
    ├── sub-s03/
    │   ├── prescan_survey.csv
    │   ├── demographics.csv
    │   └── ...
    └── ...

/network_grant/excluded_sourcedata/
├── behavioral_data/
│   └── [same structure as above]
├── out_scanner_behavior/
│   └── [same structure]
└── survey_data/
    └── [same structure]

/network_grant/mTurk/             [No filtering]
├── s03/
│   ├── task1_responses.csv
│   └── ...
└── ...
```

#### Verification
```bash
# Count files by type
find /network_grant/sourcedata/out_scanner_behavior -type f | wc -l
find /network_grant/sourcedata/survey_data -type f | wc -l
find /network_grant/mTurk -type f | wc -l

# Check excluded subjects are in separate location
find /network_grant/excluded_sourcedata/out_scanner_behavior -type f | wc -l
```

### Phase 2: Common Issues and Solutions

#### Issue: "ModuleNotFoundError: No module named 'neuro_workflow'"
**Solution:** Use `uv run python` instead of system python

#### Issue: Excluded Subjects Not Separated
**Cause:** Scripts not marking excluded subjects correctly
**Solution:** Verify `behavioral_session_mapping.json` has `"excluded": true` for excluded subjects
```bash
uv run python -c "
import json
with open('config/behavioral_session_mapping.json') as f:
    data = json.load(f)
    excluded = [s for s, info in data['subjects'].items() if info['excluded']]
    print(f'Excluded subjects: {sorted(excluded)}')
"
```

#### Issue: Behavioral Files Not Found
**Cause:** Raw archive structure changed
**Solution:** Check archive directory structure matches script expectations
```bash
ls -la /oak/stanford/nsg/share/STUDYNAME/data/raw_cleaned | head -20
```

#### Issue: mTurk Data Missing
**Cause:** Archive path incorrect or mTurk directory structure different
**Solution:** Verify mTurk directory location
```bash
ls -la /oak/stanford/nsg/share/STUDYNAME/mTurk | head -20
```

---

## Phase 3: BOLD Trimming & Post-Processing

### Purpose
Remove dummy scans from BOLD files (standard fMRI preprocessing), trim behavioral data to match BOLD timeline, synchronize physiological data (cardiac, respiratory) with BOLD timing, and adjust event onsets.

### Prerequisites
- Completed Phase 1 (Bidsify) for all three samples
- Completed Phase 2 (Behavioral migration) - optional but recommended
- All BIDS directories read-writable (will be made read-only after completion)
- Phase 3 configuration in place: `config/task_tr_counts.json`

### Configuration Files

**Location:** `config/task_tr_counts.json`

Contains task-specific expected TR counts (used for short-scan detection):

```json
{
  "task_tr_counts": {
    "goNogo": 480,
    "stopSignalWDirectedForgetting": 480,
    "emotionRegulation": 480,
    "rest": 400,
    "sceneConstruction": 480,
    ...
  },
  "default_min_duration_minutes": 3.0
}
```

**Why needed:** Different tasks have different expected scan lengths. Use TR counts instead of duration for accurate detection.

### Running Phase 3

**Script:** `src/neuro_workflow/post_processing/post_process_bids.py`

```bash
cd /home/users/logben/neuro_workflow

uv run python src/neuro_workflow/post_processing/post_process_bids.py \
    --bids-dir /scratch/users/logben/discovery_bids \
    --bids-dir /scratch/users/logben/validation_bids \
    --bids-dir /scratch/users/logben/excluded_bids \
    -v

# Expected:
# - 15,851 BOLD volumes processed
# - 7 dummy scans removed from each (10.43s offset)
# - 15 scans require behavioral cutoff trimming
# - Physiological data synchronized
# - Event onsets adjusted
# - exclusions.json manifests created
```

#### What Gets Created/Modified

For each BIDS directory:

**Modified Files:**
- `sub-XXX/ses-YY/func/*_bold.nii.gz` - Dummy scans removed
- `sub-XXX/ses-YY/func/*_bold.json` - TR and timing metadata updated
- `sub-XXX/ses-YY/func/*_physio.tsv.gz` - Synchronized with BOLD
- `sourcedata/behavioral_data/sub-XXX/ses-YY/beh/*.csv` - Trimmed to BOLD duration

**New Files:**
- `sourcedata/exclusions.json` - Documents all trimming decisions and statistics
- `sub-XXX/ses-YY/func/*_events.tsv` - Event onsets adjusted by -10.43s

**Example exclusions.json:**
```json
{
  "summary": {
    "total_bold_files": 5000,
    "dummy_scans_removed": 35000,
    "behavioral_cutoffs_applied": 15,
    "physio_synchronized": 5000
  },
  "trimmed_scans": [
    {
      "file": "sub-s19/ses-07/func/sub-s19_ses-07_task-rest_bold.nii.gz",
      "reason": "behavioral_cutoff",
      "trim_volumes": 45,
      "original_volumes": 480,
      "final_volumes": 435
    },
    ...
  ],
  "behavioral_adjustments": {
    "sub-s19/ses-07/beh/sub-s19_ses-07_task-rest_beh.csv": {
      "original_rows": 120,
      "trimmed_rows": 108,
      "reason": "behavioral_cutoff_trimming"
    }
  }
}
```

### Trimming Details

#### Dummy Scan Removal (Standard)
- **All BOLD files:** First 7 dummy scans removed
- **Offset:** 10.43 seconds (7 × 1.49s TR)
- **Why:** Allows fMRI scanner magnetization to stabilize
- **Effect on events:** Event onsets shifted by -10.43s in events.tsv

#### Behavioral Cutoff Trimming (Selective)
- **Applied to:** 15 scans with participant behavioral issues
- **Detection:** Behavioral logs indicate early task termination
- **Example:** Participant fell asleep at volume 435 of 480
- **Action:** Trim BOLD file to 435 volumes, trim behavioral CSV to matching duration
- **Scans affected:**
  - Discovery: s19 ses-07/09 (4 scans), s43 ses-11 (1 scan)
  - Validation: s76, s1057, s1058, s1175, s1314, s247, s599, s874, s956 (9 scans)
  - Excluded: None

#### Physiological Synchronization
- **Cardiac data:** 100 Hz sampling → resampled to match BOLD
- **Respiratory data:** 25 Hz sampling → interpolated to BOLD TR
- **Timing alignment:** Adjusted to account for dummy scan removal
- **File format:** TSV gzip-compressed (standard BIDS)

#### Event Onset Adjustment
- **All events:** Shifted by -10.43s (dummy scan offset)
- **Behavioral cutoff scans:** Additional adjustment for volume trim
- **Example:** Original onset at 15.2s → adjusted to 4.77s
- **Note:** Behavioral cutoffs are rare; most adjustments are standard -10.43s

### Verification Steps

#### 1. Check Exclusions Manifest
```bash
# View trimming summary
cat /scratch/users/logben/discovery_bids/sourcedata/exclusions.json | \
    jq '.summary'

# Expected: 15,851 BOLD files processed, 7 dummy scans removed from each
```

#### 2. Verify Dummy Scan Removal
```bash
# Check a BOLD file's new shape (should be 7 volumes less)
nifti_tool -disp_hdr -infiles /scratch/users/logben/discovery_bids/sub-*/ses-*/func/*_bold.nii.gz | \
    grep "dim\[4\]" | head -5

# Should show volumes like 473, 393, 480-7=473, etc.
# (Original - 7 dummy scans)
```

#### 3. Check Event Adjustments
```bash
# Examine event timing (should be -10.43s from original)
head -5 /scratch/users/logben/discovery_bids/sub-s03/ses-01/func/sub-s03_ses-01_task-*_events.tsv

# Should show onsets like: 0.1, 5.3, 10.5 (dummy scan offset applied)
```

#### 4. Verify Behavioral File Trimming
```bash
# Count rows in behavioral CSV before and after
# (documented in exclusions.json)
cat /scratch/users/logben/discovery_bids/sourcedata/exclusions.json | \
    jq '.behavioral_adjustments'

# Example: 120 rows → 108 rows due to behavioral cutoff
```

#### 5. Validate BIDS After Trimming
```bash
# Run BIDS validator again (should still pass)
singularity run -B /scratch/users/logben \
    /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
    /scratch/users/logben/discovery_bids

# Should show: 0 critical errors
```

### Phase 3: Common Issues and Solutions

#### Issue: "Dummy scans not removed - volumes unchanged"
**Cause:** BOLD file already pre-trimmed or Phase 3 skipped
**Solution:** Check exclusions.json to confirm processing:
```bash
cat /scratch/users/logben/discovery_bids/sourcedata/exclusions.json | \
    jq '.summary.dummy_scans_removed'
```

#### Issue: Event onsets not adjusted
**Cause:** Phase 4 (event generation) not yet complete
**Solution:** Phase 3 pre-calculates adjustments; Phase 4 applies them
- Events with -10.43s adjustment are ready for Phase 4

#### Issue: Behavioral cutoff not detected
**Cause:** Behavioral data missing or format incorrect
**Solution:** Check behavioral_data directory structure
```bash
ls -la /network_grant/sourcedata/behavioral_data/sub-XXX/ses-YY/beh/ | head
```

#### Issue: Physiological sync failed
**Cause:** Missing cardiac/respiratory files
**Solution:** Check which physio files exist
```bash
find /scratch/users/logben/discovery_bids -name "*_physio.tsv.gz" | head
# Should have matching physio files for most BOLD files
```

---

## Phase 4: Event File Generation

### Purpose
Generate BIDS-compliant events.tsv files for each task-based BOLD scan, with onsets adjusted for dummy scan removal and behavioral cutoffs.

### Status: ⏳ Planned for Future Implementation

### Configuration
- Task definitions: `config/task_definitions.json` (to be created)
- Behavioral mapping: `config/behavioral_session_mapping.json` (already exists)

### Expected Inputs
- Behavioral CSV files in `sourcedata/behavioral_data/` (Phase 2b output)
- Event adjustment metadata in `sourcedata/exclusions.json` (Phase 3 output)
- Task-to-behavioral-file mappings

### Expected Outputs
```
sub-XXX/ses-YY/func/sub-XXX_ses-YY_task-taskName_events.tsv
```

**Format:**
```
onset	duration	trial_type	response_time	correct
0.1	2.3	go	0.45	1
5.3	2.3	no-go	NaN	NaN
10.5	2.3	go	0.52	1
```

### Commands (When Ready)
```bash
# Generate events files from behavioral data
uv run python src/neuro_workflow/events/generate_events.py \
    --bids-dir /scratch/users/logben/discovery_bids \
    --behavioral-mapping config/behavioral_session_mapping.json \
    --exclusions-manifest /scratch/users/logben/discovery_bids/sourcedata/exclusions.json \
    -v
```

### Notes for Implementation
- Must preserve dummy scan offset (-10.43s) applied in Phase 3
- Handle behavioral cutoff scans (event file length matches trimmed BOLD)
- Generate missing trial_type/response_time from behavioral CSV columns
- Validate event timing against BOLD file duration

---

## Phase 5: Preprocessing (fMRIPrep & Tedana)

### Purpose
Apply standard fMRI preprocessing including motion correction, registration to standard space, and multi-echo ICA denoising (Tedana).

### Prerequisites
- Completed Phase 1-3 (Bidsify, Behavioral, BOLD Trimming)
- Phase 4 events.tsv files (when ready) - optional but recommended
- fMRIPrep and Tedana available (Singularity or conda)

### fMRIPrep Configuration

#### Command Template
```bash
singularity run --cleanenv -B /scratch/users/logben:/scratch/users/logben \
    /home/groups/russpold/singularity_images/fmriprep_VERSION.simg \
    /scratch/users/logben/discovery_bids \
    /scratch/users/logben/discovery_bids/derivatives/fmriprep \
    participant \
    --participant-label 03 43 57 \
    --skip-bids-validation \
    --fd-spike-threshold 0.5 \
    --dvars-spike-threshold 1.5 \
    --dummy-scans 0 \
    --output-spaces MNI152NLin2009cAsym fsaverage5 \
    --nthreads 8 \
    --omp-nthreads 4 \
    --use-aroma
```

#### Key Parameters for This Dataset

| Parameter | Value | Reason |
|-----------|-------|--------|
| `--dummy-scans 0` | 0 | Already removed in Phase 3 |
| `--fd-spike-threshold` | 0.5 | Moderate motion threshold |
| `--dvars-spike-threshold` | 1.5 | Detect signal spikes |
| `--output-spaces` | MNI152NLin2009cAsym fsaverage5 | Standard spaces for fMRI |
| `--use-aroma` | (flag) | ICA-AROMA denoising enabled |

#### Multi-Echo Handling
If using multi-echo sequences:
- fMRIPrep automatically detects multi-echo BOLD files
- Generates optimal echo combination (OEC) BOLD
- Outputs to `*_space-*_boldref.nii.gz`

### Tedana Configuration (Post-fMRIPrep)

#### When to Use Tedana
- **Use:** If multi-echo BOLD sequences were collected
- **Skip:** If single-echo BOLD only (standard case)

#### Command Template
```bash
singularity run --cleanenv -B /scratch/users/logben:/scratch/users/logben \
    /home/groups/russpold/singularity_images/tedana_VERSION.simg \
    /scratch/users/logben/discovery_bids/derivatives/fmriprep/sub-03/ses-01/func/*_space-MNI152NLin2009cAsym_desc-OC_bold.nii.gz \
    --tr 1.49 \
    --out-dir /scratch/users/logben/discovery_bids/derivatives/tedana/sub-03/ses-01 \
    --mask /scratch/users/logben/discovery_bids/derivatives/fmriprep/sub-03/ses-01/func/*_space-MNI152NLin2009cAsym_desc-brain_mask.nii.gz \
    --fittype curvefit
```

#### Tedana Output
```
derivatives/tedana/sub-03/ses-01/
├── sub-03_ses-01_space-MNI152NLin2009cAsym_desc-ICA_bold.nii.gz
├── sub-03_ses-01_space-MNI152NLin2009cAsym_desc-ICA_components.nii.gz
├── sub-03_ses-01_AIC.nii.gz
├── sub-03_ses-01_BIC.nii.gz
├── sub-03_ses-01_mixing_matrix.tsv
└── report.html
```

### Preprocessing Checkpoints

#### Checkpoint 1: Motion Summary
```bash
# Check motion statistics across subjects
cat /scratch/users/logben/discovery_bids/derivatives/fmriprep/sub-*/ses-*/func/*_confounds.tsv | \
    awk '{print $2, $3}' | \
    sort -n | tail -20

# Flag subjects with excessive motion (>0.5mm framewise displacement)
```

#### Checkpoint 2: Registration Quality
```bash
# Visual inspection of registration (use FSLeyes or similar)
# Check if native anatomical properly aligned to standard space
fsleyes /scratch/users/logben/discovery_bids/derivatives/fmriprep/sub-03/ses-01/anat/sub-03_ses-01_space-MNI152NLin2009cAsym_T1w.nii.gz
```

#### Checkpoint 3: Tedana Component Selection
```bash
# Review auto-selected good/bad components
cat /scratch/users/logben/discovery_bids/derivatives/tedana/sub-03/ses-01/sub-03_ses-01_components.tsv | \
    awk '{print $1, $2}' | head -20
```

### Common Preprocessing Issues and Solutions

#### Issue: "Brain mask appears too small"
**Cause:** Unusual anatomy or poor T1 quality
**Solution:** Use fMRIPrep's `--extra-bold-pe-direction` or manual mask

#### Issue: Poor registration to standard space
**Cause:** Low T1 contrast or motion artifacts
**Solution:** Check T1 quality, consider re-running with different registration algorithm

#### Issue: Tedana fails on multi-echo data
**Cause:** Echo files not properly formatted or detected
**Solution:** Verify echo times in BOLD JSON sidecars

---

## Troubleshooting Guide

### General Issues

#### Python/Module Errors
| Error | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'neuro_workflow'` | Using system python | Always use `uv run python` |
| `ImportError: No module named 'flywheel'` | Flywheel SDK not installed | Run `uv install` or check pyproject.toml |
| `json.decoder.JSONDecodeError` | Malformed JSON file | Check file with `python -m json.tool` |

#### Flywheel API Issues
| Error | Cause | Solution |
|-------|-------|----------|
| `Connection timeout` | API rate limiting or network issue | Reduce parallel workers, wait 10min, retry |
| `Authentication failed` | Flywheel credentials missing/expired | Set FW_TOKEN env var, check permissions |
| `DICOM download failed` | Incomplete acquisition in Flywheel | Check reconciliation.json, may be expected |

#### BIDS Validation Issues
| Error | Cause | Solution |
|-------|-------|----------|
| `Critical: Missing .json sidecars` | Phase 1 incomplete or JSON creation failed | Rerun bidsify with retry logic |
| `Issue: Missing task definition in events.tsv` | Phase 4 not yet run | Generated in Phase 4 (future) |
| `Invalid duration in events.tsv` | Event beyond BOLD file end | Check Phase 3 trimming calculations |

### Phase-Specific Troubleshooting

#### Phase 1: Bidsify
- See "Phase 1: Common Issues and Solutions"

#### Phase 2: Behavioral Migration
- See "Phase 2: Common Issues and Solutions"

#### Phase 3: BOLD Trimming
- See "Phase 3: Common Issues and Solutions"

#### Phase 4: Events (When Ready)
- Check behavioral CSV format matches task_definitions.json
- Verify onsets fall within BOLD file duration
- Confirm dummy scan offset (-10.43s) applied

#### Phase 5: Preprocessing
- See "Preprocessing Checkpoints"

### Debug Workflows

#### Diagnose Bidsify Failures
```bash
# Check logs
cat /scratch/users/logben/discovery_bids/sourcedata/bidsify_log.json | \
    jq '.errors' | head -50

# Check warnings
cat /scratch/users/logben/discovery_bids/sourcedata/reconciliation.json | \
    jq '.warnings' | head -50
```

#### Find Missing Files
```bash
# Find BOLD files without JSON sidecars
find /scratch/users/logben/discovery_bids -name "*_bold.nii.gz" -not -exec test -f "{}".json \; -print

# Find expected but missing behavioral files
find /network_grant/sourcedata/behavioral_data -type d -empty
```

#### Check Data Integrity
```bash
# Verify all files are readable
find /scratch/users/logben/discovery_bids -type f -exec file {} \; | \
    grep -v "gzip compressed data" | \
    grep -v "JSON" | \
    grep -v "ASCII text"

# Should be mostly gzip and JSON files
```

---

## File Organization Reference

### BIDS Output Directories

```
/scratch/users/logben/
├── discovery_bids/           (5 subjects, 57 GB)
│   ├── sub-XXX/
│   ├── sourcedata/
│   │   ├── reconciliation.json
│   │   ├── bidsify_log.json
│   │   ├── exclusions.json           [Phase 3]
│   │   ├── behavioral_data/          [Phase 2b]
│   │   ├── out_scanner_behavior/     [Phase 2c]
│   │   └── survey_data/              [Phase 2c]
│   ├── .bidsignore
│   ├── .bids-validation/
│   │   └── analysis.json
│   └── derivatives/
│       ├── fmriprep/                 [Phase 5]
│       └── tedana/                   [Phase 5]
│
├── validation_bids/          (41 subjects, 810 GB)
│   └── [same structure]
│
└── excluded_bids/            (11 subjects, 49 GB)
    └── [same structure]
```

### Archive Behavioral Data Locations

```
/network_grant/
├── sourcedata/               (Sample-filtered)
│   ├── behavioral_data/
│   │   └── sub-XXX/ses-YY/beh/*.csv
│   ├── out_scanner_behavior/
│   │   └── sub-XXX/*.csv
│   └── survey_data/
│       └── sub-XXX/*.csv
├── excluded_sourcedata/      (Excluded subjects only)
│   ├── behavioral_data/
│   ├── out_scanner_behavior/
│   └── survey_data/
└── mTurk/                    (All subjects, no filtering)
    └── sub-XXX/
        └── *.csv
```

### Project Source Code

```
/home/users/logben/neuro_workflow/
├── src/neuro_workflow/
│   ├── cli.py                        (Entry point)
│   ├── bidsify/
│   │   ├── run.py                    (Phase 1 orchestrator)
│   │   ├── bids_writer.py
│   │   ├── flywheel_downloader.py
│   │   └── integration.py
│   ├── behavioral_archive/
│   │   ├── sample_validation.py      (Load sample config)
│   │   └── migrate.py                (Phase 2c core)
│   ├── post_processing/
│   │   └── post_process_bids.py      (Phase 3 orchestrator)
│   ├── bids_validation/
│   │   └── bold_analyzer.py          (TR-based short scan detection)
│   └── events/                       (Phase 4 placeholder)
│       └── generate_events.py        (Future)
│
├── scripts/
│   ├── generate_behavioral_mapping.py (Phase 2a)
│   ├── rename_behavioral_to_sourcedata.py (Phase 2b)
│   └── migrate_archive_behavioral_data.py (Phase 2c)
│
├── config/
│   ├── reconciliation_config.json    (Session overrides, excluded subjects)
│   ├── behavioral_session_mapping.json (Phase 2 output)
│   ├── task_tr_counts.json           (Task-specific TR counts)
│   └── task_definitions.json         (Phase 4 placeholder)
│
├── docs/
│   ├── WORKFLOW.md                   (This file)
│   ├── ARCHITECTURE.md               (Technical deep dive)
│   ├── BIDS-TRIMMING-AUDIT-2026-03-16.md
│   ├── STATUS-UPDATE-MAR16-2026.md
│   └── tr-based-short-scan-detection.md
│
├── tests/
│   ├── bids_validation/
│   ├── behavioral_archive/
│   └── post_processing/
│
└── pyproject.toml                    (Dependencies)
```

---

## Key Concepts

### Subject Aliases (Flywheel vs. BIDS)

Flywheel stores subjects by ID from acquisition system. BIDS standardizes to `sub-XXX` prefix.

**Mapping Rules:**
- Flywheel ID → BIDS subject name
- Example: Flywheel subject "345" → `sub-345` in BIDS
- Behavioral data: Subject directories use same ID (s003, s345, etc.)

**Finding mapping:**
```bash
cat /scratch/users/logben/discovery_bids/sourcedata/reconciliation.json | \
    jq '.subjects'
```

### Session Reconciliation

Flywheel acquisition IDs don't map cleanly to BIDS session numbers. Phase 1 uses `reconciliation_config.json` to map.

**Example Override:**
```json
{
  "session_overrides": {
    "s03": {
      "22752": "s10"  // Flywheel session 22752 → BIDS ses-10
    }
  }
}
```

**Why needed:**
- Flywheel stores session data by acquisition system ID (numeric, hard to interpret)
- BIDS requires semantic session labels (e.g., session 1, 10, etc.)
- Some sessions excluded (null values) due to incomplete data

**Finding overrides:**
```bash
cat /scratch/users/logben/discovery_bids/sourcedata/reconciliation.json | \
    jq '.session_mapping.s03'
```

### Excluded Subjects

11 subjects excluded from analysis due to data quality, incomplete acquisition, or participant withdrawal.

**List:**
- s1165, s1178, s1266, s1320, s214, s222, s250, s297, s432, s823, s968

**Handling:**
- Separate BIDS directory: `/scratch/users/logben/excluded_bids`
- Separate sourcedata: `/network_grant/excluded_sourcedata`
- NOT included in main analysis pipelines

**Marked in reconciliation_config.json:**
```json
{
  "excluded_subjects": {
    "s1165": "data quality issues",
    "s1178": "incomplete acquisition",
    ...
  }
}
```

### Dummy Scan Removal

Standard fMRI preprocessing step: discard first N volumes to allow magnetization settling.

**This dataset:**
- **Scans to remove:** First 7 volumes per BOLD file
- **TR:** 1.49 seconds
- **Time removed:** 7 × 1.49s = 10.43 seconds
- **When:** Phase 3 (automatically)
- **Impact:** Event onsets shifted by -10.43s

**Why this matters:**
- fMRIPrep expects original unprocessed BOLD files
- Use `--dummy-scans 0` flag (already removed pre-preprocessing)
- Event timing must match trimmed BOLD duration

### Behavioral Cutoff Trimming

Some participants stopped responding before end of task (e.g., fell asleep).

**Detection method:** Behavioral CSV has fewer rows than expected

**Action taken (Phase 3):**
- Trim BOLD file to match behavioral duration
- Trim behavioral CSV to match BOLD volume count
- Document in `sourcedata/exclusions.json`

**Affected scans (15 total):**
- Discovery: 5 scans (s19, s43)
- Validation: 9 scans (s76, s1057, s1058, s1175, s1314, s247, s599, s874, s956)
- Excluded: 0 scans

### Physiological Data Synchronization

Cardiac and respiratory data collected during fMRI at different sampling rates.

**Synchronization (Phase 3):**
- Cardiac (100 Hz): Downsampled to match BOLD TR (1.49s ≈ 0.67 Hz)
- Respiratory (25 Hz): Interpolated to BOLD TR grid
- Timing: Adjusted for dummy scan removal and behavioral cutoffs

**Output format:** BIDS-standard gzip-compressed TSV

**Usage in Tedana:** Automatic inclusion in ICA denoising

---

## Pipeline Checkpoints

### Pre-Pipeline Checks

- [ ] Flywheel credentials configured (FW_TOKEN env var set)
- [ ] Write access to `/scratch/users/logben/` verified
- [ ] Write access to `/network_grant/` verified
- [ ] `uv` package manager installed
- [ ] BIDS validator available (Singularity image present)

### Phase 1 Checkpoints

- [ ] Bidsify discovery completed (57 GB, 1,307 files)
- [ ] Bidsify validation completed (810 GB, 24,872 files)
- [ ] Bidsify excluded completed (49 GB, 1,551 files)
- [ ] BIDS validator shows 0 critical errors (may have warnings)
- [ ] `sourcedata/reconciliation.json` created with subject/session mapping
- [ ] `.bids-validation/analysis.json` shows BOLD quality assessment
- [ ] `.bidsignore` includes duplicate scans and 3D BOLDs

### Phase 2 Checkpoints

- [ ] `config/behavioral_session_mapping.json` generated (Phase 2a)
  - 5 discovery subjects confirmed
  - 41 validation subjects confirmed
  - 11 excluded subjects marked
- [ ] In-scanner behavioral CSVs copied to sourcedata (Phase 2b)
  - 223 files in discovery
  - 1,887 files in validation
  - 234 files in excluded_sourcedata
- [ ] Archive behavioral data migrated (Phase 2c)
  - 1,224 out-of-scanner behavior files (sample-filtered)
  - 552 survey data files (sample-filtered)
  - 2,437 mTurk files (all subjects)
  - Excluded subjects in separate directory

### Phase 3 Checkpoints

- [ ] Dummy scans removed from all BOLD files (7 volumes × 15,851 scans = 110,957 volumes)
- [ ] `sourcedata/exclusions.json` created with trimming statistics
- [ ] Behavioral cutoff trimming applied (15 scans)
  - 5 discovery scans trimmed
  - 9 validation scans trimmed
  - 1 validation scan marked with "fell_asleep" flag
- [ ] Physiological data synchronized with BOLD
- [ ] Event onsets adjusted by -10.43s (dummy scan offset)
- [ ] BIDS validator still shows 0 critical errors after trimming
- [ ] All BIDS directories made read-only

### Phase 4 Checkpoints (Future)

- [ ] `config/task_definitions.json` created with task-to-event mappings
- [ ] Events.tsv files generated for all task-based BOLD scans
- [ ] Event onsets verified within BOLD file duration
- [ ] Behavioral cutoff scans have events matching BOLD trim

### Phase 5 Checkpoints

- [ ] fMRIPrep ran successfully on all subjects
  - Anatomical processing complete
  - Functional preprocessing complete
  - Registration to standard space verified
- [ ] Preprocessing derivatives in place
- [ ] Motion summary shows acceptable FD values (<0.5mm mean)
- [ ] Tedana component selection verified (if multi-echo)
- [ ] Final QA completed

### Final Validation

- [ ] All derivatives are valid (BIDS standard)
- [ ] Dataset summary statistics documented
- [ ] README and CHANGES files updated with processing details
- [ ] Data ready for statistical analysis or model fitting

---

## Summary

This document provides a complete walkthrough of the neuro_workflow pipeline from Flywheel acquisition data through preprocessing. Each phase is self-contained but depends on successful completion of previous phases.

### Current Status (as of 2026-03-16)
- **Phase 1 (Bidsify):** ✓ Complete - 57 subjects across 3 BIDS directories
- **Phase 2 (Behavioral):** ✓ Complete - 2,344 behavioral files organized
- **Phase 3 (BOLD Trimming):** ✓ Complete - 110,957 dummy volumes removed
- **Phase 4 (Events):** ⏳ Planned
- **Phase 5 (Preprocessing):** 📋 Ready

For technical details beyond this guide, see `ARCHITECTURE.md` and individual phase audit reports.
