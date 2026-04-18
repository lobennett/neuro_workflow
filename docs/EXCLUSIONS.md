# Scan Exclusions

Every scan listed in `.bidsignore` is documented here with its reason. This is the authoritative reference for why scans are excluded from analysis. Cross-reference with `docs/SCAN-NOTES.md` for data collection context.

**Last updated:** 2026-04-14

**Threshold policy:** Scans with <50% of expected TRs are automatically excluded. Scans with 50-100% of expected TRs are retained and reviewed for salvageability. Events that extend past the BOLD scan duration are automatically ignored by the GLM — no manual trimming needed.

---

## Discovery Sample (.bidsignore)

### Incomplete acquisitions (dim4=1)

| Subject | Session | Task | Run | Reason |
|---------|---------|------|-----|--------|
| s43 | ses-08 | directedForgetting | run-1 | 3D BOLD (dim4=1). run-2 is valid; behavioral maps to run-2. |

### Legacy acquisition sequence

| Pattern | Reason |
|---------|--------|
| `sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*` | Old MPRAGEPromo sequence not used for analysis. Only SagMPRAGE T1w is used. |

### Anatomical quality exclusions

Per collaborator quality review. Comparable-quality scans are both retained.

| Subject | Session | Scan | Reason |
|---------|---------|------|--------|
| s19 | ses-03 | T1w SagMPRAGE | Slight ringing; ses-05 is best quality |
| s19 | ses-01 | T2w CubePromo | Slight ringing; ses-03 is better |
| s29 | ses-04 | T2w CubePromo | FOV/alignment slightly off; ses-01 is good quality |

### Missing behavioral data (irreconcilable)

| Subject | Session | Task | Reason | SCAN-NOTES ref |
|---------|---------|------|--------|----------------|
| s03 | ses-01 | nBack | Behavioral file missing. ses-02 has its own nBack BOLD+behavioral. | s03: "Scan 1: issue with nBack" |
| s19 | ses-02 | goNogo | Behavioral file missing. | s19: "Missing 1 goNogo" |
| s19 | ses-11 | directedForgettingWFlanker | Behavioral file missing. | s19 ses-11 listed in missing behavioral table |
| s29 | ses-01 | cuedTS | Protocol mismatch — spatialTS was the behavioral task but cuedTS was scanned. | s29: "cuedTS BOLD has no events file (irreconcilable)" |
| s29 | ses-02 | goNogo | Behavioral file missing. | s29: "Raw behavioral missing goNogo" |
| s43 | ses-02 | goNogo | Behavioral file missing. | s43 ses-02 missing behavioral |

### Prematurely ended scans (<50% of expected TRs)

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete |
|---------|---------|------|-----------|-------------|-----------|
| s10 | ses-01 | goNogo | 31 | 382 | 8% |
| s29 | ses-03 | spatialTS | 15 | 328 | 5% |
| s29 | ses-11 | stopSignalWFlanker | 179 | 366 | 49% |
| s29 | ses-12 | directedForgettingWFlanker | 54 | 598 | 9% |
| s43 | ses-11 | stopSignalWFlanker | 96 | 366 | 26% |

### Behavioral QC exclusions

| Subject | Session | Task | Reason |
|---------|---------|------|--------|
| s19 | ses-09 | flanker | Omission rate 30% > 25% threshold |

### Non-monotonic onsets — break before 50% of scan

These events files have onsets that decrease before 50% of the scan data was collected. Caused by negative RT correction reconstructing `time_elapsed` out of order. Cannot be reliably modeled.

| Subject | Session | Task | Break onset | % of BOLD at break |
|---------|---------|------|-------------|-------------------|
| s03 | ses-11 | stopSignalWDirectedForgetting | 221.0s → 211.9s | 21% |
| s10 | ses-01 | cuedTS | 72.1s → 70.2s | 15% |

Salvaged (break after 50% — events trimmed to monotonic portion):

| Subject | Session | Task | Break onset | % of BOLD at break | Rows kept |
|---------|---------|------|-------------|-------------------|-----------|
| s10 | ses-02 | shapeMatching | 419.7s → 413.8s | 86% | 469/509 |

Note: s43 ses-11 stopSignalWFlanker had a non-monotonic break at 364s but the BOLD is only 143s (26% TRs) — the break is in the overrun region and the scan is already excluded for being <50% TRs.

---

## Validation Sample (.bidsignore)

### Incomplete acquisitions (dim4=1 or <5 TRs)

| Subject | Session | Task | Run | Reason |
|---------|---------|------|-----|--------|
| s480 | ses-03 | goNogo | run-1 | 3D BOLD (dim4=1). run-2 valid; behavioral maps to run-2. |
| s480 | ses-03 | nBack | run-1 | 3 of 505 TRs (1%). run-2 valid; behavioral maps to run-2. |

### Anatomical quality exclusions

Per collaborator quality review. Comparable-quality scans are both retained (s1351 ses-01/ses-08 both clean; s1399 ses-01/ses-02 T2w both decent).

| Subject | Session | Scan | Reason |
|---------|---------|------|--------|
| s1127 | ses-01 | T1w SagMPRAGE | Heavy ringing, use not recommended; ses-09 is clean |
| s1258 | ses-01 | T1w SagMPRAGE | Mild ringing; ses-06 is better |
| s1270 | ses-06 | T1w SagMPRAGE | Ringing; ses-01 is very slightly better |
| s216 | ses-01 | T1w SagMPRAGE | Heavy ringing; ses-11 is slightly better |

### Missing behavioral data (irreconcilable)

| Subject | Session | Task | Reason | SCAN-NOTES ref |
|---------|---------|------|--------|----------------|
| s300 | ses-08 | flanker | Behavioral data lost — server crash. Makeup in ses-09. | s300: "ses-08 flanker is irreconcilable" |
| s1292 | ses-04 | nBack | Scanner failure. No behavioral data. | s1292: "ses-04 nBack is irreconcilable" |
| s1175 | ses-11 | cuedTSWFlanker | Behavioral file missing per scan notes. | s1175: "Scan 11: cuedTSWFlanker missing" |

### Prematurely ended scans (<50% of expected TRs)

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete |
|---------|---------|------|-----------|-------------|-----------|
| s394 | ses-04 | cuedTS | 2 | 329 | 1% |
| s373 | ses-02 | spatialTS | 12 | 328 | 4% |
| s599 | ses-02 | rest | 31 | 156 | 20% |
| s216 | ses-05 | directedForgetting | 94 | 405 | 23% |
| s956 | ses-04 | cuedTS | 155 | 329 | 47% |
| s1058 | ses-02 | directedForgetting | 196 | 405 | 48% |
| s247 | ses-11 | stopSignalWDirectedForgetting | 345 | 715 | 48% |

### Behavioral QC exclusions

| Subject | Session | Task | Reason |
|---------|---------|------|--------|
| s1134 | ses-08 | spatialTS | Omission rate 26% > 25% threshold |
| s1258 | ses-12 | stopSignalWDirectedForgetting | Go RT 1013ms > 1000ms threshold |
| s1351 | ses-06 | flanker | Omission rate 30% > 25% threshold |
| s1408 | ses-12 | spatialTSWCuedTS | Omission rate 27% > 25% threshold |
| s1445 | ses-12 | spatialTSWCuedTS | Omission rate 26% > 25% threshold |
| s180 | ses-12 | shapeMatchingWCuedTS | Omission rate 76% > 25% threshold |

---

## Salvaged scans (50-100% TRs, NOT in .bidsignore)

These scans were prematurely ended but retained for analysis. Events that extend past the BOLD scan duration are automatically ignored by the GLM. Reduced statistical power is expected.

### Discovery

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete |
|---------|---------|------|-----------|-------------|-----------|
| s19 | ses-04 | shapeMatching | 214 | 325 | 66% |
| s19 | ses-07 | stopSignal | 223 | 398 | 56% |
| s19 | ses-09 | cuedTS | 247 | 329 | 75% |
| s19 | ses-09 | stopSignal | 364 | 398 | 91% |
| s29 | ses-03 | stopSignal | 363 | 398 | 91% |
| s29 | ses-10 | nBack | 443 | 505 | 88% |
| s43 | ses-11 | stopSignalWDirectedForgetting | 517 | 715 | 72% |
| s43 | ses-12 | stopSignalWDirectedForgetting | 384 | 715 | 54% |

### Validation

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete |
|---------|---------|------|-----------|-------------|-----------|
| s1057 | ses-12 | stopSignalWFlanker | 184 | 366 | 50% |
| s1058 | ses-06 | rest | 97 | 156 | 62% |
| s1175 | ses-06 | spatialTS | 252 | 328 | 77% |
| s1314 | ses-05 | goNogo | 262 | 382 | 69% |
| s1391 | ses-08 | directedForgetting | 351 | 405 | 87% |
| s1391 | ses-08 | shapeMatching | 234 | 325 | 72% |
| s320 | ses-12 | stopSignalWDirectedForgetting | 509 | 715 | 71% |
| s336 | ses-05 | goNogo | 298 | 382 | 78% |
| s599 | ses-10 | nBack | 428 | 505 | 85% |
| s76 | ses-01 | flanker | 176 | 236 | 75% |
| s76 | ses-01 | stopSignal | 309 | 398 | 78% |
| s76 | ses-05 | nBack | 336 | 505 | 67% |
| s874 | ses-06 | cuedTS | 284 | 329 | 86% |

---

## Summary

| Category | Discovery | Validation | Total |
|----------|-----------|------------|-------|
| Incomplete acquisitions (dim4=1) | 1 | 2 | 3 |
| Legacy acquisition sequence | all subjects | 0 | N/A |
| Anatomical quality | 3 | 4 | 7 |
| Missing behavioral (irreconcilable) | 6 | 3 | 9 |
| Prematurely ended (<50% TRs) | 5 | 7 | 12 |
| Behavioral QC | 1 | 6 | 7 |
| Non-monotonic onsets (<50%) | 2 | 0 | 2 |
| **Total excluded scan entries** | **18** | **22** | **40** |
| Salvaged scans (50-100% TRs) | 8 | 13 | 21 |

## Session offset notes

Five validation subjects have split/skipped BIDS sessions creating a +1 offset between raw behavioral and BIDS session numbers. Handled in reconciliation manifests (`config/manifests/reconciliation_*.tsv`).

| Subject | Split session | Nature |
|---------|-------------|--------|
| s321 | ses-02 | Rest-only split (subject pulled out, restarted) |
| s1445 | ses-02 | Split session |
| s1326 | ses-03 | Rest-only split (subject adjusted earplugs) |
| s1391 | ses-06 | Split session |
| s1258 | ses-07 | Skipped (behavioral missing cuedTS, extra spatialTS) |

## Multi-run cases

Where run-1 is bidsignored, the behavioral file maps to run-2 via `dest_run` in the reconciliation manifest. Where both runs are valid, separate behavioral files exist for each.

| Subject | Session | Task | run-1 | run-2 | Notes |
|---------|---------|------|-------|-------|-------|
| s10 | ses-01 | goNogo | bidsignored (31 TRs) | valid | Behavioral → run-2 |
| s43 | ses-08 | directedForgetting | bidsignored (dim4=1) | valid | Behavioral → run-2 |
| s480 | ses-03 | goNogo | bidsignored (dim4=1) | valid | Behavioral → run-2 |
| s480 | ses-03 | nBack | bidsignored (3 TRs) | valid | Behavioral → run-2 |
| s1175 | ses-12 | cuedTSWFlanker | valid (425 TRs) | valid (420 TRs) | Separate behavioral |
| s247 | ses-12 | stopSignalWDirectedForgetting | valid (725 TRs) | valid (723 TRs) | Separate behavioral |
| s76 | ses-12 | directedForgettingWFlanker | valid (602 TRs) | valid (605 TRs) | Separate behavioral |
| s29 | ses-03 | spatialTS | bidsignored (15 TRs) | valid | Behavioral → run-2 |
| s29 | ses-12 | directedForgettingWFlanker | bidsignored (54 TRs) | valid | Behavioral → run-2 |
| s43 | ses-11 | stopSignalWDirectedForgetting | salvaged (517 TRs) | valid | Behavioral → run-2 |
| s394 | ses-04 | cuedTS | bidsignored (2 TRs) | valid | Behavioral → run-2 |
| s373 | ses-02 | spatialTS | bidsignored (12 TRs) | valid | Behavioral → run-2 |
| s216 | ses-05 | directedForgetting | bidsignored (94 TRs) | valid | Behavioral → run-2 |
| s336 | ses-05 | goNogo | salvaged (298 TRs) | valid | Behavioral → run-2 |
