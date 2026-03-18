# BIDS Directory Audit: Old (Oak) vs New (Scratch)

**Date:** 2026-03-11

**Purpose:** Compare the original BIDS directories on Oak against the newly generated ones in scratch to verify correctness and identify differences in how sessions, files, and data issues were handled.

**Old directories:**
- Discovery: `/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402`
- Validation: `/oak/stanford/groups/russpold/data/network_grant/validation_BIDS`

**New directories:**
- Discovery: `/scratch/users/logben/discovery_bids`
- Validation: `/scratch/users/logben/validation_bids`

---

## Discovery

| Aspect | Old | New |
|--------|-----|-----|
| Subjects | 5 | 5 (same) |
| Sessions per subject | 12 | 12 (same) |
| Events files | 224 | **0** |
| DWI | s29 only | **s03, s10, s29, s43** (4 subjects gained DWI) |
| Extra func runs | -- | goNogo run-02 (s10, s29), spatialTS run-02 (s29), others |
| Anat naming | `run-1_T1w` | `acq-SagMPRAGE_T1w` (more descriptive) |
| s29 ses-01 task | spatialTS BOLD | **cuedTS** BOLD (correct per scan notes) |
| Provenance | minimal | `sourcedata/`, `reconciliation.json`, `NOTES.txt` |

### Discovery Notes

- **DWI gains:** The old directory only had DWI for s29. The new pipeline correctly pulls DWI for s03, s10, s29, and s43 via the expanded acquisition map.
- **Extra functional runs:** Some sessions had duplicate or extra acquisitions on Flywheel (e.g., goNogo run-02 for s10 and s29). The new pipeline downloads all available runs.
- **Anatomical naming:** Old used generic `run-1_T1w`; new uses acquisition-descriptive labels like `acq-SagMPRAGE_T1w`.
- **s29 ses-01:** Old directory had spatialTS (the behavioral task), but the scanner actually ran cuedTS. New directory correctly has cuedTS BOLD, which is marked irreconcilable in `.bidsignore` since there is no matching behavioral/events data.
- **Events files:** Old had 224 events files. New has 0 -- these have not yet been generated.

---

## Validation

| Aspect | Old | New |
|--------|-----|-----|
| Subjects | 52 | 52 (same) |
| Tasks | 20 | 20 (same) |
| Split-session subjects | ses-01 through ses-12 | **ses-13** gained for 5 subjects |
| Func NIfTIs | baseline | **+36** overall |
| Events files | 1,888 | **0** |
| Physio files | 9,228 | **0** |
| `.bidsignore` | minimal | Comprehensive (11 excluded subjects + known bad runs) |
| spatialTS/cuedTS | present | **+6 each** |

### Validation Notes

- **Split sessions:** 5 subjects (s321, s1326, s1391, s1445, s1292) gain ses-13 in the new directory. The old directory merged split sessions or dropped the extra data; the new pipeline preserves all Flywheel sessions chronologically.
- **+36 func NIfTIs:** From split session data, s250 gaining data previously absent, and duplicate/extra acquisitions now captured.
- **`.bidsignore` coverage:** New directory has comprehensive ignore entries:
  - 11 excluded subjects: s214, s222, s250, s297, s432, s823, s968, s1165, s1178, s1266, s1320
  - Irreconcilable runs: s300/ses-08 flanker (behavioral data lost), s1292/ses-04 nBack (scanner failure)
- **Events files:** Old had 1,888 events files. New has 0 -- not yet generated.
- **Physio files:** Old had 9,228 physio files. New has 0 -- physio was not part of the Flywheel download pipeline.
- **spatialTS/cuedTS:** Both well-represented. New has +6 of each due to split sessions and extra acquisitions.
- **s300 flanker and s1292 nBack:** BOLD files exist in both old and new, but new correctly marks these as irreconcilable in `.bidsignore`.

---

## Gaps to Address

1. **Events files** -- Both new directories have 0 events files. These need to be generated (likely via `neuro-run events create` or equivalent).
2. **Physio files** -- Old validation had 9,228 physio files. These were not part of the Flywheel download pipeline and would need separate handling if required for analyses.
