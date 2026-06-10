# fMRIPrep 25.2.4 rerun on discovery + validation: single-phase view-based pipeline

**Date:** 2026-04-28
**Author:** Logan Bennett (with brainstorming assist)
**Datasets:** discovery (5 subjects), validation (41 subjects)
**Container:** `/home/groups/russpold/singularity_images/fmriprep_25.2.4.sif`

## Context

Two prior fmriprep 25.2.4 runs against `/scratch/users/logben/{discovery,validation}_bids/` failed at scale:

- **Discovery** (job 22226603): 5/5 failed. 4/5 hit FreeSurfer `talairach_afd` QC failure at ~6h. 1/5 (s19) recovered FS but timed out at 5d during BOLD processing. All 5 saturated 64 GB memory cap.
- **Validation** (job 22226639): 0/41 completed. Of 21 tasks that ran: 8 TIMEOUT (5-day wall), 3 FAILED (nipype hash race on `fsdir_run` cache), 2 OUT_OF_MEMORY. Cancelled 2026-04-28 before remaining 20 PENDING ran.

Earlier Oak runs of the same subjects with `--output-spaces res-2` (2mm) succeeded but at lower spatial resolution and without `acq-MPRAGEPromo` T1w files in the BIDS tree.

## Goal

Reliably preprocess all 46 subjects with fmriprep 25.2.4 producing the full output-space set (1mm MNI volumetric, 2mm MNI152NLin6Asym, fsaverage6, fsnative, T1w, func, CIFTI 91k) with FreeSurfer derivatives, in 1-3 weeks of cluster wall time.

## Root causes (confirmed by diagnostics)

| Class | Affected | Root cause | Fix |
|-------|----------|-----------|-----|
| FreeSurfer Talairach AFD failure | 5/5 discovery | fmriprep selected `acq-MPRAGEPromo` T1w (lower-quality acquisition); FreeSurfer's `talairach_afd` QC failed (p=0.0082 < 0.005). `.bidsignore` listed it but **pybids does not honor `.bidsignore`** | Symlink BIDS view that physically excludes `.bidsignore`d files from fmriprep's view |
| Wall-time TIMEOUT | 8 validation, 1 discovery | 5-day SLURM wall too short for 12-13 sessions × multi-echo × 1mm + CIFTI + fresh FreeSurfer under memory pressure | 7-day wall + 192 GB removes memory pressure (3× headroom); resubmit-to-resume on rare timeouts |
| OOM / memory saturation | 2 OOM, all discovery saturated 64 GB | 64 GB insufficient for 1mm + multi-echo + FS + CIFTI | 8 CPUs × 24 GB profile, 22 GB production |
| nipype hash race (FAILED early) | 3 validation (s1057, s1175, s1189) | Transient nipype bug in `fsdir_run` caching during workflow construction | Wipe affected subject's work dir + retry |

## Key constraint discovered

**`.bidsignore` is honored only by the BIDS Validator, not by BIDS apps.** pybids `BIDSLayout` does not read `.bidsignore` by default. The pre-flight pipeline must translate `.bidsignore` into something fmriprep actually respects: a **symlink BIDS view** at `<bids_dir>/derivatives/fmriprep_25.2.4_input/` containing only the non-excluded files.

## Architecture

```
Phase 0: Pre-flight (local script, idempotent)
  scripts/fmriprep_preflight.py:
    For each dataset (discovery, validation):
      1. Build symlink BIDS view at:
           <bids_dir>/derivatives/fmriprep_25.2.4_input/
         Every file in BIDS tree is symlinked except those matching .bidsignore patterns
      2. Sanity-check view:
         - every subject has ≥ 1 T1w; abort otherwise
         - subjects with intentional multi-anat (s1351 has 2 T1w; s1399 has 2 T2w)
           verified to retain both; abort otherwise
      3. Wipe stale work dirs and any failed FS dirs from prior runs

Phase 1: s03 profile  (1 SLURM job, gates Phase 2)
  Single-phase fmriprep on s03 with full resource envelope.
  Manual go/no-go review after completion.

Phase 2: Production  (45 jobs across 2 array submissions)
  Discovery (4 remaining):  array of 4, throttle 4
  Validation (41):          array of 41, throttle 12
  Both submitted concurrently (validation has --dependency=afterany on
  discovery to keep peak partition memory under ~62%).

Resume protocol (the only "fallback")
  Any failure → resubmit just that subject (single-task array of 1).
  Same flags + same work dir → fmriprep skips already-completed nodes.
```

**Job count:** 46 total (one fmriprep job per subject). One simple mental model.

## Resource envelope

| | CPUs | Mem/CPU | Total mem | Wall | Throttle |
|---|---|---|---|---|---|
| Phase 1 (s03 profile) | 8 | 24 GB | 192 GB | 7 days | n/a (1 task) |
| Phase 2 (production, 45 subjects) | 8 | 22 GB (calibrated from profile) | 176 GB | 7 days | 12 (validation), 4 (discovery) |

**CPU rationale:** fmriprep performance plateaus past 8 CPUs. Beyond 8, idle cores waste cluster credit; better to spend on memory.

**Memory rationale:** Prior runs saturated 64 GB cap. 192 GB profile envelope gives 3× headroom to *measure* peak RSS rather than re-cap. Production envelope calibrated from profile (target ~22 GB/CPU = 176 GB total). 176 GB fits all 16 russpold nodes (smallest is 191 GB total memory).

**Throttle 12 rationale:** russpold has 16 nodes, 448 CPUs, 3.4 TB memory. Memory is binding constraint. At throttle 12 with 176 GB/task = 2,112 GB peak (≈62% of partition memory). "Aggressive but not dominant"; leaves margin for other partition users.

## Output spaces & flags

```
--output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func"
--no-submm-recon --skip-bids-validation --cifti-output 91k
```

Restores parity with earlier Oak workflow (CIFTI 91k preserved) plus 1mm MNI volumetric upgrade. CIFTI required for MSHBM and grayordinate-based group analyses.

`--dummy-scans` is **not** used: scratch BIDS data already trimmed by bidsify (7 dummy volumes physically removed from NIfTIs).

## Phase 0: Pre-flight

`scripts/fmriprep_preflight.py` (new). Idempotent. Run once per dataset.

### Inputs
- Dataset name (`discovery` or `validation`) → BIDS dir from `~/.neuro_workflow/datasets.json`
- The dataset's `.bidsignore` at BIDS root
- `docs/EXCLUSIONS.md` (human-readable companion; informs sanity checks)

### Outputs
- `<bids_dir>/derivatives/fmriprep_25.2.4_input/` — symlink BIDS view
- Console summary: per-subject T1w/T2w/BOLD counts in view + total files excluded

### Algorithm

```
1. Read .bidsignore patterns from <bids_dir>/.bidsignore
2. Walk <bids_dir> top-down:
     skip derivatives/, sourcedata/, code/ subtrees
     for each file in subject subtrees + top-level metadata files:
       if file matches any .bidsignore pattern: SKIP (don't symlink)
       else: create symlink at corresponding position in view tree
3. Symlink top-level files into view: dataset_description.json, README,
   participants.tsv, .bidsignore (so view is a self-describing BIDS dataset)
4. Sanity checks (abort with error if any fail):
     - Every subject has ≥ 1 T1w in view
     - Subjects with intentional multi-anat retain expected counts:
         * Validation s1351: 2 T1w (ses-01 + ses-08)
         * Validation s1399: 2 T2w (ses-01 + ses-02)
     - No file in view points outside <bids_dir>
5. Print summary table:
     | Subject | T1w | T2w | BOLD | Excluded |
     | s03     | 1   | 1   | 110  | 4        |
     | ...
```

### Multi-anat handling

`docs/EXCLUSIONS.md` documents which subjects intentionally retain multiple T1w/T2w scans for fmriprep to average:

- **Discovery**: every subject ends up with 1 T1w + 0-1 T2w after `.bidsignore`. No multi-anat.
- **Validation s1351**: 2 T1w (ses-01 + ses-08) — both clean per collaborator review.
- **Validation s1399**: 2 T2w (ses-01 + ses-02) — both decent per collaborator review.

The view automatically handles these correctly: `.bidsignore` doesn't list either of s1351's T1ws nor either of s1399's T2ws, so both are symlinked into the view, and **fmriprep's default behavior averages multiple T1w/T2w into a per-subject anat template**. No special configuration needed.

### Why view-only (no BIDS filter file)

Earlier design considered a BIDS filter file for anat exclusions. Removed because:
- After `.bidsignore` exclusions, every subject has the right anat count for fmriprep's default behavior (1 T1w → use it; 2 T1w → average them).
- A filter file would add a parallel exclusion mechanism that must be kept in sync with `.bidsignore`.
- One mechanism = one source of truth. View IS the audit trail (you can `ls` it).

## Phase 1: s03 profile

```bash
neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 7-00:00:00 \
  --array-throttle 1 \
  --subjects-file <(echo s03)
```

**Note on `--bids-dir-override`**: this is the **one** small `neuro-run` extension this design needs (~10 lines in `pipelines/fmriprep.py`). It points fmriprep at the view path (the override) while keeping derivatives output at the registered BIDS dir's `derivatives/fmriprep_25.2.4/`. The override does not change the dataset registration, so future stages (events QC, lev1, etc.) still resolve the registered BIDS path naturally.

### Phase 1 success gates (manual review)

```
✓ recon-all.log contains "finished without error" (no Talairach failure)
✓ derivatives/sub-s03/anat/*MNI152NLin2009cAsym*desc-preproc_T1w.nii.gz exists
✓ Every non-.bidsignored BOLD has *desc-preproc_bold.nii.gz in derivatives
✓ CIFTI files (*den-91k_bold.dtseries.nii) generated
✓ confounds_timeseries.tsv exists for every BOLD
✓ HTML report renders cleanly
✓ sacct Elapsed and MaxRSS captured for calibration
```

If 1 fails: triage; resume or fix and resubmit before launching Phase 2.

### Profile report

After Phase 1 completes, write `docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md`:
- Elapsed wall time
- Peak RSS
- Stage breakdown: FreeSurfer time, ANTs time, BOLD per-session time, CIFTI generation time
- Calibration decision: production envelope (CPUs × Mem) and wall time, with justification

## Phase 2: production (45 subjects)

```bash
# Discovery: 4 remaining (s10, s19, s29, s43)
neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "..." \
  --fmriprep-args "..." \
  --nthreads 8 --mem-per-cpu-gb <calibrated> --time 7-00:00:00 \
  --array-throttle 4 \
  --subjects-file subjects_phase2_discovery.txt
# → DISCOVERY_JID

# Validation: 41 subjects, dependency on discovery to keep peak load bounded
neuro-run submit fmriprep validation \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "..." \
  --fmriprep-args "..." \
  --nthreads 8 --mem-per-cpu-gb <calibrated> --time 7-00:00:00 \
  --array-throttle 12 \
  --dependency afterany:${DISCOVERY_JID} \
  --subjects-file subjects_validation.txt
```

`afterany` lets validation start when discovery is complete in any state (we don't block validation if some discovery subjects need triage). With discovery at throttle 4 finishing in ≤7 days and validation at throttle 12 finishing in ~2-3 weeks, total wall time is ~3-4 weeks worst case, ~2-3 weeks typical.

If you'd rather they overlap (discovery and validation running simultaneously, taking ~2-3 weeks worst case), drop the dependency and reduce validation throttle to 8 (so combined peak = 4 discovery + 8 validation = 12 concurrent).

## Resume protocol (the only "fallback")

If subject `s1057` validation times out at day 7:

```bash
sacct -j <JID>_<TASKID> --format=State,Elapsed,MaxRSS

# Resume — same work dir, fmriprep skips done nodes
neuro-run submit fmriprep validation \
  --bids-dir-override /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4_input \
  --subjects-file <(echo s1057) \
  ... (same flags as Phase 2) --array-throttle 1
```

Per failure mode:
- **Memory cap hit (OOM)**: bump `--mem-per-cpu-gb`; do not wipe work dir; resubmit.
- **Wall timeout**: same flags + same work dir → fmriprep resumes from cached nodes.
- **nipype hash race** (FileNotFoundError on `*.pklz` early): wipe that subject's work dir, resubmit.
- **BIDS view bug** (e.g., dropped a needed file): fix in pre-flight, regenerate view, wipe work dir, resubmit.

## Required `neuro-run` extension

One small addition to `src/neuro_workflow/pipelines/fmriprep.py`:

**`--bids-dir-override <PATH>`**: when provided, the sbatch template binds this path as `/data` instead of the registered `bids_dir`. The output path remains `<registered_bids_dir>/derivatives/fmriprep_<version>/`. Approximately 10 lines of code plus a test.

No other changes to neuro-run, no per-subject filter files, no SLURM dependency tooling beyond what `--dependency` already passes through.

## Testing

### Pre-flight script tests (`tests/scripts/test_fmriprep_preflight.py`)

- Idempotency: run script twice; view symlinks byte-identical.
- Multi-anat sanity: assert s1351 view contains 2 T1w files, s1399 view contains 2 T2w files.
- BOLD exclusion sanity: assert s03 view does not contain `*ses-11_task-stopSignalWDirectedForgetting*` (an example .bidsignored pattern), but does contain other BOLDs from ses-11.
- Run-level exclusion: assert s10 view does not contain `*ses-01_task-goNogo_run-1*` but does contain `*ses-01_task-goNogo_run-2*`.
- Pybids round-trip: load view with BIDSLayout; assert subject and BOLD counts match expectations.
- Cross-check `docs/EXCLUSIONS.md`: parse the markdown tables, assert every excluded scan listed there is absent from the view.

### Pre-submission smoke tests

- `neuro-run show fmriprep ...` to inspect generated sbatch before submitting.
- `tree <view-path>/sub-s03 | head -20` to visually inspect the symlinks for one subject.

### Phase 2 monitoring

Daily during production:
- `sqlb | grep fmriprep` for status snapshot
- `sacct -u logben --starttime=$(date -d '24 hours ago' +%FT%T) --format=JobID,State,Elapsed,MaxRSS,ExitCode --noheader | grep fmriprep | grep -v "extern\|batch"` for completions and failures
- After first 5-10 subjects complete, compare actual peak RSS to profile envelope; bump or trim `--mem-per-cpu-gb` if needed for remaining subjects.

## Failure triage decision tree

| Failure mode | Diagnosis signal | Action |
|---|---|---|
| Talairach AFD | `recon-all.log` has "Talairach failed" | Should not occur (view excludes bad T1ws). If it does: investigate which T1w fmriprep selected; pre-flight may have a bug. |
| OOM | sacct State=OUT_OF_MEMORY or MaxRSS at allocation cap | Bump `--mem-per-cpu-gb`; same work dir; resubmit |
| Wall timeout | sacct State=TIMEOUT, MaxRSS reasonable | Resubmit (resume); if 2nd timeout → bump memory |
| nipype hash race | FileNotFoundError on `*.pklz` early in workflow log | Wipe that subject's work dir; resubmit |
| BIDS view bug | Workflow log says "no T1w found" or wrong session selected | Fix pre-flight script; regenerate view; resubmit |

## Wall-time projection

| Phase | Per-job wall | Throttle | Subjects | Cumulative wall |
|-------|--------------|----------|----------|-----------------|
| Phase 0 | minutes | n/a | 2 datasets | day 0 |
| Phase 1 | ~3-5 days | n/a | 1 (s03) | day 3-5 |
| Phase 2 discovery | ~3-5 days | 4 | 4 | days 5-10 |
| Phase 2 validation | ~3-5 days | 12 | 41 | days 10-25 (sequenced after discovery via `afterany`) |

**Best case:** ~2-3 weeks (most subjects ≤4d).
**Worst case:** ~5 weeks (multiple subjects need 7d resume).
**Most likely:** 3-4 weeks total.

## Key design decisions (single source of reference)

| Decision | Choice | Why |
|----------|--------|-----|
| `.bidsignore` translation | Symlink view at `<bids_dir>/derivatives/fmriprep_25.2.4_input/` | pybids ignores `.bidsignore`; one mechanism handles all exclusion patterns uniformly |
| View nesting location | Under `derivatives/`, sibling to fmriprep output | Lineage co-located; pybids ignores `derivatives/` so no double-scanning |
| BIDS filter file | Not used | Redundant with view; would require parallel maintenance |
| Pipeline phases | Single-phase fmriprep per subject | Two-phase (anat then BOLD) over-engineered for a failure mode (Talairach) the view already eliminates |
| Profile-first | Yes, on s03 | Validates view + resources before launching 45 subjects |
| Multi-anat subjects (s1351 T1w, s1399 T2w) | View retains both; fmriprep auto-averages | Matches `docs/EXCLUSIONS.md` intent; fmriprep's default behavior |
| Resume mechanism | Same `sbatch`, same work dir | fmriprep memoizes nodes by hash |
| CPUs | 8 | Performance plateaus past 8 (fmriprep maintainer guidance) |
| Memory | 8 × 24 GB profile, 8 × 22 GB production | 3× prior cap; 22 GB fits all 16 russpold nodes |
| Wall time | 7 days | russpold's 7d max; fits typical 12-13 session subjects with margin given 192 GB |
| Throttle | 12 validation, 4 discovery | ~62% partition memory at peak; "aggressive but not dominant" |
| Output spaces | Full (CIFTI 91k + 1mm + 2mm + fsaverage6 + fsnative + T1w + func) | Restores Oak parity; CIFTI needed for MSHBM |
| Cancellation of prior runs | Done (22226639 cancelled 2026-04-28) | Frees credit; 13/41 already failed under wrong envelope |
| `neuro-run` extensions | One: `--bids-dir-override` | Minimum surface area to support view-based input |

## Out of scope

- Changing fmriprep version (25.2.5 is available; staying on 25.2.4)
- Re-running the Oak res-2 fmriprep outputs
- Downstream stages (events QC, lev1, lev2, MSHBM)
- Changing BIDS dataset structure or `.bidsignore` patterns

## Open risks

1. **BOLD wall-time** for the heaviest 13-session validation subjects might still hit 7 days at 1mm + multi-echo + CIFTI even with 192 GB. Mitigation: resume protocol is documented; manual triage. If repeated timeouts on the same subject, escalate (split sessions or bump CPUs).
2. **nipype hash race** may recur. Mitigation: known fix is wipe + retry; usually resolves on second attempt.
3. **CIFTI output disk usage** ~ 2-3× the prior res-2 outputs. Mitigation: ensure scratch space has ≥5 TB free before launching.
4. **russpold partition contention**. Mitigation: throttle 12 caps occupancy at ~62% partition memory.
