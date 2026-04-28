# fMRIPrep 25.2.4 rerun on discovery + validation: two-phase per-subject pipeline

**Date:** 2026-04-28
**Author:** Logan Bennett (with brainstorming assist)
**Datasets:** discovery (5 subjects), validation (41 subjects)
**Container:** `/home/groups/russpold/singularity_images/fmriprep_25.2.4.sif`

## Context

Two prior fmriprep 25.2.4 runs against `/scratch/users/logben/{discovery,validation}_bids/` failed at scale:

- **Discovery** (job 22226603): 5/5 failed. 4/5 hit FreeSurfer `talairach_afd` QC failure at ~6h. 1/5 (s19) recovered FS but timed out at 5d during BOLD processing. All 5 saturated 64 GB memory cap.
- **Validation** (job 22226639): 0/41 completed. Of 21 tasks that ran: 8 TIMEOUT (5-day wall), 3 FAILED (nipype hash race on `fsdir_run` cache), 2 OUT_OF_MEMORY. Cancelled before remaining 20 PENDING ran. (Cancelled 2026-04-28.)

Earlier Oak runs of the same subjects with `--output-spaces res-2` (2mm) succeeded but at lower spatial resolution and without `acq-MPRAGEPromo` T1w files in the BIDS tree.

## Goal

Reliably preprocess all 46 subjects with fmriprep 25.2.4 producing the full output-space set (1mm MNI volumetric, 2mm MNI152NLin6Asym, fsaverage6, fsnative, T1w, func, CIFTI 91k) with FreeSurfer derivatives, in 1-3 weeks of cluster wall time.

## Root causes (confirmed by diagnostics)

| Class | Affected | Root cause | Fix |
|-------|----------|-----------|-----|
| FreeSurfer Talairach AFD failure | 5/5 discovery | fmriprep selected `acq-MPRAGEPromo` T1w (lower-quality acquisition); FreeSurfer's `talairach_afd` QC failed (p=0.0082 < 0.005). `.bidsignore` listed it but **pybids does not honor `.bidsignore`** | BIDS filter file restricts T1w to `acq-SagMPRAGE` |
| Wall-time TIMEOUT | 8 validation, 1 discovery | 5-day SLURM wall too short for 12-13 sessions × multi-echo × 1mm upsampling × CIFTI × fresh FreeSurfer | Two-phase pipeline (anat then BOLD), 7-day wall on BOLD phase, 192 GB memory |
| OOM / memory saturation | 2 OOM, all discovery saturated 64 GB | 64 GB insufficient for 1mm + multi-echo + FS + CIFTI | 8 CPUs × 24 GB = 192 GB |
| nipype hash race (FAILED early) | 3 validation (s1057, s1175, s1189) | Transient nipype bug in `fsdir_run` caching during workflow construction with parallel workers | Wipe affected subject's work dir + retry; usually resolves on second attempt |

## Key constraint discovered

**`.bidsignore` is honored only by the BIDS Validator, not by BIDS apps.** pybids `BIDSLayout` does not read `.bidsignore` by default, so fmriprep saw and processed every file in the BIDS tree regardless of the patterns. The pre-flight pipeline must translate `.bidsignore` into:
- A per-subject `--bids-filter-file` JSON (handles anat exclusions by entity)
- A symlink BIDS view (handles BOLD exclusions which can't be expressed as entity filters)

## Architecture

```
Phase 0: Pre-flight (local, no SLURM, idempotent)
  • Generate per-subject BIDS filter JSONs (anat exclusions)
  • Build symlink BIDS view (BOLD exclusions applied)
  • Wipe stale work dirs and failed FS dirs

Phase 1: Profile on s03
  1A: Anat-only s03    (1 SLURM job, ~1d wall)
  1B: BOLD s03         (1 SLURM job, ≤7d wall, depends on 1A)

  Manual go/no-go gate after 1B:
    pass → Phase 2
    fail → triage and re-run as needed (no auto-pivot)

Phase 2: Production (45 subjects: 4 discovery + 41 validation)
  2A: Anat-only array (45 jobs, throttle 12, ~1d wall each)
  2B: BOLD array      (45 jobs, throttle 12, 7d wall each,
                       --dependency=aftercorr:2A)

Resume protocol (only "fallback")
  Any 2A or 2B failure → manual single-subject resubmit:
    - Memory issue: bump --mem-per-cpu-gb, same work dir
    - Wall timeout: same sbatch, same work dir → fmriprep resumes
    - nipype hash race: wipe that subject's work dir, resubmit
    - Logic error: fix root cause, wipe work dir, resubmit
```

**Job count:** 92 total (46 anat + 46 BOLD). One job per (subject, phase). Failures isolated by subject.

## Resource envelope

| Phase | CPUs | Mem/CPU | Total Mem | Wall | Throttle |
|-------|------|---------|-----------|------|----------|
| 1A (s03 anat) | 8 | 24 GB | 192 GB | 1 day | n/a (1 task) |
| 1B (s03 BOLD) | 8 | 24 GB | 192 GB | 7 days | n/a (1 task) |
| 2A (anat × 45) | 8 | 22 GB (calibrated) | 176 GB | 1 day | 12 |
| 2B (BOLD × 45) | 8 | 22 GB (calibrated) | 176 GB | 7 days | 12 |

**CPU rationale:** fmriprep performance plateaus past 8 CPUs (per fmriprep maintainers). Beyond 8, idle cores waste cluster credit; better to spend on memory.

**Memory rationale:** Prior runs saturated 64 GB cap. 192 GB profile envelope gives 3× headroom to *measure* peak RSS rather than re-cap. Production envelope is calibrated from profile (target: ~22 GB/CPU). 22 GB/CPU = 176 GB total, fits all 16 russpold nodes (smallest is 191 GB total memory).

**Throttle 12 rationale:** russpold has 16 nodes / 448 CPUs / 3.4 TB memory. Memory is the binding constraint. At throttle 12 with 176 GB/task = 2,112 GB peak (≈62% of partition memory). This hits "aggressive but not dominant" — leaves margin for other partition users. Throttle 16 would consume 88% of partition memory, crossing the "don't occupy all of them" line.

## Output spaces & flags

```
--output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func"
--no-submm-recon --skip-bids-validation --cifti-output 91k
--anat-only           # Phase 1A and 2A only
```

Restores parity with the earlier Oak runs (which had `cifti-output 91k`) and adds the 1mm MNI volumetric upgrade. CIFTI is required for MSHBM and grayordinate-based group analyses. MNI152NLin6Asym:res-2 is for FSL/randomise compatibility downstream.

`--dummy-scans` is **not** used: scratch BIDS data is already trimmed by the bidsify pipeline (7 dummy volumes physically removed).

## Phase 0: Pre-flight script

`scripts/fmriprep_preflight.py` (new). Idempotent.

### Inputs
- Dataset name (`discovery` or `validation`) → BIDS dir from `~/.neuro_workflow/datasets.json`
- The dataset's `.bidsignore` at BIDS root

### Outputs
1. `config/fmriprep/{dataset}/filters/sub-{SUBJECT}.json` — per-subject filter JSON
2. `/scratch/users/logben/{dataset}_bids_view/` — symlink BIDS view (BOLD exclusions applied)
3. Console summary table

### Algorithm

```
1. Parse .bidsignore. Classify each non-comment line:
     pattern matches *T1w* or *T2w*  → ANAT exclusion
     pattern matches *bold*           → BOLD exclusion
     other                            → OTHER exclusion (treated as view-side)

2. For each subject:
     a. Enumerate anat files NOT in ANAT exclusions; record session, acquisition.
     b. Compose filter JSON:
          {
            "t1w": {"datatype":"anat", "suffix":"T1w",
                    "acquisition":"SagMPRAGE",   # discovery only; omitted for validation
                    "session":[allowed sessions]},
            "t2w": {"datatype":"anat", "suffix":"T2w",
                    "session":[allowed sessions]},
            "bold": {"datatype":"func", "suffix":"bold"},
            "fmap": {"datatype":"fmap"}
          }
     c. Write to config/fmriprep/{dataset}/filters/sub-{SUBJECT}.json

3. Build symlink view:
     - Top-level files (dataset_description.json, README, participants.tsv): symlinked
     - For each file under sub-*/:
         matches BOLD or OTHER exclusion → SKIP
         else → symlink to corresponding position in view tree
     (anat exclusions NOT applied here; filter file handles them)

4. Print summary table:
     | Subject | T1w in view | T1w after filter | BOLD in view | BOLD excluded |
```

### Why this split (filter for anat, view for BOLD)
- Anat exclusions are entity-aligned (acquisition + session) → filter file expresses cleanly.
- BOLD exclusions are per-(session, task) tuples → BIDS filter files cannot encode disjunction-of-conjunctions; symlink view physically removes excluded files.
- `.bidsignore` remains the single source of truth; both artifacts are derived.

## Phase 1: s03 profile

### Phase 1A — anat-only s03

```bash
neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids_view \
  --bids-filter-dir config/fmriprep/discovery/filters \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w" \
  --fmriprep-args "--anat-only --no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 1-00:00:00 \
  --array-throttle 1 \
  --subjects-file <(echo s03)
```

### Phase 1B — BOLD s03

```bash
neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids_view \
  --bids-filter-dir config/fmriprep/discovery/filters \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 7-00:00:00 \
  --array-throttle 1 \
  --dependency afterok:<ANAT_S03_JID> \
  --subjects-file <(echo s03)
```

Same work dir as 1A → fmriprep skips already-completed anat nodes.

### Phase 1 success gates (manual review before launching Phase 2)

```
Phase 1A:
  ✓ recon-all.log contains "finished without error"
  ✓ No "Talairach failed" in any run logs
  ✓ derivatives/sub-s03/anat/*MNI152NLin2009cAsym*desc-preproc_T1w.nii.gz exists
  ✓ sourcedata/freesurfer/sub-s03_ses-05/scripts/recon-all-status.log shows DONE
  ✓ sacct MaxRSS captured

Phase 1B:
  ✓ No "CRITICAL" lines in workflow log
  ✓ Every non-.bidsignored BOLD has its preproc_bold.nii.gz in derivatives
  ✓ CIFTI files (*den-91k_bold.dtseries.nii) generated
  ✓ confounds_timeseries.tsv exists for every BOLD
  ✓ HTML report renders cleanly
  ✓ sacct Elapsed and MaxRSS captured for calibration
```

### Profile report

After Phase 1 completes, write `docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md` capturing:
- Anat phase: elapsed, peak RSS, FreeSurfer time vs ANTs time
- BOLD phase: elapsed, peak RSS, breakdown by stage (STC, HMC, coregistration, resampling, CIFTI)
- Calibration decision: production envelope and wall time, with justification

## Phase 2: production (45 subjects)

### Phase 2A — anat-only array

```bash
# Discovery: 4 remaining (s10, s19, s29, s43)
neuro-run submit fmriprep discovery \
  --subjects-file subjects_phase2_discovery.txt \
  --bids-dir-override /scratch/users/logben/discovery_bids_view \
  --bids-filter-dir config/fmriprep/discovery/filters \
  --output-spaces "..." \
  --fmriprep-args "--anat-only ..." \
  --nthreads 8 --mem-per-cpu-gb <calibrated> --time 1-00:00:00 \
  --array-throttle 4
# → DISCOVERY_2A_JID

# Validation: 41 subjects
neuro-run submit fmriprep validation \
  --subjects-file subjects_validation.txt \
  --bids-dir-override /scratch/users/logben/validation_bids_view \
  --bids-filter-dir config/fmriprep/validation/filters \
  --output-spaces "..." \
  --fmriprep-args "--anat-only ..." \
  --nthreads 8 --mem-per-cpu-gb <calibrated> --time 1-00:00:00 \
  --array-throttle 12
# → VALIDATION_2A_JID
```

### Phase 2B — BOLD array

```bash
neuro-run submit fmriprep discovery \
  --subjects-file subjects_phase2_discovery.txt \
  ... (same flags as 1B except --time 7-00:00:00, --array-throttle 4) \
  --dependency aftercorr:${DISCOVERY_2A_JID}

neuro-run submit fmriprep validation \
  --subjects-file subjects_validation.txt \
  ... (same flags as 1B except --time 7-00:00:00, --array-throttle 12) \
  --dependency aftercorr:${VALIDATION_2A_JID}
```

`aftercorr` pairs array tasks: 2B task N starts when 2A task N completes successfully. If 2A task N fails, its corresponding 2B task is held; that subject is triaged manually.

### Resume protocol

If subject `s1057` validation 2B times out at day 7:

```bash
sacct -j <2B_JID>_<TASKID> --format=State,Elapsed,MaxRSS

# Resume — same work dir → fmriprep skips done nodes
neuro-run submit fmriprep validation \
  --subjects-file <(echo s1057) \
  ... (same flags) --array-throttle 1
```

If memory was the issue: bump `--mem-per-cpu-gb`, do not wipe work dir.
If logic error: wipe `/scratch/users/logben/work/fmriprep_validation_25.2.4/sub-s1057/`, resubmit.

## Required `neuro-run` extensions

Three small additions to `src/neuro_workflow/pipelines/fmriprep.py`:

1. **`--bids-dir-override <PATH>`** — point fmriprep at a different input dir (the symlink view) without changing the dataset registration. Derivatives still land under the registered BIDS dir.
2. **`--bids-filter-dir <DIR>`** — additive to the existing `--bids-filter-file`. The sbatch template resolves `<DIR>/sub-{SUBJECT}.json` per array task and passes it as `--bids-filter-file` to fmriprep. Mutually exclusive with `--bids-filter-file` for the same submission.
3. **`--dependency <SPEC>`** — passthrough to `sbatch --dependency=<SPEC>`. Supports `afterok:JID`, `aftercorr:ARRAY_JID`, etc.

Total ~30 lines of code changes plus tests.

## Testing

### Pre-flight script tests (`tests/scripts/test_fmriprep_preflight.py`)

- Parse actual `.bidsignore` from both datasets; assert correct anat/bold/other classification.
- For each subject, validate filter JSON against pybids: `BIDSLayout(view_dir).get(subject=S, **filt["t1w"])` returns the expected file count.
- Idempotency: run script twice; filter JSONs and view symlinks byte-identical.
- Symlink view sanity: no `.bidsignore`d BOLD file in view; all non-excluded files present.
- Edge cases: subject with multiple T1ws after `.bidsignore` (s19: ses-01 MPRAGEPromo + ses-05 SagMPRAGE → after filter, ses-05 SagMPRAGE only).

### Pre-submission smoke tests

- `neuro-run show fmriprep ...` to inspect generated sbatch before submitting.
- pybids dry-run on s03's view + filter to confirm fmriprep sees exactly the expected files.

### Phase 2 monitoring

Daily check during production:
- `sqlb | grep fmriprep` — what's running/queued.
- `sacct -u logben --starttime=...` — completions and failures over the last 24h.
- After first 5-10 BOLD subjects complete, compare actual peak RSS to profile envelope; bump or trim memory accordingly.

## Failure triage decision tree

| Failure mode | Diagnosis signal | Action |
|---|---|---|
| Talairach AFD | `recon-all.log` has "Talairach failed" | Pre-run FS with `-notal-check` for that subject; resubmit anat phase |
| OOM | sacct State=OUT_OF_MEMORY or MaxRSS at allocation cap | Bump `--mem-per-cpu-gb`; same work dir; resubmit |
| Wall timeout | sacct State=TIMEOUT, MaxRSS reasonable | Resubmit (resume); if 2nd timeout → bump memory or split sessions |
| nipype hash race | FileNotFoundError on `*.pklz` early in workflow log | Wipe that subject's work dir; resubmit |
| BIDS filter bug | Workflow log says "no T1w found" or wrong session selected | Fix filter JSON; rerun pre-flight; resubmit |

## Wall-time projection

| Phase | Per-job wall | Throttle | Subjects | Total walls | Cumulative |
|-------|--------------|----------|----------|-------------|------------|
| Phase 1A | ~1 day | n/a | 1 | 1 day | day 1 |
| Phase 1B | ~3-5 days | n/a | 1 | ~3-5 days | day 4-6 |
| Phase 2A | ~1 day | 12 | 45 | ~4 days | day 8-10 |
| Phase 2B | ~3-7 days | 12 | 45 | ~12-25 days | day 20-35 |

**Best case:** ~3 weeks (most subjects ≤4d BOLD).
**Worst case:** ~5 weeks (many subjects need 7d resume).
**Most likely:** 3-4 weeks total.

## Key design decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Anat T1 selection | BIDS filter restricts to `acq-SagMPRAGE` (discovery) | Solves Talairach AFD failure root cause |
| `.bidsignore` translation | Hybrid: filter file (anat) + symlink view (BOLD) | Filter cannot express per-(session,task) exclusions |
| Profile-first | Yes, on s03 with full two-phase run | Validates pipeline + measures resource envelope |
| Two-phase split | Per-subject anat then BOLD | Fail-fast on T1 issues; isolates BOLD timeouts; one job per (subject, phase) for clean tracking |
| Per-session BOLD chunking | No (rejected) | Adds 4× job count; resume-from-work-dir achieves same robustness with less complexity |
| Auto-fallback to per-session | No (rejected) | YAGNI; designing around unobserved failure mode |
| Resume mechanism | Same `sbatch`, same `-w` work dir | fmriprep already memoizes nodes |
| CPUs | 8 | Performance plateaus past 8 (fmriprep maintainers' guidance) |
| Memory | 8 × 24 GB profile, 8 × 22 GB production | 3× prior cap; 22 GB fits all 16 russpold nodes |
| Wall time | 1d anat, 7d BOLD | russpold's 7d max; fits typical 12-13 session subjects with margin given 192 GB |
| Throttle | 12 production | ~62% partition memory at peak; "aggressive but not dominant" |
| Output spaces | Full (CIFTI + 1mm + 2mm + fsaverage6 + fsnative + T1w + func) | Restores parity with earlier Oak workflow; CIFTI needed for MSHBM |
| Cancellation of prior runs | Yes, 22226639 cancelled 2026-04-28 | Frees credit; 13/41 already failed under wrong envelope |

## Out of scope for this plan

- Changing fmriprep version (25.2.5 is available but staying on 25.2.4)
- Re-running the Oak res-2 fmriprep outputs
- Downstream stages (events QC, lev1, lev2, MSHBM)
- Changing BIDS dataset structure or `.bidsignore` patterns

## Open risks

1. **BOLD phase 7-day wall might be insufficient for 13-session validation subjects** even at 192 GB. Mitigation: resume protocol is documented; manual triage. If repeated timeouts, consider per-session-group BOLD as a documented escalation (not auto-pivot).
2. **nipype hash race may recur**. Mitigation: known fix is wipe + retry; usually resolves on second attempt.
3. **CIFTI output disk usage** ~ 2-3× the prior res-2 outputs. Mitigation: ensure scratch space has ≥5 TB free before launching.
4. **russpold partition contention**. Mitigation: throttle 12 caps occupancy at ~62% partition memory; honors "aggressive but not dominant" goal.
