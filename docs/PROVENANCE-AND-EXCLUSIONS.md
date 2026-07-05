# Provenance & Exclusions — network_grant precision fMRI

**Last updated:** 2026-07-04 · **Scope:** the full analytic path from Flywheel to
second-level models, with a detailed treatment of the exclusion framework — every
source, exactly how it is computed, how the sources compile into a per-cohort
**lockfile**, how the human-readable artifacts (`.bidsignore`, `EXCLUSIONS.md`) are
*rendered* from that lockfile, the **drift gate**, and how the whole thing is
**reproduced** end-to-end and used to certify the version-controlled Oak datasets.

This is the "understand and trust the exclusion set" reference. For orientation to the
data itself see `docs/DATASETS.md`; for copy-pasteable commands see
`docs/PIPELINE-WALKTHROUGH.md`; for per-`.bidsignore`-entry
rationale, the per-cohort catalog is *rendered* to each dataset's `EXCLUSIONS.md`; for the
run-manifest schema see [§11 below](#run-manifest-schema--clean-tree-policy).

> **Note.** This document is the single authoritative reference for the exclusion
> framework and supersedes the former `EXCLUSIONS-FLOW.md`, `EXCLUSIONS.md`
> (both removed 2026-07-04), and `PROVENANCE.md` / `WORKFLOW.md` (folded in
> 2026-07-04; see §11 and `docs/PIPELINE-WALKTHROUGH.md` respectively). It reflects the
> current code; §10 records current-vs-legacy behavior worth knowing (notably:
> `lev1_outlier` is **active** and **per-contrast**, not archived).

---

## Table of contents

1. [Overview & cohorts](#1-overview--cohorts)
2. [Stage-by-stage pipeline](#2-stage-by-stage-pipeline-flywheel--lev2)
3. [The exclusion framework](#3-the-exclusion-framework)
   - [3.1 The exclusion key & entry schema](#31-the-exclusion-key--entry-schema)
   - [3.2 collection](#32-collection)
   - [3.3 behavioral-qc](#33-behavioral-qc)
   - [3.4 qa_decisions](#34-qa_decisions)
   - [3.5 motion](#35-motion)
   - [3.6 lev1_outlier](#36-lev1_outlier)
   - [3.7 How enforcement happens at lev1/lev2](#37-how-enforcement-happens-at-lev1lev2)
4. [Compilation & provenance](#4-compilation--provenance-the-lockfile)
5. [Rendering `.bidsignore` and `EXCLUSIONS.md`](#5-rendering-bidsignore-and-exclusionsmd)
6. [The drift gate](#6-the-drift-gate)
7. [End-to-end reproduction](#7-end-to-end-reproduction)
8. [The Oak artifact](#8-the-oak-artifact)
9. [Code & file-path index](#9-code--file-path-index)
10. [Where code and existing docs disagree](#10-where-code-and-existing-docs-disagree)
11. [Run-manifest schema & clean-tree policy](#run-manifest-schema--clean-tree-policy)

---

## 1. Overview & cohorts

A deeply-sampled, multi-session, multi-echo (3-echo, TR = 1.49 s) task+rest dataset built
for within-individual precision functional mapping (~12 sessions/subject, ~8 h of BOLD).
Three cohorts are defined in `config/pipeline_config.json` under `samples`:

| Cohort | N | Role | Analyzed? |
|---|--:|---|---|
| **discovery** | 5 (`s03, s10, s19, s29, s43`) | deep-dive pilot | yes |
| **validation** | 41 | replication cohort | yes |
| **excluded** | 11 | withdrawn / incomplete | **BIDS-only, never analyzed** |

Descriptive statistics (sessions, minutes, scan counts, per-source exclusion counts) are
in `docs/DATASETS.md` §2 and §6 — not repeated here. The `excluded` cohort is a dict of
`subject → drop reason` (e.g. withdrew, lens/ear issue, unreliable); it is provided as
BIDS for completeness and has no exclusion lockfile.

The config also defines `discovery_oak` / `validation_oak` / `excluded_oak` roster keys —
identical subject lists used when the exclusion machinery is retargeted at the Oak
datasets (see §7–§8).

---

## 2. Stage-by-stage pipeline (Flywheel → lev2)

The pipeline has one **reproducible core** (raw BIDS + the compiled exclusion lockfile,
both version-controlled) and a set of **regenerable derivatives** (fMRIPrep, lev1, lev2 —
not byte-reproducible, accepted). Exclusions accrue at three points as their evidence
appears (pre-fMRIPrep, post-fMRIPrep, post-lev1).

| # | Stage | What runs | Key parameters | Inputs → Outputs |
|--:|---|---|---|---|
| 1 | **Flywheel pull (bidsify)** | `neuro-run submit bidsify <cohort>` | project `r01network`; `subject_aliases`, `skip_subjects`, `session_overrides` from `pipeline_config.json`. Does **not** trim volumes | Flywheel → BIDS NIfTI/JSON/physio + `sourcedata/reconciliation.json` |
| 2 | **Dummy-scan trim** | `scripts/trim_bold.py <bids>` | Removes first **7** volumes; writes `NumberOfVolumesDiscardedByUser: 7` to sidecar. Idempotent (sidecar check), atomic writes | `*_bold.nii.gz` → trimmed in place |
| 3 | **Behavioral reconcile / migrate** | `scripts/reconcile_sessions.py` (read-only manifest) → review → `scripts/migrate_behavioral.py` | `dest_session` remaps 5 session-offset subjects (s321, s1445, s1326, s1391, s1258); `dest_run` handles 7 multi-run cases (run-1 short/aborted, behavioral → run-2) | raw CSVs → `sourcedata/in_scanner_behavior/sub-*/ses-*/beh/*.csv` |
| 4 | **Events generation** | `neuro_workflow.events.create` | Onsets adjusted for the 7 trimmed dummy volumes; `break_with_performance_feedback` baked into TSVs; non-monotonic (backward-clock) tails truncated | behavioral CSVs → `*_events.tsv` |
| 5 | **fMRIPrep 25.2.4** | container run on the `.bidsignore`-filtered BIDS | `--dummy-scans 0` (trimming already done upstream) | BIDS → `derivatives/fmriprep_25.2.4/` (incl. `*_desc-confounds_timeseries.tsv`) |
| 6 | **lev1 surface GLM** | `neuro_workflow.analysis.lev1.run` | `--space` (surface: fsLR/CIFTI), `--exclusions-file <compiled>`, `--min-runs 2`; onsets/trim are NOT re-applied (done upstream) | fMRIPrep → per-run contrasts + per-(subject,task,contrast) **fixed-effects** in `derivatives/lev1_surface/` |
| 7 | **lev1-outlier QC** | `neuro_workflow.qa.lev1_outliers` | per-voxel cohort mean/SD → outlier %; reads per-contrast VIF CSVs lev1 emits | lev1 maps → `lev1_outliers.csv`, `lev1_flagged.tsv`, `lev1_outliers.pdf` |
| 8 | **lev2 fixed-effects / group** | `neuro_workflow.analysis.lev2.run` (+ `surface.py`) | surface: sign-flip permutation; drops `_desc-belowMinRuns_` maps | lev1 fixed-effects → group maps |

Every lev1/lev2 run writes a `run-manifest.json` (code SHA, `uv.lock` hash,
`config_version`, tool versions, and the `{path, sha256}` of the compiled exclusions it
consumed) — see [§11 below](#run-manifest-schema--clean-tree-policy).

---

## 3. The exclusion framework

The exclusion set is the **scientific ground truth** for "which scans / contrasts enter
analysis." It is **path-independent** (keyed by BIDS identity, not by any filesystem
location), version-controlled, and rendered — never hand-edited — into the artifacts
downstream tools read.

Five **generators** each read one class of evidence and emit `list[dict]` entries. They
are registered against the `ExclusionGenerator` Protocol
(`src/neuro_workflow/exclusions/base.py`) and invoked as:

```
neuro-run exclusions generate <source> <cohort> [source-specific args]
```

Sources are written to `~/.neuro_workflow/exclusions/<cohort>/sources/<source>.json`
(here `~/.neuro_workflow` = `core.config.CONFIG_DIR`), each wrapped as
`{"_meta": {...}, "entries": [...]}`. `compile_exclusions` then merges them plus committed
overrides into the compiled list and the committed lockfile (§4).

### 3.1 The exclusion key & entry schema

Every entry is a dict with required fields (`core.exclusions.REQUIRED_FIELDS`):
`subject`, `session`, `task`, `run`, `action`, `reason`. Subject/session/run carry BIDS
prefixes (`sub-s10`, `ses-05`, `run-1`); **task is stored bare** (`goNogo`). Entries also
carry `source` and optional `metrics` / `contrast`.

The **scan key** used everywhere for identity and enforcement is the 4-tuple
`(subject, session, task, run)`; its string form (`create_exclusion_key`,
`analysis/core/utils.py`) is:

```
{subject}_{session}_{task}_{run}      e.g.  sub-s10_ses-05_task-goNogo_run-1
```

`VALID_ACTIONS` (`core.exclusions`):

| Action | Meaning | Removes BOLD? | Emits `.bidsignore` glob? | Skips run at lev1? |
|---|---|:--:|:--:|:--:|
| `exclude` | scan-level drop | yes | yes | yes |
| `trim` | scan-level drop (RT-tail salvage variant) | yes | yes | yes |
| `exclude-contrast` | drop **one contrast's** fixed-effects contribution | **no** | **no** | **no** — carries a `contrast` field |
| `force-include` | override: remove a scan from the compiled set | — | — | — |
| `force-exclude` | override: add a scan (`source: "override"`) | yes | yes | yes |

`validate_entry` rejects any entry missing a required field, with an action not in
`VALID_ACTIONS`, or an `exclude-contrast` entry with no `contrast` — `save_source_entries`
fails loud before writing (no silently-malformed entries reach disk).

**Provenance-stripped keyset.** For diffing (gate + reproduction), each gating entry
(`action ∈ {exclude, trim, exclude-contrast}`) collapses to a **7-tuple**
`(subject, session, task[bare], run, action, source, contrast)` via
`testing/reproduce/canonical.py::compiled_to_keyset`. `reason` is intentionally excluded
(informational, not identity).

### 3.2 collection

**Data-collection issues that no QC metric can recover.** Source of truth is the
committed, human-curated file `data/exclusions/<cohort>_collection.bidsignore` — a
`.bidsignore`-format list of glob lines grouped under `#`-comment headers (the comment
becomes the entry `reason`, prefixed `collection: `). It captures:

- incomplete acquisitions (`dim4=1`),
- prematurely-ended scans (**<50% of expected TRs** — the study's automatic-exclusion
  floor; 50–100% are salvaged),
- irreconcilable BOLD (missing/mismatched behavioral),
- onset-break scans,
- and anatomical/legacy exclusions (old MPRAGEPromo, ringing T1w/T2w, etc.).

The `CollectionGenerator` (`exclusions/collection.py`) ingests **only functional-BOLD**
glob lines matching `_FUNC_GLOB_RE`
(`sub-<s>/ses-<n>/func/sub-<s>_ses-<n>_task-<t>_run-<r>_echo-*_bold.*`). Each line is
**expanded against the real BIDS tree** into concrete per-scan entries: `run-*` → every
matching run, multi-echo files deduped to one entry per `(sub,ses,task,run)`. Lines are
filtered to the cohort roster (`load_dataset_subjects`). **Anatomical / wildcard-subject
lines** (`anat/`, `*_T1w.*`, `sub-*/…`) are **skipped** — they drive fMRIPrep anatomical
selection, not the lev1 BOLD-scan gate.

Why it's a compiled source and not only a rendered `.bidsignore`: previously the
collection layer lived *only* in the `.bidsignore` (the fMRIPrep gate). A scan whose
fMRIPrep derivatives predated its collection exclusion would slip through the lev1 gate.
Folding it into the compiled set makes `compiled = collection ∪ QC ∪ overrides` the single
lev1 gate. (Discovery: 16 collection entries.)

### 3.3 behavioral-qc

**In-scanner task-performance failures**, computed by
`neuro_workflow.events.qc.run_qc` over the behavioral CSVs. The `BehavioralGenerator`
(`exclusions/behavioral.py`) reads `<bids>/sourcedata` (the shared
`in_scanner_behavior` tree holds all cohorts, so it filters to the cohort roster via
`load_dataset_subjects`) and stamps `source = "behavioral-qc"` on each entry.

`run_qc` walks `sub-*/ses-*/beh/*.csv`, computes per-run metrics from `test_trial` rows,
and applies **task-specific** rules. All thresholds live in `config/thresholds.yaml`
(`behavioral_qc:` block) and are bound through `events/qc_globals.py`:

| Task family | Rule (excluded when…) | Thresholds |
|---|---|---|
| **stopSignal** | `stop_success_rate < 0.25` OR `> 0.75`; OR `go_rt > 1000 ms` | `stop_success_acc_low=0.25`, `high=0.75`, `go_rt_threshold_fmri=1000` |
| **goNogo** | both dual-rules fire: `(go_acc ≤ 0.75 OR nogo_acc ≤ 0.2)` AND `(go_acc ≤ 0.5 OR nogo_acc ≤ 0.5)` | `gonogo_go_acc_1=0.75, nogo_1=0.2, go_2=0.5, nogo_2=0.5` |
| **nBack** (per load 1,2) | both dual-rules fire on match/mismatch accuracy | `nback_*back_match/mismatch_acc_combined_threshold_{1,2}` (0.2 / 0.75 / 0.5 / 0.5) |
| **all other tasks** | `acc < 0.55` OR `omission_rate > 0.25` | `acc_threshold=0.55`, `omission_rate_threshold=0.25` |

Two additional behavioral checks run for every task:

- **RT-tail cutoff** (`detect_rt_tail_cutoff`): if the last `last_n_test_trials=10`
  test trials are all non-responses (`rt == -1`) and the tail is contiguous, the run
  "cut out." If the cutoff is **before the halfway point**, the scan is `exclude`d;
  otherwise it is recorded in a **trim list** (`sourcedata/behavioral_qc/trim_list.json`)
  for salvage.
- **Non-monotonic onset truncation:** a backward `time_elapsed` clock glitch makes
  `create_events_df` truncate at the first non-monotonic onset. If that truncation would
  drop **more than 50%** of the run's test trials
  (`NONMONOTONIC_EXCLUDE_FRACTION = 0.5`, defined in `events/qc.py`), the scan is
  `exclude`d rather than kept gutted.

Note `go_rt_threshold_fmri_dual_task=1050` exists in the config for the dual-task battery
but the current `check_stop_signal_exclusion` uses only `GO_RT_THRESHOLD_FMRI` (1000).
(Discovery: 3 behavioral-qc entries.)

### 3.4 qa_decisions

**Human lev1-QA junk-trial / bad-scan decisions**, from the qa_report decisions TSV.
The `QADecisionsGenerator` (`exclusions/qa_decisions.py`) reads the TSV via
`neuro_workflow.qa.decisions.load_decisions` (schema
`subject | session | task | run | action | reason`; `action ∈ {pass, exclude, review}`).

- Only `action=exclude` rows produce entries; `pass` / `review` are counted in a stdout
  summary and skipped.
- **Scan-level** rows (session/task/run populated) → one `exclude` entry, reason suffixed
  `(scan-level)`.
- **Subject-level** rows (a bare subject key) → **expanded** via the BIDS glob
  `<bids>/sub-X/ses-*/func/*_bold.nii.gz` (multi-echo deduped) into one entry per scan,
  reason suffixed `(subject-level)`.
- Rows for subjects outside the cohort roster (`load_dataset_subjects`) are dropped — the
  decisions TSV (`config/manifests/qc_decisions.tsv`) is pooled across cohorts.

Required arg: `--decisions-tsv PATH`. (Discovery: 3 qa_decisions entries.)

### 3.5 motion

**Excessive head motion**, computed from fMRIPrep confounds. The `MotionGenerator`
(`exclusions/motion.py`) globs
`<bids>/derivatives/fmriprep_<version>/sub-*/ses-*/func/*_desc-confounds_timeseries.tsv`
and **fails loud** (`FileNotFoundError`) if the glob is empty — an empty glob almost
always means `--fmriprep-version` doesn't match the derivatives dir, and a silent `[]`
would be recorded as "motion: 0" (a silent under-exclusion). This generator is
dataset-scoped by construction (reads only the cohort's derivatives) so it does **not**
apply the roster filter.

Metrics use fMRIPrep's **`framewise_displacement`** and **`std_dvars`** (standardized,
z-units — NOT the raw `dvars` in BOLD-intensity units). Thresholds live in
`config/thresholds.yaml` (`motion:` block); the fMRIPrep version defaults to
`24.1.0rc2` in argparse but production uses `25.2.4`:

| Scan type | Rule (excluded when…) | Threshold (config key) |
|---|---|---|
| **rest** (`task == rest`) | `mean(framewise_displacement) > 0.2` | `fd_threshold = 0.2` |
| **task** (non-rest) | `proportion(FD > 0.5) > 0.2` | `proportion_fd_threshold = 0.2` |
| **all scans** | `proportion(std_dvars > 1.5) > 0.2` | `proportion_dvars_threshold = 0.2` |

The FD>0.5 and std_dvars>1.5 inner cutoffs are fixed conventions in `_compute_metrics`;
the outer proportions and the rest FD-mean are the tunable thresholds. Every emitted
entry carries a full `metrics` block (FD mean/std, proportions, std_dvars mean/std).
(Discovery: 0 motion entries.)

### 3.6 lev1_outlier

**Per-contrast design/quality outliers** from cohort lev1 QC. The `Lev1OutlierGenerator`
(`exclusions/lev1_outlier.py`) reads `lev1_outliers.csv` (one row per scan-contrast,
produced by `neuro_workflow.qa.lev1_outliers`), filters to the cohort roster, and emits
**one `exclude-contrast` entry per `(subject, session, run, contrast)`** that fires any
rule. Thresholds from `config/thresholds.yaml` (`lev1_outlier:` block):

| Rule | Fires when… | Thresholds |
|---|---|---|
| **combined** | `vif ≥ 10 AND outlier_pct ≥ 10` | `combined_vif=10.0`, `combined_outlier_pct=10.0` |
| **strict_vif** | `vif ≥ 15` | `strict_vif=15.0` |
| **strict_outliers** | `outlier_pct ≥ 15` | `strict_outlier_pct=15.0` |

The rules are OR'd. The two VIF rules (`combined`, `strict_vif`) are **skipped for
`exempt_contrasts`** — `task-baseline` and `response_time` — which are structurally
high-VIF (sum-of-all-conditions collides with the constant + cosine-drift terms;
`response_time` is a nuisance regressor collinear with task timing; ~2/3 of all VIF≥15
flags are `task-baseline`). The **outlier-only** rule (`strict_outliers`) still applies to
exempt contrasts.

**Semantics — `exclude-contrast` is not scan-level.** Unlike `exclude`/`trim`, an
`exclude-contrast` entry does **not** remove the BOLD, produces **no** `.bidsignore`
glob, and does **not** make lev1 skip the run. It drops only that run's contribution to
that one contrast's fixed-effects. When enough runs are dropped that a subject/task/
contrast falls **below the `min_runs=2` floor**, the fixed-effects map is tagged
`_desc-belowMinRuns` and lev2 drops it (see §3.7). This is the design fix over the
archived whole-scan behavior (which excluded 131/192 discovery scans on a single
contrast's VIF).

Required arg: `--lev1-outliers-csv PATH`. (Discovery: 22 lev1_outlier entries.)

### 3.7 How enforcement happens at lev1/lev2

**Scan-level (`exclude` / `trim`).** lev1's CLI requires `--exclusions-file <compiled>`.
`analysis/lev1/prepare.py` loads the compiled list via `core/utils.load_exclusions` into a
set of scan-key strings; in `runner.py::process_single_run`, if the run's key is in that
set the run is skipped (`Skipping excluded run`). Excluded scans never reach the GLM.

**Per-contrast (`exclude-contrast`).** `core/utils.load_contrast_exclusions` returns
`{(scan_key, contrast)}` pairs (scan-level actions ignored here). `runner.py`
(`compute_fixed_effects_all`) passes these as `contrast_exclusions` to
`compute_subject_fixed_effects`, which drops that run's per-run input for that contrast
only.

**Low-N tag → lev2.** `FixedEffectsAnalyzer` (`processing/fixed_effects.py`,
`min_runs=2` default) tags any contrast whose retained `n_runs < min_runs` with
`_desc-belowMinRuns` in the output filename and warns. lev2's `discover_input_files`
(`analysis/lev2/run.py`; surface variant in `lev2/surface.py`) globs the fixed-effects
maps and **filters out any path containing `_desc-belowMinRuns_`** before group analysis.
lev2 has no separate `--exclusions-file`: every meaningful group-level case is already
handled by lev1's scan filtering, the per-contrast drop, or the belowMinRuns tag.

---

## 4. Compilation & provenance (the lockfile)

`compile_exclusions(<cohort>)` (`core/exclusions.py`) does:

1. Read every `~/.neuro_workflow/exclusions/<cohort>/sources/*.json` (wrapped
   `{_meta, entries}`; legacy bare-list tolerated, with synthetic null-field meta).
2. Read `data/exclusions/<cohort>_overrides.json` (committed).
3. Apply overrides: `force-include` **removes** matching scans; `force-exclude`
   **adds** a scan with `source: "override"` — idempotently (skips a scan a source already
   excludes, so an overlapping manual force-exclude does not duplicate a compiled entry).
4. Write `~/.neuro_workflow/exclusions/<cohort>/compiled_exclusions.json` (a **bare list**
   — the format lev1 reads), and optionally a copy under
   `<bids>/derivatives/exclusions/compiled_exclusions.json`.
5. Write the committed **lockfile** `data/exclusions/<cohort>_lock.json`.

### Lockfile schema (`data/exclusions/<cohort>_lock.json`)

```json
{
  "dataset": "discovery",
  "compiled_at": "2026-06-29T17:40:52Z",
  "compiled_at_code_sha": "c1bb151+dirty",
  "compiled_path": ".../compiled_exclusions.json",
  "n_total_entries": 44,
  "n_overrides": 0,
  "sources": [
    {"generator": "collection",   "ran_at": "...", "code_sha": "c1bb151+dirty", "args": null, "n_entries": 16},
    {"generator": "lev1_outlier", "ran_at": "...", "code_sha": "c1bb151+dirty", "args": null, "n_entries": 22},
    {"generator": "behavioral-qc","ran_at": "...", "code_sha": "c1bb151+dirty", "args": null, "n_entries": 3},
    {"generator": "qa_decisions", "ran_at": "...", "code_sha": "c1bb151+dirty", "args": null, "n_entries": 3},
    {"generator": "motion",       "ran_at": "...", "code_sha": "c1bb151+dirty", "args": null, "n_entries": 0}
  ]
}
```

Provenance fields:

- **`compiled_at` / `compiled_at_code_sha`** — UTC timestamp and short git HEAD SHA at
  compile time (`core.provenance.git_sha`, re-exported as `_git_sha`). A `+dirty` suffix
  means the working tree had uncommitted changes.
- **`sources[]._meta`** — per generator: `generator`, `ran_at`, `code_sha`, the JSON-safe
  `args` it was invoked with (argparse `func` callback stripped by `_jsonify`), and
  `n_entries`. `null` fields indicate a legacy bare-list source file that predates the
  audit-trail feature.
- **`config_version`** — not in the lockfile itself but recorded in each lev1/lev2
  `run-manifest.json`: a 12-char sha256 over `config/thresholds.yaml` + the task
  `battery.yaml` (`core.thresholds.config_version`), so any threshold or task-list edit
  produces a new version string.

`neuro-run exclusions show <cohort>` prints a per-source Exclude/Trim/Total table from the
compiled JSON, then the lockfile provenance block. The committed discovery lockfile
records **44** total entries (16 collection + 22 lev1_outlier + 3 behavioral-qc + 3
qa_decisions + 0 motion).

> The lockfile shows both a `behavioral-qc` source file (3 entries, the current
> generator output — `BehavioralGenerator` stamps `source="behavioral-qc"`) and a stale
> `behavioral` source file (0 entries, an old run with a full argparse `args` block). Both
> are merged; only the non-empty one contributes. The compiled `source` field, and hence
> `render-md` grouping, uses `behavioral-qc`.

---

## 5. Rendering `.bidsignore` and `EXCLUSIONS.md`

Both human-readable artifacts are **rendered from the compiled set** — the lockfile /
compiled JSON is the single source of truth; the artifacts are never hand-edited. Pure
(no-I/O) renderers live in `core/exclusions_render.py`; the CLI writes only when
`--output` is given, and never touches the real docs / BIDS root unless that exact path is
passed.

- **`neuro-run exclusions render-md <cohort>`** → `render_md`: Markdown grouped by
  `source`, deterministically sorted, stamped
  `<!-- DO NOT EDIT — generated by 'neuro-run exclusions render-md' -->`.
- **`neuro-run exclusions render-bidsignore <cohort>`** →
  `render_bidsignore_with_collection`:
  1. Prepends the committed human-curated block **verbatim** from
     `data/exclusions/<cohort>_collection.bidsignore` (carries its own header;
     `FileNotFoundError` if missing — never silently emit a partial `.bidsignore`).
  2. Appends the generated QC block (`render_bidsignore`): one glob line per
     `exclude`/`trim` entry (`_BIDSIGNORE_ACTIONS`), form
     `sub-<s>/ses-<n>/func/sub-<s>_ses-<n>_task-<t>_run-<r>_echo-*_bold.*`, sorted &
     de-duped, under a DO-NOT-EDIT stamp. `exclude-contrast` and `force-include` produce
     **no** glob line.
  3. **Drops `source=="collection"` compiled entries** from the generated section (they
     are already present verbatim in the prepended block) to avoid duplicating every
     collection glob.

`check_md_drift` / `check_bidsignore_drift` compare a committed artifact against a fresh
render and return `(drifted, unified-diff)` — the basis for keeping committed artifacts
in lockstep with the compiled set.

---

## 6. The drift gate

`scripts/exclusion_gate.py` halts the pipeline on **undeliberate** exclusion drift.
It diffs a **newly-compiled** exclusion set against a **frozen reference**
(`data/exclusions/<cohort>_reference_compiled.json`) using the provenance-stripped
7-tuple keyset (`compiled_to_keyset` — `reason` excluded, so wording changes don't trip
the gate):

```
uv run python scripts/exclusion_gate.py \
  --new       ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --source    motion \
  --report    /scratch/.../gate_discovery_motion.md
```

- **`added`** = keys in new but not reference; **`dropped`** = keys in reference but not
  new. Each is printed with full evidence (source, action, contrast, reason) and written
  to a Markdown report.
- **`--source`** scopes the diff to one source (e.g. compare `motion` like-for-like when a
  stage only just gained it). A `--source`-scoped run is an intentionally partial view: a
  scan that *moved* between sources shows as a drop under the old source and an add under
  the new; run **unscoped** (`--source` omitted) for the full picture.
- **Exit codes:** `0` = no drift; **`3`** = drift detected (deliberately distinct from
  other scripts' exit codes). So exclusions change only with evidence + a sign-off that
  re-freezes the reference.

---

## 7. End-to-end reproduction

`scripts/reproduce_cohort.py` proves that the committed core (Flywheel snapshot + BIDS +
lockfiles) regenerates the same analytic selection. It is a **live** operation (reads real
fMRIPrep derivatives, behavioral data, and lev1 outputs) but **never writes** to the
committed `config/exclusions` or `data/exclusions` trees — a `_hermetic_exclusion_paths`
context manager redirects `EXCLUSIONS_DIR`, `LOCKFILE_DIR`, and the collection dir to a
scratch work dir for the duration.

```
uv run python scripts/reproduce_cohort.py discovery  --out /tmp/rep.md
uv run python scripts/reproduce_cohort.py validation --out /tmp/rep.md
```

Steps (`main`):

- **a. Replay** the frozen Flywheel inventory snapshot
  (`data/repro/fw_inventory_<cohort>.json`, captured by
  `scripts/capture_fw_inventory.py`) → **stub BIDS** via a `FakeFlywheel` client injected
  through `sys.modules` (the real Flywheel SDK is not required on the compute node) +
  `replay_to_bids`.
- **b. Stage** real fMRIPrep confound metrics (v `25.2.4`) into the stub tree
  (`stage_metrics`).
- **c. Run all 5 generators hermetically**, seeding the committed
  `<cohort>_collection.bidsignore` and `<cohort>_overrides.json` into the scratch dirs,
  then `compile_exclusions` and `render_bidsignore_with_collection`.
- **d.** Compute the **lev2-eligible set** = BIDS runs − scan-level exclusions, with
  per-contrast (`exclude-contrast`) cells removed, compared against the real lev1 surface
  fixed-effects (`derivatives/lev1_surface`).
- **e. Three diffs**, each with documented **boundary normalizers** (everything dropped is
  logged and dumped to a sidecar JSON — nothing hidden):
  1. **Filenames** — produced stub BIDS vs real BIDS, after removing known
     snapshot/replay boundaries: `rescan_subject` (`sub-<id>-<n>/`), `fmap_sidecar`
     (magnitude/fieldmap/phasediff), `anat_only_session`, and `orphan_events`
     (events.tsv whose scan is excluded, whose task is a dual task with no lev1 contrast
     config, or a multi-run run-1 orphan). Physio is excluded up front (out of scope).
  2. **Exclusion set** — rendered `.bidsignore` line-set vs the committed reference
     `.bidsignore` at the real BIDS root. A **prereq guard** exits **2** (distinct from
     the FAIL exit 1) if the reference is an unresolved git-annex pointer
     (`/annex/objects/…`) or missing.
  3. **Lev2-eligible** — with a boundary that removes model-only cells lev1
     under-produced at runtime (`belowMinRuns`/absent, run count < 2 via
     `lev1_indiv_run_counts`), which are not derivable from the exclusion set.
- **f.** Build a report with a provenance block (`config_version`, `fmriprep_version`,
  counts). **Exit 0** iff the report's first line contains `PASS`.

**`--bids-root`** retargets the four BIDS-derived paths (bids, fmriprep_src,
lev1_fe_dir, committed_bidsignore) under a new root so the **same** reproduction certifies
the **Oak** datasets; `--lev1-outliers-csv` overrides the outlier CSV location
(regenerated on Oak). Discovery and validation both reproduce **ALL-3-PASS** (Filenames /
Exclusion set / Lev2-eligible).

---

## 8. The Oak artifact

The canonical, backed-up, version-controlled datasets live at:

```
/oak/stanford/groups/russpold/data/network_grant/bids/{discovery,validation,excluded}
```

- Three **git-annex** datasets: **raw BIDS annexed + committed**; `derivatives/`
  (fMRIPrep, XCP-D, lev1) are plain files (regenerable, git-ignored). Post-processing
  present includes fMRIPrep `25.2.4`, `derivatives/xcp_d_26.0.2`, surface lev1
  (`derivatives/lev1_surface`).
- The raw BIDS on Oak is **byte-identical** to the scratch working copies
  (md5-verified) — the Oak copy is the durable, checksummed home of the reproducible core.
- These datasets are certified by the same reproduction harness (§7) retargeted with
  `--bids-root <oak dataset>` (roster keys `discovery_oak` / `validation_oak` in
  `pipeline_config.json`; Oak-specific lockfiles/collection/overrides carry the `_oak`
  suffix, e.g. `data/exclusions/discovery_oak_lock.json`).

---

## 9. Code & file-path index

| Path | Role |
|---|---|
| `config/pipeline_config.json` | Cohort rosters (`samples`), Flywheel aliases, session overrides |
| `config/thresholds.yaml` | Single source of truth for all QC/motion/lev1-outlier thresholds |
| `src/neuro_workflow/core/thresholds.py` | Loads `thresholds.yaml`; `config_version()` hash |
| `src/neuro_workflow/core/exclusions.py` | Schema, `save_source_entries`, `compile_exclusions`, override merge, query API |
| `src/neuro_workflow/core/exclusions_render.py` | `render_md`, `render_bidsignore`, `render_bidsignore_with_collection`, drift checks |
| `src/neuro_workflow/exclusions/base.py` | `ExclusionGenerator` Protocol, registry, `make_meta`, `load_dataset_subjects` |
| `src/neuro_workflow/exclusions/{collection,behavioral,qa_decisions,motion,lev1_outlier}.py` | The 5 generators |
| `src/neuro_workflow/events/qc.py` + `qc_globals.py` | Behavioral-QC metric computation & rules |
| `src/neuro_workflow/qa/lev1_outliers.py` | Cohort lev1 QC → `lev1_outliers.csv` |
| `src/neuro_workflow/cli/exclusions.py` | `neuro-run exclusions {generate,compile,show,import,query,render-md,render-bidsignore}` |
| `src/neuro_workflow/analysis/core/utils.py` | `create_exclusion_key`, `load_exclusions`, `load_contrast_exclusions` |
| `src/neuro_workflow/analysis/lev1/{prepare,runner}.py`, `processing/fixed_effects.py` | lev1 scan-skip, per-contrast drop, `_desc-belowMinRuns` tag |
| `src/neuro_workflow/analysis/lev2/{run,surface}.py` | `discover_input_files` (drops `_desc-belowMinRuns_`) |
| `src/neuro_workflow/testing/reproduce/canonical.py` | `compiled_to_keyset`, `bids_fileset`, `bidsignore_lineset` |
| `scripts/exclusion_gate.py` | Drift gate (exit 3 on drift) |
| `scripts/reproduce_cohort.py` | End-to-end reproduction (exit 0 on PASS, 2 on prereq) |
| `data/exclusions/<cohort>_lock.json` | Committed audit lockfile |
| `data/exclusions/<cohort>_collection.bidsignore` | Committed human-curated collection block |
| `data/exclusions/<cohort>_overrides.json` | Committed force-include / force-exclude |
| `data/exclusions/<cohort>_reference_compiled.json` | Frozen gate reference |
| `data/repro/fw_inventory_<cohort>.json` | Frozen Flywheel snapshot |

---

## 10. Where code and existing docs disagree

Points to reconcile in the other docs (this document follows the code):

1. **`EXCLUSIONS-FLOW.md` — `lev1_outlier` is described as archived/"do not use"
   with whole-scan (`strict_vif=15`) granularity.** Stale. The generator is **active** and
   emits **per-contrast** `exclude-contrast` entries with the `exempt_contrasts`
   (`task-baseline`, `response_time`) carve-out; the committed discovery lockfile shows it
   contributing 22 entries. `docs/DATASETS.md` §6 already reflects the current behavior.
2. **`EXCLUSIONS-FLOW.md` roster filter** references a dataset `subjects_file` /
   `~/.neuro_workflow/datasets.json`. Current code resolves the roster from
   `config/pipeline_config.json` `samples` via `load_dataset_subjects` /
   `resolve_dataset_subjects`; the removed `subjects_*.txt` files are gone.
3. **`EXCLUSIONS-FLOW.md` CLI path** points at `src/neuro_workflow/cli.py`; the
   handlers now live in `src/neuro_workflow/cli/exclusions.py`.
4. **`EXCLUSIONS-FLOW.md` "operator playbook"** says there is *no automated path* from
   cohort QC to the registry (act only via `qa_decisions`/overrides). The automated path
   now exists — the `lev1_outlier` generator — as long as it is understood to be
   per-contrast, not scan-level.
5. **`EXCLUSIONS.md`** (last updated 2026-04-14) predates the compiled-source model:
   it describes `.bidsignore` as the authoritative store. The authoritative store is now
   the compiled set / lockfile; `.bidsignore` and `EXCLUSIONS.md` are **rendered** from it.
6. **Two behavioral source files in the lockfile** (`behavioral-qc` with 3 entries and a
   stale `behavioral` with 0) — a harmless provenance artifact of the source-file naming
   (`BehavioralGenerator.name = "behavioral"` but entries stamp `source="behavioral-qc"`),
   worth cleaning up on the next full recompile so the source list is unambiguous.

---

## Run-manifest schema & clean-tree policy

> Folded in from the former `PROVENANCE.md` (2026-07-04). Every lev1 and lev2 run
> automatically records its provenance; this section describes what is captured, where it
> lands, and how the clean-tree policy works. (§4 above covers the compiled-**exclusions**
> lockfile and its own, separate provenance fields — `compiled_at`, `compiled_at_code_sha`,
> per-source `_meta` — including `config_version`'s role there; not repeated here.)

### run-manifest.json

Written to `<output_dir>/run-manifest.json` at the end of each lev1 or lev2 run. Fields:

| Field | Description |
|-------|-------------|
| `stage` | `"lev1"` or `"lev2"` |
| `code_sha` | Short git HEAD SHA, with `+dirty` suffix if working tree has uncommitted changes |
| `code_dirty` | Boolean — `true` if working tree is dirty |
| `uv_lock_hash` | First 12 hex chars of sha256(`uv.lock`) — pins the exact resolved dependency graph |
| `config_version` | 12-char sha256 over `config/thresholds.yaml` + `battery.yaml` — changes whenever a study threshold or task list changes |
| `tool_versions` | Dict of `package → installed version` for key analysis tools |
| `exclusions_source` | `{path, sha256}` of the compiled exclusions JSON consumed by this run (lev1 only) |
| `args` | The parsed CLI arguments (JSON-safe) |
| `created_at` | UTC ISO timestamp |
| `host` | `{nodename, sysname, release, machine, user}` |
| `slurm_job_id` | SLURM job ID, or `null` if run outside SLURM |
| `inputs` | Per-file manifest: `[{path, size_bytes, sha256}, …]` for key input files |

Lev2 additionally includes an `input_provenance` block that summarises the `run-manifest.json` from each lev1 subject directory it consumed.

### dataset_description.json

Written to `<output_dir>/dataset_description.json`. Minimal valid BIDS derivative file:

```json
{
  "Name": "lev1",
  "BIDSVersion": "1.10.0",
  "DatasetType": "derivative",
  "GeneratedBy": [{
    "Name": "neuro-workflow",
    "Version": "<installed version>",
    "CodeURL": "git:<short SHA>"
  }],
  "SourceDatasets": [{"URL": "<bids_dir>"}, {"URL": "<fmriprep_dir>"}]
}
```

### Where outputs land

```
<output_dir>/
├── run-manifest.json
└── dataset_description.json
```

For lev1, `<output_dir>` is the per-subject results directory (e.g., `derivatives/lev1/sub-s10/`). For lev2, it is the group-level output directory.

### Clean-tree policy

By default, a lev1 or lev2 run warns loudly to stderr if the working tree has uncommitted changes, but the run still proceeds. The manifest records `code_dirty: true` in that case.

To suppress the warning (e.g., during active development):
```bash
uv run neuro-run submit lev1 discovery --allow-dirty
```

To enforce a hard failure on a dirty tree (stricter reproducibility enforcement), use `require_clean_tree(allow_dirty=False)` programmatically from `core/provenance`.

### Python API

```python
from neuro_workflow.core import provenance

# Write a run manifest
provenance.write_run_manifest(
    output_dir,
    stage="lev1",
    args=parsed_args,
    inputs=[Path("sub-s10_task-flanker_bold.nii.gz")],
    exclusions_source="data/exclusions/discovery_lock.json",
    allow_dirty=True,
)

# Write BIDS dataset_description.json
provenance.write_dataset_description(
    output_dir,
    name="lev1",
    source_datasets=[{"URL": "/scratch/users/logben/discovery_bids"}],
)

# Get the current config version hash
version = provenance.config_version()

# Check for dirty working tree
if provenance.git_is_dirty():
    print("Working tree has uncommitted changes")
```
