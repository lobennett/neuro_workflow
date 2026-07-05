# neuro_workflow Architecture

**Last updated:** 2026-06-09

## Scope

`neuro_workflow` covers the core study pipeline:

```
Flywheel → BIDS → events → exclusions → fMRIPrep → FreeSurfer → QSIPrep → Happy → fsqc → lev1 → lev2
```

MSHBM parcellation, prevalence analysis, parcellation reliability, and XCP-D denoising were extracted into a separate repository (`network_analysis`, at `github.com/lobennett/network_analysis`). They are no longer present in this repo. If you need those pipelines, see that repo.

---

## Package Structure

```
src/neuro_workflow/
├── analysis/                          # First- and second-level GLM analysis
│   ├── config.py                     # Analysis configuration management
│   ├── core/
│   │   ├── task_utils.py             # Task-specific utility functions
│   │   └── utils.py                  # Core analysis utilities
│   ├── io/
│   │   └── file_discovery.py         # BIDS file discovery and indexing
│   ├── lev1/
│   │   ├── prepare.py                # Setup / exclusion loading
│   │   ├── runner.py                 # Orchestration loop over subjects/sessions
│   │   ├── run.py                    # Entry point + argparse (writes provenance)
│   │   └── processing/               # Per-step modules
│   │       ├── confounds.py
│   │       ├── contrasts.py
│   │       ├── design.py
│   │       ├── events.py
│   │       ├── fixed_effects.py
│   │       ├── glm.py
│   │       ├── imaging.py
│   │       ├── masks.py
│   │       ├── quality_control.py
│   │       ├── residuals.py
│   │       └── surface_data.py
│   ├── lev2/
│   │   └── run.py                    # Group-level aggregation (writes provenance)
│   └── task_config/                  # Task battery + per-task YAML configs
│       ├── battery.yaml              # Canonical base/dual task lists (config-as-code)
│       ├── loader.py                 # Load/validate task configs; ContrastFormulaError
│       └── tasks/                    # Per-task YAML files (18 tasks: 8 base + 10 dual)
│
├── bidsify/                           # Flywheel → BIDS conversion
│   ├── bids_writer.py
│   ├── config.py
│   ├── file_selector.py
│   ├── flywheel_query.py
│   ├── physio.py
│   ├── physio_query.py
│   └── run.py
│
├── cli/                               # neuro-run CLI (package, replaces cli.py)
│   ├── __init__.py                   # Entry point + re-exports; auto-registers pipelines
│   ├── _common.py                    # Shared collaborators (get_dataset, submit_sbatch, …)
│   ├── bidsify.py                    # bidsify subcommand handler
│   ├── dataset.py                    # add-dataset subcommand handler
│   ├── events.py                     # events {create,qc,trim} subcommand handlers
│   ├── exclusions.py                 # exclusions {generate,compile,show,import,query,
│   │                                 #             render-md,render-bidsignore} handlers
│   ├── pipelines.py                  # show + submit subcommand handlers
│   └── qa.py                         # qa subcommand handler
│
├── core/                              # Shared utilities
│   ├── acquisition.py                # N_DUMMY, TR_SECONDS (single source of truth)
│   ├── config.py                     # Project-wide configuration loader
│   ├── exclusions.py                 # Exclusion source reading / compile pipeline
│   ├── exclusions_render.py          # render_md, render_bidsignore, drift detection
│   ├── image.py                      # NIfTI/imaging utilities
│   ├── provenance.py                 # write_run_manifest, write_dataset_description,
│   │                                 # require_clean_tree, git_sha, config_version
│   ├── slurm.py                      # SLURM job submission helpers
│   └── thresholds.py                 # load_thresholds, config_version(); loads
│                                     # config/thresholds.yaml at import
│
├── events/                            # Behavioral event file pipeline
│   ├── create.py
│   ├── qc.py
│   ├── qc_globals.py
│   ├── trim.py
│   └── utils.py
│
├── exclusions/                        # Exclusion generators
│   ├── base.py                       # Base class + _git_sha, _jsonify helpers
│   ├── behavioral.py                 # Behavioral-QC exclusion generator
│   ├── lev1_outlier.py               # Lev1 VIF/outlier exclusion generator
│   ├── motion.py                     # Motion exclusion generator
│   └── qa_decisions.py               # QA-decision exclusion generator
│
├── pipelines/                         # SLURM pipeline wrappers
│   ├── base.py                       # ContainerPipeline + LocalAnalysisPipeline base classes
│   ├── bidsify.py
│   ├── fmriprep.py
│   ├── freesurfer.py
│   ├── fsqc.py
│   ├── happy.py
│   ├── lev1.py
│   ├── lev2.py
│   └── qsiprep.py
│
├── qa/                                # Quality-assurance modules
│   ├── base.py
│   ├── cohort.py
│   ├── decisions.py
│   ├── fieldmap_check.py
│   ├── global_signal.py
│   ├── lev1_outliers.py
│   ├── metrics/
│   │   ├── freesurfer.py
│   │   ├── motion.py
│   │   └── outputs.py
│   ├── reliability_movies.py
│   └── report.py
│
├── templates/                         # Jinja2 SLURM sbatch templates
│   ├── bidsify.sbatch
│   ├── fmriprep.sbatch
│   ├── freesurfer.sbatch
│   ├── fsqc.sbatch
│   ├── happy.sbatch
│   ├── lev1.sbatch
│   ├── lev2.sbatch
│   └── qsiprep.sbatch
│
└── testing/
    └── synthetic.py                  # make_events, plant_bold, make_synthetic_run
                                      # (planted-contrast recovery tests)
```

---

## Config Files

```
config/
├── pipeline_config.json              # Subject lists, session overrides, Flywheel aliases
├── thresholds.yaml                   # Study-level QC/motion/VIF thresholds (config-as-code;
│                                     # loaded by core/thresholds.py)
├── bids_filters/                     # BIDS query filters for fmriprep/qsiprep
└── manifests/
    ├── reconciliation_discovery.tsv  # Reviewed behavioral-BOLD manifest (discovery)
    └── reconciliation_validation.tsv # Reviewed behavioral-BOLD manifest (validation)
```

See `docs/CONFIG.md` for the schema and purpose of `thresholds.yaml` and `battery.yaml`.

---

## CLI Surface

`neuro-run` is the single entry point. All subcommands:

```
neuro-run add-dataset   # Register a BIDS dataset with SLURM defaults
neuro-run show          # Preview an sbatch script
neuro-run submit        # Submit a pipeline job (fmriprep, qsiprep, freesurfer, …)
neuro-run bidsify       # Run bidsify directly (no SLURM)
neuro-run events        # events {create, qc, trim}
neuro-run qa            # Run a QA command
neuro-run exclusions    # exclusions {generate, compile, show, import,
                        #             query, render-md, render-bidsignore}
```

The `cli/` package replaced the old flat `cli.py`. Each subsystem lives in its own handler module; `cli/__init__.py` re-exports all public names so existing `monkeypatch.setattr("neuro_workflow.cli.<name>", ...)` test patches keep working.

---

## Key Design Points

### cli/ package (was cli.py)
`src/neuro_workflow/cli/` is a package with per-subsystem handler modules (`pipelines.py`, `qa.py`, `exclusions.py`, `bidsify.py`, `events.py`, `dataset.py`) and a shared `_common.py`. The `__init__.py` re-exports every public symbol from the old flat module so callers and test patches are unaffected.

### Config-as-code
Study-level thresholds that previously lived as hardcoded literals are now in `config/thresholds.yaml`. The task battery (base + dual task lists) lives in `src/neuro_workflow/analysis/task_config/battery.yaml`. Both files feed `config_version()`, a short sha256 hash consumed by the provenance system.

### Contrast-formula validation
`analysis/task_config/loader.py` validates that every contrast formula in a task YAML only references declared regressor names. Invalid formulas raise `ContrastFormulaError` (a `ValueError` subclass) at config-load time, not at GLM-fit time.

### Provenance
`core/provenance.py` provides `write_run_manifest`, `write_dataset_description`, and `require_clean_tree`. Lev1 and lev2 call these automatically: every run emits `<output_dir>/run-manifest.json` and a BIDS-valid `dataset_description.json`. Both accept `--allow-dirty` to permit running against an uncommitted working tree (a warning is printed; `code_dirty` is set to `true` in the manifest). See `docs/PROVENANCE-AND-EXCLUSIONS.md#run-manifest-schema--clean-tree-policy` for the full schema.

### Exclusions commands
`neuro-run exclusions query` reports why a specific scan is excluded or trimmed. `render-md` and `render-bidsignore` regenerate `EXCLUSIONS.md` and `.bidsignore` from the compiled exclusions JSON (outputs carry a DO-NOT-EDIT stamp and support drift detection). Ingestion of the static collection-exclusion tables into the single compiled source is tracked separately (PR5c, pending).

### Synthetic testing
`src/neuro_workflow/testing/synthetic.py` provides `make_events`, `plant_bold`, `make_mask`, and `make_synthetic_run`. These helpers are used by the planted-contrast recovery tests (`tests/analysis/lev1/test_synthetic_recovery.py`) to validate the GLM path end-to-end against known ground truth.

### Fork extraction
MSHBM, prevalence analysis, parcellation reliability, and the XCP-D pipeline are no longer in this repo. They live in the separate `network_analysis` repository (`github.com/lobennett/network_analysis`, source at `/scratch/users/logben/network_analysis`).

---

## Testing

```bash
uv run pytest tests/ --ignore=tests/analysis -q   # Core suite (~570 tests)
uv run pytest tests/ -v                            # Full suite including analysis
uv run pytest tests/analysis/ -v                   # Analysis-only (needs lev1 deps)
```

Test layout mirrors the package: `tests/exclusions/`, `tests/pipelines/`, `tests/qa/`, `tests/analysis/lev1/`, `tests/analysis/lev2/`, `tests/scripts/`.
