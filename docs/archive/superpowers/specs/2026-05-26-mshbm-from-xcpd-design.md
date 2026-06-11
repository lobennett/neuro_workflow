# MSHBM From XCP-D — Design

**Date:** 2026-05-26
**Status:** Approved (design); pending implementation plan
**Scope:** New prep script that converts XCP-D denoised CIFTI outputs into MSHBM-ready fsaverage6 GIFTIs, replacing the task-residual + Du2025-postproc pipeline used previously.

## Motivation

The previous MSHBM training pipeline used lev1 task residuals + Du2025-style postprocessing (18-regressor confound + bandpass + 2mm smoothing) on rest + task data. That approach produced training parcellations (Params_Final.mat + sub-{XXX}_MSHBM.dlabel.nii for the discovery N=5 cohort), but the time series were lev1-residualized rather than directly preprocessed for functional-connectivity analysis.

XCP-D already denoises full timeseries (rest + task) with a stronger 36-parameter regression, despiking, censoring, and bandpass — the standard precision-network-mapping preprocessing. Building MSHBM input on top of XCP-D produces parcellations from data that more closely match published precision-mapping conventions (Du2025, Kong2019).

## Approach Overview

**Pipeline**: convert XCP-D `desc-denoised` CIFTI outputs (fsLR_den-91k surface, unsmoothed, motion+confound regressed, censoring-interpolated, 0.008-0.10 Hz bandpassed) into MSHBM-ready fsaverage6 GIFTIs (2mm FWHM smoothed). Then run MSHBM training using the existing wrapper but pointed at the new input directory.

**Why this is tight**: XCP-D already does motion regression, bandpass, despike, censoring. The only steps missing for MSHBM are space conversion (fsLR_32k → fsaverage6) and surface smoothing (2mm FWHM). No re-doing of regression.

## Input/Output

### Input
- XCP-D 26.0.2 outputs at:
  - `/scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2/sub-{XXX}/ses-{NN}/func/sub-{XXX}_ses-{NN}_task-{T}_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii`
  - `/scratch/users/logben/validation_bids/derivatives/xcp_d_26.0.2/...` (same pattern)
- Per-task or per-run variants exist (`*_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii`). Use the **per-task concatenated** version (without `_run-N`) since XCP-D was run with `--combine-runs`.

### Output
- New directory: `/scratch/users/logben/mshbm_inputs_discovery_xcpd/` (and `mshbm_inputs_validation_xcpd/`, then pool both into `mshbm_inputs_pooled_xcpd/`).
- Per-subject files following the same naming convention as the existing prep-mshbm output:
  - `{lh,rh}_ses-{NN}_task-{T}_xcpd_fsaverage6_sm2.nii.gz`
- Each file is a (V, 1, 1, T) NIfTI wrapping the fsaverage6 time series for one hemisphere, one session, one task. This matches what `mshbm_convert_task_residuals.py` already produces from lev1 GIFTIs.

## Resampling Details (fsLR_32k → fsaverage6)

Use `wb_command -metric-resample` with `BARYCENTRIC` method (simpler than ADAP_BARY_AREA, no area surfaces needed; standard for 32k → 41k upsampling).

Sphere files from `templateflow`:
- current-sphere: `tpl-fsLR_space-fsaverage_hemi-{L,R}_den-32k_sphere.surf.gii` (fsLR_32k vertices positioned in fsaverage coordinate frame)
- new-sphere: `tpl-fsaverage_hemi-{L,R}_den-41k_sphere.surf.gii` (fsaverage6 ≈ 40,962 vertices/hemi)

Step-by-step per (subject, session, task, hemi):
```
1. wb_command -cifti-separate <input.dtseries.nii> COLUMN \
       -metric CORTEX_LEFT  out_lh_unresampled.func.gii \
       -metric CORTEX_RIGHT out_rh_unresampled.func.gii
2. wb_command -metric-resample out_<h>_unresampled.func.gii \
       <fsLR_32k_sphere> <fsaverage6_sphere> BARYCENTRIC \
       out_<h>_fsaverage6.func.gii
3. wb_command -metric-smoothing <fsaverage6_midthickness> \
       out_<h>_fsaverage6.func.gii 0.85 \
       out_<h>_fsaverage6_sm2.func.gii
   (0.85 sigma ≈ 2mm FWHM: FWHM = 2.355 × sigma)
4. python: load .func.gii data; reshape to (V, 1, 1, T); save as NIfTI
```

### fsaverage6 midthickness
Templateflow provides pial + white but not midthickness directly. Compute once per hemi at script init:
```
wb_command -surface-average -surf <pial> -surf <white> -out <midthickness>
```
Cache to `/scratch/users/logben/mshbm_inputs_discovery_xcpd/.fsaverage6_midthickness_{L,R}.surf.gii`.

## Smoothing Kernel

Du2025 uses 2mm FWHM. wb_command's smoothing expects σ in mm:
- σ = FWHM / 2.355 = 2.0 / 2.355 ≈ 0.849 mm

## Code Organization

### Files

| File | Responsibility |
|---|---|
| `scripts/mshbm_from_xcpd.py` | NEW — per-subject driver: enumerate sessions/tasks, run cifti-separate / metric-resample / metric-smoothing, convert .func.gii → (V,1,1,T) .nii.gz |
| `src/neuro_workflow/analysis/mshbm/from_xcpd.py` | NEW — pure-Python helpers (file discovery, gifti → nifti wrapper, sphere/midthickness path resolution) — testable with TDD |
| `tests/analysis/mshbm/test_from_xcpd.py` | NEW — unit tests for helpers (no wb_command needed; mock the subprocess calls) |
| `/scratch/groups/russpold/logben/mshbm_from_xcpd.sbatch` | NEW — SLURM array submission wrapper |
| `/home/users/logben/network_glm/PrecisionNetworkMapping/MSHBM/MSHBM_Params_Training.sh` | Unchanged (bigmem, 384G, 4cpu wrapper that already works) |

### Reuse from existing pipeline
- MSHBM training wrapper + `MSHBM_wrapper.m` — unchanged
- Du2025 postproc module (`src/neuro_workflow/analysis/mshbm/preproc.py`) — not needed, XCP-D already did regression + bandpass
- `mshbm_convert_task_residuals.py` — superseded by the new path

## Execution Plan

### Stage 1: Smoke on s10 (discovery)
- Convert s10 XCP-D outputs (12 sessions × ~5 tasks each ≈ 60 cells × 2 hemis = ~120 GIFTIs → ~120 NIfTIs)
- Eyeball one cell in Workbench: load `lh_ses-01_task-rest_xcpd_fsaverage6_sm2.nii.gz` data on the fsaverage6 pial
- Check time-series length matches XCP-D's denoised TR count

### Stage 2: Discovery N=5 + train
- Run prep for all 5 discovery subjects
- Build sub_list.csv pointing at the new inputs
- Submit MSHBM_Params_Training_Prep.sh (which auto-chains MSHBM_Params_Training.sh)
- Verify Params_Final.mat + per-subject .dlabel.nii written

### Stage 3: Validation N=41 prep
- Run prep on all 41 validation subjects
- 2-3h SLURM array depending on subject count

### Stage 4: Pooled N=46 training
- Build pooled sub_list.csv
- Submit MSHBM training on bigmem (use 512G mem this time per prior N=46 observation)
- Final deliverable: per-subject `.dlabel.nii` for all 46 subjects + Params_Final.mat

## SLURM Resourcing

Per-subject prep job:
- wb_command runs sequentially, ~5-10 sec per (session × task × hemi)
- s10 has ~120 cells → ~10-20 min wall time
- 1 CPU, 4G mem, normal partition, 2h walltime (generous margin)

Array submission for N=5 discovery or N=41 validation:
- `--array=1-N`, each task processes one subject
- Concurrency limited by partition queue depth

MSHBM training:
- Discovery N=5: bigmem, 384G, 4cpu, 12h (parameters that just worked)
- Pooled N=46: bigmem, 512G, 8cpu, 24h (per memory of prior successful run)

## Testing / Validation

### Unit tests (TDD where possible)
- Helper functions in `src/neuro_workflow/analysis/mshbm/from_xcpd.py`: file discovery, sphere path resolution, GIFTI ⇄ NIfTI wrapper. Tests in `tests/analysis/mshbm/test_from_xcpd.py`.
- No tests for the wb_command subprocess pipeline itself — validated by smoke.

### Smoke validation
- Single subject (s10), single session/task, single hemi
- Output NIfTI dimensions: (40962, 1, 1, T) — verify T matches XCP-D's denoised TR count
- Visual: load on fsaverage6 surface in Workbench, confirm signal looks anatomically sensible (motor cortex active during motor task, default-mode resting topology)

### Cross-pipeline sanity check
- Pick one session/task with strong known activation (e.g., flanker incongruent-congruent at ses-01)
- Compare correlation map seed-from-PCC-vertex (default mode network anchor) between:
  - lev1-residual + Du2025 preproc input
  - XCP-D-denoised + new prep input
- Expect strong agreement on DMN topology

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| wb_command not on PATH on compute nodes | `module load workbench/1.5.0` in sbatch (precedent from `xcpd.sbatch`) |
| Sphere path not in templateflow cache on compute node | Templateflow cache is in `$HOME/.cache/templateflow/` which is mounted on compute nodes; pre-verified to exist |
| TR count mismatch between XCP-D denoised and original BOLD | XCP-D fills censored frames via interpolation when run in ABCD mode → output has same TR count as input. Verify in smoke. |
| Concatenated-runs file missing for some session/task | Fall back to per-run file if the no-run-suffix file doesn't exist; log a warning |
| Subject has missing tasks for some session | Skip cleanly, log info; MSHBM tolerates uneven session counts |

## Out of Scope

- Re-running XCP-D with different config — current outputs are reused as-is.
- Volume-space MSHBM — surface only.
- Comparison harness vs the lev1-residual+Du2025 pipeline (separate analysis).
- ABCC-format (censored) variant — using `desc-denoised` only.

## Success Criteria

1. `scripts/mshbm_from_xcpd.py` produces `(V=40962, 1, 1, T)` NIfTIs per (subject, session, task, hemi) named `{lh,rh}_ses-{NN}_task-{T}_xcpd_fsaverage6_sm2.nii.gz`.
2. Smoke run on s10 completes without error; outputs render correctly in Workbench.
3. Discovery N=5 MSHBM training runs to completion using new inputs; produces `Params_Final.mat` and 5 `sub-{XXX}_MSHBM.dlabel.nii`.
4. Validation N=41 prep completes; pooled N=46 MSHBM training produces all 46 individual parcellations.
5. Discovery-cohort parcellations (XCP-D-based) qualitatively match the prior task-residual-based parcellations on coarse network topology (sanity check, not a strict equality test).
