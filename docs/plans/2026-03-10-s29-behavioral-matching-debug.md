# s29 Behavioral Session Matching — Debug Plan

**Date:** 2026-03-10
**Status:** Needs investigation tomorrow

## Current state

Behavioral rename ran on new discovery BIDS at `/scratch/users/logben/discovery_bids/`.
Session mapping written to `sourcedata/behavioral/session_mapping.json`.

### Match results across all subjects

| Subject | Matched | Issues |
|---------|---------|--------|
| s03 | 12/12 | ses-01: BIDS has `nBack` but behavioral doesn't (subset match, not exact) |
| s10 | **12/12 EXACT** | No issues |
| s19 | 12/12 | ses-02: BIDS has `goNogo` not in behavioral; ses-11: BIDS has `directedForgettingWFlanker` not in behavioral |
| s29 | **10/12** | 2 unmatched behavioral, 2 skipped BIDS, plus 1 subset mismatch |
| s43 | 12/12 | ses-02: BIDS has `goNogo` not in behavioral |

### "Subset match" problem (affects s03, s19, s29, s43)

The matcher uses `raw_tasks <= bids_tasks` (subset), so it succeeds when
behavioral has FEWER tasks than BIDS. This means a session can match even
though BIDS has tasks with no corresponding behavioral CSV. These are
one-directional mismatches — every behavioral file has a BIDS counterpart,
but some BIDS tasks lack a behavioral file.

**Specific subset mismatches:**

| Subject | Raw session | BIDS session | Extra BIDS tasks (no behavioral) |
|---------|-------------|--------------|----------------------------------|
| s03 | ses-01 | ses-01 | `nBack` |
| s19 | ses-02 | ses-02 | `goNogo` |
| s19 | ses-11 | ses-11 | `directedForgettingWFlanker` |
| s29 | ses-02 | ses-05 | `goNogo` |
| s43 | ses-02 | ses-02 | `goNogo` |

**Likely cause:** The subject was scanned on that task but the behavioral
data was either not collected, corrupted, or excluded during QC. This is
probably fine — the behavioral CSVs that DO exist are correctly placed,
there's just no behavioral file for that one task.

**Action needed:** Verify with Patrick/Russ whether missing behavioral
CSVs for these tasks are expected (known exclusions) or represent data loss.

### s29 unmatched sessions (the real problem)

**2 unmatched behavioral sessions:**

```
raw ses-09: {directedForgetting, shapeMatching, spatialTS, stopSignal}
raw ses-10: {flanker, goNogo, nBack}
```

**2 skipped BIDS sessions:**

```
BIDS ses-01: fmap only (no func data — single-echo protocol, first visit)
BIDS ses-02: {cuedTS, directedForgetting, shapeMatching, stopSignal}
```

**Why they don't match:**

- `raw ses-09` has `spatialTS` but BIDS ses-02 has `cuedTS` instead.
  These are different task sets — neither is a subset of the other.
- `raw ses-10` has `{flanker, goNogo, nBack}` which is a subset of
  BIDS ses-03 `{cuedTS, flanker, goNogo, nBack}` — but ses-03 was
  already consumed by `raw ses-08` in pass 2.

**What this means:** s29's early Flywheel sessions (ses-01/ses-02) used
a different task protocol than the rest. The behavioral raw_cleaned data
was numbered assuming a different session order. Behavioral ses-09 and
ses-10 appear to be the sessions that correspond to early scans with a
different protocol.

### s29 session timeline (full picture)

```
BIDS ses-01 (2020-11-11): fmap only — single-echo protocol
BIDS ses-02 (2020-11-13): cuedTS, directedForgetting, shapeMatching, stopSignal
                          ^ different task set (no spatialTS, has cuedTS in Set B)
BIDS ses-03 (2020-11-14): cuedTS, flanker, goNogo, nBack  ← matched to raw ses-08
BIDS ses-04 (2020-12-02): ← matched to raw ses-01
...
BIDS ses-10 (2021-03-03): ← matched to raw ses-07
BIDS ses-11 (2021-03-17): ← matched to raw ses-11
BIDS ses-12 (2021-03-19): ← matched to raw ses-12
```

## TODO for tomorrow

### 1. Decide: are the subset mismatches acceptable?

For s03/ses-01, s19/ses-02, s19/ses-11, s29/ses-02, s43/ses-02:
BIDS has tasks that behavioral doesn't. The behavioral files that DO exist
are placed correctly. The question is whether the missing behavioral CSVs
are expected (subject skipped that task, data was excluded, etc.).

**If acceptable:** No code changes needed. Document in NOTES.txt.

**If not acceptable:** Check the raw_cleaned exclusions directory and
`fmri_behavior_exclusions/` for those specific task/session combos.
Path: `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/fmri_behavior_exclusions/`

### 2. Resolve s29 raw ses-09 and ses-10

These behavioral sessions have no matching BIDS session. Options:

**Option A: Manual investigation**
- Check if raw ses-09 and ses-10 correspond to BIDS ses-02 (different
  protocol) by examining timestamps or acquisition content
- If they do, the task mismatch is because the protocol changed mid-study
  and behavioral data reflects the intended protocol, not what was actually
  scanned
- In that case, we could relax the match for s29 specifically (config override)

**Option B: Check old mapping**
- Look at the old discovery BIDS behavioral sourcedata (if it exists) to
  see how ses-09/ses-10 were handled previously
- Path to check: `/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/sourcedata/`

**Option C: Accept the gap**
- 10/12 is the best automatic matching can do for s29
- Document that raw ses-09 and ses-10 have no BIDS match due to early
  protocol differences
- Flag for manual review by PI

### 3. Verify the rename output

After resolving the above, verify the final state:
```bash
# Count files per subject
for sub in s03 s10 s19 s29 s43; do
    echo "$sub: $(find /scratch/users/logben/discovery_bids/sourcedata/behavioral/sub-$sub -name '*.csv' | wc -l) CSVs"
done

# Spot-check a session
ls /scratch/users/logben/discovery_bids/sourcedata/behavioral/sub-s03/ses-01/beh/
```

### 4. Rerun the rename if changes are made

If any matching logic or config changes are needed:
```bash
# Delete existing output
rm -rf /scratch/users/logben/discovery_bids/sourcedata/behavioral/

# Dry run first
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /scratch/users/logben/discovery_bids/sourcedata/behavioral \
  --bids-dir /scratch/users/logben/discovery_bids \
  --dry-run

# Then for real
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /scratch/users/logben/discovery_bids/sourcedata/behavioral \
  --bids-dir /scratch/users/logben/discovery_bids
```

## Key file locations

- New BIDS: `/scratch/users/logben/discovery_bids/`
- Behavioral raw: `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned/`
- Session mapping: `/scratch/users/logben/discovery_bids/sourcedata/behavioral/session_mapping.json`
- Rename script: `scripts/rename_behavioral_to_sourcedata.py`
- Matching logic: `scripts/rename_behavioral_to_sourcedata.py:match_sessions()` (two-pass greedy)
- Reconciliation config: `src/neuro_workflow/bidsify/reconciliation_config.json`
- Old BIDS (reference): `/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/`
