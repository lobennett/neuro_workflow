# MSHBM Pipeline Comparison — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorming) → ready for implementation plan
**Pilot subject:** sub-s10 (cohort-reusable)

## Goal

Quantify how much the **functional preprocessing pipeline** changes a DU15NET
15-network individual parcellation (MSHBM), holding everything else fixed. The
only variable across arms is denoising; FreeSurfer, surface space, data scope,
scan set, and MSHBM configuration are held identical.

This supersedes the earlier rest-only iProc parcellation, which conflated
pipeline **and** data-scope (rest-only) **and** FreeSurfer version (6.0 vs 7.3.2).

## Three arms

Each arm produces `sub-s10_MSHBM.dlabel.nii` + `{lh,rh}.label.gii` (fsaverage6):

1. **iProc** — multi-echo tedana denoising + bandpass. Re-run on FS 7.3.2 (see
   §iProc FS-swap). Input surfaces = iProc `*_tedana_bpss_fsaverage6` for all
   task+rest scans.
2. **fMRIPrep→XCP-D** — XCP-D confound regression + bandpass. Reuse the existing
   `mshbm_inputs_discovery_xcpd/sub-s10/` (full task+rest, fsaverage6, sm2)
   **if** confirmed to derive from fMRIPrep 25.2.4; else refresh via
   `scripts/mshbm_from_xcpd.py` on `xcp_d_26.0.2`.
3. **fMRIPrep+bandpass** — fMRIPrep surfaces + the lab's `mshbm.preproc`
   (confound regression + bandpass) only, no XCP-D. Built fresh.

## Invariants (what makes it apples-to-apples)

- **FreeSurfer 7.3.2** from fMRIPrep 25.2.4 — all three arms project onto the
  *same* `sphere.reg`. (Both fMRIPrep 24.1.0rc2 and 25.2.4 bundle FS 7.3.2.)
- **fsaverage6** surface space.
- **Full task+rest BOLD timeseries** — no GLM residuals (per J. Du's guidance).
- **Surface smoothing = 2mm FWHM** across all arms. The reusable XCP-D inputs are
  already sm2; iProc-FS7 and fMRIPrep+bandpass surfaces are smoothed to 2mm FWHM
  on the fsaverage6 midthickness (`wb_command -metric-smoothing`) to match. (The
  earlier rest-only iProc run used sm0 and is superseded for this comparison.)
- **Identical scan set** — intersection of scans present and QC-passing in all
  three arms; a scan dropped by any arm is dropped from all. Per-session manifest
  written to each arm's output dir (logged, not silent).
- **Same MSHBM config** — DU15NET 15-network pretrained prior
  (`MSHBM_prior_15.mat`), `MSHBM_GROUP_BY_SESSION=1` (task+rest runs in a session
  average their correlation before top-10% binarization — Du 2024 convention,
  matching the existing XCP-D `sess_grouped` run), same smoothing/iterations,
  N=1.

## Surface quality motivation (measured 2026-06-02, sub-s10)

| Metric | iProc FS 6.0.0 | fMRIPrep FS 7.3.2 |
|---|---|---|
| SurfaceHoles (defects fixed) | 51 (lh 28 / rh 23) | 9 (lh 2 / rh 7) |
| Final white-surface Euler | 2 (0 residual) | 2 (0 residual) |
| Est. total intracranial vol | 1,418,221 mm³ | 1,099,800 mm³ |

Final surfaces are topologically valid in both (Euler forced to 2), but iProc's
FS 6.0 carries ~5.7× the defect burden and a 29% ETIV discrepancy — motivating
the swap to FS 7.3.2 and removing FreeSurfer version as a confound.

## iProc FreeSurfer-swap rerun

FreeSurfer is woven into iProc beyond the final projection: `T1_warp_and_mask`
runs `bbregister --s <fs_subj>` (BOLD→anat registration target = the FS white
surface), and `filter_and_project` uses the FS subject's surfaces/`sphere.reg`.
So the swap cascades into a near-full rerun.

Plan:
1. **Ingest** fMRIPrep 25.2.4 FS 7.3.2 recon (`sub-s10_ses-09`) into iProc's
   `fs/s10/` as the FS subject (replacing FS 6.0 `09_009`), with iProc `setup`'s
   conformed-space sanity check.
2. **Re-run** `T1_warp_and_mask` (new `bbregister`) → `combine_and_apply_warp` →
   tedana (MNI111 + NAT111) → `filter_and_project`. Reuse
   `unwarp_motioncorrect_align` (FS-independent) unchanged.
3. Output to a **separate tree** (e.g. `…/iproc_fs7/`) so the FS 6.0 results
   remain as a baseline arm. New `*_tedana_bpss_fsaverage6` surfaces for all 57
   task+rest scans.

Driven by the existing `scripts/iproc_scatter.py` scatter tooling with the same
partition-courtesy throttling. This is the expensive piece (~the prior campaign).

## fMRIPrep arms

**Arm 2 (XCP-D):** confirm the existing discovery XCP-D MSHBM inputs derive from
fMRIPrep 25.2.4. If yes → reuse `mshbm_inputs_discovery_xcpd/sub-s10/` (zero new
compute). If no → refresh via `mshbm_from_xcpd.py`.

**Arm 3 (fMRIPrep+bandpass):** new tested module `mshbm/from_fmriprep.py` +
driver. Per scan: take fMRIPrep 25.2.4 `fsnative` surface BOLD → resample to
fsaverage6 via the same FS 7.3.2 `sphere.reg` (identical resampling path to the
other arms) → apply `mshbm.preproc` (existing, tested confound-regress + bandpass
module; fMRIPrep confounds TSV, the lab's existing regressor set — no new
nuisance model) → 2mm-FWHM surface smoothing (`mshbm.preproc`'s optional
smoothing step) → write fsaverage6 NIfTIs named to the MSHBM glob
`{lh,rh}*fsaverage6_sm*.nii.gz`.

## MSHBM runs

All arms through the same `run_MSHBM.sh` path: DU15NET 15-net prior,
`MSHBM_GROUP_BY_SESSION=1`, `normal` partition, 64/96 GB, codedir =
`~/network_glm/PrecisionNetworkMapping` (fully-populated clone), with the
template `.gitkeep` dirs + 24h time + mem fixes from this session. Output dirs:
`mshbm_output_{iproc_fs7,xcpd,fmriprep_bp}_s10`.

## Quality comparison module (`mshbm/compare.py`, tested)

- **Cross-arm agreement:** vertex label-agreement % + per-network Dice for every
  arm pair (network labels aligned via the shared DU15NET prior).
- **Intrinsic quality (headline):** within-parcel functional homogeneity — mean
  correlation of each cortical vertex's timeseries to its parcel's mean
  timeseries, per arm. Higher = parcellation better captures coherent FC.
  Budget permitting, split-half generalization (parcellate on half the sessions,
  score homogeneity on the held-out half).
- **Descriptors:** per-network size distributions, spatial
  contiguity/fragmentation, and input **tSNR** per arm (preprocessing-quality
  proxy that contextualizes parcellation differences).
- **Outputs:** metrics TSV + side-by-side surface figure (rows: iProc-FS6
  baseline, iProc-FS7, XCP-D, fMRIPrep+bandpass) + homogeneity/Dice bar chart.

## Components

All subject-parameterized, tested, in `src/neuro_workflow/analysis/mshbm/`:

- `from_iproc.py` — extend discovery from rest-only to **all task+rest** scans,
  and add 2mm-FWHM surface smoothing (`wb_command -metric-smoothing`) to match
  the sm2 invariant (the current rest-only path emits sm0).
- `from_fmriprep.py` — new Arm 3 builder (fMRIPrep + `mshbm.preproc` →
  fsaverage6).
- `compare.py` — metrics + figures.
- iProc FS-ingest helper + scatter rerun driver (reuses `iproc_scatter.py`).

Tests mirror existing `tests/analysis/mshbm/` conventions (discovery/naming/
reshape unit tests; comparison-metric unit tests on synthetic labels).

## Verification gates (stop-and-check)

1. FS-ingest conformed-space match before rerunning iProc.
2. iProc-FS7 surface QC — re-measure SurfaceHoles, confirm all 57 scans reproject
   cleanly (456 surfaces).
3. Common-scan-set sanity (count + per-session manifest) before MSHBM.
4. Each MSHBM parcellation QC'd (15 networks present, balanced size distribution)
   as done for the rest-only run.

## Cohort extension

Once s10 validates the FS-swap + 3-arm machinery, the cohort run is a fan-out
over the subject parameter (the discovery subjects, then validation). No new
components.

## Out of scope

- GLM task residuals (explicitly excluded — full timeseries per J. Du).
- New nuisance-regression models (reuse `mshbm.preproc` / XCP-D as-is).
- Re-running fMRIPrep or XCP-D from scratch (reuse existing FS 7.3.2 derivatives).
- Multi-resolution (only DU15NET 15-network).

## Risks

- **iProc FS-swap cost** — the heaviest item (full iProc rerun incl. NAT 256³
  tedana). Mitigated by reusing `unwarp_motioncorrect_align` and existing scatter
  throttling.
- **N=1 group-prior** — validated working on the rest-only run; same here.
- **Denoising asymmetry** — iProc ME-tedana has no single-echo equivalent; this
  *is* the pipeline difference being measured, contextualized by the tSNR
  descriptor and the two fMRIPrep arms bracketing iProc.
