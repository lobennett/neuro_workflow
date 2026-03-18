# BIDS Rerun Results - Clean Slate (Mar 14, 2026)

## Summary
This document records the results of re-running bidsify on all three datasets (discovery, validation, excluded) with a clean slate. Recent code improvements include:
- Reduced parallel workers (16 → 4) to avoid Flywheel API rate limiting
- Safe JSON sidecar patching with retry logic (3 attempts)
- Duplicate anatomical and DWI scan detection
- Proper metadata fields (Units for fieldmaps, TaskName for BOLD, B0FieldSource)

## Execution Timeline

### Container Build
- Job ID: 18687976
- Status: [IN PROGRESS - will complete ~30 min after submission]
- Image: /home/groups/russpold/singularity_images/neuro_workflow.sif

### Bidsify Execution
- Discovery (5 subjects):
  - Job ID: 18688008
  - Status: [IN PROGRESS - 30-60 min expected]
  - Output: `/scratch/users/logben/discovery_bids`

- Validation (41 non-excluded subjects):
  - Job ID: 18688021
  - Status: [IN PROGRESS - 2-3 hours expected]
  - Output: `/scratch/users/logben/validation_bids`

- Excluded (11 subjects):
  - Job ID: 18688025
  - Status: [IN PROGRESS - 30-60 min expected]
  - Output: `/scratch/users/logben/excluded_bids`

## Directory Sizes (expected after rerun)
- discovery_bids: ~94G
- validation_bids: ~796G
- excluded_bids: ~49G

## Validator Results (Error Reduction)

### Discovery
| Metric | Old | New | Change |
|--------|-----|-----|--------|
| ERROR count | ? | ? | ? |
| Missing TR | ? | ? | ? |
| Missing Units | ? | ? | ? |

### Validation
| Metric | Old | New | Change |
|--------|-----|-----|--------|
| ERROR count | ? | ? | ? |
| Missing TR | ? | ? | ? |
| Missing Units | ? | ? | ? |

### Excluded
| Metric | Old | New | Change |
|--------|-----|-----|--------|
| ERROR count | ? | ? | ? |

*To fill in actual numbers:*
```bash
bash /tmp/compare_validators.sh
```

## Duplicate Scan Detection

### Anatomical Duplicates (.bidsignore entries)
- s19: Second T1w marked ✓/✗
- [Other subjects with duplicates]: [status]

### DWI Duplicates
- [Subjects with duplicates]: [status]

## Corrupted File Fixes
- RepetitionTime parsing issues: [improved/same]
- JSON sidecar integrity: [improved/same]
- Units field present in fieldmaps: [YES/NO]
- TaskName present in BOLD: [YES/NO]

## Archive Management
- Old discovery_bids archived to: `discovery_bids.archive_20260314_120910`
- Old validation_bids archived to: `validation_bids.archive_20260314_120910`
- Old excluded_bids archived to: `excluded_bids.archive_20260314_120910`
- Retention: [Keep for 2 weeks / Delete immediately / Other]

## Behavioral Data Correspondence
- Discovery: [Status - pending verification]
- Validation: [Status - pending verification]
- Excluded: [Status - pending verification]

See `bids-sourcedata-correspondence-2026-03-14.md` for details.

## Next Steps
- [ ] Monitor bidsify jobs (tasks 3-5) for completion
- [ ] Run BIDS validator (Task 7): `sbatch /tmp/validate_all_bids.sh`
- [ ] Verify improvements (Task 8): `bash /tmp/inspect_improvements.sh`
- [ ] Run correspondence check (Task 10)
- [ ] Update this report with final metrics
- [ ] Decide on archive retention
- [ ] Proceed with downstream processing if all validations pass

## Clearance Status
- [ ] BIDS validator errors reduced
- [ ] Duplicate scans properly detected and marked
- [ ] Metadata integrity confirmed
- [ ] Behavioral correspondence verified
- **READY FOR DOWNSTREAM PROCESSING**: [Not yet - pending validation]
