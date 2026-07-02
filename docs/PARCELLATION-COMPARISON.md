# Parcellation comparison — Template Matching vs MSHBM

**Purpose:** describe the two individual-network cortical parcellation pipelines run on
the network_grant precision dataset, and lay out ranked hypotheses for why the
**template-matching** parcellations (Gracie Grimsrud's ReproTM pipeline) appear
qualitatively better — more territorially coherent, less "amoeba-shaped" — than our
**MSHBM** (CBIG MS-HBM / DU15NET) parcellations. Intended to be handed to a reviewer
(human or LLM) for a methods opinion.

Both pipelines run on the same discovery cohort (`s03, s10, s19, s29, s43`; ~12
sessions/subject, ~40 min rest + ~440 min task, multi-echo, TR 1.49 s) and both produce
a per-subject network label map on the cortical surface. They differ fundamentally in
method: TM is a deterministic per-vertex match to a fixed group template; MSHBM is an
iterative hierarchical Bayesian model fit per subject.

---

## Pipeline A — Template Matching (ReproTM; Gracie Grimsrud)

- **Code:** `/oak/stanford/groups/russpold/users/grimsrud/projects/pfm_compare/code/temp_match_pfm/`
  — Python fork of **ReproTM** (Kate Godfrey, *in prep*), implementing the
  **Gordon et al. 2017 (Neuron)** seed-map-to-template winner-take-all method.
- **Method (single-pass, deterministic, N=1):** for each grayordinate, take its
  whole-brain connectivity row (its seed map) and compare it to a set of group-average
  network templates. Assign the grayordinate **winner-take-all** to the most similar
  network. Similarity is **eta²** (primary) and Pearson r (alternative). No iteration,
  no per-subject model estimation, no random init — deterministic given the input.
- **Group template (the anchor):**
  `tpl-ABCC2026-a3-9to16_space-fsLR_den-91k_desc-seedmap_stat-zscored.mat` — a z-scored
  group-average seed-map matrix (grayordinates × networks), **15 networks + SCAN**, built
  from the **ABCD-BIDS Community Collection (ages 9–16)** via FD<0.2, ≥10 min/subject,
  Fisher-z aggregation. ⚠️ **Pediatric template applied to adult subjects** (domain
  mismatch — flag this).
- **Inputs:** dense connectomes (`.dconn.nii`) in **fsLR den-91k** (91,282 grayordinates),
  built from **XCP-D 26.0.2** `desc-denoised` dtseries. Chain:
  fMRIPrep 25.2.4/5 → XCP-D → `make_dconn.py` → z-score → ReproTM. Run per condition:
  **rest / task / all / per-individual-task**, all runs concatenated (`ses-concatenated`,
  XCP-D `--combine-runs`).
- **Denoising:**
  - Upstream XCP-D `--mode abcd`, `--despike`, `--fd-thresh 0.3`, respiratory notch motion
    filter (12–20), **no spatial smoothing**, default ABCD bandpass, `--combine-runs`.
  - In `make_dconn.py`: a second **FD<0.2 mm** frame-censoring pass, require **≥100 good
    frames**, then `wb_command -cifti-correlation` → dconn.
  - **Region-wise dconn z-scoring** (Hermosillo et al. 2024): the connectome is split into
    9 cortex/subcortex blocks, each z-scored separately, matching the z-scored template
    range.
- **Cleanup:** min-cluster-size 30 (clusters <30 grayordinates dissolved, vertices
  reassigned to border-neighbor mode) + optional SCAN-network refinement.
- **Output:** `*_ReproTM_template-ABCC2026-a3-9to16_minsize-30.dlabel.nii` (CIFTI,
  fsLR 91k), 5 discovery subjects × {rest, task, all} + 8 per-task variants, under
  `/oak/.../derivatives/analysis/temp_match_results/`.

---

## Pipeline B — MSHBM (CBIG MS-HBM / DU15NET; our pipeline)

- **Code:** Python wrappers in `src/neuro_workflow/analysis/mshbm/` driving MATLAB in
  `external/PrecisionNetworkMapping` (fork of the Du/Buckner "PrecisionNetworkMapping");
  core CBIG EM lives in an external CBIG_CODE clone
  (`~/network_glm/PrecisionNetworkMapping`). Implements **Kong et al. 2019 Multi-Session
  Hierarchical Bayesian Model**, in the **Du et al. 2024/2025** precision configuration.
- **Method (iterative generative model, hierarchical):** a two-level Bayesian mixture —
  group → subject → session latent parameters — fit by **EM** (`conv_th=1e-5`,
  `max_iter=100`). Each session's vertex×ROI connectivity **profile is binarized to the
  top ~10%** of correlations; the model estimates inter-session and inter-subject variance
  components and produces a per-subject **15-network** parcellation. **Data-hungry and
  denoising-sensitive** — it estimates variance components from the data itself.
- **Group prior (the anchor):** `MSHBM_prior_15.mat` — the **DU15NET** 15-network prior
  (`lh_labels_fs6`/`rh_labels_fs6`) from Du et al. 2024's separate 15-subject Harvard
  sample. The pipeline **skips group-prior estimation** and borrows this external prior
  directly — there is **no group model estimated from the Stanford cohort** to regularize
  toward local consistency.
- **Inputs:** **fsaverage6** surfaces (profiles targeted to fsaverage3 = 642 ROIs).
  Adapters: `from_iproc.py` (iProc/tedana), `from_fmriprep.py` (in-repo Du-2025
  18-regressor denoise), `from_xcpd.py` (XCP-D denoised → resampled to fsaverage6, 2 mm
  smooth). `--rest-only` is **opt-in, not default**; preferred comparison arms use full
  task+rest.
- **Denoising (in-repo, `mshbm/preproc.py`):** confound regression (31-regressor set
  excluding GSR, or Du-2025 18-regressor set with GSR), Butterworth bandpass
  (0.009–0.08 or 0.01–0.10 Hz depending on driver), FD/DVARS censoring with
  **interpolation** of bad frames (not deletion), surface smoothing 0 mm (prep path) or
  2 mm (XCP-D/comparison arms).
- **Session grouping:** `MSHBM_GROUP_BY_SESSION` — default `0` treats **each short run as
  its own "session"** (noisy binarized profiles); `=1` averages all runs in a recording
  day before binarization (much less profile noise).
- **Output:** `<sub>_MSHBM.dlabel.nii` (CIFTI, fsaverage6), 15 networks. N=5 discovery run
  + several N=1 (s10) comparison arms + a pooled-46 run, under
  `/scratch/users/logben/mshbm_*`.
- **Documented quality problems already found in our runs:**
  1. **EM under-convergence:** `max_iter` was historically **5** (copied from CBIG's
     2-subject toy example) — "capped training at 10% of the iterations needed for the EM
     posterior to converge, leaving MSHBM with amoeba-shaped, territorially-incoherent
     network assignments." Fixed 5→50→100, but early on-disk outputs are under-converged.
  2. **Wrong input timeseries:** earlier runs fed **lev1 task residuals** rather than
     FC-preprocessed data — weaker denoising than XCP-D's 36P+despike+censor+bandpass.
  3. **Confounded earlier comparison:** the poor iProc-MSHBM result "conflated pipeline
     **and** data-scope (rest-only) **and** FreeSurfer version (6.0 vs 7.3.2)."

---

## Head-to-head

| | Template Matching (ReproTM) | MSHBM |
|---|---|---|
| Method | Per-vertex seed-map → group-template, **winner-take-all** | Hierarchical Bayesian **EM** mixture model |
| Estimation | **None** (deterministic, single pass) | Iterative EM, estimates variance components |
| N=1 robustness | **High** — group template fully anchors labels | **Low** — sparse data destabilizes the fit |
| Group anchor | ABCC-2026 pediatric seed-map template (15+SCAN) | DU15NET borrowed prior (15); **no local group** |
| Space | fsLR den-91k (whole-brain) | fsaverage6 (cortex) |
| Denoising | XCP-D 36P/abcd + FD<0.2 + region-wise z-score | in-repo 18–31 regressors + bandpass + interpolation |
| Profile step | Full connectivity row, continuous eta² | **Top-10% binarized** profile per session |
| Known failure modes here | pediatric-template domain mismatch | under-converged EM, residual-input, single-run "sessions" |

---

## Ranked hypotheses — why template matching is winning

1. **No fragile estimation on N=1 data.** Template matching is a deterministic argmax
   against a fixed group template — it cannot under-converge or produce degenerate
   variance estimates. MSHBM must fit a hierarchical model per subject; with one subject
   and short rest, its inter-session/inter-subject variance terms are ill-posed and the
   parcellation is unstable. This is the single biggest structural difference.
2. **MSHBM's EM was (and may still partly be) under-converged.** The documented
   `max_iter=5` bug directly produces the "amoeba-shaped, incoherent" parcels being
   observed. Any parcellation generated before the 5→100 fix is invalid; confirm which
   iteration count each on-disk MSHBM output actually used.
3. **Input-denoising asymmetry.** ReproTM consumes XCP-D's full FC-grade denoising (36P,
   despike, notch, censor, bandpass) plus a second FD<0.2 pass and region-wise z-scoring.
   Several MSHBM runs consumed weaker inputs (lev1 residuals, or fewer regressors, GSR
   present/absent inconsistently). MSHBM's profile-fitting is more sensitive to residual
   nuisance than a template argmax.
4. **Profile binarization + single-run "sessions" amplify noise in MSHBM.** Top-10%
   binarization of short single-run profiles (`GROUP_BY_SESSION=0`) discards magnitude
   information and is noisy; template matching uses the full continuous connectivity row.
   Verify whether the compared MSHBM run used session-grouping.
5. **Template matching gets a stronger, more complete anchor.** Every vertex is directly
   and fully anchored to a group template; MSHBM borrows an external prior *and skips
   local group estimation*, so it has neither strong per-subject data nor a cohort-level
   regularizer.
6. **Cleanup + resolution differences (secondary).** ReproTM applies explicit min-size-30
   topological cleanup and SCAN refinement in whole-brain fsLR 91k; MSHBM relies on its
   spatial-smoothness prior in fsaverage6. This favors ReproTM's visual coherence.

---

## Confounds to control before concluding "TM > MSHBM as methods"

- ReproTM's template is **pediatric ABCD** applied to adult subjects.
- Different surface spaces (fsLR-91k vs fsaverage6).
- Different spatial smoothing.
- Non-identical denoising and data conditions across the two runs.

A fair test holds denoising, surface space, smoothing, scan-set, and network definition
constant and compares **only the assignment algorithm** — which is what the existing
`pfm_compare` / MSHBM comparison-design docs set out to do
(`docs/superpowers/specs/2026-06-02-mshbm-pipeline-comparison-design.md`).

---

## Key paths

- **TM code:** `/oak/stanford/groups/russpold/users/grimsrud/projects/pfm_compare/code/temp_match_pfm/`
  (`run.py`, `ReproTM/ReproTM_v1.0.0.py`, `make_dconn/make_dconn.py`,
  `zscore_dconn/`, `minsize/`, `dscalar2dlabel/`, `seed_map_generation/`)
- **TM template:** `.../ReproTM/support_files/templates/tpl-ABCC2026-a3-9to16_space-fsLR_den-91k_desc-seedmap_stat-zscored.mat`
- **TM outputs:** `/oak/.../derivatives/analysis/temp_match_results/{april_2026_fmriprep_xcpd,june_2026_discovery_tasks}/`
- **MSHBM code:** `neuro_workflow/src/neuro_workflow/analysis/mshbm/` +
  `external/PrecisionNetworkMapping/MSHBM/` (`MSHBM_wrapper.m`,
  `MSHBM_Params_Training.m`, `MSHBM_prior_15.mat`, `ColorMap_15.txt`)
- **MSHBM outputs:** `/scratch/users/logben/mshbm_training_discovery_du2025/.../ind_parcellation/sub-*/sub-*_MSHBM.dlabel.nii`
  and `/scratch/users/logben/mshbm_output_*_s10/...`
- **Comparison design docs:** `neuro_workflow/docs/superpowers/specs/2026-06-02-mshbm-pipeline-comparison-design.md`
  (+ `2026-05-08-rest-only-mshbm-design.md`, `2026-05-26-mshbm-from-xcpd-design.md`)
