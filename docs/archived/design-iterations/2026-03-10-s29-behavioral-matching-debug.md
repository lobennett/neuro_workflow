# Behavioral-to-BIDS Session Matching — Comprehensive Plan

**Date:** 2026-03-11 (updated)
**Status:** Implementation complete — ready for execution

## Source of truth hierarchy

1. **Flywheel data** — ground truth for what was actually scanned
2. **raw_cleaned behavioral data** — already adjusted for known issues (flipped mappings, etc.)
3. **Scan tracking sheets** — biased, prone to manual entry errors. Use for context only.
4. **Behavioral notes (behavioral.md)** — documents known missing tasks per subject

## Decisions made

- Subset mismatches (BIDS has tasks with no behavioral CSV, OR behavioral has tasks with no BIDS session) are **acceptable** — behavioral data was sometimes lost, corrupted, or excluded during QC; some tasks were run behaviorally but not scanned
- Flywheel data is authoritative — tracking sheet disagreements are tracking sheet errors
- s29-2/20210305 is NOT a duplicate — it is s29's Scan 10 (2021-03-05) with `{rest, flanker, goNogo, nBack}`, collected under the wrong subject label
- Bidirectional subset matching: match when `raw_tasks <= bids_tasks` OR `bids_tasks <= raw_tasks` — needed because discovery has behavioral subsets of BIDS, while validation has BIDS subsets of behavioral (cuedTS/spatialTS collected behaviorally but not always scanned)

---

## Code changes completed

### 1. Bidirectional subset matching (`scripts/rename_behavioral_to_sourcedata.py`)

Changed `match_sessions()` Pass 1 and Pass 2 from:
```python
if raw_tasks <= bids_tasks:  # raw subset of BIDS only
```
to:
```python
if raw_tasks <= bids_tasks or bids_tasks <= raw_tasks:  # either direction
```

This fixes validation matching where behavioral data consistently has extra tasks (cuedTS, spatialTS) that weren't scanned.

### 2. Removed s29-2/20210305 exclusion (`reconciliation_config.json`)

Removed the incorrect exclusion so s29 will get 13 BIDS sessions after re-running bidsify.

### 3. Added excluded validation subjects to config

Added `excluded_validation_subjects` dict with reasons. Subjects without explicit notes are marked as "withdrew from study".

---

## Current match results

### Discovery (current BIDS — s29 still at 12 sessions, needs rerun)

| Subject | Match | Notes |
|---------|-------|-------|
| s03 | 12/12 | ses-01 subset: BIDS has `nBack` with no behavioral (behavioral.md: "s03 issue w/ nBack") |
| s10 | 12/12 | No issues |
| s19 | 12/12 | ses-02 subset: missing `goNogo` behavioral; ses-11 subset: missing `directedForgettingWFlanker` |
| s29 | **11/12** | raw ses-10 unmatched (needs bidsify rerun to add ses-11 from s29-2/20210305) |
| s43 | 12/12 | ses-02 subset: missing `goNogo` behavioral |

**After s29 bidsify rerun:** s29 expected **11/12** (raw ses-09 has no BIDS match — protocol mismatch)

### Validation (41 subjects with behavioral data)

| Subject | Match | Notes |
|---------|-------|-------|
| 39 subjects | 12/12 or 13/13 | Perfect match |
| s1292 | 12/13 | ses-11 unmatched: `{goNogo, shapeMatching, spatialTS}` — no BIDS session with compatible task set |
| s300 | 11/12 | ses-08 unmatched: `{cuedTS, directedForgetting, stopSignal}` — no BIDS session with compatible task set |

### Excluded validation subjects (11 — BIDS only, no behavioral matching)

```
s214  — dropped for being unreliable
s222  — dropped for poor behavioral performance
s250  — dropped (lens prescription issue)
s297  — discontinued (ear issues after scanning)
s432  — withdrew from study
s823  — withdrew from study
s968  — withdrew from study
s1165 — withdrew from study
s1178 — withdrew from study
s1266 — withdrew from study
s1320 — withdrew from study
```

---

## Remaining execution steps

### Step 1: Rerun bidsify for discovery

```bash
rm -rf /scratch/users/logben/discovery_bids/
neuro_workflow submit bidsify --sample discovery --output-dir /scratch/users/logben/discovery_bids
# Wait for job, verify s29 now has 13 sessions
ls -d /scratch/users/logben/discovery_bids/sub-s29/ses-*
```

### Step 2: Rerun behavioral rename for discovery

```bash
rm -rf /scratch/users/logben/discovery_bids/sourcedata/behavioral/
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /scratch/users/logben/discovery_bids/sourcedata/behavioral \
  --bids-dir /scratch/users/logben/discovery_bids \
  --dry-run
# Verify s29 shows 11/12 (raw ses-09 still unmatched — expected), then run for real
```

### Step 3: Run behavioral rename for validation

```bash
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /scratch/users/logben/validation_bids/sourcedata/behavioral \
  --bids-dir /scratch/users/logben/validation_bids \
  --dry-run
# Review match results, then run for real (remove --dry-run)
```

### Step 4: Add excluded subjects to .bidsignore

```bash
for sub in s214 s222 s250 s297 s432 s823 s968 s1165 s1178 s1266 s1320; do
    echo "sub-${sub}/" >> /scratch/users/logben/validation_bids/.bidsignore
done
```

### Step 5: Audit and document

For each subject with <100% match rate or subset mismatches:
1. Cross-reference with `behavioral.md` notes
2. Cross-reference with scan tracking CSV
3. Add explanation to `sourcedata/NOTES.txt`

---

## Key file locations

| What | Path |
|------|------|
| New discovery BIDS | `/scratch/users/logben/discovery_bids/` |
| New validation BIDS | `/scratch/users/logben/validation_bids/` |
| Behavioral raw | `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned/` |
| Rename script | `scripts/rename_behavioral_to_sourcedata.py` |
| Reconciliation config | `src/neuro_workflow/bidsify/reconciliation_config.json` |
| Included validation subjects | `subs_validation.txt` (41 subjects) |
| Scan notes | `scan_notes/` |
| Old BIDS (reference) | `/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/` |

## Open questions

**s29 raw ses-09** (`{directedForgetting, shapeMatching, spatialTS, stopSignal}`) — this behavioral session has no matching BIDS session. BIDS ses-02 on 2020-11-13 has `{cuedTS, directedForgetting, shapeMatching, stopSignal}` (cuedTS instead of spatialTS). The behavioral data reflects the intended protocol (Set B with spatialTS), but the scanner ran cuedTS instead. This behavioral data has no imaging counterpart and should be documented as such.
