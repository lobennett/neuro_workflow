# TR-Based Short Scan Detection for BOLD Imaging

## Overview

This document describes the updated short scan detection system for BOLD fMRI data, which uses **actual TR counts** instead of duration thresholds to identify prematurely terminated scans.

## Why TR-Based Detection?

### Problem with Duration Thresholds

The original approach used a global, fixed duration threshold (3.0 minutes) to flag short scans:

```
scan_is_short = (num_timepoints * TR_seconds) < threshold_seconds
```

This approach has issues:
- **Global threshold ignores task length**: A 180-second rest scan is normal, but a 180-second nBack scan is truncated
- **Not protocol-aware**: Different sequences have different expected lengths
- **Fixed at 3.0 minutes**: Arbitrary, not based on actual protocol specifications

### Advantages of TR-Based Detection

Since TR is fixed at 1.49s for all functional scans, the **number of TRs is the canonical metric**:

```
scan_is_short = (actual_TRs < minimum_acceptable_TRs_for_task)
```

Benefits:
- **Task-specific**: Each task has a canonical expected TR count based on protocol
- **Robust**: Accounts for small timing variations (±5% or ±10 TRs)
- **Empirically grounded**: Derived from actual old BIDS data
- **Precise**: Detects which exact scans are truncated

## Canonical TR Counts

Extracted from old archived BIDS directories:

| Task | Expected TRs | Shortfall Tolerance | Min Acceptable TRs | Notes |
|------|-------------|---------------------|-------------------|-------|
| rest | 163 | ±10 | 153 | Very consistent across subjects |
| flanker | 244 | ±12 | 232 | Small natural variation (~4 TRs) |
| goNogo | 394 | ±19 | 375 | Small natural variation (~4 TRs) |
| shapeMatching | 333 | ±16 | 317 | Small natural variation (~2 TRs) |
| spatialTS | 342 | ±17 | 325 | Small natural variation (~6 TRs) |
| cuedTS | 340 | ±17 | 323 | Moderate variation (~14 TRs) |
| directedForgetting | 423 | ±21 | 402 | Small natural variation (~11 TRs) |
| nBack | 512 | ±25 | 487 | Small natural variation (~5 TRs) |
| stopSignal | 493 | ±24 | 469 | Moderate variation (~5 TRs) |
| stopSignalWDirectedForgetting | 723 | ±36 | 687 | Combined task, consistent |
| directedForgettingWFlanker | 605 | ±30 | 575 | Combined task, consistent |
| stopSignalWFlanker | 375 | ±18 | 357 | Combined task, consistent |
| cuedTSWFlanker | 432 | ±21 | 411 | Combined task, only in validation |

**Source**: Extracted from:
- `/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/`
- `/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/`

**Method**: Maximum observed TRs per task (protocol was fully followed) with shortfall tolerance = ~5% of expected TRs or 10 TRs minimum.

## Implementation

### Configuration File: `config/task_tr_counts.json`

```json
{
  "task_tr_counts": {
    "rest": {
      "expected_trs": 163,
      "min_acceptable_trs": 153,
      "shortfall_tolerance_trs": 10
    },
    ...
  },
  "tr_seconds": 1.49,
  "dummy_scans_per_task": 7,
  "source": "Extracted from old archived BIDS directories",
  "method": "Maximum observed TRs; allow ~5% variation or 10 TRs minimum"
}
```

### Code Changes

**File**: `src/neuro_workflow/bids_validation/bold_analyzer.py`

- Updated `BoldAnalyzer.__init__()`:
  - New parameter: `task_tr_counts: Optional[Dict[str, int]]`
  - Stores per-task TR specifications
  - Sets `use_tr_based_detection` flag based on config availability

- Updated `_analyze_bold_file()`:
  - Primary check: Compare actual TRs to `min_acceptable_trs` from config
  - Fallback: Use duration-based threshold if TR config unavailable
  - Reports reason: e.g., "Scan has 19 TRs, but minimum 342 TRs required"

**File**: `src/neuro_workflow/bidsify/integration.py`

- New function: `_load_task_tr_counts()`
  - Loads `config/task_tr_counts.json` if available
  - Extracts `min_acceptable_trs` from each task config
  - Returns `Dict[str, int]` mapping task names to minimum acceptable TRs

- Updated `run_bold_analysis_and_update_bidsignore()`:
  - Calls `_load_task_tr_counts()` before initializing analyzer
  - Passes `task_tr_counts` to `BoldAnalyzer`
  - Falls back to global duration threshold if TR config not found

## Real-World Example

New validation BIDS (job 18688335, in progress) already shows how TR-based detection would work:

**Current Data**:
```
spatialTS: Expected 342 TRs, but has:
  - Most scans: 336 TRs ✓ (within tolerance)
  - One scan: 19 TRs ✗ (clearly truncated)
```

**Duration-Based Detection**:
- 19 TRs × 1.49s = 28.3 seconds
- Threshold: 3.0 minutes = 180 seconds
- Result: **NOT flagged** (28 < 180 is below threshold, but 180 > ~28)
- Outcome: **MISSES** the truncated scan

**TR-Based Detection**:
- 19 TRs < 325 minimum required
- Result: **FLAGGED** as short
- Reason: "Scan has 19 TRs, but minimum 325 TRs required"
- Outcome: **CATCHES** the truncated scan

## Workflow Integration

When `bidsify` completes:

1. Automatically runs `run_bold_analysis_and_update_bidsignore()`
2. Loads TR specifications from `config/task_tr_counts.json`
3. For each BOLD file:
   - Reads actual TR count from NIfTI header
   - Looks up expected minimum for that task
   - Flags if actual < minimum
4. Saves detailed report to `.bids-validation/analysis.json`
5. Updates `.bidsignore` with patterns for flagged scans

## Testing

To test the TR-based detection on a BIDS directory:

```bash
cd /home/users/logben/neuro_workflow
uv run python -c "
from pathlib import Path
from neuro_workflow.bids_validation.bold_analyzer import BoldAnalyzer
import json

# Load TR counts config
config = json.loads(Path('config/task_tr_counts.json').read_text())
task_tr_counts = {k: v['min_acceptable_trs']
                  for k, v in config['task_tr_counts'].items()}

# Analyze BIDS directory
analyzer = BoldAnalyzer(
    '/scratch/users/logben/validation_bids',
    task_tr_counts=task_tr_counts,
    verbose=True
)

# Run analysis
issues = analyzer.analyze()
print(f'Found {sum(len(v) for v in issues.values())} issues:')
for category, issue_list in issues.items():
    print(f'  {category}: {len(issue_list)} scans')
"
```

## Future Enhancements

1. **Multi-echo handling**: Account for echo-specific variations
2. **Run-level analysis**: Detect if specific runs are consistently short
3. **Subject-level reporting**: Flag subjects with multiple short scans
4. **Integration with fMRIPrep**: Pass short scan info to pipeline
5. **Automated thresholding**: Learn expected TR counts from current data if config unavailable

## References

- BIDS Specification: https://bids-standard.github.io/
- FSL fslval: Extract header information from NIfTI files
- Old BIDS data: Provides ground truth for expected TR counts
