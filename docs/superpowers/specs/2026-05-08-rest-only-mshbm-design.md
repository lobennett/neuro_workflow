# Rest-Only MSHBM on Discovery — design

**Date:** 2026-05-08
**Status:** Draft, ready for review
**Scope:** Sub-project 1 of the MSHBM precision network mapping effort: get rest-only MSHBM running on the discovery cohort using the existing `prep-mshbm` + `mshbm` pipelines, view the resulting per-subject networks in Connectome Workbench. Out of scope: pyMSHBM equivalence study (sub-project 2), refactoring task-residual saving into lev1 (sub-project 3).

---

## Context

The repo already contains:

- `analysis/mshbm/run.py` (~808 lines) — prep code that discovers task residuals + rest BOLD across multiple fmriprep output spaces (fsnative, fsaverage6, MNI, T1w), projects everything to fsaverage6 via FreeSurfer's `mri_surf2surf` / `mri_vol2surf`, and writes MSHBM-compatible NIfTI files. Despite the module name, this is *prep*, not the MSHBM model itself.
- `pipelines/prep_mshbm.py` — SLURM array wrapper around the prep script.
- `pipelines/mshbm.py` — SLURM wrapper that invokes `bash {mshbm_dir}/MSHBM/run_MSHBM.sh ...` against a sibling MATLAB repo (Buckner's `PrecisionNetworkMapping`). The actual MSHBM algorithm lives outside this repo, in MATLAB.

Discovery's fmriprep run already produced **240 `space-fsaverage6_bold.func.gii`** files for rest data — meaning the prep step's heaviest work (surface projection) is already done. For rest-only, prep is essentially a format conversion + rename.

The user's fork of Buckner's `PrecisionNetworkMapping` (`lobennett/PrecisionNetworkMapping`) lives at `/home/users/logben/network_glm/PrecisionNetworkMapping`. As of 2026-05-08 it is synced with `bucknerlab/main` (merged) plus two necessary customizations:
- Sherlock-specific paths and module-loaded `wb_command` (vs. Harvard NCF defaults).
- BIDS subject ID handling (`strjoin(SUB, '_')` instead of the upstream's `SUB{i}(1:3)` 3-char truncation, which would silently collide BIDS subject IDs).
- Bug fix in `MSHBM/run_MSHBM.sh` (`$output_dir` → `$outputdir` typo).
- `readtable` `'ReadVariableNames',false` for the subject CSV format the prep script produces.

---

## Goals

1. Add `--rest-only` flag to `prep-mshbm` pipeline + the underlying analysis script. When set, skip task-residual discovery and processing entirely. Make `--glm-dir` optional in this mode.
2. Surface a clear error if neither `--rest-only` nor `--glm-dir` is set, or if both are set.
3. Operate the existing `mshbm` pipeline with `--mshbm-dir /home/users/logben/network_glm/PrecisionNetworkMapping` (the fork's location).
4. Produce per-subject MSHBM output (`.dscalar.nii` network labels) for the 5 discovery subjects from rest data alone.
5. Do not break the existing task+rest path. Task-residual processing continues to work when `--glm-dir` is supplied without `--rest-only`.

## Non-goals

- pyMSHBM (Python port) evaluation. Deferred to sub-project 2.
- Refactoring lev1 to save fsaverage6 residuals natively. Deferred to sub-project 3.
- Connectome Workbench visualization automation. Manual step at end.
- Removing the task-residual code paths in `analysis/mshbm/run.py`. They stay; just bypassed when `rest_only=True`.

---

## Architecture

Three small, additive code changes in this repo. Zero changes to the MATLAB MSHBM repo (already adapted for Sherlock + BIDS subject IDs in your fork).

```
src/neuro_workflow/pipelines/prep_mshbm.py     ← add --rest-only flag, make --glm-dir optional
src/neuro_workflow/templates/prep_mshbm.sbatch ← conditionally render --rest-only / --glm-dir
src/neuro_workflow/analysis/mshbm/run.py       ← add --rest-only, gate task-residual paths
tests/pipelines/test_prep_mshbm.py             ← extend with 4 tests
tests/analysis/mshbm/test_run.py               ← new file, 1 test
```

The `pipelines/mshbm.py` and `templates/mshbm.sbatch` need no code changes — pass `--mshbm-dir` explicitly at submit time.

---

## Data flow

```
fmriprep already produced (5 subjects × 12 sessions × 2 hemispheres ≈ 120 files):
  /scratch/.../discovery_bids/derivatives/fmriprep_25.2.4/sub-{S}/ses-{N}/func/
    sub-{S}_ses-{N}_task-rest_run-1_hemi-{L,R}_space-fsaverage6_bold.func.gii
                ↓
neuro-run submit prep-mshbm discovery --rest-only \
    --fmriprep-dir /scratch/.../discovery_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/mshbm_inputs_discovery
                ↓
analysis/mshbm/run.py per subject (rest-only branch):
   skip discover_task_residuals_* + process_*_residuals
   discover_rest_bold_fsaverage6() finds GIFTIs
   process_rest_fsaverage6() identity mri_surf2surf → NIfTI
   writes:
     mshbm_inputs_discovery/sub-{S}/{lh,rh}_ses-{N}_task-rest_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz
                ↓
neuro-run submit mshbm discovery \
    --surface-inputs-dir /scratch/users/logben/mshbm_inputs_discovery \
    --output-dir /scratch/users/logben/mshbm_output_discovery \
    --mshbm-dir /home/users/logben/network_glm/PrecisionNetworkMapping
                ↓
templates/mshbm.sbatch:
  bash /home/users/logben/network_glm/PrecisionNetworkMapping/MSHBM/run_MSHBM.sh \
       {sub_list_file} {output_dir} {mshbm_dir}
                ↓
mshbm_output_discovery/Params_{sub-s03_sub-s10_sub-s19_sub-s29_sub-s43}/
  group_priors / individual_parcellations / profiles_and_ini_params /
  per-subject .dscalar.nii network labels
                ↓
[user opens .dscalar.nii in Connectome Workbench manually]
```

---

## CLI semantics

`prep-mshbm` adds:

```
--rest-only         (bool flag, default False)
--glm-dir PATH      (now optional; default None)
```

Validation rules:
- exactly one of `--rest-only` / `--glm-dir` must be present
- `--rest-only` AND `--glm-dir` together → CLI error
- neither → CLI error

Existing required args (`--fmriprep-dir`, `--output-dir`) unchanged. Existing optional args (`--rest-fmriprep-dir`, `--sessions`, resource args) unchanged.

Inside `analysis/mshbm/run.py`'s `process_subject()`, when `args.rest_only` is True the function:
- Skips the entire task-residual discovery block (lines that call `discover_task_residuals_volume` / `discover_task_residuals_surface` and the corresponding processing functions).
- Runs only the rest-discovery + rest-processing block.
- Gracefully handles `args.glm_dir is None`.

---

## Error handling + edge cases

- **`--rest-only` and `--glm-dir` both set**: argparse-level error with clear message. Implemented via a post-`parse_args` validation in `pipelines/prep_mshbm.py`'s `add_cli_args` consumer (or in `analysis/mshbm/run.py`'s `main`).
- **Neither flag set**: same — clear error.
- **`--rest-only` set but no fsaverage6 GIFTIs in fmriprep dir**: `discover_rest_bold_fsaverage6` returns empty list. Generator emits a clear error mentioning fmriprep's `--output-spaces fsaverage6` requirement.
- **mshbm-dir doesn't exist**: `bash {mshbm_dir}/MSHBM/run_MSHBM.sh` fails at sbatch time with "No such file"; surfaced in `.err` log.
- **MATLAB module load failure**: existing `module load matlab` in `templates/mshbm.sbatch` handles this; SLURM logs surface failures.
- **BIDS subject ID handling**: handled by the fork's `strjoin(SUB, '_')` fix.
- **Concurrent SLURM jobs**: validation lev1 (job 24286662) is in flight on russpold; prep-mshbm + mshbm jobs queue politely.

---

## Tests

`tests/pipelines/test_prep_mshbm.py` (extend existing):

1. **`test_rest_only_omits_glm_dir`** — render sbatch with `--rest-only`; assert `--rest-only` rendered, `--glm-dir` not rendered.
2. **`test_glm_dir_path_unchanged`** — render with only `--glm-dir`; assert backwards-compat.
3. **`test_neither_flag_errors`** — assert `parser.error` / `SystemExit`.
4. **`test_both_flags_error`** — assert error when both passed.

`tests/analysis/mshbm/test_run.py` (new file):

5. **`test_process_subject_rest_only_skips_task_residual_discovery`** — monkeypatch `discover_task_residuals_volume` and `discover_task_residuals_surface` to record calls. Call `process_subject(args=Namespace(rest_only=True, glm_dir=None, ...))` against a fake fmriprep tree with fsaverage6 GIFTIs. Assert task-residual functions never called; rest discovery + processing run normally.

**Operational verification (post-merge, manual):**

6. Submit `prep-mshbm discovery --rest-only ...` against discovery's fmriprep dir. Confirm SLURM completes. Spot-check `sub-s03` output: 12 sessions × 2 hemispheres = 24 NIfTI files at the expected names.
7. Submit `mshbm discovery --surface-inputs-dir ... --mshbm-dir /home/users/logben/network_glm/PrecisionNetworkMapping`. Wait for MATLAB MSHBM to complete. Hours of walltime expected.
8. Open output `.dscalar.nii` in Connectome Workbench manually; sanity-check networks against published Buckner 15-network parcellation.

---

## Code-style guardrails

- `--rest-only` is a single boolean flag, not a tri-state. The "task-only" mode is implicit when `--glm-dir` is set without `--rest-only`. Don't introduce a `--task-only` flag.
- All edits additive (no removal of existing task-residual paths).
- Tests follow existing `tests/pipelines/test_prep_mshbm.py` style — render the sbatch script, grep for substrings.
- The new `tests/analysis/mshbm/` directory needs an `__init__.py`.

---

## Open questions / decisions deferred to implementation

1. **Where to put the validation logic** (both-flags-error, neither-flag-error): the cleanest place is `pipelines/prep_mshbm.py:add_cli_args` calling `parser.error(...)` after the `parse_args` call site. The implementer reads `cli.py`'s pipeline-arg-parsing flow at implementation time and matches that pattern.
2. **`mshbm-dir` as a CLI arg vs. dataset config field**: today it's only a CLI arg with a wrong default (`{neuro_workflow}/../PrecisionNetworkMapping` doesn't exist). Could move to dataset config (`mshbm_dir` per dataset), but YAGNI for sub-project 1. Keep as CLI arg; pass `--mshbm-dir` explicitly at submit time.
