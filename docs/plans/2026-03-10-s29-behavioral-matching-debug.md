# Behavioral-to-BIDS Session Matching — Comprehensive Plan

**Date:** 2026-03-11 (updated)
**Status:** Ready for implementation

## Source of truth hierarchy

1. **Flywheel data** — ground truth for what was actually scanned
2. **raw_cleaned behavioral data** — already adjusted for known issues (flipped mappings, etc.)
3. **Scan tracking sheets** — biased, prone to manual entry errors. Use for context only.
4. **Behavioral notes (behavioral.md)** — documents known missing tasks per subject

## Decisions made

- Subset mismatches (BIDS has tasks with no behavioral CSV) are **acceptable** — behavioral data was sometimes lost, corrupted, or excluded during QC
- Flywheel data is authoritative — tracking sheet disagreements are tracking sheet errors
- s29-2/20210305 is NOT a duplicate — it is s29's Scan 10 (2021-03-05) with `{rest, flanker, goNogo, nBack}`, collected under the wrong subject label

---

## Part 1: Fix s29-2/20210305 exclusion (bidsify config)

### Problem

`reconciliation_config.json` excludes `s29-2/20210305` as a "true duplicate." It is actually s29's Scan 10 (2021-03-05) with real task data (`{rest, flanker, goNogo, nBack}`). The old `compare_fw_oak.py` script excluded it, but the old BIDS was wrong to do so.

### Fix

Remove the `s29-2` session override entirely from `reconciliation_config.json`:

```json
// REMOVE this block:
"s29-2": {
    "20210305": {
        "exclude": true,
        "reason": "True duplicate of s29 session..."
    }
}
```

### Impact

- s29 goes from 12 to **13 BIDS sessions**
- New session slots in as **ses-11** (2021-03-05), between current ses-10 (2021-03-03) and ses-11 (2021-03-17)
- Current ses-11 and ses-12 become ses-12 and ses-13
- Behavioral matching improves from 10/12 to **11/12**:
  - raw ses-10 (`{flanker, goNogo, nBack}`) now matches new BIDS ses-11 (`{flanker, goNogo, nBack}`)
  - raw ses-11 and ses-12 (dual tasks) shift to match BIDS ses-12 and ses-13

### After fix — s29 session mapping

```
BIDS ses-01 (2020-11-11): fmap only (single-echo test session)
BIDS ses-02 (2020-11-13): cuedTS, directedForgetting, shapeMatching, stopSignal
BIDS ses-03 (2020-11-14): cuedTS, flanker, goNogo, nBack   ← raw ses-08 (pass 2)
BIDS ses-04 (2020-12-02): Set B                             ← raw ses-01
BIDS ses-05 (2020-12-04): Set A                             ← raw ses-02
BIDS ses-06 (2021-02-03): Set B                             ← raw ses-03
BIDS ses-07 (2021-02-05): Set A                             ← raw ses-04
BIDS ses-08 (2021-02-24): Set B                             ← raw ses-05
BIDS ses-09 (2021-02-25): Set A                             ← raw ses-06
BIDS ses-10 (2021-03-03): Set B                             ← raw ses-07
BIDS ses-11 (2021-03-05): flanker, goNogo, nBack (s29-2)    ← raw ses-10 (pass 2)
BIDS ses-12 (2021-03-17): dual tasks                        ← raw ses-11 (pass 2)
BIDS ses-13 (2021-03-19): dual tasks                        ← raw ses-12 (pass 2)
```

**Remaining unmatched:** raw ses-09 (`{directedForgetting, shapeMatching, spatialTS, stopSignal}`) — no BIDS session has this exact task set. BIDS ses-02 has `cuedTS` instead of `spatialTS`. This behavioral session has no corresponding imaging data.

**Remaining skipped BIDS:** ses-01 (fmap only), ses-02 (non-standard task set — no behavioral data exists for it)

---

## Part 2: Discovery sample — expected match results after fix

| Subject | Expected | Notes |
|---------|----------|-------|
| s03 | 12/12 | ses-01 subset: BIDS has `nBack` with no behavioral (behavioral.md: "s03 issue w/ nBack") |
| s10 | 12/12 EXACT | No issues |
| s19 | 12/12 | ses-02 subset: missing `goNogo` behavioral (behavioral.md: "s19 Missing 1 goNogo"); ses-11 subset: missing `directedForgettingWFlanker` behavioral |
| s29 | **11/12** | raw ses-09 has no BIDS match (task protocol mismatch). BIDS ses-01/ses-02 have no behavioral match. |
| s43 | 12/12 | ses-02 subset: missing `goNogo` behavioral (behavioral.md: "s43 Missing 1 goNogo") |

All subset mismatches are **explained by behavioral.md notes** — confirmed acceptable.

---

## Part 3: Validation sample — excluded subjects and .bidsignore

### Included subjects (from subs_validation.txt, 41 subjects)

```
s76 s180 s216 s247 s286 s295 s300 s320 s321 s336 s373 s394 s415
s480 s599 s645 s874 s956 s1035 s1057 s1058 s1127 s1134 s1175
s1189 s1258 s1267 s1270 s1273 s1292 s1314 s1326 s1338 s1351
s1391 s1399 s1402 s1408 s1445 s1481 s1486
```

### Excluded subjects (in config but NOT in subs_validation.txt, 11 subjects)

These should still be pulled into BIDS but added to `.bidsignore`:

```
s214  — dropped for being unreliable
s222  — dropped for poor behavioral performance
s250  — dropped (lens prescription issue)
s297  — discontinued (ear issues after scanning)
s432  — dropped
s823  — ?
s968  — ?
s1165 — ?
s1178 — ?
s1266 — ?
s1320 — ?
```

### .bidsignore additions needed

After bidsify runs, add glob patterns to `.bidsignore` for excluded subjects:

```
sub-s214/
sub-s222/
sub-s250/
sub-s297/
sub-s432/
sub-s823/
sub-s968/
sub-s1165/
sub-s1178/
sub-s1266/
sub-s1320/
```

---

## Part 4: Validation behavioral matching — known issues from scan notes

From `behavioral.md` and `validation_scan_tracking.csv`:

| Subject | Issue | Impact on matching |
|---------|-------|--------------------|
| s1175 | ses-11 cuedTSWFlanker missing | Subset mismatch expected |
| s1035 | Missing 1 goNogo, shapeMatching; extra stop, flanker | Session task sets may differ from standard |
| s1314 | Missing goNogo, nBack, shapeMatching, spatialTS; extra stop, flanker, cuedTS, DF | Heavily modified protocol |
| s956 | Missing 1 goNogo, 1 flanker; extra shapeMatching, stopSignal | |
| s295 | Missing 1 spatial | |
| s1258 | Missing 1 cuedTS; extra spatial | |
| s76 | ses-01 stopSignal/flanker stopped after block 3; ses-05 nBack wrong TR; ses-11 directedForgettingWFlanker n/a | |
| s247 | ses-01 spatialTS failed then reran; flipped flanker mapping | |
| s297 | rest and nBack missing from session | |

---

## Part 5: Implementation steps

### Step 1: Remove s29-2/20210305 exclusion

```bash
# Edit reconciliation_config.json — remove the s29-2 session_overrides block
# Run tests
uv run python -m pytest tests/bidsify/ -k "not test_download_and_place"
# Commit
```

### Step 2: Rerun bidsify for discovery

```bash
# Clear and rerun discovery
rm -rf /scratch/users/logben/discovery_bids/
neuro_workflow submit bidsify --sample discovery --output-dir /scratch/users/logben/discovery_bids
# Wait for job, verify s29 now has 13 sessions
ls -d /scratch/users/logben/discovery_bids/sub-s29/ses-*
```

### Step 3: Rerun behavioral rename for discovery

```bash
rm -rf /scratch/users/logben/discovery_bids/sourcedata/behavioral/
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /scratch/users/logben/discovery_bids/sourcedata/behavioral \
  --bids-dir /scratch/users/logben/discovery_bids \
  --dry-run
# Verify s29 shows 11/12, then run for real (remove --dry-run)
```

### Step 4: Run bidsify for validation

```bash
neuro_workflow submit bidsify --sample validation --output-dir /scratch/users/logben/validation_bids
# Wait for job
```

### Step 5: Add excluded subjects to .bidsignore

After validation bidsify completes, append excluded subject directories to `.bidsignore`:

```bash
# Script should handle this, or manually:
for sub in s214 s222 s250 s297 s432 s823 s968 s1165 s1178 s1266 s1320; do
    echo "sub-${sub}/" >> /scratch/users/logben/validation_bids/.bidsignore
done
```

### Step 6: Run behavioral rename for validation

```bash
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /scratch/users/logben/validation_bids/sourcedata/behavioral \
  --bids-dir /scratch/users/logben/validation_bids \
  --dry-run
# Review match results, then run for real
```

### Step 7: Audit and document

For each subject with <100% match rate or subset mismatches:
1. Cross-reference with `behavioral.md` notes
2. Cross-reference with scan tracking CSV
3. Add explanation to `sourcedata/NOTES.txt`

---

## Part 6: Script changes needed

### `reconciliation_config.json`
- Remove `s29-2` from `session_overrides`
- Add excluded validation subjects list (or handle in code)

### `src/neuro_workflow/bidsify/run.py`
- After writing `.bidsignore`, also append excluded subject directories for validation sample
- Need a way to know which subjects are excluded (could add `excluded_subjects` field to config, or read from `subs_validation.txt`)

### `scripts/rename_behavioral_to_sourcedata.py`
- No logic changes needed — two-pass matcher already handles the s29 case correctly once the BIDS data is right

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

## Open question

**s29 raw ses-09** (`{directedForgetting, shapeMatching, spatialTS, stopSignal}`) — this behavioral session has no matching BIDS session. BIDS ses-02 on 2020-11-13 has `{cuedTS, directedForgetting, shapeMatching, stopSignal}` (cuedTS instead of spatialTS). Was s29's Scan 1 protocol different from what was intended? The behavioral data reflects the intended protocol (Set B with spatialTS), but the scanner ran cuedTS instead. This behavioral data has no imaging counterpart and should be documented as such.
