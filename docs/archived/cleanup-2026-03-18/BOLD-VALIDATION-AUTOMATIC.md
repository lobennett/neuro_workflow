# BOLD Validation - Automatic During Bidsify

**Status:** ✓ CONFIRMED
**Date:** March 14, 2026
**Change:** Validation now runs automatically after bidsify completes

---

## Overview

BOLD validation is **automatically enabled** when you run `bidsify`. You no longer need to pass a `--run-validation` flag—it will always happen.

## Behavior

When you run:
```bash
neuro-run bidsify validation --output-dir /scratch/users/logben/validation_bids
```

The workflow is:
1. ✓ Run bidsify (pull from Flywheel, organize into BIDS)
2. ✓ **Automatically run BOLD analysis** (new scans are checked for issues)
3. ✓ **Automatically update .bidsignore** (problematic scans added with descriptions)
4. ✓ Save analysis results to `.bids-validation/analysis.json`

**No action needed** — validation happens in the background.

## How to Skip (if needed)

If you want to skip validation for some reason:
```bash
neuro-run bidsify validation --output-dir /scratch/users/logben/validation_bids --skip-validation
```

This is useful for:
- Testing bidsify independently
- Running validation separately later
- Skipping validation in development workflows

## Output

After bidsify completes, you'll see:

**Analysis Results:**
```
{bids_dir}/.bids-validation/analysis.json
```
Contains:
- Metadata (TR threshold, timestamp)
- Issues found (grouped by category: short_scan, three_d, missing_tr, etc.)
- Filepath references for each issue

**Updated .bidsignore:**
```
{bids_dir}/.bidsignore
```
Automatically updated with entries like:
```
# Missing TR metadata
sub-s1273/ses-05/func/*task-spatialTS_run-1_echo-3_bold*

# 3D BOLD (dim missing time axis)
sub-s43/ses-08/func/*task-directedForgetting_run-1*
```

## Configuration

Override the default TR threshold:
```bash
neuro-run bidsify validation \
    --output-dir /scratch/users/logben/validation_bids \
    --tr-threshold-minutes 4.0
```
Default: 3.0 minutes

## Error Handling

By default, if validation finds issues, it logs a warning and continues:
```
WARNING: BOLD analysis found 2 problematic scans
(scans added to .bidsignore)
```

To fail the entire bidsify if issues are found:
```bash
neuro-run bidsify validation \
    --output-dir /scratch/users/logben/validation_bids \
    --validation-fail-hard
```

## What Gets Checked

The validation automatically detects:

| Issue Type | Severity | Action |
|------------|----------|--------|
| **3D BOLD** | Critical | Added to .bidsignore |
| **Missing TR** | Critical | Added to .bidsignore |
| **Short Scan** | Medium | Added to .bidsignore if < 3 min |
| **Corrupt NIfTI** | Critical | Added to .bidsignore |
| **Corrupt JSON** | Medium | Logged as warning |

## Verification

After bidsify completes, verify validation happened:

```bash
# Check analysis was created
ls -lh /scratch/users/logben/validation_bids/.bids-validation/analysis.json

# Check .bidsignore was updated
tail -20 /scratch/users/logben/validation_bids/.bidsignore

# View detailed results
jq . /scratch/users/logben/validation_bids/.bids-validation/analysis.json | less
```

## Testing

The automatic behavior is tested in:
- `tests/bids_validation/test_e2e_bidsignore_automation.py::test_bidsify_automatic_validation_behavior`

All 53 tests pass (✓).

## Backward Compatibility

✓ Old scripts/commands work unchanged
✓ Validation is non-breaking (warns, doesn't fail by default)
✓ Only new behavior: analysis results are saved automatically

## Files Involved

- `src/neuro_workflow/cli.py` — Changed `--run-validation` to `--skip-validation` (inverted logic)
- `src/neuro_workflow/cli.py` — `cmd_bidsify()` always calls `run_bold_analysis_and_update_bidsignore()` unless `--skip-validation`
- `src/neuro_workflow/bidsify/integration.py` — Does the actual analysis and merging
- `src/neuro_workflow/bids_validation/bold_analyzer.py` — Scans BOLD files for issues

---

## Summary

✅ **BOLD validation is now automatic during bidsify**

- Runs after every `neuro-run bidsify` without extra flags
- Updates .bidsignore automatically
- Can be skipped with `--skip-validation` if needed
- Non-breaking: warns, doesn't fail by default
- Full results saved to `.bids-validation/analysis.json`
