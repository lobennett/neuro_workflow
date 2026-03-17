# BIDS Validator Findings - March 14, 2026

## Status
Validators run successfully via SLURM job 18686858 on all three datasets.

## Issues Summary

### Validation BIDS (41 subjects)
**Critical Errors (7 types):**
1. **REPETITION_TIME_MUST_DEFINE** - 74+ files across multiple subjects
   - s1273/ses-05, s1408/ses-09 (found by analyzer)
   - **s956 in ses-07, ses-09** (NOT detected by analyzer)
   
2. **UNITS_MUST_DEFINE** - Fieldmap files missing Units metadata
   - s1267/ses-01, s1351/ses-10, s956 in ses-08 to ses-12
   
3. **JSON_INVALID** - Malformed JSON sidecars
   - s1267/ses-01/fmap/sub-s1267_ses-01_run-1_fieldmap.json (corrupt at line 37)
   
4. **TASK_NAME_MUST_DEFINE** - Task files missing TaskName
   - s956 in multiple sessions (same files as REPETITION_TIME)
   
5. **BOLD_NOT_4D** - 3D BOLD files instead of 4D
   - s480/ses-03/func/*task-goNogo* (found by analyzer)
   
6. **NIFTI_PIXDIM4** - Missing time dimension
   - s480/ses-03 (same files as BOLD_NOT_4D)
   
7. **CONTINOUS_RECORDING_MISSING_JSON** - Physio files need JSON sidecars
   - s956 physio recordings across multiple sessions

### Discovery BIDS (5 subjects)
- Similar warnings about missing SliceTiming and events.tsv
- No critical errors

### Excluded BIDS (11 subjects)
- Similar warnings about missing SliceTiming and events.tsv
- No critical errors

## Root Cause Analysis

**Why BOLD Analyzer Missed These:**
1. Only scans `*_bold.nii.gz` files
2. Doesn't check fieldmaps (`fmap/`)
3. Doesn't validate JSON file syntax (only reads RepetitionTime field)
4. Doesn't check for physiological recording JSON sidecars
5. s956 issues may involve corrupted/missing JSON that analyzer doesn't catch

## Recommended Actions

### Option A: Enhance BOLD Analyzer (Broader Fix)
- Expand to scan all modality files (fmap, physio, etc.)
- Add JSON validation (proper JSON syntax check)
- Check all required metadata fields by modality

### Option B: Use Validator Output Directly (Faster)
- Parse validator output to extract issues
- Automatically generate .bidsignore from validator errors
- Simpler but depends on validator being correct

### Option C: Hybrid Approach (Recommended)
- Keep BOLD analyzer focused on BOLD files (what it does well)
- Use validator output for comprehensive issue detection
- Merge both sources into .bidsignore

## Files Involved

**Validator output logs:**
- `/home/users/logben/neuro_workflow/validator_logs/discovery_validator.txt`
- `/home/users/logben/neuro_workflow/validator_logs/validation_validator.txt`
- `/home/users/logben/neuro_workflow/validator_logs/excluded_validator.txt`

**Current .bidsignore files:**
- `/scratch/users/logben/discovery_bids/.bidsignore` (4 entries)
- `/scratch/users/logben/validation_bids/.bidsignore` (4 entries)
- `/scratch/users/logben/excluded_bids/.bidsignore` (2 entries)

## Next Steps

1. Decide which approach to implement (A, B, or C)
2. Update code to detect all issues
3. Regenerate .bidsignore files comprehensively
4. Re-run validator to verify .bidsignore suppresses all fixable errors
