# Static Behavioral Session Mapping Config

**Date:** 2026-03-11
**Status:** Approved, ready for implementation

## Problem

The behavioral rename script uses a greedy task-set matching algorithm to pair raw behavioral sessions with BIDS sessions. This works for 45/46 subjects but fails for s29, where raw session numbering is offset from BIDS chronological order due to early test sessions and a protocol mismatch. The algorithm also makes the mapping opaque — there's no single artifact documenting which behavioral session maps to which BIDS session.

## Decision

Replace the runtime matching algorithm with a **static JSON config file** that explicitly maps every `raw_ses → bids_ses` pair for every subject across both samples. The algorithm becomes a one-time generator; the rename script becomes a pure lookup + copy.

## Config file

**Location:** `config/behavioral_session_mapping.json`

### Schema

```json
{
  "generated": "ISO-8601 timestamp",
  "generator": "scripts/generate_behavioral_mapping.py",
  "sources": {
    "bids_discovery": "/scratch/users/logben/discovery_bids",
    "bids_validation": "/scratch/users/logben/validation_bids",
    "behavioral_raw": "/oak/.../behavioral_data/raw_cleaned",
    "reconciliation_discovery": "sourcedata/reconciliation.json",
    "reconciliation_validation": "sourcedata/reconciliation.json",
    "scan_notes": "scan_notes/"
  },
  "subjects": {
    "<subject_label>": {
      "sample": "discovery|validation",
      "excluded": false,
      "exclude_reason": null,
      "mappings": [
        {
          "raw": "ses-NN",
          "bids": "ses-NN",
          "bids_date": "YYYY-MM-DD",
          "tasks": ["task1", "task2"]
        }
      ],
      "skipped_bids": ["ses-NN"],
      "unmatched_raw": ["ses-NN"],
      "irreconcilable_bids_runs": [
        {"session": "ses-NN", "task": "taskName", "reason": "free text"}
      ],
      "notes": ["free-text per-subject provenance"]
    }
  }
}
```

### Field definitions

- `mappings[].raw` — raw_cleaned session label
- `mappings[].bids` — BIDS session label this maps to
- `mappings[].bids_date` — Flywheel timestamp date for the BIDS session (audit trail)
- `mappings[].tasks` — exact BIDS task names for which CSVs will be copied
- `skipped_bids` — BIDS sessions with no behavioral match (fmap-only, rest-only, etc.)
- `unmatched_raw` — raw sessions with no BIDS match (protocol mismatch, missing scan)
- `irreconcilable_bids_runs` — BOLD runs in BIDS that will never get events files; drives `.bidsignore`
- `excluded` — validation subjects not in subs_validation.txt; drives `.bidsignore` for entire subject dir
- `notes` — free-text provenance for manual corrections

## Scripts

### `scripts/generate_behavioral_mapping.py` (new, one-time)

Generates the config JSON by:
1. Running the existing matching algorithm against both BIDS directories
2. Enriching each mapping with `bids_date` from reconciliation.json
3. Writing the full config to `config/behavioral_session_mapping.json`
4. Printing a summary of subjects needing manual review (inconsistent offsets, unmatched sessions)

After generation, manual corrections are applied (see below).

### `scripts/rename_behavioral_to_sourcedata.py` (simplified)

Rewritten to:
1. Read `config/behavioral_session_mapping.json`
2. For each subject's mappings, copy raw CSVs to `sourcedata/behavioral/sub-{sub}/{bids_ses}/beh/`
3. Generate `.bidsignore` entries from `irreconcilable_bids_runs` and `excluded` subjects
4. Write `session_mapping.json` to sourcedata for downstream consumption

No matching logic at runtime.

## Manual corrections

### s29 (discovery) — date-corrected mapping

The algorithm maps raw ses-01 to BIDS ses-04 (wrong date). Correct mapping:

| Raw | BIDS | Date | Notes |
|-----|------|------|-------|
| ses-01 | ses-02 | 2020-11-13 | Protocol mismatch: raw has spatialTS, BIDS has cuedTS. Only dF/sM/sS overlap. |
| ses-02 | ses-03 | 2020-11-14 | Subset: raw missing goNogo |
| ses-03 | ses-04 | 2020-12-02 | |
| ses-04 | ses-05 | 2020-12-04 | |
| ses-05 | ses-06 | 2021-02-03 | |
| ses-06 | ses-07 | 2021-02-05 | |
| ses-07 | ses-08 | 2021-02-24 | |
| ses-08 | ses-09 | 2021-02-25 | |
| ses-09 | ses-10 | 2021-03-03 | |
| ses-10 | ses-11 | 2021-03-05 | s29-2 data |
| ses-11 | ses-12 | 2021-03-17 | Dual tasks |
| ses-12 | ses-13 | 2021-03-19 | Dual tasks |

Skipped BIDS: ses-01 (fmap-only test session)
Unmatched raw: none (ses-01 now maps to ses-02, albeit with protocol mismatch)

### s300 (validation) — irreconcilable flanker

Add to `irreconcilable_bids_runs`:
```json
{"session": "ses-08", "task": "flanker", "reason": "flanker behavioral data lost — server shut down before save (scan operator note 4/13/2023)"}
```

### s1292 (validation) — scanner failure

Verify after validation rerun. Expected: ses-04 nBack scan exists but behavioral doesn't (scanner failure). Add:
```json
{"session": "ses-04", "task": "nBack", "reason": "nBack scan ended before task completed — scanner failure (scan operator note 10/20)"}
```

### Excluded validation subjects

11 subjects with `"excluded": true`:
- s214 (dropped for being unreliable), s222 (poor behavioral performance), s250 (lens prescription), s297 (ear issues), s432/s823/s968/s1165/s1178/s1266/s1320 (withdrew from study)

## .bidsignore generation

The rename script generates `.bidsignore` entries from:
1. `excluded` subjects → `sub-{sub}/`
2. `irreconcilable_bids_runs` → `sub-{sub}/{session}/func/*task-{task}*`

## Implementation steps

1. Create `scripts/generate_behavioral_mapping.py`
2. Run it to generate initial config
3. Hand-correct s29 mapping
4. Add s300 and s1292 irreconcilable entries + scan operator notes
5. Add excluded validation subjects
6. Simplify `scripts/rename_behavioral_to_sourcedata.py` to use config
7. Run rename for both samples
8. Verify output
