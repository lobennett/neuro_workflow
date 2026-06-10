# sub-s03: replace ses-13 T1w + rerun fmriprep

**Date:** 2026-05-20
**Author:** logben
**Status:** Approved

## Problem

The sub-s03 fmriprep rerun (job 25256995_1, completed 2026-05-19) used the
ses-13 rescue T1w and produced bad FreeSurfer surfaces: **lh holes 70 + rh
holes 95 = 165 total** (mean Euler –163). Root cause: the dcm2niix gear on
Flywheel was re-run for FW session 25210, overwriting the original good
conversion. The bad version (sagittal-native 230×512×512, voxel 0.8×0.5×0.5)
is what `neuro-run submit bidsify` currently fetches.

A proven-good alternative conversion of the same scan exists in the May-2022
BIDS dataset on oak:
`/oak/.../discovery_BIDS_20250402/sub-s03/ses-05/anat/sub-s03_ses-05_run-1_T1w.nii.gz`
(axial 512×512×230, voxel 0.5×0.5×0.8, md5 `9bf100862c69489d71d6e19a1cbc228e`)
which gives **13 total holes** when reconstructed by FreeSurfer 7.3.2.

## Goal

Restore clean surfaces for sub-s03 by substituting the good T1w for the bad
one in scratch BIDS at the same path, then rerunning fmriprep end-to-end on
sub-s03 only. FreeSurfer recon-all will run fresh against the good T1w.

Out of scope: lev1, prep-mshbm, MSHBM (those happen after fmriprep
re-completion, tracked separately).
Out of scope: diagnosing the Flywheel dcm2niix gear divergence (open question
for a future cohort-wide audit).

## Constraints

- Keep BIDS layout consistent: anatomical session is **ses-13**, T1w filename
  keeps `acq-SagMPRAGE` entity.
- Keep trimmed-TR convention (327 TRs) — the new fmriprep run uses scratch
  BIDS BOLDs which are already trimmed by `trim_bold.py`.
- Keep fmriprep output-space set identical to the rest of the discovery
  cohort: `MNI152NLin2009cAsym res-1 + MNI152NLin6Asym res-2 + T1w +
  fsaverage6 + fsnative + fsLR-91k`.
- No documentation entries describing the file's source — the substitution is
  an artifact-level fix, not a pipeline-level change.

## Approach

### Step 1 — Replace the ses-13 T1w

Overwrite the bad ses-13 T1w NIfTI in scratch BIDS with the good one. The
current scratch ses-13 T1w may be a datalad git-annex symlink; if so, use
`datalad unlock` before overwriting and `datalad save` after.

| | path |
|---|---|
| Source | `/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/sub-s03/ses-05/anat/sub-s03_ses-05_run-1_T1w.nii.gz` |
| Target | `/scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz` |

After write, verify `md5sum` of the new ses-13 T1w equals
`9bf100862c69489d71d6e19a1cbc228e`.

Keep the existing scratch ses-13 sidecar JSON (rich BIDS metadata
auto-populated by bidsify) — only the NIfTI content needs changing.

**No `.bidsignore` changes**: ses-13 anat was already visible to fmriprep.
Overwriting the NIfTI content at the same path requires no visibility
adjustments.

### Step 2 — Wipe stale ses-13-derived fmriprep outputs

Remove the previous (bad-T1w) fmriprep outputs for s03 so fmriprep restarts
cleanly:

```bash
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03
rm -f  /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_anat.html
rm -f  /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_ses-*_func.html
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-13
rm -rf /scratch/users/logben/work/fmriprep_discovery_25.2.4/single_subject_s03_wf
```

Note the FS subject dir is also removed so recon-all starts fresh against the
good T1w.

### Step 3 — Re-run fmriprep on sub-s03

Use the canonical `neuro-run submit fmriprep discovery` invocation with
`--subjects-file /tmp/subjects_s03_only.txt`. fmriprep runs recon-all on the
good T1w from scratch, then produces all BOLD-derived outputs.

Expected runtime: ~48 h (similar to the prior s03 run; recon-all is the
dominant cost).

### Step 4 — Verify

After fmriprep completes:
1. `aseg.stats` for `sub-s03_ses-13` shows ≤ 20 total surface holes (expected
   ≈ 13 based on the oak-derived FS run)
2. Re-run `scripts/qa_report.py` against the regenerated cohort:
   - Expect Euler ≈ –13 instead of –163 for s03
   - Expect `scans_flagged_outputs` = 0 (all output spaces present)
3. Confirm BOLD outputs are 327 TRs (trimmed convention preserved)

## Components & data flow

```
scratch BIDS ses-13 (bad T1w)          oak ses-05 T1w (good)
        │                                      │
        └── overwrite content ◄────────────────┘
                  │
                  ▼
        scratch BIDS ses-13 (good T1w)
                  │
                  ▼
        wipe stale fmriprep outputs + FS dir
                  │
                  ▼
        fmriprep s03 end-to-end (~48 h)
                  │
                  ▼
        QA confirms holes ≈ 13
                  │
                  ▼
        lev1 / prep-mshbm reruns (separate task)
```

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `datalad unlock` needed if file is git-annex'd | Detect upfront, unlock before write, save after |
| Oak T1w + scratch fieldmaps / other anat-deriv steps interact poorly | Same DICOM source as previous attempts; only conversion differs; orientation re-encoding is standard fmriprep territory |
| fmriprep produces good surfaces but a different output-space set than the rest of the cohort | Pass identical `--output-spaces` to the cohort's discovery run; verified in Task 5 of the plan |
| Pipeline still produces bad output | QA gate in Step 4; fall back to excluding s03 from surface analyses if it fails again |

## Files to create / modify

| File | Change |
|---|---|
| `/scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz` | Replace content with oak T1w |
| `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/` | Delete (will be regenerated) |
| `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_*.html` | Delete |
| `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-13/` | Delete (recon-all will recreate) |
| `/scratch/users/logben/work/fmriprep_discovery_25.2.4/single_subject_s03_wf/` | Delete |

No code changes in `src/`. No test changes. No documentation updates to
`EXCLUSIONS.md` or `SCAN-NOTES.md`.

## Success criteria

- fmriprep completes successfully for s03 (exit 0)
- `aseg.stats` for `sub-s03_ses-13` shows ≤ 20 total surface holes
- All expected output spaces present (no `scans_flagged_outputs` flag)
- BOLD outputs at 327 TRs (matches trimmed convention)
- QA cohort dashboard shows s03 no longer an outlier
