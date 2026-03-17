# Static Behavioral Session Mapping — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the runtime matching algorithm with a static JSON config that explicitly maps every raw behavioral session to its BIDS session, then simplify the rename script to a pure config-driven copy.

**Architecture:** A one-time generator script produces `config/behavioral_session_mapping.json` from the current matching algorithm + reconciliation timestamps. The rename script is rewritten to read this config and copy files — no matching logic. Manual corrections (s29 date fix, s300/s1292 irreconcilable entries) are applied to the config after generation.

**Tech Stack:** Python 3.11+, pathlib, json. No new dependencies.

---

### Task 1: Create the generator script

**Files:**
- Create: `scripts/generate_behavioral_mapping.py`

The generator reuses the existing matching functions from `rename_behavioral_to_sourcedata.py` and enriches results with BIDS dates from reconciliation.json.

**Step 1: Write `scripts/generate_behavioral_mapping.py`**

```python
#!/usr/bin/env python3
"""Generate behavioral_session_mapping.json from BIDS + raw_cleaned data.

One-time script. Output is hand-reviewed and corrected before use.

Usage:
    uv run python scripts/generate_behavioral_mapping.py \
        --raw-dir /oak/.../behavioral_data/raw_cleaned \
        --discovery-bids /scratch/users/logben/discovery_bids \
        --validation-bids /scratch/users/logben/validation_bids \
        --output config/behavioral_session_mapping.json
"""
```

Core logic:
1. Import `build_bids_task_map`, `build_raw_session_map`, `match_sessions`, `parse_csv_filename` from the existing rename script
2. For each sample (discovery, validation):
   - Load `reconciliation.json` to get `bids_session → timestamp` mapping
   - For each subject with raw behavioral data:
     - Run `match_sessions()` to get mappings
     - Enrich each mapping with `bids_date` from reconciliation timestamps
     - Record `skipped_bids`, `unmatched_raw`
     - Flag subjects with inconsistent offsets for manual review
3. Add excluded validation subjects with `"excluded": true` and reasons from `reconciliation_config.json`
4. Write to output path

**Step 2: Run the generator**

```bash
mkdir -p config
uv run python scripts/generate_behavioral_mapping.py \
    --raw-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
    --discovery-bids /scratch/users/logben/discovery_bids \
    --validation-bids /scratch/users/logben/validation_bids \
    --output config/behavioral_session_mapping.json
```

Expected: JSON file with ~46 subjects, each with mappings array. Console prints subjects needing review.

**Step 3: Commit generated config**

```bash
git add scripts/generate_behavioral_mapping.py config/behavioral_session_mapping.json
git commit -m "feat: generate static behavioral session mapping config"
```

---

### Task 2: Hand-correct s29 mapping

**Files:**
- Modify: `config/behavioral_session_mapping.json` (s29 entry)

**Step 1: Fix s29 mappings**

Replace the algorithm-generated s29 mappings with the date-correct mapping:

| raw | bids | bids_date | tasks | note |
|-----|------|-----------|-------|------|
| ses-01 | ses-02 | 2020-11-13 | [directedForgetting, shapeMatching, stopSignal] | protocol mismatch: raw has spatialTS, BIDS has cuedTS — only 3 overlapping tasks have events |
| ses-02 | ses-03 | 2020-11-14 | [cuedTS, flanker, nBack] | raw missing goNogo (behavioral.md) |
| ses-03 | ses-04 | 2020-12-02 | [directedForgetting, shapeMatching, spatialTS, stopSignal] | |
| ses-04 | ses-05 | 2020-12-04 | [cuedTS, flanker, goNogo, nBack] | |
| ses-05 | ses-06 | 2021-02-03 | [directedForgetting, shapeMatching, spatialTS, stopSignal] | |
| ses-06 | ses-07 | 2021-02-05 | [cuedTS, flanker, goNogo, nBack] | |
| ses-07 | ses-08 | 2021-02-24 | [directedForgetting, shapeMatching, spatialTS, stopSignal] | |
| ses-08 | ses-09 | 2021-02-25 | [cuedTS, flanker, goNogo, nBack] | |
| ses-09 | ses-10 | 2021-03-03 | [directedForgetting, shapeMatching, spatialTS, stopSignal] | |
| ses-10 | ses-11 | 2021-03-05 | [flanker, goNogo, nBack] | s29-2 data |
| ses-11 | ses-12 | 2021-03-17 | [directedForgettingWFlanker, stopSignalWDirectedForgetting, stopSignalWFlanker] | |
| ses-12 | ses-13 | 2021-03-19 | [directedForgettingWFlanker, stopSignalWDirectedForgetting, stopSignalWFlanker] | |

Set `skipped_bids: ["ses-01"]`, `unmatched_raw: []`.

Add notes:
- "ses-01 is fmap-only test session (2020-11-11), no behavioral data"
- "raw ses-01 maps to BIDS ses-02 despite protocol mismatch (spatialTS behavioral vs cuedTS scanned) — only 3/4 tasks overlap"
- "Date-corrected mapping: algorithm matched raw ses-01→ses-04 (wrong date), manually fixed to ses-02 based on scan tracking dates"

**Step 2: Add s29 irreconcilable entries**

BIDS ses-02 has cuedTS BOLD but raw ses-01 has spatialTS behavioral — the cuedTS run will have no events:
```json
"irreconcilable_bids_runs": [
    {"session": "ses-02", "task": "cuedTS", "reason": "protocol mismatch: cuedTS was scanned but spatialTS was the behavioral task (Nov 13 2020)"}
]
```

**Step 3: Commit**

```bash
git add config/behavioral_session_mapping.json
git commit -m "fix(s29): hand-correct behavioral session mapping to match scan dates"
```

---

### Task 3: Add s300 and s1292 irreconcilable entries

**Files:**
- Modify: `config/behavioral_session_mapping.json` (s300, s1292 entries)

**Step 1: s300 — add irreconcilable flanker**

In s300's entry, add:
```json
"irreconcilable_bids_runs": [
    {"session": "ses-08", "task": "flanker", "reason": "flanker behavioral data lost — server shut down before save (scan operator note 4/13/2023)"}
]
```

Also verify that s300's `unmatched_raw` includes ses-08, and add note:
```
"ses-08: cuedTS behavioral exists but cuedTS was deleted from Flywheel (duplicate, operator deleted shorter copy). flanker BOLD exists but behavioral lost."
```

**Step 2: s1292 — add irreconcilable nBack**

In s1292's entry, add:
```json
"irreconcilable_bids_runs": [
    {"session": "ses-04", "task": "nBack", "reason": "nBack scan ended before task completed — scanner failure (scan operator note 10/20)"}
]
```

Note: s1292 raw ses-04 is missing nBack behavioral because the scanner failed during that task. The nBack BOLD may exist on Flywheel (partial scan) but has no behavioral data.

**Step 3: Commit**

```bash
git add config/behavioral_session_mapping.json
git commit -m "docs: add irreconcilable entries for s300 (flanker) and s1292 (nBack)"
```

---

### Task 4: Add excluded validation subjects

**Files:**
- Modify: `config/behavioral_session_mapping.json`

**Step 1: Add entries for 11 excluded subjects**

For each excluded subject, add an entry with:
```json
"s214": {
    "sample": "validation",
    "excluded": true,
    "exclude_reason": "dropped for being unreliable",
    "mappings": [],
    "skipped_bids": [],
    "unmatched_raw": [],
    "irreconcilable_bids_runs": [],
    "notes": []
}
```

Subjects and reasons:
- s214: dropped for being unreliable
- s222: dropped for poor behavioral performance
- s250: dropped (lens prescription issue)
- s297: discontinued (ear issues after scanning)
- s432: withdrew from study
- s823: withdrew from study
- s968: withdrew from study
- s1165: withdrew from study
- s1178: withdrew from study
- s1266: withdrew from study
- s1320: withdrew from study

**Step 2: Commit**

```bash
git add config/behavioral_session_mapping.json
git commit -m "docs: add excluded validation subjects to mapping config"
```

---

### Task 5: Rewrite the rename script to use config

**Files:**
- Modify: `scripts/rename_behavioral_to_sourcedata.py`

**Step 1: Rewrite the script**

The new script:
1. Reads `config/behavioral_session_mapping.json`
2. Accepts `--input-dir`, `--output-dir`, `--sample` (discovery|validation|all), `--dry-run`
3. For each subject in the config matching the sample:
   - Skip if `excluded`
   - For each mapping entry, find the raw CSVs in `input_dir/{subject}/{raw_ses}/`
   - For each CSV, parse the task name with `parse_csv_filename()`
   - If the task is in the mapping's `tasks` list, copy to `output_dir/sub-{subject}/{bids_ses}/beh/`
4. Generate `.bidsignore` entries:
   - `sub-{sub}/` for each excluded subject
   - `sub-{sub}/{session}/func/*task-{task}*` for each irreconcilable run
5. Write `.bidsignore` to the BIDS directory (append, don't overwrite)
6. Write `session_mapping.json` to output_dir for downstream consumption

Keep the existing `parse_csv_filename()`, `LONG_NAME_TO_BIDS`, `_BIDS_TASK_ALIASES`, `build_output_path()`, and `SKIP_DIRS` from the current script. Remove `match_sessions()`, `build_bids_task_map()`, and `build_raw_session_map()` — these stay in the generator only.

**Step 2: Test with dry run for discovery**

```bash
uv run python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
    --output-dir /scratch/users/logben/discovery_bids/sourcedata/behavioral \
    --sample discovery \
    --dry-run
```

Expected: 59 CSVs for s03 (12 ses × ~5 tasks), similar for s10/s19/s43, ~55 for s29 (12 ses × ~4 tasks). No matching algorithm output — just "copying X files for Y subjects".

**Step 3: Test with dry run for validation**

```bash
uv run python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
    --output-dir /scratch/users/logben/validation_bids/sourcedata/behavioral \
    --sample validation \
    --dry-run
```

**Step 4: Commit**

```bash
git add scripts/rename_behavioral_to_sourcedata.py
git commit -m "refactor: rewrite behavioral rename to use static mapping config"
```

---

### Task 6: Run for real and verify

**Step 1: Run rename for discovery**

```bash
uv run python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
    --output-dir /scratch/users/logben/discovery_bids/sourcedata/behavioral \
    --sample discovery
```

**Step 2: Verify discovery output**

```bash
# Check s29 specifically — ses-01 raw should be in ses-02 BIDS
ls /scratch/users/logben/discovery_bids/sourcedata/behavioral/sub-s29/ses-02/beh/
# Should have: directedForgetting, shapeMatching, stopSignal CSVs (NOT spatialTS — protocol mismatch)

# Check total file counts
find /scratch/users/logben/discovery_bids/sourcedata/behavioral -name '*.csv' | wc -l
```

**Step 3: Run rename for validation**

```bash
uv run python scripts/rename_behavioral_to_sourcedata.py \
    --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
    --output-dir /scratch/users/logben/validation_bids/sourcedata/behavioral \
    --sample validation
```

**Step 4: Verify .bidsignore**

```bash
cat /scratch/users/logben/discovery_bids/.bidsignore
# Should contain: sub-s29/ses-02/func/*task-cuedTS*

cat /scratch/users/logben/validation_bids/.bidsignore
# Should contain:
# sub-s214/ through sub-s1320/ (excluded subjects)
# sub-s300/ses-08/func/*task-flanker*
# sub-s1292/ses-04/func/*task-nBack*
```

**Step 5: Commit any remaining changes**

```bash
git add -A
git commit -m "feat: complete behavioral rename with static mapping for both samples"
```
