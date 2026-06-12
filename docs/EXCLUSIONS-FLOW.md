# Exclusions Flow

End-to-end reference for how scan exclusions propagate through the pipeline. Covers every source, the generator that captures it, the compile + lockfile audit, and how lev1/lev2 honor the result.

For per-`.bidsignore`-entry rationale, see `docs/EXCLUSIONS.md`. For the broader pipeline, see `docs/WORKFLOW.md`.

---

## 1. Overview

```
[BIDS dataset]
      │
      ├── .bidsignore  ─────────────────────────────────────────────────┐
      │                                                                 │
[fmriprep on filtered BIDS] ──── derivatives/fmriprep_<v>/ ──┐          │
                                                             │          │
[cohort QC: neuro_workflow.qa.lev1_outliers]                 │          │
                          │                                  │          │
                          └─ lev1_outliers.csv ─┐            │          │
                                                │            │          │
[qa_report UI] ── decisions.tsv ─────┐          │            │          │
                                     │          │            │          │
                                     v          v            v          │
              ┌───────────────────────────────────────────────┐         │
              │ Exclusion generators (per dataset, on demand) │         │
              │  - motion (reads fmriprep confounds)          │         │
              │  - behavioral (reads sourcedata events)       │         │
              │  - lev1_outlier (reads cohort QC CSV)         │         │
              │  - qa_decisions (reads decisions TSV)         │         │
              │  - collection (reads committed                │         │
              │      {ds}_collection.bidsignore)              │         │
              └───────────────────────────────────────────────┘         │
                          │                                             │
                          v                                             │
              ~/.neuro_workflow/exclusions/<ds>/sources/*.json          │
              data/exclusions/<ds>_overrides.json (committed)           │
                          │                                             │
                          v                                             │
              compile_exclusions(<ds>)                                  │
                          │                                             │
                          ├── ~/.neuro_workflow/.../compiled_exclusions.json
                          │                                             │
                          └── data/exclusions/<ds>_lock.json (committed)│
                                            │                           │
                                            v                           │
                              [neuro-run exclusions show <ds>]          │
                                                                        │
[lev1.run --exclusions-file <compiled>]  ◄────────────────────── filters scans
                          │
                          v
              lev1 fixed-effects (per subject, per task, per contrast)
                          │
                          ├── tagged _desc-belowMinRuns when n_runs < min_runs
                          │
                          v
              [lev2 discover_input_files]  ◄────── drops _desc-belowMinRuns files
                          │
                          v
                    Group analysis
```

The chain runs left-to-right, top-to-bottom. Excluded scans never reach lev1 (filtered at scan-discovery time); subjects with too few retained sessions don't reach lev2 (filtered at fixed-effects-discovery time).

---

## 2. Exclusion sources

| Origin | What it captures | Captured by | Granularity |
|---|---|---|---|
| `.bidsignore` (in BIDS dir) | Bad/unusable raw data (corrupt scans, withdrawn subjects, partial runs, behavioral failures) | fmriprep itself (BIDS-native; no derivatives produced) | Per-file pattern |
| fmriprep confounds | Excessive motion (FD mean for rest, FD>0.5 proportion, std_dvars>1.5 proportion) | `motion` generator | Per-scan |
| Sourcedata behavioral events | Behavioral QC failures (omission rate, RT) | `behavioral` generator | Per-scan |
| Cohort QC `lev1_outliers.csv` + Jeanette-style PDF | Per-(subject, task, contrast) high VIF or high outlier-voxel proportion | **manual review only** (the `lev1_outlier` generator was archived 2026-05-07 — see Section 3) | Visual inspection; act via `qa_decisions` or override |
| qa_report decisions TSV | Manual annotations from the qa_report UI (`action ∈ pass/exclude/review`) | `qa_decisions` generator (scan-level rows direct; subject-level rows expanded via BIDS BOLD glob) | Per-scan or per-subject |
| Manual override | Force-include (un-exclude) or force-exclude (add) | `data/exclusions/<ds>_overrides.json` (read by `compile_exclusions`) | Per-scan |
| Lev1 fixed-effects min_runs | Subjects whose retained sessions for a (task, contrast) fall below `--min-runs` (default 2) | `_desc-belowMinRuns` filename tag, written by lev1, honored by lev2's `discover_input_files` glob filter | Per-(subject, task, contrast) |

`.bidsignore` is the only source that operates *upstream* of fmriprep — it removes scans from BIDS itself. Everything else operates on fmriprep derivatives or cohort outputs and feeds into the exclusions registry.

---

## 3. Generator reference

All generators implement the `ExclusionGenerator` Protocol from `src/neuro_workflow/exclusions/base.py`. They return `list[dict]` from `generate()`; the CLI saves the result to `~/.neuro_workflow/exclusions/<ds>/sources/<gen>.json` wrapped with `_meta` provenance.

**Pattern**: `neuro-run exclusions generate <generator> <dataset> [generator-specific args]`

### `motion`

- **Reads:** `<bids_dir>/derivatives/fmriprep_<version>/sub-*/ses-*/func/*_desc-confounds_timeseries.tsv`
- **Defaults:** `--fd-threshold 0.2` (rest only), `--proportion-fd-threshold 0.2`, `--proportion-dvars-threshold 0.2`, `--fmriprep-version 24.1.0rc2`
- **Logic:** rest scans flagged when `mean(framewise_displacement) > fd-threshold`; task scans flagged when proportion of `framewise_displacement > 0.5` exceeds `proportion-fd-threshold`. All scans flagged when proportion of `std_dvars > 1.5` exceeds `proportion-dvars-threshold`.
- **Notable**: reads `std_dvars` (standardized z-units), NOT raw `dvars`. The threshold convention `>1.5` is for std_dvars; raw dvars is in BOLD-intensity units.
- **Sample**: `neuro-run exclusions generate motion discovery --fmriprep-version 25.2.4`

### `behavioral`

- **Reads:** `<bids_dir>/sourcedata/...` behavioral CSVs via `neuro_workflow.events.qc.run_qc`
- **Defaults:** `--behavioral-dir <bids>/sourcedata`
- **Logic:** internal QC rules in `events/qc.py` (omission rate, RT thresholds).
- **Sample**: `neuro-run exclusions generate behavioral discovery`

### `lev1_outlier` — **archived (2026-05-07); do not use as written**

> **Status:** the generator code still exists and runs, but its output is **not in active use** for discovery (and should not be for validation either). The strict_vif=15 rule excluded whole scans based on a single contrast's VIF — most often `task-baseline`, whose collinearity with motion regressors is benign and routinely produces VIF in the 20-130 range on healthy data. On discovery this excluded 131/192 scans and produced zero fixed-effects for cuedTS, directedForgetting, and shapeMatching. The scan-level granularity itself is the design error: a high-VIF *contrast* should not preclude the *whole scan* from GLM. The cohort QC PDF + `lev1_flagged.tsv` (from `neuro_workflow.qa.lev1_outliers`) are the manual-review surface; act on them via `qa_decisions` or `data/exclusions/<ds>_overrides.json` instead.

The archived discovery output (131 entries) is preserved at `~/.neuro_workflow/exclusions/discovery/sources_archived/lev1_outlier_2026-05-07_pre-rerun.json` for audit history. A future revisit may either delete the generator entirely or repurpose it to filter individual effect-size files at lev2 (per-(subject, task, contrast) granularity rather than per-scan); that decision is open.

Original spec retained below for archival/reference only:

- **Reads:** `lev1_outliers.csv` produced by `neuro_workflow.qa.lev1_outliers` cohort QC.
- **Required arg**: `--lev1-outliers-csv PATH`
- **Defaults:** `--combined-vif 10 --combined-outlier-pct 10 --strict-vif 15 --strict-outlier-pct 15`
- **Logic:** three OR'd rules per (scan, contrast):
    - **combined**: `vif >= combined-vif AND outlier_pct >= combined-outlier-pct`
    - **strict_vif**: `vif >= strict-vif`
    - **strict_outliers**: `outlier_pct >= strict-outlier-pct`
  Per-scan aggregation: if any contrast on a scan fires any rule, emit one entry; reason lists every flagged contrast and its rule.
- **Dataset filter:** when the dataset has a `subjects_file`, rows whose subject is not in the roster are dropped.
- **Sample (do not run on production datasets without revisiting the design):** `neuro-run exclusions generate lev1_outlier discovery --lev1-outliers-csv /scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv`

### `qa_decisions`

- **Reads:** the qa_report decisions TSV (schema: `subject|session|task|run|action|reason`; `action ∈ pass/exclude/review`).
- **Required arg**: `--decisions-tsv PATH`
- **Logic**: only `action=exclude` rows produce entries. `pass`/`review` are counted in a stdout summary and skipped.
    - Scan-level rows (`session/task/run` populated) → one entry.
    - Subject-level rows (`session/task/run = "-"`) → expanded to per-scan entries via `<bids>/sub-X/ses-*/func/*_bold.nii.gz` glob.
- **Dataset filter**: same as `lev1_outlier` — applies before the BIDS glob to skip filesystem reads for non-member subjects.
- **Sample**: `neuro-run exclusions generate qa_decisions discovery --decisions-tsv /path/to/qa_decisions_discovery.tsv`

### `collection`

- **Reads:** the committed human-curated `data/exclusions/<ds>_collection.bidsignore` (incomplete acquisitions, <50%-TR scans, irreconcilable-BOLD, onset-break breaks — the exclusions that do NOT come from a QC metric).
- **Required arg**: none (the committed collection file is the input).
- **Logic**: each functional-BOLD glob line is expanded against the BIDS dir into concrete per-scan entries (`run-*` → every real run; multi-echo files deduped to one entry/scan). Anatomical / wildcard-subject lines (`anat/`, `*_T1w.*`, `sub-*/...`) are skipped — they drive fMRIPrep anatomical selection, not the lev1 BOLD-scan gate.
- **Why it exists**: the collection `.bidsignore` was previously *only* the fMRIPrep layer (prepended at `render-bidsignore` time); it was NOT in the compiled exclusions lev1 reads, so a scan whose fMRIPrep derivatives predate its collection exclusion could slip through the lev1 gate. Ingesting it as a source makes `compiled = collection ∪ QC ∪ overrides` the single lev1 gate. `render-bidsignore` still prepends the verbatim human block and now drops `source=collection` compiled entries from the generated section so collection globs are not duplicated.
- **Sample**: `neuro-run exclusions generate collection discovery`

### `_desc-belowMinRuns` (not a generator — a filename tag)

- **Set by:** lev1's `FixedEffectsAnalyzer._build_base_filename`.
- **When:** the analyzer's contrast had `n_runs < min_runs` (configurable via `--min-runs INT` on `lev1.run`, default 2).
- **Honored by:** lev2's `discover_input_files`, which drops paths containing `_desc-belowMinRuns_` from the input list before group analysis.

---

## 4. Compile + lockfile audit

`compile_exclusions(<ds>)` does five things:

1. Reads each `~/.neuro_workflow/exclusions/<ds>/sources/*.json`. Each file is `{"_meta": {...}, "entries": [...]}` (legacy bare-list format also tolerated for older files).
2. Reads `data/exclusions/<ds>_overrides.json` if present.
3. Applies overrides:
    - `force-include` removes a scan from the merged list.
    - `force-exclude` adds a scan with `source: "override"`.
4. Writes `~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json` (a bare list — the format lev1 reads).
5. Writes `data/exclusions/<ds>_lock.json` (committed to git — the canonical audit artifact).

### Lockfile schema

```json
{
    "dataset": "discovery",
    "compiled_at": "2026-05-08T03:55:42Z",
    "compiled_at_code_sha": "270db94",
    "compiled_path": "/home/users/logben/.neuro_workflow/exclusions/discovery/compiled_exclusions.json",
    "n_total_entries": 131,
    "n_overrides": 0,
    "sources": [
        {
            "generator": "lev1_outlier",
            "ran_at": "2026-05-07T17:30:00Z",
            "code_sha": "20b5738",
            "args": {
                "lev1_outliers_csv": "/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv",
                "combined_vif": 10.0,
                "combined_outlier_pct": 10.0,
                "strict_vif": 15.0,
                "strict_outlier_pct": 15.0
            },
            "n_entries": 131
        }
    ]
}
```

A `code_sha` value with `+dirty` suffix means the working tree had uncommitted changes when that source was generated (or when compile ran). `null` values for per-source fields mean the file was in legacy bare-list format and the generator hasn't been re-run since this audit-trail feature landed.

### `neuro-run exclusions show <ds>`

Prints a per-source count table from the compiled JSON, then a provenance block from the lockfile (when one exists):

```
Exclusions for 'discovery':
Source           Exclude     Trim    Total
-----------------------------------------
lev1_outlier         131        0      131
-----------------------------------------
Total                131        0      131

Provenance (data/exclusions/discovery_lock.json):
  Compiled at: 2026-05-08T03:55:42Z (code_sha: 270db94)
  Total entries: 131, overrides: 0
  - lev1_outlier    ran_at=2026-05-07T17:30:00Z code_sha=20b5738 n_entries=131
  - motion          ran_at=2026-05-07T18:00:00Z code_sha=20b5738 n_entries=0
  - behavioral      ran_at=2026-05-07T18:00:00Z code_sha=20b5738 n_entries=0
```

---

## 5. Lev1 / lev2 propagation

### Lev1: filter scans before GLM

Lev1's CLI requires `--exclusions-file <compiled>`. The path is canonically `~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json`. Lev1's scan discovery filters out anything whose `(subject, session, task, run)` matches an exclusion entry with `action ∈ exclude/trim`.

### Lev1: tag low-N fixed-effects

After GLM, lev1 computes fixed-effects per (subject, task, contrast). When `n_runs_remaining < args.min_runs` (default 2), the saved fixed-effects filename includes `_desc-belowMinRuns` between `_rtmodel-RTDur` and `_stat-fixed-effects`. A WARNING is emitted to stderr per tagged contrast.

The output filename example for a tagged map:

```
sub-s03_task-flanker_contrast-incongruent-congruent_rtmodel-RTDur_desc-belowMinRuns_stat-fixed-effects.nii.gz
```

Vs. an untagged map:

```
sub-s03_task-flanker_contrast-incongruent-congruent_rtmodel-RTDur_stat-fixed-effects.nii.gz
```

### Lev2: drop tagged maps from group analysis

Lev2's `discover_input_files` globs `<lev1_dir>/sub-*/*/fixed_effects/*<contrast>_rtmodel-*_stat-fixed-effects.nii.gz`, then filters out any path containing `_desc-belowMinRuns_`. No separate `--exclusions-file` arg — by design, every meaningful lev2-relevant case (whole-subject exclusion, mostly-excluded subject) is already handled by lev1's filtering or the belowMinRuns tag.

---

## 6. Override mechanism

`data/exclusions/<ds>_overrides.json` is a committed JSON list of override entries:

```json
[
    {
        "subject": "sub-s03",
        "session": "ses-02",
        "task": "task-cuedTS",
        "run": "run-1",
        "action": "force-include",
        "reason": "Manual review confirmed scan is usable despite high VIF"
    },
    {
        "subject": "sub-s10",
        "session": "ses-04",
        "task": "task-flanker",
        "run": "run-1",
        "action": "force-exclude",
        "reason": "Subject reported feeling unwell mid-run; not flagged by automated thresholds"
    }
]
```

`force-include` removes a scan from the compiled list (the auto-flagged exclusion is overridden).
`force-exclude` adds a scan with `source: "override"`.

Edits are tracked via git history on the override file. The override file is consulted at compile time; no need to re-run generators after editing it.

---

## 7. Operator playbook

### Recipe: exclude a scan based on visual review (qa_report)

This is the primary path for adding manual exclusions to the pipeline.

1. Open the qa_report HTML for the dataset.
2. Find the scan; mark it `exclude` in the decisions TSV (or use the UI if it writes back).
3. `uv run neuro-run exclusions generate qa_decisions <ds> --decisions-tsv <path>`
4. `uv run neuro-run exclusions compile <ds>`
5. Re-run lev1 for affected subjects (the new exclusion is now in `compiled_exclusions.json`, which lev1's `--exclusions-file` reads).

### Recipe: exclude a scan based on the cohort QC PDF / `lev1_flagged.tsv`

`neuro_workflow.qa.lev1_outliers` produces a Jeanette-style cohort QC PDF and a `lev1_flagged.tsv` that surface high-VIF or high-outlier-voxel scans/contrasts. **There is no automated path from these to the exclusions registry today** (the `lev1_outlier` generator was archived 2026-05-07 — see Section 3). To act on cohort-QC findings:

1. Inspect the PDF and `lev1_flagged.tsv` manually.
2. Decide which scans to exclude. Note: the cohort QC flags individual `(subject, task, contrast)` triples, but the current exclusion registry only supports per-scan (`subject, session, task, run`) entries — there's no per-contrast filter at lev2 yet.
3. For each scan you want excluded: either mark it in the qa_report decisions TSV (then follow the recipe above) **or** add a `force-exclude` entry to `data/exclusions/<ds>_overrides.json` (see "exclude a scan because automated thresholds didn't catch it" below).

### Recipe: exclude a scan because automated thresholds didn't catch it

1. Edit `data/exclusions/<ds>_overrides.json`. Add a `force-exclude` entry with subject/session/task/run + a reason.
2. Commit the change.
3. `uv run neuro-run exclusions compile <ds>` — picks up the override.
4. Re-run lev1.

### Recipe: include a scan that was auto-flagged but is actually fine

1. Edit `data/exclusions/<ds>_overrides.json`. Add a `force-include` entry with the same scan identity + reason.
2. Commit + compile + re-run lev1.

### Recipe: recompute exclusions from scratch

1. Decide which sources are stale and re-run their generators:
    - Motion: `neuro-run exclusions generate motion <ds> --fmriprep-version <v>`
    - Behavioral: `neuro-run exclusions generate behavioral <ds>`
    - QA decisions: `neuro-run exclusions generate qa_decisions <ds> --decisions-tsv <path>`
    - **Note:** the `lev1_outlier` generator was archived 2026-05-07. Do not run it without revisiting the design (see Section 3).
2. `uv run neuro-run exclusions compile <ds>`
3. Inspect: `uv run neuro-run exclusions show <ds>`

### Recipe: inspect what's currently excluded for a dataset

```bash
uv run neuro-run exclusions show <ds>
```

Or for the raw data:

```bash
cat ~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json | python -m json.tool | head -50
cat data/exclusions/<ds>_lock.json | python -m json.tool
```

### Recipe: reproduce another machine's exclusion state

When you clone the repo and want to recreate the exclusion state another machine produced:

1. Read `data/exclusions/<ds>_lock.json`. The `sources` array lists every generator that contributed, with the args it was invoked with.
2. For each source, run the corresponding generator with the same args. Where a source's `args` field is `null` (legacy from before the audit-trail feature), inspect `<ds>` git history or stale `.err` files to reconstruct.
3. Copy `data/exclusions/<ds>_overrides.json` from git.
4. `uv run neuro-run exclusions compile <ds>`
5. Compare your fresh `<ds>_lock.json` to the committed one — `n_total_entries` and per-source `n_entries` should match (timestamps and SHA will differ).

### Recipe: I added a `_desc-belowMinRuns` exclusion at lev1 — what happens to that subject in lev2?

The subject is dropped from every contrast's lev2 group analysis where their fixed-effects map carries the tag. Other contrasts (where the subject had `n_runs >= min_runs`) include them normally. Drop is automatic via `discover_input_files`.

---

## 8. File paths reference

### Per-dataset (in repo, committed)

| Path | Role |
|---|---|
| `data/exclusions/<ds>_overrides.json` | Manual force-include / force-exclude entries |
| `data/exclusions/<ds>_lock.json` | Audit lockfile (compile artifact; canonical record) |
| `<bids_dir>/.bidsignore` | Per-file skip patterns (BIDS-native; honored by fmriprep) |

### Per-dataset (out-of-repo, machine-local)

| Path | Role |
|---|---|
| `~/.neuro_workflow/exclusions/<ds>/sources/<gen>.json` | Per-generator output (`{_meta, entries}`) |
| `~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json` | Merged list (bare JSON list of entries) |
| `~/.neuro_workflow/datasets.json` | Registered datasets (bids_dir, subjects_file, etc.) |

### Inputs to generators (vary per setup)

| Generator | Input |
|---|---|
| `motion` | `<bids>/derivatives/fmriprep_<v>/sub-*/ses-*/func/*_desc-confounds_timeseries.tsv` |
| `behavioral` | `<bids>/sourcedata/...` (behavioral CSVs) |
| `lev1_outlier` | `lev1_outliers.csv` from `neuro_workflow.qa.lev1_outliers` cohort QC |
| `qa_decisions` | `decisions.tsv` from the qa_report UI |

### Lev1/lev2 outputs

| Path | Role |
|---|---|
| `<lev1_dir>/sub-*/<task>/fixed_effects/*_stat-fixed-effects.nii.gz` | Subject-level fixed-effects maps; `_desc-belowMinRuns_` substring marks low-N |
| `<lev2_dir>/<contrast>/...` | Group-level FSL randomise outputs |

### Code

| Path | Role |
|---|---|
| `src/neuro_workflow/exclusions/base.py` | Protocol, registry, `_git_sha`, `_jsonify`, `make_meta`, `load_dataset_subjects` |
| `src/neuro_workflow/exclusions/{motion,behavioral,lev1_outlier,qa_decisions}.py` | Per-generator implementations |
| `src/neuro_workflow/core/exclusions.py` | `save_source_entries`, `compile_exclusions`, `_lockfile_path`, override merging |
| `src/neuro_workflow/cli.py` | `neuro-run exclusions {generate,compile,show,import}` subcommands |
| `src/neuro_workflow/analysis/lev1/processing/fixed_effects.py` | `FixedEffectsAnalyzer._build_base_filename` (writes `_desc-belowMinRuns`) |
| `src/neuro_workflow/analysis/lev2/run.py` | `discover_input_files` (filters `_desc-belowMinRuns_`) |
| `src/neuro_workflow/qa/decisions.py` | `load_decisions(tsv)` shared loader |

---

## See also

- `docs/WORKFLOW.md` — the full pipeline (BIDSify → fmriprep → lev1 → lev2)
- `docs/EXCLUSIONS.md` — per-`.bidsignore`-entry rationale
- `docs/SCAN-NOTES.md` — raw data collection notes
- `docs/archive/superpowers/specs/` — design specs for each exclusion feature (Project B + C)
