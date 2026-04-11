# Scan Exclusions

Every scan listed in `.bidsignore` is documented here with its reason. This is the authoritative reference for why scans are excluded from analysis. Cross-reference with `docs/SCAN-NOTES.md` for data collection context.

**Last updated:** 2026-04-11

---

## Discovery Sample (.bidsignore)

### Incomplete acquisitions (dim4=1)

| Subject | Session | Task | Reason |
|---------|---------|------|--------|
| s43 | ses-08 | directedForgetting | 3D BOLD (dim4=1) — scan ended prematurely. run-2 is valid and promoted to run-1. |

### Legacy acquisition sequence

| Pattern | Reason |
|---------|--------|
| `sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*` | Old MPRAGEPromo sequence not used for analysis. Only SagMPRAGE T1w is used. |

### Missing behavioral data (irreconcilable)

| Subject | Session | Task | Reason | SCAN-NOTES ref |
|---------|---------|------|--------|----------------|
| s03 | ses-01 | nBack | Behavioral file missing. Both ses-01 and ses-02 have nBack BOLD; ses-02 has its own behavioral file. | s03: "Scan 1: issue with nBack" |
| s19 | ses-02 | goNogo | Behavioral file missing. | s19: "Missing 1 goNogo (per behavioral notes)" |
| s19 | ses-11 | directedForgettingWFlanker | Behavioral file missing. | s19 ses-11 listed in missing behavioral table |
| s29 | ses-01 | cuedTS | Protocol mismatch — spatialTS was the behavioral task but cuedTS was scanned. No behavioral data for cuedTS. | s29: "Protocol mismatch — cuedTS BOLD has no events file (irreconcilable)" |
| s29 | ses-02 | goNogo | Behavioral file missing. | s29: "Raw behavioral missing goNogo" |
| s43 | ses-02 | goNogo | Behavioral file missing. | s43 ses-02 listed in missing behavioral table |

### Prematurely ended scans

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete | Reason |
|---------|---------|------|-----------|-------------|-----------|--------|
| s29 | ses-03 | spatialTS | 15 | 328 | 5% | Scan terminated early |
| s29 | ses-12 | directedForgettingWFlanker | 54 | 598 | 9% | Scan terminated early |
| s43 | ses-11 | stopSignalWFlanker | 96 | 366 | 26% | Scan terminated early |
| s29 | ses-11 | stopSignalWFlanker | 179 | 366 | 49% | Scan terminated early |
| s43 | ses-11 | stopSignalWDirectedForgetting | 517 | 715 | 72% | Scan terminated early |

---

## Validation Sample (.bidsignore)

### Incomplete acquisitions (dim4=1)

| Subject | Session | Task | Reason |
|---------|---------|------|--------|
| s480 | ses-03 | goNogo | 3D BOLD (dim4=1) — scan ended prematurely. |

### Missing behavioral data (irreconcilable)

| Subject | Session | Task | Reason | SCAN-NOTES ref |
|---------|---------|------|--------|----------------|
| s300 | ses-08 | flanker | Behavioral data lost — server shut down before save. Makeup flanker collected in ses-09. | s300: "ses-08 flanker is irreconcilable (BOLD exists, no events)" |
| s1292 | ses-04 | nBack | Scanner failure, nBack ended before task completed. No behavioral data. | s1292: "ses-04 nBack is irreconcilable" |
| s1175 | ses-11 | cuedTSWFlanker | Behavioral file missing per scan notes. | s1175: "Scan 11: cuedTSWFlanker missing (per behavioral notes)" |

### Prematurely ended scans

| Subject | Session | Task | Actual TRs | Expected TRs | % Complete | Reason |
|---------|---------|------|-----------|-------------|-----------|--------|
| s394 | ses-04 | cuedTS | 2 | 329 | 1% | Scan terminated early |
| s373 | ses-02 | spatialTS | 12 | 328 | 4% | Scan terminated early |
| s10 | ses-01 | goNogo | 31 | 382 | 8% | Scan terminated early |
| s599 | ses-02 | rest | 31 | 156 | 20% | Scan terminated early |
| s216 | ses-05 | directedForgetting | 94 | 405 | 23% | Scan terminated early |
| s956 | ses-04 | cuedTS | 155 | 329 | 47% | Scan terminated early; SCAN-NOTES: "cuedTS cut halfway through" |
| s1058 | ses-02 | directedForgetting | 196 | 405 | 48% | Scan terminated early |
| s247 | ses-11 | stopSignalWDirectedForgetting | 345 | 715 | 48% | Scan terminated early |
| s43 | ses-11 | stopSignalWDirectedForgetting | 361 | 715 | 50% | Scan terminated early |
| s1057 | ses-12 | stopSignalWFlanker | 184 | 366 | 50% | Scan terminated early |
| s43 | ses-12 | stopSignalWDirectedForgetting | 384 | 715 | 54% | Scan terminated early |
| s19 | ses-07 | stopSignal | 223 | 398 | 56% | Scan terminated early |
| s1058 | ses-06 | rest | 97 | 156 | 62% | Scan terminated early |
| s19 | ses-04 | shapeMatching | 214 | 325 | 66% | Scan terminated early |
| s76 | ses-05 | nBack | 336 | 505 | 67% | Scan terminated early; SCAN-NOTES: "nBack task TR was wrong — entire run invalid" |
| s1314 | ses-05 | goNogo | 262 | 382 | 69% | Scan terminated early; SCAN-NOTES: "goNogo cut with 3 minutes remaining" |
| s320 | ses-12 | stopSignalWDirectedForgetting | 509 | 715 | 71% | Scan terminated early |
| s1391 | ses-08 | shapeMatching | 234 | 325 | 72% | Scan terminated early |
| s19 | ses-09 | cuedTS | 247 | 329 | 75% | Scan terminated early |
| s76 | ses-01 | flanker | 176 | 236 | 75% | Scan terminated early; SCAN-NOTES: "stopSignal and flanker stopped after block 3" |
| s19 | ses-09 | flanker | 182 | 236 | 77% | Scan terminated early |
| s1175 | ses-06 | spatialTS | 252 | 328 | 77% | Scan terminated early |
| s336 | ses-05 | goNogo | 298 | 382 | 78% | Scan terminated early |
| s76 | ses-01 | stopSignal | 309 | 398 | 78% | Scan terminated early; SCAN-NOTES: "stopSignal and flanker stopped after block 3" |
| s599 | ses-10 | nBack | 428 | 505 | 85% | Scan terminated early |
| s874 | ses-06 | cuedTS | 284 | 329 | 86% | Scan terminated early |
| s1391 | ses-08 | directedForgetting | 351 | 405 | 87% | Scan terminated early |
| s29 | ses-10 | nBack | 443 | 505 | 88% | Scan terminated early |
| s29 | ses-03 | stopSignal | 363 | 398 | 91% | Scan terminated early |
| s19 | ses-09 | stopSignal | 364 | 398 | 91% | Scan terminated early |
| s03 | ses-01 | nBack | 475 | 505 | 94% | Scan terminated early |

---

## Summary

| Category | Discovery | Validation | Total |
|----------|-----------|------------|-------|
| Incomplete acquisitions (dim4=1) | 1 | 1 | 2 |
| Legacy acquisition sequence | all subjects | 0 | N/A |
| Missing behavioral (irreconcilable) | 6 | 3 | 9 |
| Prematurely ended scans | 5 | 31 | 36 |
| **Total excluded scans** | **12** | **35** | **47** |

## Session offset notes

Five validation subjects have split/skipped BIDS sessions that create a +1 offset between raw behavioral session numbers and BIDS session numbers. These are handled in the reconciliation manifests (`config/manifests/reconciliation_*.tsv`) by mapping behavioral files to the correct BIDS session. The split sessions themselves contain only rest data.

| Subject | Split session | Nature |
|---------|-------------|--------|
| s321 | ses-02 | Rest-only split (subject pulled out, restarted) |
| s1445 | ses-02 | Split session |
| s1326 | ses-03 | Rest-only split (subject adjusted earplugs) |
| s1391 | ses-06 | Split session |
| s1258 | ses-07 | Skipped (behavioral missing cuedTS, extra spatialTS) |
