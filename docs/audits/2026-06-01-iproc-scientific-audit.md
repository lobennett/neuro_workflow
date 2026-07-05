# iProc Fork↔Upstream Scientific Audit

**Repo:** `/scratch/users/logben/iProc` | **Fork:** `HEAD` (lobennett/iProc, branch `container-and-bids-tooling`) | **Fork-point:** `0ae6246` | **Upstream:** `upstream/main` (harvard-nrg/iProc)
**Mode:** strictly read-only. No working-tree or git-state mutations performed.

---

## 1. VERDICT

**The fork is scientifically faithful in every numerical/algorithmic respect that has been verified, but it is NOT a clean superset of upstream: it is missing one entire upstream feature family — fieldmap-optional processing (`PREPTOOL='none'` / `NOFM`) — that upstream introduced after the fork point.**

Bottom line, split three ways:

1. **Core science is frozen and faithful.** Every denoising/registration parameter that matters scientifically is byte-identical or provably equivalent across base/fork/upstream: tedana (`fittype=curvefit`, `tedpca=kic`, `gscontrol=None`, echo-time extraction), the 0.01–0.1 Hz bandpass, 36P nuisance construction, `3dTproject -ort` invocations, surface projection (`mri_vol2surf --projfrac 0.5 --interp trilinear --trgsubject fsaverage6`), motion-correction args, and the CSF/WM/WB mask atlas files (MD5-identical). Verdicts `BANDPASS-01`, `NUISANCE-01`, `3dTPROJ-01`, `MASK-01`, `V3` all **refuted the claimed divergence** (= confirmed equivalent).

2. **The fork's own changes are justified.** The fork's divergences from the fork-point are all defensible: container/FSL-5.0.10 workarounds, BIDS orientation handling, BIDS ingestion tooling, and one genuinely important correctness fix (per-scan `NUMVOL` via `fslnvols`/MAT-file enumeration for variable-length runs) that upstream *lacks*.

3. **The one real faithfulness gap is a capability gap, not a corruption.** The fork cannot run with `PREPTOOL='none'` (no-fieldmap workflows). It will crash, not silently mis-compute. For the current GE-fieldmap discovery/validation cohort (which always has fieldmaps), this is latent, not active. Verdicts `DIV-001`, `DIV-005`, `DIV-006`, `TV-4`, `VERIFY-1`, `FIELDMAP_CONDITIONAL` all stand (**not refuted**) — these are REAL divergences.

Net: **faithful for the data it is currently running on; missing an upstream feature it would need to process fieldmap-less studies.**

---

## 2. DIRECTION-1 — What the fork changed (grouped by unit)

Severity = scientific impact. Verify-verdict "stands" = real divergence; "refuted" = disproven (equivalent).

### Unit: bids_ingest / steps_core (BIDS-to-iProc pathway)
| File | Change | Class | Sev | Verify | Rec | patch_hint |
|---|---|---|---|---|---|---|
| `bids_setup/bids_discover.py` | New 528-line BIDS discovery → YAML manifest | infrastructure | high | n/a (new file) | keep-justified | — |
| `bids_setup/bids_generate.py` | New 468-line manifest→config/CSV/cfg generator + JSON sidecar patching | infrastructure | high | n/a | keep-justified | — |
| `iproc/steps.py` `anat_from_bids()` | glob-based T1w resolution (handles `acq-`) | infrastructure | low | n/a | keep-justified | none |
| `iproc/steps.py` `func_from_bids()` | case-insensitive task glob+filter (`REST`↔`rest`) | infrastructure | low | `DIV-003` refuted (BIDS `_` separator guarantees uniqueness) | keep-justified | none |
| `iproc/steps.py` `prepare_fieldmaps_topup()` | str→list coercion for fmapm/fmapp | infrastructure | low | n/a | keep-justified | none |
| `iproc/steps.py` `calculate_nuisance_params()` | `codedir` expanduser (l.1652) | infrastructure | none | n/a | keep-justified | none |
| `runscript/func_from_bids.py` | dual-path: realpath for FSL (git-annex), original path for JSON lookup | sci-equivalent | medium | `JSON_SIDECAR_LOOKUP_GIT_ANNEX` stands as a *needed fix*; `INTENSITY_FLOAT32`,`VOLUME_TRIMMING_UNIFORM`,`RAS_ORIENTATION` refuted (equivalent) | keep-justified | none |
| `runscript/anat_from_bids.py` | realpath/expanduser for git-annex | sci-equivalent | low | converged w/ upstream | keep-justified | none |
| `iproc/bids/__init__.py` | `re.sub(r'\.json$',…)` (vs `rstrip`); conditional anat-error; flexible anat regex | sci-equivalent | low | refuted (equivalent/safer) | keep-justified | none |
| `iproc/bids/__init__.py` | **fieldmap processing unconditional; no `preptool` param** | possible-divergence | **high** | `FIELDMAP_CONDITIONAL` **stands** | revert-toward-upstream | add `preptool` arg to `match_scan_no_to_bids(...)`; wrap fmap blocks (l.62–87, 159–177) in `if preptool and preptool!='none':` |
| `runscript/recon_all.sh` | `rsync --remove-source-files`→`mv` (container lacks rsync) | infrastructure | low | n/a | keep-justified | none |

### Unit: fieldmap (GE vendor adaptation)
| File | Change | Class | Sev | Verify | Rec | patch_hint |
|---|---|---|---|---|---|---|
| `runscript/fmap_from_bids.py` | read `EchoTimeDifference`/`Manufacturer` from JSON; detect GE/SIEMENS/PHILIPS | sci-equivalent | high | `verify-1` stands (real, correct fix); `verify-3` stands (×1000 s→ms correct) | keep-justified | none |
| `runscript/fmap_from_bids.py` | GE path: skip `fsl_prepare_fieldmap`, `fslmaths -mul 6.283185 -mas` (Hz→rad/s) | possible-divergence | high | `verify-1` stands (math correct: 2π); `verify-2` refuted (mask already binary) | keep-justified | none |
| `runscript/fmap_from_bids.py` | **PHILIPS routed through GE Hz→rad/s path** | possible-divergence | high | `verify-8` **stands** — scientifically WRONG for Philips phase-diff data | revert-toward-upstream (partial) | route PHILIPS through `fsl_prepare_fieldmap` (phase-difference), not the Hz conversion |
| `runscript/fmap_from_bids.py` | drop `iproc.commons`; inline `run()`; save `orig_fmapp_inputs` before `merge()` | infrastructure | low–med | `verify-6` refuted (1 phasediff per BIDS; break-on-first correct) | keep-justified | none |
| `runscript/fmap_from_bids.py` | remove `module load fsl/4.0.3-ncf` | infrastructure | low | container manages FSL | keep-justified | none |
| `runscript/fm_unw.sh` | dim check hard-fail→warning (GE fmap≠BOLD in-plane res) | sci-equivalent | high | `verify-4` stands but FLIRT resamples; **synced with upstream `2f9278a`** | keep-justified | none |
| `runscript/fmap_from_bids_topup.sh` | `ln -s`→`ln -sf` for `--overwrite` | infrastructure | low | matches upstream | keep-justified | none |
| `runscript/fmap_from_bids_topup.sh` | **MISSING upstream `realpath()` on AP/PA NIfTI** | possible-divergence | medium | `verify-5` refuted (paths absolute in practice; harmless) | revert-toward-upstream (defensive) | add `AP_BIDS_NIFTI=$(realpath …)` / `PA_BIDS_NIFTI=$(realpath …)` before symlink |
| `runscript/fmap_topup_prep.sh` | **MISSING upstream module/FSLDIR fallback** | infrastructure | medium | `verify-7` refuted (container shim always satisfies `module load`) | revert-toward-upstream (portability) | adopt upstream `if module load … elif [ -n "$FSLDIR" ] … else error` block |

### Unit: registration / masks (T1→MNI warp, midvol target)
| File | Change | Class | Sev | Verify | Rec | patch_hint |
|---|---|---|---|---|---|---|
| `runscript/compute_T1_MNI_warp.sh` | drop `fslswapdim x -z y`→`cp` (RAS+ post-reorient2std) | possible-divergence | high | `verify-001` stands (upstream crashes on BIDS data; fork correct) | keep-justified | data-orientation dependent; coordinate if input convention changes |
| `runscript/compute_T1_MNI_warp.sh` | FLIRT search ±180°→±30° | sci-equivalent | medium | `T1-search-range` stands; s10 matrix rotations all well-behaved (<11°) | keep-justified | valid for pre-oriented T1s |
| `runscript/compute_T1_MNI_warp.sh` | hex-float→decimal `.mat` post-processing (FSL 5.0.10 bug) | infrastructure | high | `T1-hex-float` stands (real bug, upstream lacks fix) | keep-justified | retain until FSL upgraded |
| `runscript/compute_T1_MNI_warp.sh` | restore FNIRT `--config=T1_2_MNI152_2mm` | sci-equivalent | medium | `T1-fnirt-config` stands (prevents SingularException; upstream lacks) | keep-justified | standard FSL T1→MNI config |
| `container/flirt_wrapper.sh` | New: wrap FSL 5.0.10 flirt, hex→decimal `-omat` | sci-equivalent | none | `V1,V3,V4,V5,V6,V7` refuted/stand-as-needed-fix; ~1e-11 err ≪ voxel | keep-justified | none |
| `container/convert_xfm_wrapper.sh` | New: same for convert_xfm | sci-equivalent | none | same | keep-justified | none |
| `runscript/create_upsampled_midvol_target.sh` | `fslcreatehd`+`flirt -applyxfm`→`flirt -applyisoxfm` | sci-equivalent | low | `midvol-dims` stands (fork ≠ upstream's applyisoxfm; fork still uses fixed-dim base approach) | see Overlap §4 | — |
| `bids_setup/bids_generate.py` | `MASKSDIR=${iproc:codedir}/mni_masks` | infrastructure | high | `verify-003` refuted (correct path, MD5-identical masks) | keep-justified | none |

### Unit: mc_midvol / numvol_cfg (variable-length NUMVOL fix) — the standout fork contribution
| File | Change | Class | Sev | Verify | Rec | patch_hint |
|---|---|---|---|---|---|---|
| `runscript/fm_unwarp_and_mc_to_midvol.sh` | `NUMVOL=$(fslnvols ${MC_IN})` overrides cfg arg-7 | sci-equivalent | high | `TV-1,TV-2,TV-3,verify-fslnvols-reassign` all **stand** (real correctness fix; no-op for fixed-length) | keep-justified | none |
| `iProc_p4_sbatch_combined.py` | volnums from actual `MAT_\d{4}` files vs `range(numvol)` | sci-equivalent | high | `verify-volnums-logic`,`verify-output-names-compat`,`verify-fixed-length-no-op` refuted (equiv for fixed); `verify-variable-length-correctness` stands | keep-justified | none |
| `iProc_p4_sbatch_combined_ME.py` | same MAT-file enumeration | sci-equivalent | low | `V1` stands (backward-compatible) | keep-justified | none |

### Unit: combine_warp / tedana_me — missing PREPTOOL plumbing
| File | Change | Class | Sev | Verify | Rec | patch_hint |
|---|---|---|---|---|---|---|
| `runscript/combine_warps_parallel.sbatch` & `_ME.sbatch` | `rsync --remove-source-files`→`mv`+`rmdir` | infrastructure | low | spotcheck PASS (file-identity rename) | keep-justified | none |
| `runscript/combine_warps_parallel*.sbatch` | **MISSING upstream `PREPTOOL` param shift** | infrastructure | — | `DIV-002` refuted (PREPTOOL metadata-only in scripts; fork self-consistent), `VERIFY-1` stands (real, intentional omission) | tied to fieldmap-optional backport | — |
| `iProc_p4_sbatch_combined_ME.py` | **MISSING `--preptool` arg + 3 `_noFM` functions + dispatch** | possible-divergence | high | `V2,V5` stand (fork cannot run `preptool=none`) | revert-toward-upstream | add `--preptool` arg; add `convert_warpcall_MNI_noFM`, `convert_warpcall_anat_noFM`, `apply_warpcall_anat_noFM` (upstream `bca044b`); add `if preptool=='none':` dispatch |
| `iProc_p4_sbatch_combined_ME.py` | mode 644→755 | infrastructure | none | — | keep-justified | none |
| `run_tedana.py` | (no change) | faithful | none | `V3,V4` refuted | — | — |

### Unit: fs6 surface projection / nuisance_bandpass — fully faithful
| File | Change | Class | Verify |
|---|---|---|---|
| `runscript/fs6_project_to_surf.sh` | loop refactor + `parallel` fallback (cherry-pick of upstream `a89b3b6`) | infrastructure / **byte-identical to upstream** |
| `runscript/calculate_nuisance_params.sh` | `IPROC_SRUN`→`command -v parallel` | infrastructure / **identical to upstream** (both diverged same way) |
| `nuisance_regress.sbatch`, `bandpass.sbatch`, `bandpass_ME.sbatch`, `wholebrain_only_regress.sh` | no change | faithful |

---

## 3. DIRECTION-2 — Upstream fixes the fork LACKS

| File | Upstream change | Scientific relevance | Backport |
|---|---|---|---|
| `iproc/steps.py` `fm_unwarp_and_mc_to_midvol()` | `PREPTOOL='none'`/`nofm` branch: dummy `fm_bold_no='000'`, `fm_task_type='FOO'`, conditional EF_UD warp, conditional sidecar read, pass `nofm_str` as param 21 (`bca044b`) | **Critical capability.** Without it the fork crashes (KeyError on `FIRST_FMAP`/`FMAP_DIR`; sidecar read failure; arg-count mismatch) on any no-fieldmap run. `DIV-001`,`DIV-005` stand. | **yes** (if no-fieldmap studies are in scope) |
| `iproc/steps.py` `prepare_fieldmaps()` / `xnat_to_nii_gz_fieldmap()` | `elif preptool=='none':` notice + `if preptool!='none':` guard around fmap loop | Prevents fieldmap iteration when none configured. `DIV-006` stands. | yes (with above) |
| `iproc/csvHandler/__init__.py` | `preptool` threaded into `ingest_bold_csv`/`append_scan`; conditional fmap check | Fieldmap-optional manifest ingestion | yes (with above) |
| `iProc_p4_sbatch_combined.py` & `_ME.py` | `--preptool` arg + `*_noFM` warp functions + dispatch (`bca044b`) | Enables linear-only (convert_xfm/flirt) warp composition when no fieldmap. `V2`,`V5`,`VERIFY-1` stand. | yes (with above) |
| `runscript/combine_warps_parallel*.sbatch` | `PREPTOOL` param shift | Plumbing for the above (metadata-only in script per `DIV-002`) | yes (with above) |
| `runscript/fmap_from_bids_topup.sh` | `realpath()` on AP/PA NIfTI | Defensive; harmless today (`verify-5` refuted) but good robustness | maybe |
| `runscript/fmap_topup_prep.sh` | module-load → FSLDIR fallback | Portability outside container/Lmod; harmless today (`verify-7` refuted) | maybe |
| `run_tedana.py`, bandpass/nuisance/fs6 scripts | — | No upstream-only science the fork lacks | — |

> Note: the fork's **`fslnvols`/MAT-file NUMVOL fix is the inverse** — upstream lacks it (Direction-2 in the other direction). It is a real correctness improvement the fork holds and upstream should backport.

---

## 4. OVERLAP RECONCILIATION (files changed in both directions)

| File | fork ≡ upstream? | Reconciliation |
|---|---|---|
| `runscript/fs6_project_to_surf.sh` | **YES** (hash `5237970`) | Fork cherry-picked upstream `a89b3b6`/`0a72331`; byte-identical. |
| `runscript/fs6_project_to_surf_ME.sh` | YES | Unchanged in both; base version current. |
| `runscript/calculate_nuisance_params.sh` | **YES** | Both replaced `IPROC_SRUN` with `command -v parallel`, identically. |
| `runscript/fm_unw.sh` | **YES** | Both carry the dim-check→warning (upstream `2f9278a`). Fully synced. |
| `runscript/anat_from_bids.py` | YES (l.29) | Converged on `realpath(expanduser())` for git-annex. |
| `runscript/create_upsampled_midvol_target.sh` | **NO** | Fork still uses base `fslcreatehd`+`flirt -applyxfm` (fixed 176×176×130 / 106×106×78); upstream evolved to `flirt -applyisoxfm`. `midvol-dims` **stands**: both yield correct isotropic spacing (1.2/2 mm) but upstream adapts FOV, fork hard-codes dims. Low severity; harmonize toward upstream's `-applyisoxfm` for FOV robustness. |
| `runscript/compute_T1_MNI_warp.sh` | NO | Fork applies 4 BIDS/FSL-5.0.10 fixes upstream lacks; upstream would crash on this fork's data. Not interchangeable — both directions legitimate, no reconciliation needed beyond awareness. |
| `runscript/func_from_bids.py` | NO | Fork adds dual-path JSON/realpath handling beyond upstream's single realpath. Fork superset; needed fix. |
| `iproc/bids/__init__.py` | NO | Fork has safer regex/anat handling AND the missing `preptool` gating. Mixed: keep fork's regex fixes, backport upstream's preptool gating. |
| `iProc_p4_sbatch_combined.py` / `_ME.py` | NO | Fork has NUMVOL fix (upstream lacks); upstream has `--preptool`/`_noFM` (fork lacks). **Non-overlapping** — a clean merge would union both. |
| `iproc/csvHandler/__init__.py` | NO | Upstream-only `preptool` work; fork untouched. |

---

## 5. EMPIRICAL SPOT-CHECK RESULTS

- **NUMVOL (real s10 FLANKER_009):** cfg NUMVOL=234 (`tasktype_consolidated.csv`) but actual scan = **253 volumes** (`MAT_0000…MAT_0252`; `.par` = 253 rows). Confirms the fork's `fslnvols`/MAT-file fix is load-bearing: upstream/base would cap at 234 → `applywarp` fails on vols 234–252, midvol off by 9 (117 vs correct 126), `tail -n NUMVOL` misaligns motion regressors. **VERIFIED REAL.**
- **MNI masks:** `avg152T1_ventricles_MNI.nii.gz` MD5 `3c980efcee2ed68125cd95078c264ec8`; `avg152T1_WM_MNI.nii.gz` MD5 `9a9123338a1f6de9530deed6dff36b3e`. Standard FSL AVG152, unmodified by fork; identical between fork and upstream. **PASS.**
- **Bandpass / 36P / 3dTproject:** byte-/parameter-identical across base/fork/upstream (0.01–0.1 Hz; 9→18→36 regressor construction; `-ort -input -mask -prefix`). **PASS.**
- **tedana:** `tedana_workflow(...)` textually identical (`fittype=curvefit, tedpca=kic, gscontrol=None`); echo-time JSON extraction identical and correctly ordered. **PASS.**
- **fs6 surface projection:** shell expansion produces 8 identical `mri_vol2surf … --projfrac 0.5 --regheader $SESST --trgsubject fsaverage6 --interp trilinear` lines matching base. **PASS.**
- **hex-float wrapper precision:** `float.fromhex()` + `f'{v:.10f}'` → abs err ~1e-11, ~3.8e-9% relative; ≪ 0.1 mm voxel; ~3 nm over a 10 mm translation even after 3 compositions. **PASS (scientifically negligible).**
- **T1 search-range (s10):** `mpr_brain_to_mni.mat` rotations X=−10.07°, Y=0.10°, Z=0.69° — all within ±30°; FNIRT converged. **PASS.**
- **mv vs rsync (combine_warps):** file-identity rename, structure/symlinks preserved, no content/interp change; only loss is `-v` logging. **PASS.**
- **Shell syntax (`bash -n`)** on `compute_T1_MNI_warp.sh`, `create_upsampled_midvol_target.sh` across all three versions: **PASS.**
- **Could NOT run** (FSL absent / live SLURM jobs / read-only): GE Hz→rad/s voxel-value check, unwarp visual QA, `func_from_bids` ambiguous-`acq-` selection. See §6 follow-ups.

---

## 6. MINIMAL-EDITS TARGET

**Set A — truly required to run on Sherlock (container/paths/bids-io/sbatch). Keep, all justified, all verified harmless-or-correct:**
- Container/FSL-5.0.10: `container/flirt_wrapper.sh`, `container/convert_xfm_wrapper.sh`, hex→decimal block in `compute_T1_MNI_warp.sh`.
- rsync→mv (no rsync in container): `recon_all.sh`, `combine_warps_parallel{,_ME}.sbatch`, and the uncommitted `cp -f` in `calculate_nuisance_params.sh`.
- Module/subprocess isolation: drop `iproc.commons` + `module load fsl` in `fmap_from_bids.py`; `sys.path.insert`/realpath for git-annex in `func_from_bids.py`/`anat_from_bids.py`; `ln -sf`.
- BIDS I/O: `bids_setup/bids_discover.py`, `bids_setup/bids_generate.py`, `MASKSDIR=${iproc:codedir}/mni_masks`, glob/case-insensitive task matching, safer `re.sub` JSON-suffix, flexible anat regex.

**Set B — changes that touched science (must remain explicitly justified, all verified sound):**
- `compute_T1_MNI_warp.sh`: `fslswapdim`→`cp` (RAS+ assumption), FLIRT ±180→±30, FNIRT `--config=T1_2_MNI152_2mm`. Justified for BIDS+reorient2std data; **document the RAS+ input precondition** since it is orientation-dependent.
- `fmap_from_bids.py`: JSON-driven `EchoTimeDifference`/`Manufacturer`, GE Hz→rad/s (2π). Correct and an upstream improvement.
- `fm_unw.sh` dim-check→warning (already synced with upstream).
- `fslnvols`/MAT-file NUMVOL fix — a genuine correctness fix; **recommend upstreaming**.

**Set C — required-but-not-yet-done (revert toward / backport from upstream):**
1. **Fieldmap-optional (`PREPTOOL='none'`/`NOFM`)** across `iproc/steps.py`, `iproc/bids/__init__.py`, `iproc/csvHandler/__init__.py`, `iProc_p4_sbatch_combined{,_ME}.py`, `combine_warps_parallel{,_ME}.sbatch`. **High severity, latent** (crashes only if `PREPTOOL='none'`; current GE cohort always has fieldmaps). Backport upstream `bca044b`/`c7316b5` if no-fieldmap studies are ever in scope.
2. **PHILIPS fieldmap path (real science bug, `verify-8`):** Philips phase-difference fieldmaps are currently routed through the GE Hz→rad/s branch, which is incorrect. If Philips data will ever be processed, route PHILIPS through `fsl_prepare_fieldmap` (phase-difference) instead. No Philips data in the current cohort, so latent.
3. **Defensive/portability (low priority):** `realpath()` in `fmap_from_bids_topup.sh`; module/FSLDIR fallback in `fmap_topup_prep.sh`. Both verified harmless today (container shim + absolute paths); backport only for non-container portability.
4. **Optional harmonization:** `create_upsampled_midvol_target.sh` → upstream's `flirt -applyisoxfm` for FOV-adaptive dims (fork's fixed-dim approach is correct for current acquisitions).

**Recommended follow-up empirical checks (could not run, read-only/FSL-absent):** sample GE fieldmap voxel values pre/post Hz→rad/s; confirm no ambiguous `acq-` variants for a single task+run in the BIDS trees (else the `.count()==1` filter is ambiguous); add `echoes.sort(key=lambda e: e['echo'])` in `bids_discover.py` if any dataset has echo files that do not sort naturally.

Relevant paths: `/scratch/users/logben/iProc/iproc/steps.py`, `/scratch/users/logben/iProc/iproc/bids/__init__.py`, `/scratch/users/logben/iProc/iProc_p4_sbatch_combined_ME.py`, `/scratch/users/logben/iProc/runscript/fmap_from_bids.py`, `/scratch/users/logben/iProc/runscript/compute_T1_MNI_warp.sh`, `/scratch/users/logben/iProc/runscript/fm_unwarp_and_mc_to_midvol.sh`, `/scratch/users/logben/iProc/container/flirt_wrapper.sh`.
