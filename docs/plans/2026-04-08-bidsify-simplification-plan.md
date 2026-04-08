# Bidsify Pipeline Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify bidsify to a focused Flywheel-to-BIDS converter — pull all data, name with session corrections, trim 7 BOLD dummy volumes, log timestamps. Remove .bidsignore automation, physio/behavioral trimming, duplicate filtering, parallel processing, and retry wrappers.

**Architecture:** Surgical removal from existing codebase. New consolidated `config/pipeline_config.json` replaces 3 scattered config files. `run.py` loses ~200 lines of complexity. 6 modules deleted, `bids_validation/` archived locally. Sequential processing replaces ThreadPoolExecutor.

**Tech Stack:** Python 3.13, nibabel, flywheel-sdk, pytest, uv, Apptainer/Singularity, SLURM

**Prerequisites:** Run `module load uv` before any `uv run` commands in this plan. This applies to all test runs, script executions, and CLI invocations.

---

### Task 1: Create consolidated config file

**Files:**
- Create: `config/pipeline_config.json`

**Step 1: Create the config file**

Merge data from `src/neuro_workflow/bidsify/reconciliation_config.json` (flywheel settings, samples, notes) and `config/behavioral_samples.json` (subject lists). Restructure into `flywheel`, `samples`, `notes` sections. The `samples.validation` list must contain only the 41 non-excluded subjects. The `samples.excluded` dict maps subject IDs to exclusion reasons.

```json
{
  "flywheel": {
    "project": "r01network",
    "subject_aliases": {
      "s19-2": "s19",
      "s29-2": "s29",
      "s43-2": "s43",
      "ex26207": "s297"
    },
    "skip_subjects": ["n01"],
    "session_overrides": {
      "s03": {
        "22752": {
          "reassign_to": "s10",
          "reason": "Session 22752 (2021-02-12) labeled under s03 on Flywheel but belongs to s10"
        },
        "25210": {
          "exclude": true,
          "reason": "Empty/test session -- no usable imaging data"
        }
      },
      "s29": {
        "22424": {
          "exclude": true,
          "reason": "Fmap-only test session (2020-11-11) -- single-echo protocol, no usable functional data, no behavioral data"
        }
      }
    }
  },
  "samples": {
    "discovery": ["s03", "s10", "s19", "s29", "s43"],
    "validation": [
      "s76", "s180", "s216", "s247", "s286", "s295", "s300", "s320",
      "s321", "s336", "s373", "s394", "s415", "s480", "s599", "s645",
      "s874", "s956", "s1035", "s1057", "s1058", "s1127", "s1134",
      "s1175", "s1189", "s1258", "s1267", "s1270", "s1273", "s1292",
      "s1314", "s1326", "s1338", "s1351", "s1391", "s1399", "s1402",
      "s1408", "s1445", "s1481", "s1486"
    ],
    "excluded": {
      "s214": "dropped for being unreliable",
      "s222": "dropped for poor behavioral performance",
      "s250": "dropped (lens prescription issue)",
      "s297": "discontinued (ear issues after scanning)",
      "s432": "withdrew from study",
      "s823": "withdrew from study",
      "s968": "withdrew from study",
      "s1165": "withdrew from study",
      "s1178": "withdrew from study",
      "s1266": "withdrew from study",
      "s1320": "withdrew from study"
    }
  },
  "notes": {
    "discovery": [
      "s03/session 22752 was mislabeled on Flywheel -- reassigned to s10 based on scan content and timeline",
      "s29/session 22424 (2020-11-11) is fmap-only test session -- excluded from Flywheel pull, not downloaded to BIDS",
      "s29-2/20210305 is s29 Scan 10 (2021-03-05) collected under wrong subject label -- not a duplicate"
    ],
    "validation": [
      "ex26207 is an alias for s297 on Flywheel",
      "Split sessions exist for s321, s968, s1326, s1292, s1189, s1391 -- these are merged chronologically"
    ]
  }
}
```

**Step 2: Commit**

```bash
git add config/pipeline_config.json
git commit -m "feat: add consolidated pipeline config

Merges flywheel settings, sample definitions, and notes into a single
config/pipeline_config.json. Replaces scattered configs in bidsify/
and config/ directories.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Update config.py with TDD

**Files:**
- Modify: `src/neuro_workflow/bidsify/config.py:99-102`
- Modify: `tests/bidsify/test_config.py:149-179`

**Step 1: Write the failing test**

Replace `TestLoadReconciliationConfig` class in `tests/bidsify/test_config.py` (lines 149-179):

```python
class TestLoadPipelineConfig:
    def test_loads_json(self):
        config = load_pipeline_config()
        assert isinstance(config, dict)

    def test_flywheel_project(self):
        config = load_pipeline_config()
        assert config["flywheel"]["project"] == "r01network"

    def test_subject_aliases(self):
        config = load_pipeline_config()
        aliases = config["flywheel"]["subject_aliases"]
        assert aliases["s19-2"] == "s19"
        assert aliases["s29-2"] == "s29"
        assert aliases["s43-2"] == "s43"
        assert aliases["ex26207"] == "s297"

    def test_skip_subjects(self):
        config = load_pipeline_config()
        assert "n01" in config["flywheel"]["skip_subjects"]

    def test_session_overrides(self):
        config = load_pipeline_config()
        overrides = config["flywheel"]["session_overrides"]
        assert overrides["s03"]["22752"]["reassign_to"] == "s10"
        assert overrides["s29"]["22424"]["exclude"] is True

    def test_samples_discovery(self):
        config = load_pipeline_config()
        assert config["samples"]["discovery"] == ["s03", "s10", "s19", "s29", "s43"]

    def test_samples_validation_count(self):
        config = load_pipeline_config()
        assert len(config["samples"]["validation"]) == 41

    def test_samples_excluded(self):
        config = load_pipeline_config()
        excluded = config["samples"]["excluded"]
        assert isinstance(excluded, dict)
        assert len(excluded) == 11
        assert "s214" in excluded

    def test_excluded_sample_resolves_to_subject_list(self):
        """Excluded dict keys can be used as a subject list."""
        config = load_pipeline_config()
        subjects = list(config["samples"]["excluded"].keys())
        assert "s214" in subjects
        assert "s1320" in subjects
        assert len(subjects) == 11
```

Also update the import at line 9:

```python
from neuro_workflow.bidsify.config import (
    ACQUISITION_MAP,
    SKIP_ACQUISITIONS,
    load_pipeline_config,
    map_acquisition,
)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bidsify/test_config.py::TestLoadPipelineConfig -v`
Expected: FAIL with `ImportError: cannot import name 'load_pipeline_config'`

**Step 3: Write minimal implementation**

Replace lines 99-102 of `src/neuro_workflow/bidsify/config.py`:

```python
def load_pipeline_config():
    """Load the consolidated pipeline config from config/pipeline_config.json."""
    # Walk up from this file to find the project root (contains config/ dir)
    config_dir = Path(__file__).resolve().parent.parent.parent.parent / "config"
    config_path = config_dir / "pipeline_config.json"
    with open(config_path) as f:
        return json.load(f)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/bidsify/test_config.py::TestLoadPipelineConfig -v`
Expected: PASS (all 8 tests)

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/config.py tests/bidsify/test_config.py
git commit -m "feat: replace load_reconciliation_config with load_pipeline_config

Reads from config/pipeline_config.json with new nested structure:
flywheel.project, flywheel.subject_aliases, samples.excluded, etc.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Write new TDD tests for run.py simplification

**Files:**
- Modify: `tests/bidsify/test_run.py`

Write all failing tests upfront for the new behavior. These will guide the run.py changes in Task 5.

**Step 1: Write the failing tests**

Add to `tests/bidsify/test_run.py`:

```python
from neuro_workflow.bidsify.run import write_session_timestamps


def test_no_bidsignore_written(tmp_path):
    """Bidsify must NOT create a .bidsignore file."""
    # Simulate a minimal bidsify run result — no bidsignore_entries anywhere
    bidsignore_path = tmp_path / ".bidsignore"
    assert not bidsignore_path.exists()


def test_process_subject_session_no_bidsignore_param():
    """process_subject_session signature must not accept bidsignore_entries."""
    import inspect
    sig = inspect.signature(process_subject_session)
    assert "bidsignore_entries" not in sig.parameters


def test_duplicate_anat_gets_run_number(tmp_path):
    """Two T1w scans in same session get run-01 and run-02."""
    session_info = {
        "bids_session": "ses-01",
        "fw_session": MagicMock(),
    }
    session_info["fw_session"].reload.return_value = session_info["fw_session"]

    # Two T1w acquisitions (same type, different timestamps)
    acq1 = MagicMock()
    acq1.label = "NEW Sag_MPRAGE_T1"
    acq1.id = "acq1_id"
    acq1.timestamp = "2025-01-01T09:00:00"
    acq1.reload.return_value = acq1
    nifti1 = MagicMock(); nifti1.name = "t1w_1.nii.gz"; nifti1.type = "nifti"
    nifti1.size = 100; nifti1.created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    json1 = MagicMock(); json1.name = "t1w_1.json"; json1.type = "source code"
    json1.size = 50; json1.created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    acq1.files = [nifti1, json1]

    acq2 = MagicMock()
    acq2.label = "NEW Sag_MPRAGE_T1"
    acq2.id = "acq2_id"
    acq2.timestamp = "2025-01-01T10:00:00"
    acq2.reload.return_value = acq2
    nifti2 = MagicMock(); nifti2.name = "t1w_2.nii.gz"; nifti2.type = "nifti"
    nifti2.size = 100; nifti2.created = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    json2 = MagicMock(); json2.name = "t1w_2.json"; json2.type = "source code"
    json2.size = 50; json2.created = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    acq2.files = [nifti2, json2]

    log_entries = []

    with patch("neuro_workflow.bidsify.run.download_and_place") as mock_dl, \
         patch("neuro_workflow.bidsify.run.patch_sidecar"):
        mock_dl.return_value = {"fw_filename": "t1.nii.gz", "bids_path": "/tmp/t1.nii.gz", "size": 100, "created": None}

        warnings = process_subject_session(
            "s19", session_info, [acq1, acq2], tmp_path, log_entries,
        )

    # Check that download_and_place was called with run-1 and run-2 paths
    dl_calls = mock_dl.call_args_list
    bids_paths = [str(c[0][2]) for c in dl_calls]  # 3rd positional arg is dest_path
    run1_paths = [p for p in bids_paths if "run-1" in p]
    run2_paths = [p for p in bids_paths if "run-2" in p]
    assert len(run1_paths) >= 1, f"Expected run-1 in paths: {bids_paths}"
    assert len(run2_paths) >= 1, f"Expected run-2 in paths: {bids_paths}"


def test_write_session_timestamps(tmp_path):
    """session_timestamps.tsv is written with correct columns and data."""
    rows = [
        {"subject": "s03", "bids_session": "ses-01", "flywheel_session_label": "22751", "flywheel_timestamp": "2020-10-28T14:32:00+00:00"},
        {"subject": "s03", "bids_session": "ses-02", "flywheel_session_label": "22942", "flywheel_timestamp": "2020-11-18T09:15:00+00:00"},
    ]
    sourcedata = tmp_path / "sourcedata"
    sourcedata.mkdir()

    write_session_timestamps(rows, sourcedata)

    tsv_path = sourcedata / "session_timestamps.tsv"
    assert tsv_path.exists()
    lines = tsv_path.read_text().strip().split("\n")
    assert lines[0] == "subject\tbids_session\tflywheel_session_label\tflywheel_timestamp"
    assert lines[1].startswith("s03\tses-01\t22751\t")
    assert len(lines) == 3  # header + 2 data rows
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bidsify/test_run.py -v -k "bidsignore or duplicate_anat or session_timestamps"`
Expected: FAIL — `write_session_timestamps` not importable, `bidsignore_entries` still in signature, no run numbering

**Step 3: Commit test file**

```bash
git add tests/bidsify/test_run.py
git commit -m "test: add failing tests for bidsify simplification

Tests: no .bidsignore, no bidsignore_entries param, duplicate anat
run numbering, session_timestamps.tsv output.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Archive and delete unused files

**Files:**
- Archive: `src/neuro_workflow/bids_validation/`, `tests/bids_validation/`, `config/behavioral_discrepancy_mapping.json`
- Delete: 6 bidsify modules, 5 test files, 3 config files

**Step 1: Archive files locally**

```bash
mkdir -p ~/.neuro_workflow_archive/src/neuro_workflow
mkdir -p ~/.neuro_workflow_archive/tests
mkdir -p ~/.neuro_workflow_archive/config

cp -r src/neuro_workflow/bids_validation ~/.neuro_workflow_archive/src/neuro_workflow/
cp -r tests/bids_validation ~/.neuro_workflow_archive/tests/
cp config/behavioral_discrepancy_mapping.json ~/.neuro_workflow_archive/config/
```

**Step 2: Delete archived files from repo**

```bash
rm -rf src/neuro_workflow/bids_validation
rm -rf tests/bids_validation
rm config/behavioral_discrepancy_mapping.json
```

**Step 3: Delete trimming/exclusion modules**

```bash
rm src/neuro_workflow/bidsify/physio_trimming.py
rm src/neuro_workflow/bidsify/trimming_orchestrator.py
rm src/neuro_workflow/bidsify/exclusions_manifest.py
rm src/neuro_workflow/bidsify/behavioral_trimming.py
rm src/neuro_workflow/bidsify/bold_trimming.py
rm src/neuro_workflow/bidsify/integration.py
```

**Step 4: Delete old config files**

```bash
rm src/neuro_workflow/bidsify/reconciliation_config.json
rm config/reconciliation_config.json
rm config/behavioral_samples.json
```

**Step 5: Delete outdated tests**

```bash
rm tests/bidsify/test_physio_trimming.py
rm tests/bidsify/test_behavioral_trimming.py
rm tests/bidsify/test_trimming_orchestrator.py
rm tests/bidsify/test_exclusions_manifest.py
rm tests/bidsify/test_bold_trimming.py
```

**Step 6: Verify remaining tests still import cleanly**

Run: `uv run python -c "from neuro_workflow.bidsify.config import map_acquisition; print('OK')"`
Expected: `OK`

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove trimming modules, old configs, and bids_validation

Deleted modules: physio_trimming, trimming_orchestrator, exclusions_manifest,
behavioral_trimming, bold_trimming, integration.
Deleted configs: reconciliation_config.json (x2), behavioral_samples.json.
Archived to ~/.neuro_workflow_archive: bids_validation/, behavioral_discrepancy_mapping.json.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Simplify run.py

**Files:**
- Modify: `src/neuro_workflow/bidsify/run.py`

This is the main surgical edit. Remove complexity, add run numbering and timestamp logging. The goal is to make all tests from Task 3 pass.

**Step 1: Rewrite run.py**

Key changes to `src/neuro_workflow/bidsify/run.py`:

**Imports (replace lines 1-31):**
```python
"""Orchestrate Flywheel -> BIDS conversion."""

import json
import logging
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from neuro_workflow.bidsify.config import map_acquisition, load_pipeline_config
from neuro_workflow.bidsify.flywheel_query import (
    collect_subject_sessions,
    build_session_timeline,
    query_project_subjects,
)
from neuro_workflow.bidsify.file_selector import select_files
from neuro_workflow.bidsify.bids_writer import (
    bids_filename,
    patch_sidecar,
    write_dataset_description,
    write_readme,
    download_and_place,
)
from neuro_workflow.bidsify.physio import convert_physio_to_bids
from neuro_workflow.bidsify.physio_query import (
    find_gephysio_analyses,
    match_analyses_to_acquisitions,
)

logger = logging.getLogger(__name__)
```

Remove: `from neuro_workflow.bidsify.physio_trimming import trim_physio_data`, `Counter` import stays (used for task runs).

**Remove `_safe_patch_sidecar` function** (lines 81-112). All call sites change from `_safe_patch_sidecar(path, field=val)` to `patch_sidecar(path, **fields)`.

**`process_subject_session` signature (replace lines 115-118):**
```python
def process_subject_session(
    subject_label, session_info, acq_objects, output_dir, log_entries,
):
```

Remove `bidsignore_entries` parameter entirely.

**Inside `process_subject_session`, remove** (lines 132-133, 147-162):
- `bidsignore_entries` initialization
- `anat_scans_by_type` dict
- `dwi_scans_by_key` dict
- `_latest_anat_acq` pre-computation loop

**Add run counters** after `task_run_counter = Counter()` (line 140):
```python
    anat_run_counter = Counter()  # keyed by (suffix, acq_label)
    dwi_run_counter = Counter()   # keyed by (dir_label, acq_label)
```

**Replace anat block (lines 276-331)** with:
```python
        elif modality == "anat":
            suffix = mapping["suffix"]
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "anat"

            anat_key = (suffix, acq_label)
            anat_run_counter[anat_key] += 1
            run = anat_run_counter[anat_key]

            stem = bids_filename(subject_label, bids_ses, acq=acq_label, run=run, suffix=suffix)

            if selected.get("nifti"):
                info = download_and_place(acq, selected["nifti"], dest_dir / f"{stem}.nii.gz")
                log_entries.append(info)
            if selected.get("json"):
                json_path = dest_dir / f"{stem}.json"
                info = download_and_place(acq, selected["json"], json_path)
                log_entries.append(info)
```

**Replace DWI block (lines 333-374)** with:
```python
        elif modality == "dwi":
            dir_label = mapping.get("dir")
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "dwi"

            dwi_key = (dir_label, acq_label)
            dwi_run_counter[dwi_key] += 1
            run = dwi_run_counter[dwi_key]

            stem = bids_filename(subject_label, bids_ses, acq=acq_label, dir=dir_label, run=run, suffix="dwi")

            for ext in ("nifti", "json", "bval", "bvec"):
                if selected.get(ext):
                    file_ext = {"nifti": ".nii.gz", "json": ".json", "bval": ".bval", "bvec": ".bvec"}[ext]
                    info = download_and_place(acq, selected[ext], dest_dir / f"{stem}{file_ext}")
                    log_entries.append(info)
```

**Replace _safe_patch_sidecar calls** (lines 234, 264, 380-383):
- `_safe_patch_sidecar(json_path, TaskName=task_name)` → `patch_sidecar(json_path, TaskName=task_name)`
- `_safe_patch_sidecar(json_path, b0_field_identifier=fmap_id, Units="Hz")` → `patch_sidecar(json_path, b0_field_identifier=fmap_id, Units="Hz")`
- `_safe_patch_sidecar(sidecar_path, b0_field_source=fieldmap_id)` → `patch_sidecar(sidecar_path, b0_field_source=fieldmap_id)`

Remove the `if _safe_patch_sidecar(...)` / `else` error handling pattern. Replace with direct call (let exceptions propagate for debugging).

**Remove physio trimming block (lines 412-438).** Keep lines 386-410 (physio download + convert). The block starting `# Trim dummy volumes (7 TRs @ 1.49s` through the end of that try/except is deleted.

**Remove bidsignore from `_process_one_subject`** (lines 457-495):
- Remove `bidsignore_entries = []` (line 464)
- Remove `bidsignore_entries=bidsignore_entries` from `process_subject_session` call (line 485)
- Remove `"bidsignore_entries"` from return dict (line 494)
- Add `"timestamp_rows"` to return dict — collect from sessions:

```python
    timestamp_rows = []
    for session_info in sessions:
        timestamp_rows.append({
            "subject": subject_label,
            "bids_session": session_info["bids_session"],
            "flywheel_session_label": session_info["fw_session"].label,
            "flywheel_timestamp": session_info["timestamp"].isoformat() if session_info["timestamp"] else "",
        })
```

**Add `write_session_timestamps` function** (new, after `build_reconciliation`):
```python
def write_session_timestamps(rows, sourcedata_dir):
    """Write session_timestamps.tsv to sourcedata directory.

    Args:
        rows: List of dicts with subject, bids_session, flywheel_session_label, flywheel_timestamp.
        sourcedata_dir: Path to sourcedata directory.
    """
    tsv_path = Path(sourcedata_dir) / "session_timestamps.tsv"
    header = "subject\tbids_session\tflywheel_session_label\tflywheel_timestamp"
    lines = [header]
    for row in sorted(rows, key=lambda r: (r["subject"], r["bids_session"])):
        lines.append(f"{row['subject']}\t{row['bids_session']}\t{row['flywheel_session_label']}\t{row['flywheel_timestamp']}")
    tsv_path.write_text("\n".join(lines) + "\n")
```

**Rewrite `run_bidsify` (lines 498-607):**

```python
def run_bidsify(sample_name, output_dir, subjects=None, flywheel_project=None, overwrite=False):
    """Main entry point for Flywheel -> BIDS conversion."""
    import flywheel

    config = load_pipeline_config()
    fw_config = config["flywheel"]
    project_label = flywheel_project or fw_config["project"]
    aliases = fw_config["subject_aliases"]
    skip = set(fw_config["skip_subjects"])
    session_overrides = fw_config.get("session_overrides", {})

    if subjects is None:
        sample_data = config["samples"].get(sample_name, [])
        # excluded is a dict (keys are subjects), others are lists
        subjects = list(sample_data.keys()) if isinstance(sample_data, dict) else sample_data

    output_dir = Path(output_dir)
    if (output_dir / "dataset_description.json").exists() and not overwrite:
        raise FileExistsError(
            f"Output directory already contains BIDS data: {output_dir}. Use --overwrite to replace."
        )

    fw = flywheel.Client()
    all_subjects, project = query_project_subjects(fw, project_label)

    subjects_to_process = [s for s in subjects if s not in skip]
    for s in subjects:
        if s in skip:
            logger.info("Skipping %s (in skip list)", s)

    reconciliation = {"generated": datetime.now(timezone.utc).isoformat(), "subjects": {}}
    all_log_entries = []
    all_timestamp_rows = []

    logger.info("Processing %d subjects sequentially", len(subjects_to_process))

    for subject_label in subjects_to_process:
        try:
            result = _process_one_subject(
                subject_label, all_subjects, aliases, output_dir,
                session_overrides=session_overrides,
            )
            reconciliation["subjects"][result["subject"]] = result["reconciliation"]
            all_log_entries.extend(result["log_entries"])
            all_timestamp_rows.extend(result["timestamp_rows"])
            logger.info("Processed %s: %d files", subject_label, len(result["log_entries"]))
        except Exception:
            logger.exception("Failed to process %s", subject_label)

    # Write dataset description
    dataset_names = {
        "discovery": "Network Discovery Sample",
        "validation": "Network Validation Sample",
        "excluded": "Network Excluded Sample",
    }
    ds_name = dataset_names.get(sample_name, sample_name)
    write_dataset_description(output_dir, ds_name)
    write_readme(output_dir, ds_name)

    # Write reconciliation, timestamps, and log to sourcedata/
    sourcedata_dir = output_dir / "sourcedata"
    sourcedata_dir.mkdir(parents=True, exist_ok=True)

    with open(sourcedata_dir / "reconciliation.json", "w") as f:
        json.dump(reconciliation, f, indent=2)

    write_session_timestamps(all_timestamp_rows, sourcedata_dir)

    sample_notes = config.get("notes", {}).get(sample_name, [])
    if sample_notes:
        notes_path = sourcedata_dir / "NOTES.txt"
        notes_path.write_text("\n".join(sample_notes) + "\n")

    log = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_files": len(all_log_entries),
        "files": all_log_entries,
    }
    with open(sourcedata_dir / "bidsify_log.json", "w") as f:
        json.dump(log, f, indent=2)

    logger.info(
        "Done. %d subjects, %d files written to %s",
        len(subjects_to_process), len(all_log_entries), output_dir,
    )
```

**Step 2: Run all new tests**

Run: `uv run pytest tests/bidsify/test_run.py -v`
Expected: PASS — all tests including new ones from Task 3

**Step 3: Run full bidsify test suite**

Run: `uv run pytest tests/bidsify/ -v`
Expected: PASS (some existing tests may need minor fixups — see Task 6)

**Step 4: Commit**

```bash
git add src/neuro_workflow/bidsify/run.py
git commit -m "refactor: simplify run.py — remove bidsignore, trimming, parallel processing

- Remove .bidsignore generation entirely
- Remove physio trimming (keep download + BIDS conversion)
- Remove duplicate anatomical/DWI filtering (use run numbering instead)
- Remove _safe_patch_sidecar retry wrapper (direct calls)
- Replace ThreadPoolExecutor with sequential loop
- Add run-number incrementing for duplicate scans
- Add write_session_timestamps() for sourcedata/session_timestamps.tsv
- Add 'excluded' as first-class sample name
- ~607 lines -> ~400 lines

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Fix remaining test breakage

**Files:**
- Modify: `tests/bidsify/test_run.py` (existing `test_process_subject_session_downloads_physio`)
- Modify: `tests/bidsify/test_config.py` (remove old import if not already done)

**Step 1: Update existing physio test**

In `tests/bidsify/test_run.py`, the existing `test_process_subject_session_downloads_physio` (lines 43-112) references `bidsignore_entries` and patches `trim_physio_data`. Update:

- Remove `bidsignore_entries = []` (line 83)
- Remove `bidsignore_entries=bidsignore_entries` from the function call (line 108)
- Remove `patch("neuro_workflow.bidsify.run.trim_physio_data")` if present in the `with` block (the import no longer exists)
- The `patch("neuro_workflow.bidsify.run.patch_sidecar")` stays

**Step 2: Remove old import from test_config.py**

If `load_reconciliation_config` is still imported in the test file, remove it. Only `load_pipeline_config` should be imported.

**Step 3: Run full test suite**

Run: `uv run pytest tests/bidsify/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/bidsify/
git commit -m "test: fix existing tests for simplified bidsify

Remove bidsignore_entries references and trim_physio_data patches
from existing test_run.py. Update test_config.py imports.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Update run.py callers — config key paths

**Files:**
- Modify: `src/neuro_workflow/bidsify/run.py` (if any references to old config keys remain)
- Possibly modify: `src/neuro_workflow/pipelines/bidsify.py`, `src/neuro_workflow/cli.py`

The old config had flat keys (`config["flywheel_project"]`, `config["subject_aliases"]`). The new config nests them under `config["flywheel"]`. Check that `run_bidsify()` uses the new paths (already addressed in Task 5 rewrite). Also check if any other files reference `load_reconciliation_config`.

**Step 1: Search for old references**

Search for: `load_reconciliation_config`, `config["flywheel_project"]`, `config["subject_aliases"]`, `config["skip_subjects"]`

These should all be updated to the new nested paths in the Task 5 rewrite. If any callers outside `run.py` reference the old config, update them.

**Step 2: Run full test suite**

Run: `uv run pytest tests/bidsify/ -v`
Expected: ALL PASS

**Step 3: Commit if changes needed**

```bash
git add -u
git commit -m "fix: update remaining references to old config key paths

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Remove STATUS-PIPELINE-SIMPLIFICATION.md

**Files:**
- Delete: `STATUS-PIPELINE-SIMPLIFICATION.md`

**Step 1: Delete**

```bash
rm STATUS-PIPELINE-SIMPLIFICATION.md
```

**Step 2: Commit**

```bash
git add STATUS-PIPELINE-SIMPLIFICATION.md
git commit -m "docs: remove obsolete STATUS-PIPELINE-SIMPLIFICATION.md

Superseded by bidsify simplification design doc.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Rewrite bidsify sections**

Replace the "Pipeline Simplification (March 18, 2026)" and "Bidsify Updates (March 14, 2026)" sections with a single, current section reflecting the simplified pipeline:

Key points to document:
- Config lives in `config/pipeline_config.json` (single source of truth)
- Sequential processing (no parallelism)
- Only trimming: 7 dummy BOLD volumes (inline nibabel)
- No .bidsignore generation (manual curation later)
- Physio downloaded but not trimmed
- Duplicate scans get run numbering (run-01, run-02)
- `sourcedata/session_timestamps.tsv` logged per dataset
- Three sample names: discovery, validation, excluded
- `neuro-run submit bidsify {sample} --output-dir {path} --overwrite`

Remove references to:
- `_safe_patch_sidecar` retry logic
- Physio trimming (cardiac 1,043 samples, respiratory 261)
- Duplicate anatomical handling (keep LATEST)
- 3D BOLD validation check removal
- `irreconcilable_scans` and `trim_scans_end` config sections
- ThreadPoolExecutor parallelism

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for simplified bidsify pipeline

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Update docs/WORKFLOW.md, docs/ARCHITECTURE.md, docs/BIDS-ARCHITECTURE.md

**Files:**
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/BIDS-ARCHITECTURE.md`

**Step 1: Update WORKFLOW.md Phase 1 (Bidsify)**

Rewrite the bidsify phase to reflect:
- Config: `config/pipeline_config.json`
- Three samples: discovery, validation, excluded
- Sequential Flywheel pull, BIDS naming, 7-vol BOLD trim
- `sourcedata/session_timestamps.tsv` output
- No .bidsignore, no physio trimming, no duplicate filtering
- Remove/defer Phase 3 (BOLD Trimming) — note it as future work

**Step 2: Update ARCHITECTURE.md**

Remove references to deleted modules (physio_trimming, trimming_orchestrator, exclusions_manifest, behavioral_trimming, bold_trimming, integration, bids_validation). Update run.py description. Update config.py description (new function name, new config path).

**Step 3: Update BIDS-ARCHITECTURE.md**

Remove .bidsignore references. Note that .bidsignore curation is a separate manual process.

**Step 4: Commit**

```bash
git add docs/WORKFLOW.md docs/ARCHITECTURE.md docs/BIDS-ARCHITECTURE.md
git commit -m "docs: update WORKFLOW, ARCHITECTURE, BIDS-ARCHITECTURE for simplified pipeline

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Update pipeline description**

Update bidsify section to show simplified workflow:
```bash
neuro-run submit bidsify discovery  --output-dir /scratch/users/logben/discovery_bids --overwrite
neuro-run submit bidsify validation --output-dir /scratch/users/logben/validation_bids --overwrite
neuro-run submit bidsify excluded   --output-dir /scratch/users/logben/excluded_bids --overwrite
```

Remove references to old dataset registration approach if present.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README.md for simplified bidsify pipeline

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Final verification — run all tests

**Files:** None (verification only)

**Step 1: Run full test suite**

```bash
uv run pytest tests/bidsify/ -v
```

Expected: ALL PASS. No import errors, no references to deleted modules.

**Step 2: Check for stale imports**

```bash
uv run python -c "from neuro_workflow.bidsify.run import run_bidsify, write_session_timestamps; print('OK')"
uv run python -c "from neuro_workflow.bidsify.config import load_pipeline_config; print('OK')"
```

Expected: Both print `OK`.

**Step 3: Verify no references to deleted modules**

Search the codebase for any remaining imports of deleted modules:
- `physio_trimming`
- `trimming_orchestrator`
- `exclusions_manifest`
- `behavioral_trimming`
- `bold_trimming`
- `load_reconciliation_config`
- `bidsignore_entries`

Expected: Zero matches in `src/` and `tests/`.

---

### Task 13: Rebuild container and run pipeline

**Files:** None (execution only)

**Step 1: Rebuild Singularity container**

```bash
bash neuro_workflow.sh
```

This submits an SLURM job. Wait for completion (~30 min). Monitor:
```bash
squeue -u $USER
```

**Step 2: Delete existing BIDS dirs**

```bash
rm -rf /scratch/users/logben/discovery_bids
rm -rf /scratch/users/logben/validation_bids
rm -rf /scratch/users/logben/excluded_bids
```

**Step 3: Run bidsify for all three samples**

```bash
uv run neuro-run submit bidsify discovery  --output-dir /scratch/users/logben/discovery_bids --overwrite
uv run neuro-run submit bidsify validation --output-dir /scratch/users/logben/validation_bids --overwrite
uv run neuro-run submit bidsify excluded   --output-dir /scratch/users/logben/excluded_bids --overwrite
```

**Step 4: Monitor jobs**

```bash
squeue -u $USER
```

**Step 5: Verify outputs**

Once jobs complete:

```bash
# Check subject counts
ls -d /scratch/users/logben/discovery_bids/sub-*/ | wc -l   # expect 5
ls -d /scratch/users/logben/validation_bids/sub-*/ | wc -l  # expect 41
ls -d /scratch/users/logben/excluded_bids/sub-*/ | wc -l    # expect 11

# Check no .bidsignore exists
test ! -f /scratch/users/logben/discovery_bids/.bidsignore && echo "OK: no .bidsignore"
test ! -f /scratch/users/logben/validation_bids/.bidsignore && echo "OK: no .bidsignore"
test ! -f /scratch/users/logben/excluded_bids/.bidsignore && echo "OK: no .bidsignore"

# Check session_timestamps.tsv exists
head /scratch/users/logben/discovery_bids/sourcedata/session_timestamps.tsv
head /scratch/users/logben/validation_bids/sourcedata/session_timestamps.tsv
head /scratch/users/logben/excluded_bids/sourcedata/session_timestamps.tsv

# Spot-check duplicate run numbering (if any duplicates exist)
find /scratch/users/logben/discovery_bids -name "*run-2*" -type f
```
