# Cohort Reproduction Certificate

This certifies that the `scripts/reproduce_cohort.py` harness reproduced both
the discovery and validation cohorts from their Flywheel replay snapshots and
that the reproduced BIDS/exclusion/lev2-eligible sets matched the real,
on-disk data exactly (zero mismatches across all three diffs).

- **Run date:** 2026-07-05
- **Repo code SHA:** `9d2ab473eca764f9346f730e8ddc00482755f0d6`
- **fMRIPrep version:** 25.2.4

## Results

### Discovery cohort — PASS (exit 0)

| Diff | Result | Matched | Only in produced | Only in reference |
|---|---|---|---|---|
| Filenames | PASS | 2035 | 0 | 0 |
| Exclusion-set | PASS | 25 | 0 | 0 |
| Lev2-eligible | PASS | 220 | 0 | 0 |

### Validation cohort — PASS (exit 0)

| Diff | Result | Matched | Only in produced | Only in reference |
|---|---|---|---|---|
| Filenames | PASS | 15983 | 0 | 0 |
| Exclusion-set | PASS | 46 | 0 | 0 |
| Lev2-eligible | PASS | 1797 | 0 | 0 |

## PHI note

The Flywheel replay snapshots used to drive this reproduction
(`data/repro/fw_inventory_{discovery,validation}.json`) are retained in a
controlled, non-git location because they contain scan-date metadata (PHI).
They are not part of this repository and are not referenced by content in
this certificate.
