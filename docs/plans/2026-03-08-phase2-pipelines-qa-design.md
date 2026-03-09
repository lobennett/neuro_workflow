# Design: Phase 2 — New Pipelines + QA Scripts

## Goal

Consolidate `custom_scripts/` into the neuro-workflow package. Add 4 container pipelines (qsiprep, happy, freesurfer, fsqc) and 5 QA scripts (outlier-report, breaks, global-signal, reliability, neg-events).

## Architecture

Two registration systems matching two different concerns:

- **Pipelines** — container-based SLURM array jobs. Follow the existing `Pipeline` protocol. Invoked via `neuro-run submit <pipeline> <dataset>`.
- **QA scripts** — Python analysis/figures. Follow a new `QaCommand` protocol. Invoked via `neuro-run qa <script> <dataset>`.

All paths come from the registered dataset config + CLI args. No hardcoded paths.

## Package Structure (additions)

```
src/neuro_workflow/
├── pipelines/
│   ├── qsiprep.py          # QSIPrep diffusion preprocessing
│   ├── happy.py             # Rapidtide cardiac phase removal (with auto-prepare)
│   ├── freesurfer.py        # FreeSurfer recon-all (deprecated)
│   └── fsqc.py              # FreeSurfer QC validation
├── qa/
│   ├── __init__.py
│   ├── base.py              # QaCommand protocol + registry
│   ├── outlier_report.py    # VIF + outlier analysis + figures
│   ├── breaks.py            # Break/feedback detection in behavioral data
│   ├── global_signal.py     # Global signal QA plots
│   ├── reliability.py       # Reliability movie generator
│   └── neg_events.py        # Event file monotonicity checker
└── templates/
    ├── qsiprep.sbatch
    ├── happy.sbatch
    ├── freesurfer.sbatch
    └── fsqc.sbatch
```

## New Pipeline Definitions

### qsiprep

```bash
neuro-run submit qsiprep discovery --version 1.1.1 --output-resolution 1.5
```

- **Container:** `docker://pennlinc/qsiprep`
- **Default resources:** 8 CPUs, 8GB/cpu, 24h
- **CLI args:** `--version` (required), `--output-resolution` (default: 1.5), `--qsiprep-args` (passthrough)
- **Template:** Standard apptainer run with BIDS I/O, participant-level, array over subjects

### happy

```bash
neuro-run submit happy discovery --version 3.1.8
```

- **Container:** `docker://fredericklab/rapidtide`
- **Default resources:** 4 CPUs, 2GB/cpu, 10min
- **CLI args:** `--version` (required), `--happy-args` (passthrough)
- **Special behavior:** `build_context` auto-discovers BOLD + physio file pairs in the BIDS directory, writes a scan list to `{derivatives}/happy/scan_list.txt`, and sets `--array=1-N` based on scan count (not subject count). Each SLURM task processes one scan.
- **Template:** Reads scan list line-by-line, extracts BOLD/physio paths per task

### freesurfer (deprecated)

```bash
neuro-run submit freesurfer discovery --version 8.1.0 --subjects-file subs_discovery_fs.csv
```

- **Container:** local SIF at `{image_dir}/freesurfer_{version}.sif`
- **Default resources:** 4 CPUs, 16GB/cpu, 4 days
- **CLI args:** `--version` (required), `--subjects-file` (overrides dataset subjects file; expects CSV with subject_id, ses_t1, run_t1, ses_t2, run_t2)
- **Template:** Parses CSV row per array task, runs `recon-all` with T1w (and optional T2w)
- **Minimal engineering** — wraps existing script as-is

### fsqc

```bash
neuro-run submit fsqc discovery --version 2.1.4 --freesurfer-dir /path/to/freesurfer
```

- **Container:** `docker://deepmi/fsqc`
- **Default resources:** 4 CPUs, 8GB/cpu, 2 days
- **CLI args:** `--version` (required), `--freesurfer-dir` (required: path to freesurfer derivatives), `--fsqc-args` (passthrough)
- **Template:** Uses `xvfb-run` for headless rendering, processes all subjects in one job (no array)

## QA Command Protocol

```python
class QaCommand(Protocol):
    name: str
    description: str

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None: ...
```

Registration follows the same pattern as pipelines: a `_REGISTRY` dict, `register()`, `get_qa_command()`, `list_qa_commands()`.

CLI: `neuro-run qa <command> <dataset> [args]`

### QA Scripts

#### outlier-report

```bash
neuro-run qa outlier-report discovery --lev1-dirs /path/to/lev1 --exclusions-file /path/to/exclusions.json --output-dir /scratch/output
```

Analyzes first-level GLM contrasts for VIF and outlier percentages. Generates QA figures (PNG/PDF) and summary CSVs. Ported from `run_network.py`, `run_report.py`, `plotting_functions.py`.

#### breaks

```bash
neuro-run qa breaks discovery --behavioral-dir /oak/.../behavioral_data/raw_cleaned --output-dir data/
```

Analyzes behavioral CSVs to identify breaks with performance feedback. Outputs JSON files. Ported from `run_breaks.py`.

#### global-signal

```bash
neuro-run qa global-signal discovery --output-dir /scratch/global_signal_figs
```

Calculates and plots global signal from echo-2 BOLD data. Outputs per-subject PNGs and a combined PDF. Ported from `run_global_signal.py`.

#### reliability

```bash
neuro-run qa reliability discovery --fmriprep-version 24.1.0rc2 --output-dir /path/to/reliability_figs
```

Creates MP4 movies showing fMRI reliability across sessions. Uses fmriprep derivatives (T1w-space preprocessed BOLD). Ported from `run_visualize_reliability.py`.

#### neg-events

```bash
neuro-run qa neg-events discovery
```

Reports event files with non-monotonically increasing onsets. Console output only. Ported from `run_neg_events.py`.

## Dependencies

Core package remains zero-dependency. QA extras declared in `pyproject.toml`:

```toml
[project.optional-dependencies]
qa = [
    "nilearn>=0.12",
    "nibabel>=5.0",
    "matplotlib>=3.0",
    "pandas>=2.0",
    "numpy>=1.24",
    "img2pdf>=0.5",
]
```

Install: `uv pip install -e ".[qa]"`

Each QA command checks for required imports at runtime and prints a clear error if missing:
```
Error: 'nilearn' required for 'outlier-report'. Install with: uv pip install -e ".[qa]"
```

## CLI Changes

```python
# In main(), add qa subcommand:
qa_p = subparsers.add_parser("qa", help="Run QA analysis scripts")
qa_p.add_argument("command", help="QA command name")
qa_p.add_argument("dataset", help="Dataset name")
# QA-command-specific args added dynamically
```

## Implementation Order

1. Add `qa/base.py` with QaCommand protocol and registry
2. Add qsiprep pipeline (most similar to fmriprep)
3. Add fsqc pipeline
4. Add freesurfer pipeline (deprecated, minimal)
5. Add happy pipeline (most complex — auto-prepare)
6. Add `neuro-run qa` CLI subcommand
7. Port `neg-events` QA (simplest — no deps beyond pandas)
8. Port `breaks` QA
9. Port `global-signal` QA
10. Port `outlier-report` QA (most complex — multiple files)
11. Port `reliability` QA
12. Add optional QA dependencies to pyproject.toml
13. Remove `custom_scripts/` directory
14. Update README
