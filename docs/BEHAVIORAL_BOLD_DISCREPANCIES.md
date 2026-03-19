# Behavioral-BOLD Correspondence Discrepancies (Mar 19, 2026)

This document tracks all behavioral/BOLD mismatches found during correspondence checking.

## Discovery Subjects (5 total)

### Salvageable Discrepancies

**s03 ses-01 nBack**
- Status: SALVAGEABLE
- Issue: BOLD scan exists (ses-01) but behavioral file is in raw_cleaned ses-02 directory
- File: `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned/s03/ses-02/n_back_single_task_network__fmri_results (7).csv`
- Solution: Manually copy behavioral file to correct location and re-run migration
- Action Needed: Copy s03 ses-02/nBack to ses-01 output OR update session mapping

### Missing Behavioral Files (add to .bidsignore)

1. **s19 ses-02 goNogo** - Behavioral file is missing
2. **s19 ses-11 directedForgettingWFlanker** - Behavioral file is missing
3. **s29 ses-01 cuedTS** - Behavioral file is missing
4. **s29 ses-02 goNogo** - Behavioral file is missing
5. **s43 ses-02 goNogo** - Behavioral file is missing

## Validation Subjects (41 total)

### Salvageable Discrepancies

**s300 ses-08 flanker**
- Status: SALVAGEABLE
- Issue: BOLD scan exists (ses-08) but behavioral file is in raw_cleaned ses-09 directory
- File: `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned/s300/ses-09/flanker_single_task_network__fmri_results.csv`
- Solution: Manually copy behavioral file to correct location and re-run migration
- Action Needed: Copy s300 ses-09/flanker to ses-08 output OR update session mapping

### Missing Behavioral Files (add to .bidsignore)

1. **s1175 ses-11 cuedTSWFlanker** - Behavioral file is missing
2. **s1292 ses-04 nBack** - Behavioral file is missing
3. **s180 ses-12 shapeMatchingWCuedTS** - Behavioral file is missing
4. **s321 ses-02 spatialTS** - Behavioral file is missing

### Behavioral Files without BOLD (add to .bidsignore)

1. **s321 ses-01 spatialTS** - BOLD scan is missing for this task
   - Behavioral file exists but has no corresponding BOLD data
   - Action: Exclude behavioral file from migration

## Summary

- **Total Discovery Discrepancies**: 6 (1 salvageable, 5 missing behavioral)
- **Total Validation Discrepancies**: 10 (1 salvageable, 4 missing behavioral, 1 behavioral without BOLD, 4 missing behavioral)
- **Total Truly Missing**: 9 behavioral files with no corresponding BOLD
- **Total Salvageable**: 2 behavioral files with mislabeled sessions

## Next Steps

1. Decide whether to salvage s03 ses-01 nBack and s300 ses-08 flanker
2. Add behavioral files without BOLD to .bidsignore
3. Add missing behavioral task sessions to .bidsignore
4. Re-run behavioral migration with corrected mappings if salvaging
5. Re-run correspondence check to verify
