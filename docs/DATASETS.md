# Datasets — network_grant precision fMRI

**Last updated:** 2026-07-01 · **Purpose of this doc:** a high-level orientation to the
datasets for someone (or an LLM session) planning analyses — especially **precision /
individualized functional mapping** in the tradition of Gordon & Laumann (MSC),
Gratton, and Braga & Buckner (dense within-individual sampling).

All descriptive numbers below are **computed from the actual BIDS** (post dummy-scan
trimming) via `scripts`-style scans, not estimated. TR = **1.49 s**; every functional
run is **multi-echo (3 echoes)**.

---

## 1. What this dataset is, in one paragraph

A **deeply-sampled, multi-session, multi-echo** task+rest fMRI dataset built for
**within-individual precision functional mapping**. Each participant was scanned across
**~12 sessions on separate days**, yielding **~8 hours (~480 min) of BOLD per subject** —
roughly **~40 min resting-state** plus **~440 min task** spanning an **8-task cognitive-
control battery** (plus 10 harder "dual-task" combinations in a subset). The design
favors *many short runs distributed across many days* over a few long runs, capturing
day-to-day state variation while accumulating enough data for reliable single-subject
network estimation. Data are organized into three cohorts: **discovery** (5, the
deep-dive pilot), **validation** (41, the replication cohort), and **excluded** (11,
incomplete/withdrawn — retained as BIDS only, not analyzed).

---

## 2. Cohorts at a glance

| Cohort | Subjects | Sessions (total) | Sessions/subj | Scans¹ | Rest min/subj | Task min/subj | Total BOLD min/subj |
|---|--:|--:|--:|--:|--:|--:|--:|
| **discovery** | 5 | 60 | 12 (all) | 294 | **46.0** (45.9–46.4) | **441** (429–466) | **487** (475–512) |
| **validation** | 41 | 497 | 12.1 (12–13) | 2,312 | **39.1** (31.8–46.5) | **440** (432–457) | **479** (469–504) |
| **excluded** | 11 | 31 | 2.8 (1–12) | 139 | 9.9 (0–40.5) | 93.8 (26–330) | 103.8 (26–370) |

¹ One "scan" = one `(subject, session, task, run)`; each is 3 echoes. Numbers are the
raw BIDS inventory (before `.bidsignore` filtering; see §6).

**Scale:** discovery ≈ 2,436 BOLD-min (~41 h); **validation ≈ 19,644 BOLD-min (~327 h)**;
excluded ≈ 1,141 min. Analysis cohorts (discovery + validation) = **46 subjects, 557
sessions, ~2,600 multi-echo runs, ~370 h of fMRI.**

The **excluded** cohort is heterogeneous by design (participants who withdrew, had
lens/ear issues, or were dropped for reliability/behavioral reasons) — hence 1–12
sessions and much less data per subject. It is provided as BIDS for completeness but is
**not** part of any analysis.

---

## 3. Cognitive task battery

A response-inhibition / cognitive-control / working-memory battery (RDoC-style),
one paradigm per run. Per-run durations are intrinsic to each task's trial structure.

### Base tasks (8) — one task per run

| Task | Cognitive domain | disc runs (min/run) | val runs (min/run) |
|---|---|--:|--:|
| **cuedTS** | Cued task-switching (cognitive flexibility) | 25 (8.1) | 206 (8.1) |
| **directedForgetting** | Memory suppression / directed forgetting | 26 (9.7) | 207 (10.0) |
| **flanker** | Eriksen flanker — response/attention conflict | 25 (5.9) | 208 (5.9) |
| **goNogo** | Go/No-Go — prepotent response inhibition | 26 (8.4) | 204 (9.4) |
| **nBack** | N-back — working memory load | 26 (12.2) | 206 (12.4) |
| **shapeMatching** | Shape matching — visual discrimination | 25 (8.0) | 204 (8.1) |
| **spatialTS** | Spatial task-switching (flexibility) | 25 (7.8) | 205 (8.1) |
| **stopSignal** | Stop-signal — action cancellation | 25 (11.5) | 208 (9.9) |

Each base task is sampled **~5×/subject** (≈ one run per session per task in most
sessions) — the repeated within-subject sampling that makes reliable single-subject
task contrasts possible.

### Dual tasks (10) — two concurrent paradigms per run

Harder "dual-task interference" runs combining two base paradigms. Sampled **much more
sparsely** and unevenly across the cohort:

- **Well-sampled** (validation): `stopSignalWDirectedForgetting` (83 runs, 17.6 min/run),
  `stopSignalWFlanker` (83, 9.0), `spatialTSWCuedTS` (56, 12.2).
- **Sparse** (2–6 runs each): `directedForgettingWFlanker`, `directedForgettingWCuedTS`,
  `flankerWShapeMatching`, `cuedTSWFlanker`, `shapeMatchingWCuedTS`,
  `nBackWShapeMatching`, `nBackWSpatialTS`, `spatialTSWShapeMatching`.

> **⚠️ Analysis caveat:** dual-task first-/second-level modeling is **not yet
> implemented** — the 10 dual-task GLM configs are placeholders. All committed
> first-/second-level results are **base-tasks-only**. Dual-task BOLD + events are
> present in BIDS and can be modeled once contrast configs are authored.

### Rest

- **discovery:** 12 rest runs/subject (one per session), ~3.8 min/run → **~46 min/subject**.
- **validation:** ~10 rest runs/subject (9–12), ~3.9 min/run → **~39 min/subject** (31.8–46.5).

Rest is **short-run but distributed across all ~12 sessions** — a deliberately
"day-sampled" resting-state design rather than a single long rest scan.

---

## 4. Per-subject data budget (the precision-mapping numbers)

For within-individual (N-of-1) analyses, the quantities that matter most:

| Quantity | discovery | validation |
|---|--:|--:|
| Sessions (days) per subject | 12 | 12–13 |
| **Resting-state min/subject** | **46** (45.9–46.4) | **39** (31.8–46.5) |
| Rest runs/subject | 12 | 9–12 |
| **Task min/subject** | **441** | **440** |
| Task runs/subject | ~47 | ~46 |
| **Total BOLD min/subject** | **487** (~8.1 h) | **479** (~8.0 h) |

Interpretation for precision FC:
- **Rest reliability.** ~40–46 min of rest per subject *distributed over ~12 days*
  meets/exceeds common single-subject RSFC-reliability thresholds (Gordon/Laumann/
  Gratton report individual networks stabilizing by ~30–40+ min, with day-to-day
  sampling reducing state-specific bias). Rest here is spread across sessions, so it
  captures cross-day variability rather than one day's state.
- **Task data is abundant** (~440 min/subject) — enabling (a) reliable single-subject
  task-activation maps, and (b) **task-general** network estimation and **task-vs-rest
  network stability** analyses (à la Gratton 2018), and (c) using task residuals as
  additional "pseudo-rest" for FC (a common precision-mapping trick to boost usable
  minutes).

---

## 5. Acquisition & preprocessing

- **Sequence:** multi-echo EPI, **3 echoes** per run (100% of runs — enables ME-ICA /
  tedana-style denoising, improved tSNR, and dropout recovery — valuable for precision
  reliability). Full echo times / voxel size / scanner params are in the BIDS sidecar
  JSONs (`*_bold.json`).
- **TR:** 1.49 s.
- **Dummy scans:** the first **7 volumes** are trimmed post-conversion
  (`NumberOfVolumesDiscardedByUser: 7` in each sidecar); event onsets are shifted by
  7 × 1.49 = **10.43 s** accordingly. fMRIPrep is therefore run with `--dummy-scans 0`.
- **Preprocessing:** **fMRIPrep 25.2.4**, output spaces include volumetric
  (MNI152NLin2009cAsym, MNI152NLin6Asym), **surface (fsnative, fsaverage, fsLR/CIFTI
  91k)**, and native `func`/`T1w`. Confounds (FD, DVARS, aCompCor, motion params) are
  the basis for motion QC.
- **Surface analysis stream:** first-level GLMs are computed on the **fsaverage6**
  surface (`derivatives/lev1_surface`), and second-level uses a surface sign-flip
  permutation — i.e. the analysis is **cortical-surface based**, aligning with modern
  precision-mapping / individualized-parcellation pipelines (MSHBM, template matching).
- **Post-processing available:** XCP-D (`derivatives/xcp_d_26.0.2`) for denoised
  timeseries / connectivity.

---

## 6. Exclusions & QC (what is analysis-ready)

Not every collected scan enters analysis. A single **compiled exclusion lockfile** per
cohort (`data/exclusions/<cohort>_lock.json`, rendered to each dataset's `.bidsignore`
and `EXCLUSIONS.md`) is the authority, built from five sources:

| Source | What it flags | discovery | validation |
|---|---|--:|--:|
| `collection` | Data-collection issues (aborted/3D-only scans, missing behavioral, protocol) | 16 | 15 |
| `behavioral-qc` | Behavioral performance / non-monotonic-onset failures | 3 | 8 |
| `qa_decisions` | Human lev1-QA junk-trial-rate decisions | 3 | 10 |
| `motion` | FD/DVARS thresholds (rest: mean-FD>0.2 / prop-std_dvars>1.5; task: prop-FD>0.5 / prop-std_dvars>1.5) | 0 | 10 |
| `lev1_outlier` | Per-contrast VIF / design outliers (drops one contrast's contribution) | 22 | 97 |
| **Total entries** | | **44** | **142** |

Enforcement is **key-based** (`sub_ses_task-run`), applied at first-level; `.bidsignore`
is the rendered human-readable view. Scans flagged `exclude`/`trim` are dropped whole;
`exclude-contrast` drops only that contrast's contribution to fixed-effects (below the
`min_runs=2` floor a subject/task/contrast is dropped from group analysis).

---

## 7. Layout & access

- **Canonical (Oak, backed-up, version-controlled):**
  `/oak/stanford/groups/russpold/data/network_grant/bids/{discovery,validation,excluded}`
  — git-annex datasets; raw BIDS annexed + committed; derivatives (`derivatives/`) are
  plain files (regenerable, git-ignored).
- **In-scanner behavioral** (source for events): each dataset's
  `sourcedata/in_scanner_behavior/sub-*/ses-*/beh/*.csv`.
- **Events:** `sub-*/ses-*/func/*_events.tsv` (onsets already dummy-scan-adjusted).
- **BIDS entities:** `sub-<id>_ses-<NN>_task-<task>[_run-<n>]_echo-<1|2|3>_bold.nii.gz`.
  Sessions are numbered by ascending acquisition date; a handful of validation subjects
  (s321, s1445, s1326, s1391, s1258) have a +1 session-offset handled in curation.
- **Reproducibility:** each dataset reproduces from a frozen Flywheel inventory snapshot
  + committed manifests/lockfiles through first-/second-level exclusion selection
  (machine-checked by a reproduction harness).

---

## 8. Notes for precision-functional-mapping analyses

- **N-of-1 feasibility:** with ~8 h of BOLD across ~12 days per subject, each subject in
  discovery/validation is individually analyzable (individualized parcellation,
  single-subject task maps, within-subject FC reliability). This is an MSC-scale design
  applied to 46 analyzable subjects.
- **Prefer surface + fsLR/CIFTI** outputs for individualized cortical work; a rest-based
  MSHBM/individual-parcellation stream already exists in this project.
- **Boost usable FC minutes** by concatenating rest + task-residual timeseries
  (task GLM residuals are produced by the surface lev1 stream) — pushing effective
  per-subject minutes well above the ~40 min rest alone.
- **Multi-echo** enables tedana/ME denoising — recommended before FC to improve
  single-subject reliability (a known lever in precision mapping).
- **Day-to-day sampling** (rest + tasks spread over ~12 sessions) supports analyses of
  network *stability vs. state* (Gratton) and reduces single-session state bias.
- **Cohort strategy:** treat **discovery (n=5)** as the deep pilot for method
  development / parameter choices, and **validation (n=41)** as the pre-registered
  replication cohort — do not tune on validation.
- **Dual tasks** are collected but unmodeled (see §3 caveat) — a ready avenue for
  dual-task-interference / network-reconfiguration work once GLM configs are authored.
