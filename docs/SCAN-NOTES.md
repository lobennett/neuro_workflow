# Scan Notes: Excluded and Incomplete Subjects

This document summarizes subjects that were excluded, withdrew, had incomplete sessions, missing or bad data, or required makeup sessions. It is intended as a quick reference for researchers investigating data quality issues.

---

## Excluded Subjects (Validation Cohort)

These subjects were dropped from the study entirely. Their data should not be used in analyses.

| Subject | Scans Completed | Reason | Notes |
|---------|-----------------|--------|-------|
| s214    | 4 | Dropped — unreliable | Session 4: couldn't get spatialTS |
| s222    | 1 | Dropped — poor behavioral performance | "Had really bad behavior" |
| s250    | 1 | Dropped — lens prescription issue | Lens prescription exceeded CNI capacity; couldn't read instructions |
| s297    | 1 | Discontinued — ear issues after scanning | rest and nBack missing |
| s432    | 1 | Withdrew | Had to leave scanner before stopSignal; no DTIs collected |
| s823    | 2 | Withdrew | — |
| s968    | 7 | Withdrew | Extensive issues: makeup sessions for directedForgetting and stopSignal; high motion (scan 3); hearing complaints and restart (scan 4); incomplete spatialTS and kicked out of scanner (scan 5); nBack cut short (scan 7) |
| s1165   | 2 | Withdrew | Possible wrong prescription for right eye; scan 2 missing rest |
| s1178   | 2 | Withdrew | Missing both diffusions |
| s1266   | 4 | Withdrew | Scan 3: wrong task run (stopSignalWFlanker instead of stopSignal) |
| s1320   | 1 | Withdrew | "Just crazy behavior. Drop them" |

---

## Discovery Subjects with Issues

### s29 — Excluded Test Session + Protocol Mismatch

Flywheel session 22424 (Scan 0, 2020-11-11) was a fmap-only test session and is excluded from the Flywheel pull entirely — it is not downloaded to BIDS. After excluding it, raw and BIDS session numbers align 1:1.

| BIDS Session | Scan | Date | Issue |
|--------------|------|------|-------|
| _(excluded)_ | 0 | 2020-11-11 | Test session — fmap only. Excluded from Flywheel pull (`session_overrides` in `reconciliation_config.json`). |
| ses-01 | 1 | 2020-11-13 | Protocol mismatch — spatialTS was the behavioral task but cuedTS was scanned. Only 3 of 4 tasks overlap. **cuedTS BOLD has no events file (irreconcilable).** |
| ses-02 | 2 | 2020-11-14 | Raw behavioral missing goNogo. |
| ses-11 | 11 | 2021-03-17 | Task order flipped: "stop+DF and DF+flanker" (dual-task session). |

### s03 — Extra/Mislabeled Sessions

- Flywheel session 22752 (2021-02-12): Mislabeled — actually belongs to **s10**. Reassigned in `reconciliation_config.json`.
- Flywheel session 25210 (2022-05-24): Extra T1w only. Excluded.
- Scan 1: Missing T2w; issue with nBack.
- Scan 2: Still missing T2w.

### s10 — Missing Sessions and DTIs

- Only 11 sessions on Flywheel (received extra session from s03 mislabel).
- Multiple scans missing DTI.
- Got T1w on scan 9; both diffusions on scan 11.

### s43 — Missing Anatomicals

- Missing T2w entirely.
- Scan 2: Got pe1 instead of pe0 (pe0 still needed). Got pe0 on scan 9.
- Scan 8: No eye tracking for first scan; had to run 3 shims.

### s19 — Minor Issues

- Scan 1: Only fmap and rest collected.
- Missing 1 goNogo (per behavioral notes).

---

## Validation Subjects with Data Issues

### s300 — Lost Behavioral Data + Duplicate Deletion

- **Scan 8 (2023-04-13):** Flanker behavioral data lost — server shut down before save. Two cuedTS scans collected; operator deleted shorter duplicate from Flywheel. **ses-08 flanker is irreconcilable (BOLD exists, no events).**
- **Scan 9 (2023-05-09):** Makeup flanker collected to replace lost data.

### s1292 — Scanner Failure

- **Scan 4 (10/20):** nBack ended before task completed — scanner failure. No nBack behavioral data. **ses-04 nBack is irreconcilable.**
- **Scan 10 (1/12):** Another nBack not acquired due to scanner failure.

### s76 — Repeated Acquisition Issues

- **Scans 1-6:** No T1w collected across 6 scans. All anatomicals obtained on scan 7.
- **Scan 1:** stopSignal and flanker stopped after block 3.
- **Scan 5:** nBack task TR was wrong — entire run invalid.
- **Scan 11:** Subject pulled out after rest; directedForgettingWFlanker not collected.

### s321 — Split Session

- **Scan 1:** Subject felt poking at head, pulled out. Exam ended and restarted — two Flywheel sessions for scan 1 (one with rest, one with tasks).
- BIDS ses-02 is the rest-only split (skipped in behavioral mapping).

### s295 — Task Ordering Swap

- **Scans 3-4:** Tasks from scan 3 were administered during scan 4 and vice versa. Behavioral files adjusted accordingly.
- **Scan 8:** Unable to get spatialTS.

### s1258 — Missing cuedTS + Sleep

- BIDS ses-07 skipped (behavioral missing cuedTS; has extra spatialTS instead). Offset changes from ses-07 onward (+1).
- **Scan 5:** Participant fell asleep during last task.

### s1326 — Split Session

- **Scan 3:** Subject pulled out to adjust earplugs. Two Flywheel sessions: one with rest, one with tasks.
- BIDS ses-03 is the rest-only split (skipped in behavioral mapping).

### s1391 — Split Session

- BIDS ses-06 is a split session (skipped in behavioral mapping). Offset changes from ses-06 onward (+1).

### s1445 — Split Session + Behavioral Concerns

- BIDS ses-02 is a split session (skipped in behavioral mapping). Offset changes from ses-02 onward (+1).
- **Scan 2:** "Look at their last three tasks data."
- **Scan 4:** "Check their spatial behavior, looked like they drifted off maybe?"
- **Scan 6:** "Said he was sleepy. Check behavioral accuracy."

### s956 — Incomplete Tasks + Missing DTI

- **Scan 2:** Missing diffusion.
- **Scan 4:** cuedTS cut halfway through.
- Missing 1 goNogo and 1 flanker; has extra shapeMatching and stopSignal.

### s1035 — Extra/Missing Tasks

- Missing 1 goNogo and 1 shapeMatching.
- Has extra stopSignal and flanker.
- **Scan 11:** Subject "may have been a bit hungover."

### s1314 — Incomplete Tasks

- Missing 1 goNogo, nBack, shapeMatching, and spatialTS.
- Has extra stopSignal, flanker, cuedTS, and directedForgetting.
- **Scan 3:** Coughing a lot — check motion.
- **Scan 5:** goNogo cut with 3 minutes remaining.

### s1175 — Lights On During Scan

- **Scan 6:** Lights were on in scanner room until after directedForgetting. Check results for possible effects.
- **Scan 11:** cuedTSWFlanker missing (per behavioral notes).
- **Scan 12:** Re-ran flankerWCuedTS to replace scan 11 issue.

---

## General Notes

- **Demographics battery (discovery cohort):** Did not include WHODAS-2, DSM-5, or GAD-7.
- **spatialTS behavioral data:** All raw files contain the column `predictable_dimension` despite none being predictableTS tasks.
- **Mask thresholds (decided 2025-10-10):** Within-subject = 1.0; across-subject = 0.9.
- **Event file trimming:** Scans with >10 trailing omissions were trimmed (subject stopped responding). Scans where subject fell asleep were **not** trimmed.

---

## BIDS Structural Cleanup - March 19, 2026

### s480 ses-03 task-goNogo (validation_bids)

**Issue**: Duplicate BOLD runs (run-1 and run-2 present for same task in same session)

**Resolution**:
- Deleted BOLD: run-1_echo-{1,2,3}_bold.{nii.gz,json} (6 files)
- Deleted physio: run-1_recording-cardiac/respiratory_physio.{json,tsv.gz} (4 files)
- Promoted BOLD: run-2 → run-1 (6 files renamed)
- Promoted physio: run-2 → run-1 (4 files renamed: cardiac JSON/TSV, respiratory JSON/TSV)
- Rationale: BIDS validator flagged duplicate runs; run-1 was original acquisition, run-2 was repeat. Kept run-2 based on acquisition quality assessment. All associated BOLD echoes and physiological recordings (cardiac 100Hz, respiratory 25Hz) also promoted to maintain temporal alignment.

### s43 ses-08 task-directedForgetting (discovery_bids)

**Issue**: 3D BOLD file (incomplete scan - ended prematurely) with duplicate run numbering

**Resolution**:
- Deleted: run-1_echo-{1,2,3}_bold.{nii.gz,json} (6 files, 3D scan)
- Promoted: run-2 → run-1 (6 files renamed, valid 4D scan)
- Rationale: run-1 was incomplete 3D acquisition; run-2 is valid 4D functional data. BIDS validator identified the 3D issue; cleanup removes invalid data while maintaining proper run numbering.
