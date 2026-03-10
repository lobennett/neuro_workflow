# Design: BIDS-aware behavioral session matching in rename script

## Problem

The `scripts/rename_behavioral_to_sourcedata.py` script copies behavioral CSVs from `raw_cleaned/` to a BIDS sourcedata layout using the session labels as-is. However, Flywheel session numbering (assigned chronologically by timestamp in bidsify) and `raw_cleaned/` session numbering (assigned manually by someone organizing the data) do not always match.

Observed mismatches across 5 BIDSified subjects:
- **s03**: BIDS has 14 sessions, raw has 12. BIDS ses-07 is a mixed/partial scan session with no behavioral counterpart, shifting all subsequent sessions by 1. BIDS ses-14 is empty.
- **s10**: BIDS has 11 sessions, raw has 12. A repeated task-set scan in Flywheel collapses two raw sessions into one BIDS session.
- **s29**: BIDS has 13 sessions, raw has 12. BIDS ses-01 is empty (no func data), shifting everything by 1.
- **s19, s43**: Session counts match and task sets align.

## Approach

Modify the rename script to require `--bids-dir` and match behavioral sessions to BIDS sessions by task content using greedy ordered matching.

### Interface

```bash
python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/.../raw_cleaned \
    --output-dir /oak/.../sourcedata/behavioral_data \
    --bids-dir /scratch/users/logben/discovery_BIDS \
    [--dry-run]
```

### Matching algorithm

For each subject present in both `raw_cleaned/` and `--bids-dir`:

1. Build ordered list of BIDS sessions with task sets (from `func/` filenames, excluding rest)
2. Build ordered list of behavioral sessions with task sets (from CSV filenames)
3. Greedy ordered match:
   - Walk both lists with a BIDS pointer
   - For each behavioral session, advance BIDS pointer until `behavioral_tasks <= bids_tasks` (subset or equal)
   - Emit the mapping; skip BIDS sessions with no behavioral match
   - Behavioral sessions with zero recognized tasks are skipped with a warning

Key behaviors:
- **Subset matching**: behavioral session may have fewer tasks than BIDS (e.g., missing nBack behavioral data but scan exists)
- **Skips extra BIDS sessions**: mixed/partial/empty Flywheel sessions that have no behavioral counterpart
- **Order-preserving**: both lists sorted by session number, temporal ordering maintained

### Output

Copied files use the BIDS session label:
```
{output-dir}/sub-s03/ses-08/beh/sub-s03_ses-08_task-goNogo_beh.csv  (raw ses-07 -> bids ses-08)
```

Audit file at `{output-dir}/session_mapping.json`:
```json
{
  "generated": "2026-03-10T...",
  "bids_dir": "/scratch/users/logben/discovery_BIDS",
  "subjects": {
    "s03": {
      "mappings": [
        {"raw_session": "ses-01", "bids_session": "ses-01", "tasks": ["goNogo", "shapeMatching", "spatialTS"]}
      ],
      "skipped_bids_sessions": ["ses-07", "ses-14"],
      "unmatched_raw_sessions": []
    }
  }
}
```

Compact summary table printed to stdout.

### Scope

Changes are limited to `scripts/rename_behavioral_to_sourcedata.py`:
- New: `build_bids_task_map()`, `match_sessions()`
- Modified: `main()` (add `--bids-dir`), `build_output_path()` (use matched session label)
- Unchanged: `parse_csv_filename`, `discover_csvs`, `zero_pad_session`
- Bugfix: add `cuedTaskSwitching` and `spatialTaskSwitching` to `_BIDS_TASK_ALIASES`

No changes to `src/neuro_workflow/`.
