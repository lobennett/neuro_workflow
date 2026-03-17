# Validation Subjects Resolution - s295 and s321 Added

**Date**: March 17, 2026
**Issue**: Validation BIDS missing 2 subjects (39/41 instead of 41/41)
**Status**: ✓ RESOLVED

## Problem

Validation BIDS was missing 2 subjects from the expected 41 non-excluded validation sample:
- **s295**: Unavailable during initial bidsify run
- **s321**: Unavailable during initial bidsify run

## Resolution

### 1. Identified Missing Subjects
```
Expected non-excluded validation: 41
Actual in validation_bids: 39
Missing: s295, s321
```

### 2. Made validation_bids Writable
```bash
chmod -R u+w /scratch/users/logben/validation_bids
```

### 3. Re-ran Bidsify for Missing Subjects
Submitted SLURM job to add s295 and s321:
```bash
run_bidsify(
    sample_name="validation",
    output_dir=Path("/scratch/users/logben/validation_bids"),
    subjects=["s295", "s321"],
    overwrite=True
)
```

### 4. Verified Results
- **s295**: 11 sessions, 156 BOLD files ✓
- **s321**: 13 sessions, 168 BOLD files ✓
- Updated reconciliation.json: 41/41 subjects

### 5. Re-secured Directory
Made validation_bids read-only (dr-xr-xr-x) for preprocessing

## Final BIDS Status - ALL COMPLETE ✓

| BIDS Dataset | Subjects | BOLD Files | Status |
|---|---|---|---|
| **Discovery** | 5/5 | 882 | Read-only ✓ |
| **Validation** | 41/41 | 6,923 | Read-only ✓ |
| **Excluded** | 11/11 | 417 | Read-only ✓ |

### Total
- **57 subjects** across all BIDS directories
- **8,222 BOLD files**
- All directories verified read-only for preprocessing handoff

## Ready for Preprocessing

All BIDS directories are now:
- ✓ Complete with all expected subjects
- ✓ Validated against BIDS specification
- ✓ Read-only for data integrity
- ✓ Ready for fMRIPrep with `--dummy-scans 0`
- ✓ Ready for Tedana multi-echo denoising

---

**Validation BIDS is now complete with all 41/41 non-excluded subjects.**
