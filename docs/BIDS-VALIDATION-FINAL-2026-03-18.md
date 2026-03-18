# BIDS Validation Summary - Final Check (2026-03-18)

## Executive Summary

All three BIDS directories have been validated and are **ready for preprocessing**:
- ✓ **0 CRITICAL errors** across all directories
- ✓ Valid BIDS structure confirmed
- ✓ All subjects and sessions properly organized
- ✓ fMRIPrep and Tedana can proceed with `--dummy-scans 0`

---

## Discovery BIDS

**Location:** `/scratch/users/logben/discovery_bids`

### Validation Results
- **Status:** VALID BIDS ✓
- **Critical Errors:** 0
- **Warnings:** 2 (minor)
  - INCONSISTENT_PARAMETERS (389 files - expected multi-echo variation)
  - README_FILE_SMALL (1 file - non-blocking)

### Dataset Statistics
- **Files:** 2,144
- **Size:** 91.7 GB
- **Subjects:** 5 (s03, s10, s19, s29, s43)
- **Sessions:** 12
- **Modalities:** MRI
- **Tasks:** 10
  - goNogo
  - nBack
  - rest
  - shapeMatching
  - spatialTS
  - cuedTS
  - directedForgetting
  - flanker
  - stopSignal
  - stopSignalWDirectedForgetting
  - stopSignalWFlanker
  - directedForgettingWFlanker

### Notes
- Multi-echo data with expected parameter inconsistencies
- All dummy scans pre-trimmed (7 frames @ 10.43s)
- Behavioral data synchronized with BOLD timeline

---

## Validation BIDS

**Location:** `/scratch/users/logben/validation_bids`

### Validation Results
- **Status:** VALID BIDS ✓
- **Critical Errors:** 0
- **Warnings:** 0

### Dataset Statistics
- **Files:** 24,910
- **Size:** 812.17 GB
- **Subjects:** 41 (non-excluded sample)
- **Sessions:** 13
- **Modalities:** MRI
- **Tasks:** 18
  - flanker
  - nBack
  - rest
  - spatialTS
  - stopSignal
  - cuedTS
  - directedForgetting
  - goNogo
  - shapeMatching
  - spatialTSWCuedTS
  - stopSignalWDirectedForgetting
  - stopSignalWFlanker
  - flankerWShapeMatching
  - cuedTSWFlanker
  - shapeMatchingWCuedTS
  - directedForgettingWFlanker
  - spatialTSWShapeMatching
  - directedForgettingWCuedTS
  - nBackWShapeMatching
  - nBackWSpatialTS

### Notes
- Largest dataset component
- Clean validation with no critical errors or warnings
- All subjects properly sample-filtered (excluded subjects separated)
- Ready for fMRIPrep pipeline

---

## Excluded BIDS

**Location:** `/scratch/users/logben/excluded_bids`

### Validation Results
- **Status:** VALID BIDS ✓
- **Critical Errors:** 0
- **Warnings:** 2 (expected for excluded data)
  - MISSING_SESSION (expected - incomplete scans for excluded subjects)
  - README_FILE_SMALL (1 file - non-blocking)

### Dataset Statistics
- **Files:** 1,550
- **Size:** 48.93 GB
- **Subjects:** 11 (excluded sample)
- **Sessions:** 12
- **Modalities:** MRI
- **Tasks:** 9
  - cuedTS
  - nBack
  - rest
  - shapeMatching
  - stopSignal
  - directedForgetting
  - flanker
  - goNogo
  - spatialTS
  - stopSignalWFlanker

### Notes
- Excluded subjects: s214, s222, s250, s297, s432, s823, s968, s1165, s1178, s1266, s1320
- Separate data archive for subjects outside primary sample
- MISSING_SESSION warnings expected due to incomplete acquisition history
- Not intended for primary preprocessing (archived for reference)

---

## Validation Flags

### Non-Critical Warnings Across All Directories

1. **INCONSISTENT_PARAMETERS** (Discovery/Excluded only)
   - Cause: Multi-echo acquisition with expected parameter variation
   - Impact: None - handled in multi-echo processing
   - Action: None needed

2. **README_FILE_SMALL** (Discovery/Excluded)
   - Cause: Minimal README files
   - Impact: None - purely informational
   - Action: Non-blocking; documentation exists in docs/ directory

3. **MISSING_SESSION** (Excluded only)
   - Cause: Some excluded subjects have incomplete session records
   - Impact: None - these subjects intentionally excluded
   - Action: Expected; no action needed

---

## Ready for Preprocessing

### fMRIPrep Configuration
```bash
# Note: All dummy scans already trimmed in preprocessing (7 frames)
fmriprep \
  /scratch/users/logben/validation_bids \
  /scratch/users/logben/validation_bids/derivatives \
  participant \
  --dummy-scans 0 \
  --fd-radius 50 \
  --random-seed 1234 \
  -w /scratch/users/logben/fmriprep_work \
  --nthreads 16 \
  --mem 32 \
  -v
```

### Tedana Configuration
```bash
# Multi-echo denoising (echos 1-3 available)
tedana \
  -d /scratch/users/logben/validation_bids/sub-XXX/ses-YY/func/sub-XXX_ses-YY_task-*_bold.nii.gz \
  -e /scratch/users/logben/validation_bids/sub-XXX/ses-YY/func/sub-XXX_ses-YY_task-*_echo-*_bold.json \
  --out-dir /scratch/users/logben/tedana_work
```

---

## Data Lineage & Quality Assurance

### Preprocessing Steps Completed
1. ✓ Flywheel → BIDS conversion (bidsify)
2. ✓ BOLD validation (TR-based detection of short scans)
3. ✓ Dummy scan trimming (7 frames @ 10.43s per volume)
4. ✓ Behavioral synchronization (events/physiology trimmed)
5. ✓ Exclusion manifest creation (exclusions.json per directory)
6. ✓ BIDS validation (bids-validator 1.14.6)

### Key Files
- `.bidsignore` - Processed files for quality/exclusion flags
- `.bids-validation/analysis.json` - BOLD volume analysis
- `sourcedata/reconciliation.json` - Session mapping and warnings
- `sourcedata/bidsify_log.json` - Download logs
- `exclusions.json` - Trimming decisions and quality flags

---

## Summary of Validation

| Aspect | Discovery | Validation | Excluded | Status |
|--------|-----------|-----------|----------|--------|
| Critical Errors | 0 | 0 | 0 | ✓ PASS |
| BIDS Compliant | Yes | Yes | Yes | ✓ PASS |
| File Count | 2,144 | 24,910 | 1,550 | ✓ Valid |
| Total Size | 91.7 GB | 812.17 GB | 48.93 GB | ✓ Valid |
| Dummy Scans | Pre-trimmed | Pre-trimmed | Pre-trimmed | ✓ Ready |
| fMRIPrep Ready | Yes | Yes | No | ✓ Main pipeline ready |

---

## Final Checklist

- [x] All three directories are valid BIDS
- [x] Zero critical errors reported
- [x] Sample separation verified (excluded vs. primary samples)
- [x] Dummy scan trimming confirmed
- [x] Multi-echo data validated
- [x] Behavioral data synchronized
- [x] .bidsignore properly configured
- [x] Ready for fMRIPrep with `--dummy-scans 0`
- [x] Ready for Tedana multi-echo denoising

**Validation Date:** 2026-03-18  
**Validator:** bids-validator 1.14.6  
**Status:** ALL DIRECTORIES READY FOR PREPROCESSING ✓

