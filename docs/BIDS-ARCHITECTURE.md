# BIDS Data Architecture (Mar 19, 2026)

## Overview

The neuro_workflow uses a clean separation between behavioral source data (on Oak) and BIDS-compliant datasets (in /scratch/). This document explains the architecture and resolves common questions about data organization.

## Data Locations

### 1. Behavioral CSVs (Canonical Source)
**Location**: `/oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior/`

**Structure**:
```
sub-s03/ses-01/beh/sub-s03_ses-01_task-*.csv
sub-s03/ses-02/beh/sub-s03_ses-02_task-*.csv
...
sub-s1399/ses-12/beh/sub-s1399_ses-12_task-*.csv
```

**Contents**:
- 2,107 behavioral CSV files total
- Discovery sample: 223 files (5 subjects)
- Validation sample: 1,884 files (41 subjects)
- Raw data from behavioral experiments

**Status**: Frozen, read-only (stable reference)

### 2. BIDS Datasets (Generated)
**Locations**:
- Discovery: `/scratch/users/logben/discovery_bids/`
- Validation: `/scratch/users/logben/validation_bids/`
- Excluded: `/scratch/users/logben/excluded_bids/`

**Structure**:
```
sub-*/
├── ses-*/
│   ├── anat/       (T1w, T2w images)
│   ├── func/       (BOLD images + events.tsv)
│   └── dwi/        (DWI images, if present)
└── derivatives/    (preprocessing outputs)
```

**What BIDS Contains**:
- ✓ Anatomical scans (T1w, T2w)
- ✓ Functional BOLD scans
- ✓ Events.tsv files (generated from behavioral CSVs)
- ✓ Physiological recordings (cardiac, respiratory)
- ✗ Behavioral CSV files (external reference only)

**Status**: Read-only, production-ready

## Important Clarification: Why No Behavioral CSVs in BIDS

**Common Question**: "The behavioral files are in /oak/.../sourcedata/, so why aren't they also in /scratch/.../sourcedata/?"

**Answer**:
1. **Single Source of Truth**: Behavioral data lives on Oak (institutional storage with backups)
2. **BIDS Compliance**: sourcedata/ in BIDS is for archival versions of converted files, not external references
3. **Storage Efficiency**: No duplication of 2,107 CSV files (would be ~2GB if copied)
4. **Clarity**: BIDS directories contain only what was generated, not external data dependencies

## Data Flow

```
Raw Behavioral Data (Oak)
    ↓
generate_behavioral_mapping.py
    ↓
Session mappings (config/behavioral_session_mapping.json)
    ↓
rename_behavioral_to_sourcedata.py
    ↓
Behavioral CSVs on Oak (canonical, unchanged)
    ↓
create_events.py (reads from Oak)
    ↓
events.tsv files → BIDS func/ directories
```

**Note**: Event generation reads behavioral files from Oak, does NOT require them to be in BIDS.

## .bidsignore Content

### What's in .bidsignore (March 19, 2026)

**1. Anatomical Duplicates** (chosen during QA)
```
# Example: kept ses-05 T1w (better quality), excluded earlier acquisitions
sub-s19/ses-01/anat/sub-s19_ses-01_acq-MPRAGEPromo_T1w.*
```

**2. BOLD Scans Without Behavioral Data** (for transparency)
```
# s03 ses-01 nBack: BOLD exists but behavioral in ses-02 (scan 1 had issues)
sub-s03/ses-01/func/*task-nBack*
```

### What's NOT in .bidsignore
- ✗ Behavioral CSV files (not in BIDS)
- ✗ Files on Oak (outside BIDS scope)
- ✗ External references (only BIDS files documented)

## Event File Generation

### How Events Are Created

1. **Discovery**: `/oak/.../sub-s03/ses-01/beh/sub-s03_ses-01_task-nBack_beh.csv`
   ↓
2. **Event Creation**: Process CSV → extract onsets, durations, trial types
   ↓
3. **Output**: `/scratch/users/logben/discovery_bids/sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-1_events.tsv`

### Handling Missing Behavioral

If behavioral CSV is missing or placeholder:
- Create empty events.tsv (BIDS-compliant headers only)
- Log warning: "Creating empty events.tsv for BOLD without behavioral"
- Document in .bidsignore: `sub-s03/ses-01/func/*task-nBack*`

**Result**: Complete BIDS structure even with data quality issues

## Behavioral-BOLD Correspondence

### Final Statistics (Mar 19, 2026)
- Total behavioral-BOLD pairs: 2,610
- Matched: 2,607 (99.7%)
- Missing behavioral: 9 (placeholders created)
- Behavioral without BOLD: 1 (excluded)
- Misplaced behavioral: 1 (successfully recovered)

### Resolution Method
All discrepancies documented in:
- `docs/BEHAVIORAL_BOLD_DISCREPANCIES.md` (detailed analysis)
- `.bidsignore` (BIDS-level issues)
- Event generation logs (processing decisions)

## Verification

### Check Behavioral Data on Oak (Canonical)
```bash
# Count behavioral files
find /oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior \
  -name "*.csv" | wc -l
# Returns: ~2,107

# Verify structure
ls /oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior/sub-*/ses-*/beh/ | head
```

### Check BIDS Contains No Behavioral CSVs
```bash
# Should return 0
find /scratch/users/logben/discovery_bids -name "*.csv" | wc -l
find /scratch/users/logben/validation_bids -name "*.csv" | wc -l

# Check that events.tsv exist
ls /scratch/users/logben/discovery_bids/sub-*/ses-*/func/*_events.tsv | head
```

### Check .bidsignore Accuracy
```bash
# View current .bidsignore
cat /scratch/users/logben/discovery_bids/.bidsignore

# Verify files listed actually don't have behavioral
ls /oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior/sub-s03/ses-01/beh/
# sub-s03_ses-01_task-nBack_beh.csv should exist (behavioral in ses-01)
```

## Architecture Decision Rationale

### Why Keep Behavioral on Oak Only?
1. **Institutional Storage**: Oak has enterprise backup/redundancy
2. **Single Edit Point**: Changes go in one place, no sync issues
3. **Storage Efficiency**: BIDS directories stay lean (~1TB vs ~1.3TB if duplicated)
4. **Reproducibility**: Event generation always reads from canonical source

### Why Document in .bidsignore?
1. **BIDS Validator**: Explains why some BOLD scans lack events.tsv
2. **Transparency**: Researchers know which data was problematic
3. **Audit Trail**: Can trace decisions back to QA phase

### Why This Design Works
- **fMRIPrep**: Doesn't require events.tsv (just uses for task-based GLM)
- **Event Generation**: Can reference external files, doesn't require local copy
- **Analysis**: Uses events.tsv from BIDS, not source behavioral CSVs
- **Sharing**: BIDS easily moved; behavioral reference documented separately

## Next Steps

1. ✓ Behavioral data integrated (Mar 19, 2026)
2. ✓ Event files generated (Mar 19, 2026)
3. → fMRIPrep preprocessing (ready to start)
4. → Task-based GLM analysis (uses events.tsv)

---

**Last Updated**: 2026-03-19
**Status**: FINALIZED
