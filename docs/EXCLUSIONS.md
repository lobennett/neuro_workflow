# Scan Exclusions

Every scan listed in `.bidsignore` is documented here with its reason. This is the authoritative reference for why scans are excluded from analysis. Cross-reference with `docs/SCAN-NOTES.md` for data collection context.

**Last updated:** 2026-04-12

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

### Anatomical quality exclusions (Discovery)

Per collaborator quality review. For each subject with multiple T1w/T2w, the worse-quality scan is excluded. Comparable-quality scans are both retained.

| Subject | Session | Scan | Reason |
|---------|---------|------|--------|
| s19 | ses-03 | T1w SagMPRAGE | Slight ringing; ses-05 is best quality |
| s19 | ses-01 | T2w CubePromo | Slight ringing; ses-03 is better |
| s29 | ses-04 | T2w CubePromo | FOV/alignment slightly off; ses-01 is good quality |

### Missing behavioral data (irreconcilable)

| Subject | Session | Task | Reason | SCAN-NOTES ref |
|---------|---------|------|--------|----------------|
| s03 | ses-01 | nBack | Behavioral file missing. ses-02 has its own nBack BOLD+behavioral. | s03: "Scan 1: issue with nBack" |
| s19 | ses-02 | goNogo | Behavioral file missing. | s19: "Missing 1 goNogo (per behavioral notes)" |
| s19 | ses-11 | directedForgettingWFlanker | Behavioral file missing. | s19 ses-11 listed in missing behavioral table |
| s29 | ses-01 | cuedTS | Protocol mismatch — spatialTS was the behavioral task but cuedTS was scanned. | s29: "cuedTS BOLD has no events file (irreconcilable)" |
| s29 | ses-02 | goNogo | Behavioral file missing. | s29: "Raw behavioral missing goNogo" |
| s43 | ses-02 | goNogo | Behavioral file missing. | s43 ses-02 listed in missing behavioral table |

### Prematurely ended scans

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete | Reason |
|---------|---------|------|-----------|-------------|-----------|--------|
| s10 | ses-01 | goNogo | 31 | 382 | 8% | run-1 only; run-2 has full data and behavioral maps to run-2 |
| s29 | ses-03 | spatialTS | 15 | 328 | 5% | Scan terminated early |
| s29 | ses-03 | stopSignal | 363 | 398 | 91% | Scan terminated early |
| s29 | ses-10 | nBack | 443 | 505 | 88% | Scan terminated early |
| s29 | ses-11 | stopSignalWFlanker | 179 | 366 | 49% | Scan terminated early |
| s29 | ses-12 | directedForgettingWFlanker | 54 | 598 | 9% | Scan terminated early |
| s19 | ses-04 | shapeMatching | 214 | 325 | 66% | Scan terminated early |
| s19 | ses-07 | stopSignal | 223 | 398 | 56% | Scan terminated early |
| s19 | ses-09 | cuedTS | 247 | 329 | 75% | Scan terminated early |
| s19 | ses-09 | flanker | 182 | 236 | 77% | Scan terminated early |
| s19 | ses-09 | stopSignal | 364 | 398 | 91% | Scan terminated early |
| s43 | ses-11 | stopSignalWFlanker | 96 | 366 | 26% | Scan terminated early |
| s43 | ses-11 | stopSignalWDirectedForgetting | 517 | 715 | 72% | Scan terminated early |
| s43 | ses-12 | stopSignalWDirectedForgetting | 384 | 715 | 54% | Scan terminated early |

---

## Validation Sample (.bidsignore)

### Incomplete acquisitions (dim4=1)

| Subject | Session | Task | Run | Reason |
|---------|---------|------|-----|--------|
| s480 | ses-03 | goNogo | run-1 | 3D BOLD (dim4=1). run-2 is valid; behavioral maps to run-2. |
| s480 | ses-03 | nBack | run-1 | 3 of 505 TRs (1%). run-2 is valid; behavioral maps to run-2. |

### Anatomical quality exclusions (Validation)

Per collaborator quality review. For each subject with multiple T1w, the worse-quality scan is excluded. Comparable-quality scans are both retained (e.g., s1351 ses-01 and ses-08 both clean; s1399 ses-01 and ses-02 T2w both decent).

| Subject | Session | Scan | Reason |
|---------|---------|------|--------|
| s1127 | ses-01 | T1w SagMPRAGE | Heavy ringing, use not recommended; ses-09 is clean |
| s1258 | ses-01 | T1w SagMPRAGE | Mild ringing; ses-06 is better |
| s1270 | ses-06 | T1w SagMPRAGE | Ringing; ses-01 is very slightly better |
| s216 | ses-01 | T1w SagMPRAGE | Heavy ringing; ses-11 is slightly better |

### Missing behavioral data (irreconcilable)

| Subject | Session | Task | Reason | SCAN-NOTES ref |
|---------|---------|------|--------|----------------|
| s300 | ses-08 | flanker | Behavioral data lost — server shut down before save. Makeup flanker collected in ses-09. | s300: "ses-08 flanker is irreconcilable" |
| s1292 | ses-04 | nBack | Scanner failure, nBack ended before task completed. No behavioral data. | s1292: "ses-04 nBack is irreconcilable" |
| s1175 | ses-11 | cuedTSWFlanker | Behavioral file missing per scan notes. | s1175: "Scan 11: cuedTSWFlanker missing" |

### Prematurely ended scans

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete | Reason |
|---------|---------|------|-----------|-------------|-----------|--------|
| s394 | ses-04 | cuedTS | 2 | 329 | 1% | Scan terminated early |
| s373 | ses-02 | spatialTS | 12 | 328 | 4% | Scan terminated early |
| s599 | ses-02 | rest | 31 | 156 | 20% | Scan terminated early |
| s216 | ses-05 | directedForgetting | 94 | 405 | 23% | Scan terminated early |
| s956 | ses-04 | cuedTS | 155 | 329 | 47% | SCAN-NOTES: "cuedTS cut halfway through" |
| s1058 | ses-02 | directedForgetting | 196 | 405 | 48% | Scan terminated early |
| s247 | ses-11 | stopSignalWDirectedForgetting | 345 | 715 | 48% | Scan terminated early |
| s1057 | ses-12 | stopSignalWFlanker | 184 | 366 | 50% | Scan terminated early |
| s1058 | ses-06 | rest | 97 | 156 | 62% | Scan terminated early |
| s76 | ses-05 | nBack | 336 | 505 | 67% | SCAN-NOTES: "nBack task TR was wrong — entire run invalid" |
| s1314 | ses-05 | goNogo | 262 | 382 | 69% | SCAN-NOTES: "goNogo cut with 3 minutes remaining" |
| s320 | ses-12 | stopSignalWDirectedForgetting | 509 | 715 | 71% | Scan terminated early |
| s1391 | ses-08 | shapeMatching | 234 | 325 | 72% | Scan terminated early |
| s76 | ses-01 | flanker | 176 | 236 | 75% | SCAN-NOTES: "stopSignal and flanker stopped after block 3" |
| s1175 | ses-06 | spatialTS | 252 | 328 | 77% | Scan terminated early |
| s336 | ses-05 | goNogo | 298 | 382 | 78% | Scan terminated early |
| s76 | ses-01 | stopSignal | 309 | 398 | 78% | SCAN-NOTES: "stopSignal and flanker stopped after block 3" |
| s599 | ses-10 | nBack | 428 | 505 | 85% | Scan terminated early |
| s874 | ses-06 | cuedTS | 284 | 329 | 86% | Scan terminated early |
| s1391 | ses-08 | directedForgetting | 351 | 405 | 87% | Scan terminated early |

---

## Summary

| Category | Discovery | Validation | Total |
|----------|-----------|------------|-------|
| Incomplete acquisitions (dim4=1) | 1 | 2 | 3 |
| Legacy acquisition sequence | all subjects | 0 | N/A |
| Missing behavioral (irreconcilable) | 6 | 3 | 9 |
| Prematurely ended scans | 14 | 20 | 34 |
| **Total excluded scan entries** | **22** | **25** | **47** |

Note: s03 ses-01 nBack appears as both irreconcilable (missing behavioral) and prematurely ended (475/505 TRs, 94%). It is counted once in the total.

## Session offset notes

Five validation subjects have split/skipped BIDS sessions that create a +1 offset between raw behavioral session numbers and BIDS session numbers. These are handled in the reconciliation manifests (`config/manifests/reconciliation_*.tsv`) by mapping behavioral files to the correct BIDS session. The split sessions themselves contain only rest data.

| Subject | Split session | Nature |
|---------|-------------|--------|
| s321 | ses-02 | Rest-only split (subject pulled out, restarted) |
| s1445 | ses-02 | Split session |
| s1326 | ses-03 | Rest-only split (subject adjusted earplugs) |
| s1391 | ses-06 | Split session |
| s1258 | ses-07 | Skipped (behavioral missing cuedTS, extra spatialTS) |

## Multi-run cases

These scans have both run-1 and run-2 BOLD. Where run-1 is bidsignored, the behavioral file maps to run-2 via the `dest_run` column in the reconciliation manifest. Where both runs are valid, separate behavioral files exist for each run.

| Subject | Session | Task | run-1 | run-2 | Notes |
|---------|---------|------|-------|-------|-------|
| s10 | ses-01 | goNogo | bidsignored (31 TRs) | valid | Behavioral → run-2 |
| s43 | ses-08 | directedForgetting | bidsignored (dim4=1) | valid | Behavioral → run-2 |
| s480 | ses-03 | goNogo | bidsignored (dim4=1) | valid | Behavioral → run-2 |
| s480 | ses-03 | nBack | bidsignored (3 TRs) | valid | Behavioral → run-2 |
| s1175 | ses-12 | cuedTSWFlanker | valid (425 TRs) | valid (420 TRs) | Separate behavioral for each run |
| s247 | ses-12 | stopSignalWDirectedForgetting | valid (725 TRs) | valid (723 TRs) | Separate behavioral for each run |
| s76 | ses-12 | directedForgettingWFlanker | valid (602 TRs) | valid (605 TRs) | Separate behavioral for each run |
| s29 | ses-03 | spatialTS | bidsignored (15 TRs) | valid | Behavioral → run-2 |
| s29 | ses-12 | directedForgettingWFlanker | bidsignored (54 TRs) | valid | Behavioral → run-2 |
| s43 | ses-11 | stopSignalWDirectedForgetting | bidsignored (517 TRs) | valid | Behavioral → run-2 |
| s394 | ses-04 | cuedTS | bidsignored (2 TRs) | valid | Behavioral → run-2 |
| s373 | ses-02 | spatialTS | bidsignored (12 TRs) | valid | Behavioral → run-2 |
| s216 | ses-05 | directedForgetting | bidsignored (94 TRs) | valid | Behavioral → run-2 |
| s336 | ses-05 | goNogo | bidsignored (298 TRs) | valid | Behavioral → run-2 |
