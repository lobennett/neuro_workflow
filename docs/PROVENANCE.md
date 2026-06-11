# Provenance

**Last updated:** 2026-06-09

Every lev1 and lev2 run automatically records its provenance. This document describes what is captured, where it lands, and how the clean-tree policy works.

---

## What is recorded

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

---

## Where outputs land

```
<output_dir>/
├── run-manifest.json
└── dataset_description.json
```

For lev1, `<output_dir>` is the per-subject results directory (e.g., `derivatives/lev1/sub-s10/`). For lev2, it is the group-level output directory.

---

## config_version

`config_version()` in `core/thresholds.py` returns a 12-character sha256 hash of the raw bytes of `config/thresholds.yaml` and `src/neuro_workflow/analysis/task_config/battery.yaml` (in that fixed order). Any edit to either file produces a new hash. The value is recorded in every `run-manifest.json`, so you can tell at a glance whether two runs used the same study-level thresholds and task battery.

---

## Clean-tree policy

By default, a lev1 or lev2 run warns loudly to stderr if the working tree has uncommitted changes, but the run still proceeds. The manifest records `code_dirty: true` in that case.

To suppress the warning (e.g., during active development):
```bash
uv run neuro-run submit lev1 discovery --allow-dirty
```

To enforce a hard failure on a dirty tree (stricter reproducibility enforcement), use `require_clean_tree(allow_dirty=False)` programmatically from `core/provenance`.

---

## Python API

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
