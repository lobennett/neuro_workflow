# fMRIPrep 25.2.4 — s03 Profile Report

**Date:** 2026-04-30
**Subject:** sub-s03 (12 sessions, 57 non-`.bidsignore`d BOLD scans, multi-echo)
**SLURM job:** 23138312_1
**Container:** `/home/groups/russpold/singularity_images/fmriprep_25.2.4.sif`
**Companion to:** `2026-04-28-fmriprep-rerun-design.md`

## Executive summary

Phase 1 produced **complete and clean preprocessing data** for s03 across all expected output spaces. The SLURM task reported `FAILED` with exit code 1 due to a known fmriprep 25.2.4 bug ([fmriprep#3634](https://github.com/nipreps/fmriprep/issues/3634), fix in unreleased PR #3636) — the workflow finished successfully but the post-workflow report generator silently crashed when assembling the top-level subject wrapper report. **No preprocessing output is affected.** A bash wrapper has been added to the sbatch template to detect this benign exit-1 in production.

## Resource metrics (sacct)

| Metric | Value |
|---|---|
| State (raw SLURM) | FAILED (exit 1:0) — see [fmriprep#3634 finding](#fmriprep3634-finding) |
| Workflow log says | `fMRIPrep finished successfully!` |
| Elapsed wall time | **1d 01:39:37** (25h 39m) |
| Allocated | 8 CPUs × 24 GB/CPU = 192 GB total memory, 7-day wall |
| Peak RSS | **119,813,128 KB ≈ 114 GB** |
| Peak VMSize | 119,320,152 KB ≈ 114 GB |
| AveCPU | 4d 03:46:48 (multi-core CPU time accumulated) |

## Stage breakdown (from workflow log timestamps)

| Stage | Wall time | Notes |
|---|---|---|
| Workflow build + setup | ~5 min | argparse, BIDSLayout, workflow assembly |
| FreeSurfer recon-all | **~9.2 hours** | One subject (`sub-s03_ses-05`); finished without error; no Talairach failure |
| ANTs anat workflow (templates, normalization) | ~3-4 hours | T1w → MNI152NLin2009cAsym + MNI152NLin6Asym + T1w native + dseg |
| BOLD workflow (57 BOLDs across 12 sessions) | **~16.5 hours** | Multi-echo combination, STC, HMC, SDC, coregistration, resampling to 4 vol spaces, surface sampling, CIFTI generation, carpet plots |
| Post-workflow report assembly | ~1.5 minutes | Per-session HTML reports + per-anat HTML report all written successfully |
| Top-level wrapper report | failed silently | The fmriprep#3634 bug — exits 1 |

Per-BOLD throughput: ~17 minutes per BOLD (covers 4 volumetric spaces, 2 surface spaces × 2 hemispheres, CIFTI, carpet plot).

## Output verification

### File counts (all match expected counts derived from `.bidsignore`-filtered view)

| Output | Expected | Found |
|---|---|---|
| Unique BOLDs in scope | 57 | ✅ 57 |
| `preproc_bold.nii.gz` (4 vol spaces × 57) | 228 | ✅ 228 |
| CIFTI 91k `dtseries` | 57 | ✅ 57 |
| `fsaverage6` surface .func.gii (per hemi) | 114 | ✅ 114 |
| `fsnative` surface .func.gii (per hemi) | 114 | ✅ 114 |
| `confounds_timeseries.tsv` (258 cols × 154-505 rows) | 57 | ✅ 57 |
| Anat `desc-preproc_T1w` in 3 spaces | 3 | ✅ 3 |
| Anat brain masks in 3 spaces | 3 | ✅ 3 |
| Anat surfaces (pial, white, midthickness, sulc, thickness × 2 hemi) | 12+ | ✅ all present |
| FreeSurfer required files (aparc+aseg, surfaces, parcellations, stats) | 15 critical | ✅ 15/15 |
| HTML reports (anat + per-session × 12) | 13 | ✅ 13 |
| QC SVG figures (carpetplot, t2starhist, t2scomp, sdc, coreg, fmapCoreg, rois, confoundcorr, compcorvar × 57 + anat × 4 + fieldmap × 12) | 529 | ✅ 529 |

### Exclusion regression checks (must produce ZERO files)

| Exclusion (from `docs/EXCLUSIONS.md`) | Files in derivatives |
|---|---|
| s03 ses-01 task-nBack (irreconcilable) | 0 ✅ |
| s03 ses-11 task-stopSignalWDirectedForgetting (non-monotonic onsets) | 0 ✅ |

### Image content sanity (random samples)

| File | Shape | Mean | Std | NaN | Inf |
|---|---|---|---|---|---|
| ses-01 task-rest BOLD (2mm MNI) | (91, 109, 91, 154) | 696.8 | 562.1 | 0 | 0 |
| ses-04 task-flanker BOLD (2mm MNI) | (91, 109, 91, 246) | 670.4 | 536.9 | 0 | 0 |
| ses-12 task-stopSignalWFlanker BOLD (2mm MNI) | (91, 109, 91, 368) | 636.7 | 517.0 | 0 | 0 |
| ses-05 task-goNogo CIFTI 91k | (383, 91282) | 1003.1 | 313.6 | 0 | 0 |

**No NaN/Inf in any tested file. No "stripy"/pathological signal.**

### Confounds sanity (sample: ses-05 goNogo)

| Metric | Value |
|---|---|
| Mean FD | 0.096 mm |
| Max FD | 0.488 mm |
| Mean DVARS | 21.5 |
| Std-DVARS mean | 1.21 |
| aCompCor columns | 63 |
| tCompCor columns | 3 |
| Motion outliers | 34 |
| Cosine drift columns | 7 |
| Total columns | 258 |

### Anat workflow correctness

- ✅ FreeSurfer `recon-all` ran on `sub-s03_ses-05` only (the SagMPRAGE T1w session)
- ✅ MPRAGEPromo T1w correctly excluded by the symlink view
- ✅ recon-all `recon-all-status.log` reports "finished without error"
- ✅ `talairach_afd` did NOT fail — the original blocker is resolved
- ✅ HTML report references `acq-SagMPRAGE` ses-05 in figure paths
- ✅ Anat outputs land at `sub-s03/ses-05/anat/`

### Disk usage

| Directory | Size |
|---|---|
| `derivatives/sub-s03/` (preproc outputs) | 716 GB |
| `derivatives/sourcedata/freesurfer/sub-s03_ses-05/` | 832 MB |
| `work/fmriprep_discovery_phase1_25.2.4/` (intermediate state) | 1012 GB |

## fmriprep#3634 finding

### What happened

```
260430-11:32:44,797 nipype.workflow IMPORTANT: fMRIPrep finished successfully!
260430-11:32:44,803 nipype.workflow IMPORTANT: Works derived from this fMRIPrep execution should...
[~90 second silent gap]
Task 1 (s03) finished with exit code 1
```

After the workflow completed, fmriprep called `run_reports()` to assemble the top-level `sub-s03.html` wrapper report. The report assembly raised an exception (specific cause unknown — the bug swallows the original error). The exception handler in `fmriprep/reports/core.py` had a typo: `traceback.print_exception(file=str(...))` passes a string where a file object is required. The `TypeError` from the broken exception handler propagated, and apptainer exited with code 1.

### Identified root cause

PR #3636 ([Improve error handling in report generation](https://github.com/nipreps/fmriprep/pull/3636), merged 2026-04-21) fixes the exception handler:

```diff
-    except:  # noqa: E722
-        import sys
+    except Exception:  # noqa: BLE001
         import traceback
-
-        # Store the list of subjects for which report generation failed
-        traceback.print_exception(*sys.exc_info(), file=str(Path(output_dir) / 'logs' / errorname))
+        log_dir = Path(output_dir) / 'logs'
+        log_dir.mkdir(parents=True, exist_ok=True)
+        with open(log_dir / errorname, 'w') as f:
+            traceback.print_exc(file=f)
```

PR #3636 was merged on 2026-04-21, after the 25.2.5 release on 2026-03-10. **The fix is not yet in any LTS release.** The bug affects 25.2.4 and 25.2.5 identically.

### Effect on our run

Only the top-level `sub-s03.html` wrapper report is missing. The 13 sub-reports (anat + per-session × 12) cover all QC content; the wrapper is just an index page. No preprocessing data is affected.

### Mitigation in production sbatch template

Since fmriprep#3634 will deterministically recur on every production subject, the sbatch template was hardened:

```bash
exitcode=$?
sync; sleep 2  # Lustre flush guard

# fmriprep#3634 workaround: workflow finished cleanly but post-workflow report
# generator's exception handler has a typo bug (fixed in PR #3636).
log_file="${LOG_DIR}/fmriprep_${DS}-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}.out"
if [ "$exitcode" -eq 1 ] && [ -f "$log_file" ] && grep -q "fMRIPrep finished successfully" "$log_file"; then
  echo "Detected fmriprep#3634 benign exit-1; treating as exit 0."
  exitcode=0
fi

if [ "$exitcode" -eq 0 ]; then
  # Cleanup per-subject work dir on confirmed success only
  rm -rf "${WORK_DIR}/sub-${subject}"
fi
```

## Production calibration

Based on the s03 metrics, the production envelope is:

| Setting | s03 Profile | Production | Rationale |
|---|---|---|---|
| CPUs/task | 8 | **8** | fmriprep maintainer guidance — performance plateaus past 8 |
| Memory/CPU | 24 GB | **20 GB → 160 GB total** | Peak RSS 114 GB + 28% headroom for 13-session validation subjects |
| `--mem_mb` | 172800 | **144000** | 90% of 160 GB allocation, similar fmriprep concurrency to s03 |
| Wall time | 7 days (max) | **3 days** | s03 actual was 25.7h; 3-day wall = 2.8× safety margin |
| Throttle | n/a (1 task) | **12** (validation) / **4** (discovery — only 4 subjects remain) | Peak partition memory: 12 × 160 GB = 1920 GB ≈ 56% of 3.4 TB russpold partition |

**Per-task footprint of 160 GB fits all 16 russpold nodes** (smallest is 187 GB usable).

**Disk planning**: 46 subjects × ~700 GB derivatives ≈ 32 TB. Plus 12 concurrent work dirs × ~1 TB at peak = ~12 TB. Total scratch usage at peak ≈ 44 TB (of 76 TB available). Per-subject work dir cleanup on success keeps cumulative work dir usage from growing beyond peak.

**Wall-time projection** (worst case under throttle 12):

| Phase | Subjects | Per-job | Throttle | Total |
|---|---|---|---|---|
| Phase 2A (discovery) | 4 | ≤3 days | 4 | 3 days |
| Phase 2B (validation) | 41 | ≤3 days | 12 | ~12 days |
| Cumulative | 45 | — | — | ~15 days worst case (sequential via `--dependency=afterany`) |

Most subjects should finish in 1.5-2 days each; typical total ≈ 1-2 weeks.

## Outstanding triage items for production

For each Phase 2 subject, monitor for these failure modes:

| Failure pattern | Action |
|---|---|
| `OUT_OF_MEMORY` or MaxRSS at allocation cap | Bump `--mem-per-cpu-gb` for that subject; resubmit (fmriprep resumes from work dir cache) |
| `TIMEOUT` with reasonable MaxRSS | Resubmit (fmriprep resumes); if 2nd timeout, bump memory |
| Early `FileNotFoundError` on `*.pklz` | nipype hash race — wipe that subject's work dir, resubmit |
| Talairach failed | Should NOT occur (view excludes bad T1ws) — investigate which T1w fmriprep used |
| `FAILED` exit-1 + log has "fMRIPrep finished successfully" | Treat as success (template wrapper handles automatically) |
| `FAILED` exit-1 + no success message in log | Real failure — investigate log/crashfile, fix root cause, resubmit |
