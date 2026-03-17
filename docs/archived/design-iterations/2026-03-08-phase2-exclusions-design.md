# Design: Phase 2 — Exclusions Module

## Goal

Add a scan exclusion management system to neuro-workflow that compiles, queries, and audits exclusions from multiple automated and manual sources. Consumed by both QA scripts and GLM pipelines.

## Architecture

Source-based compilation with CLI commands. Each exclusion source is a *generator* — a registered function that scans data and produces exclusion entries with a uniform schema. A compile step merges all sources + manual overrides into a single authoritative file, stored in both the config directory and BIDS derivatives.

## Exclusion Entry Schema

Every entry, regardless of source:

```json
{
  "subject": "sub-s216",
  "session": "ses-05",
  "task": "task-rest",
  "run": "run-1",
  "source": "motion",
  "action": "exclude",
  "reason": "Proportion DVARS > 1.5 (0.222) exceeded threshold (0.2)",
  "metrics": {
    "fmriprep_fd_mean": 0.234,
    "fmriprep_proportion_dvars_over_1.5": 0.222
  }
}
```

Actions: `"exclude"` (full scan removal), `"trim"` (partial — includes trim index in metrics).

Override entries use `"action": "force-include"` or `"action": "force-exclude"`.

## File Layout

```
~/.neuro_workflow/
├── datasets.json
└── exclusions/
    └── {dataset_name}/
        ├── sources/
        │   ├── motion.json
        │   ├── neg_events.json
        │   └── behavioral.json
        ├── overrides.json
        └── compiled_exclusions.json

{bids_dir}/derivatives/exclusions/
└── compiled_exclusions.json        # copy for reproducibility
```

## Package Structure

```
src/neuro_workflow/
├── core/
│   └── exclusions.py              # Schema, load/save, compile, query API
├── exclusions/
│   ├── __init__.py
│   ├── base.py                    # ExclusionGenerator protocol + registry
│   ├── motion.py                  # Reads fmriprep confound TSVs, applies thresholds
│   ├── neg_events.py              # Reads event TSVs, detects non-monotonic onsets
│   └── behavioral.py              # Stub (future automated behavioral QA)

data/exclusions/
├── discovery_overrides.json       # Empty (no manual overrides)
└── validation_overrides.json      # 6 manual behavioral exclusions
```

## ExclusionGenerator Protocol

```python
class ExclusionGenerator(Protocol):
    name: str
    description: str

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]: ...
```

Registration follows the same pattern as Pipeline and QaCommand: `_REGISTRY`, `register()`, `get_generator()`, `list_generators()`.

## Generators

### motion

```bash
neuro-run exclusions generate motion discovery --fmriprep-version 24.1.0rc2
```

- Reads `{bids_dir}/derivatives/fmriprep_{version}/sub-*/ses-*/func/*_desc-confounds_timeseries.tsv`
- Computes: FD mean, FD std, proportion FD > 0.5, DVARS mean, proportion DVARS > 1.5
- Default thresholds: `--fd-threshold 0.2`, `--proportion-fd-threshold 0.2`, `--proportion-dvars-threshold 0.2`
- Resting-state: FD mean threshold. Task scans: proportion-based thresholds.
- Writes `sources/motion.json`

### neg-events

```bash
neuro-run exclusions generate neg-events discovery
```

- Scans `{bids_dir}/sub-*/ses-*/func/*event*.tsv`
- Detects non-monotonic onsets, computes trim index
- Rule: if `rows_to_keep / total_rows > 0.5` -> `"trim"`, else -> `"exclude"`
- Writes `sources/neg_events.json`

### behavioral (stub)

```bash
neuro-run exclusions generate behavioral discovery
```

- Prints message: generator not yet implemented, use overrides.json
- Writes empty `sources/behavioral.json`
- Future: automated behavioral QA criteria from BIDS event files

## CLI Commands

```bash
# Generate exclusions from a source
neuro-run exclusions generate <source> <dataset> [source-specific args]

# Compile all sources + overrides into compiled_exclusions.json
neuro-run exclusions compile <dataset>

# Show summary table
neuro-run exclusions show <dataset>

# Import external exclusion list as a source
neuro-run exclusions import <source-name> <dataset> --input-file <path>
```

## Compile Logic

1. Read all `sources/*.json` files
2. Read `overrides.json`
3. Key each entry by `(subject, session, task, run)`
4. A scan can appear in multiple sources (keep all entries)
5. `"force-include"` overrides remove all exclusions for that scan key
6. `"force-exclude"` overrides add an exclusion regardless of generators
7. Write `compiled_exclusions.json` to config dir + derivatives
8. Print summary table

## Query API

```python
from neuro_workflow.core.exclusions import load_compiled_exclusions, is_excluded, get_trim_info

exclusions = load_compiled_exclusions("discovery")
is_excluded("sub-s216", "ses-05", "task-rest", "run-1", exclusions)  # True
get_trim_info("sub-s03", "ses-11", "task-stopSignalWDirectedForgetting", "run-1", exclusions)
# {"onset_trim_index": 161, "rows_to_keep": 565}
```

## Reference Override Data

### validation_overrides.json

6 manual behavioral exclusions (sub-s1058, sub-s1351, sub-s1273, sub-s1408, sub-s1445, sub-s180).

### discovery_overrides.json

Empty array (no manual overrides).

## Dependencies

Core module (`core/exclusions.py`) — zero external dependencies (stdlib JSON + pathlib).

Generators: motion generator requires pandas and numpy (already in `[qa]` extras). neg-events generator requires pandas (already in `[qa]` extras). behavioral is a stub (no deps).
