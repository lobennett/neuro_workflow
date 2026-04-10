# Scripts Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 10 legacy scripts with 3 focused scripts: trim_bold.py, reconcile_sessions.py, migrate_behavioral.py.

**Architecture:** Three standalone scripts in `scripts/` with no dependency on `neuro_workflow` package modules. Each script uses only stdlib + nibabel (trim only). The reconciliation script produces a TSV manifest that the migration script consumes after human review.

**Tech Stack:** Python 3.13, nibabel, pathlib, argparse, csv, json, re

**Design doc:** `docs/plans/2026-04-09-scripts-consolidation-design.md`

---

### Task 1: Delete old scripts and config

**Files:**
- Delete: `scripts/analyze_bold_scans.py`
- Delete: `scripts/check_behavioral_bold_correspondence.py`
- Delete: `scripts/check_bids_sourcedata_correspondence.py`
- Delete: `scripts/generate_behavioral_mapping.py`
- Delete: `scripts/migrate_archive_behavioral_data.py`
- Delete: `scripts/post_process_bids.py`
- Delete: `scripts/rename_behavioral_to_sourcedata.py`
- Delete: `scripts/resolve_behavioral_discrepancies.py`
- Delete: `scripts/run_behavioral_migration.sh`
- Delete: `scripts/verify_bids_completion.sh`
- Delete: `scripts/__pycache__/` (if present)
- Delete: `config/behavioral_session_mapping.json`

**Step 1: Delete all old scripts and config**

```bash
git rm scripts/analyze_bold_scans.py \
       scripts/check_behavioral_bold_correspondence.py \
       scripts/check_bids_sourcedata_correspondence.py \
       scripts/generate_behavioral_mapping.py \
       scripts/migrate_archive_behavioral_data.py \
       scripts/post_process_bids.py \
       scripts/rename_behavioral_to_sourcedata.py \
       scripts/resolve_behavioral_discrepancies.py \
       scripts/run_behavioral_migration.sh \
       scripts/verify_bids_completion.sh
git rm config/behavioral_session_mapping.json
rm -rf scripts/__pycache__
```

**Step 2: Check for orphaned neuro_workflow.behavioral_archive modules**

Check if `src/neuro_workflow/behavioral_archive/` exists and whether anything besides the deleted scripts imports from it. If nothing else uses it, delete it too.

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: delete legacy scripts and behavioral_session_mapping.json

Replaced by three new scripts: trim_bold.py, reconcile_sessions.py,
migrate_behavioral.py (to be added in subsequent commits).

See docs/plans/2026-04-09-scripts-consolidation-design.md for rationale."
```

---

### Task 2: Write trim_bold.py — failing test

**Files:**
- Create: `scripts/trim_bold.py`
- Create: `tests/scripts/test_trim_bold.py`

**Step 1: Write the test**

```python
"""Tests for scripts/trim_bold.py"""
import json
import numpy as np
import nibabel as nib
from pathlib import Path


def make_bold(tmp_path, sub="s01", ses="ses-01", task="rest", run=1, echo=1, n_vols=163):
    """Create a minimal BOLD NIfTI + sidecar JSON for testing."""
    func_dir = tmp_path / f"sub-{sub}" / ses / "func"
    func_dir.mkdir(parents=True, exist_ok=True)
    stem = f"sub-{sub}_{ses}_task-{task}_run-{run}_echo-{echo}_bold"

    data = np.zeros((2, 2, 2, n_vols), dtype=np.float32)
    img = nib.Nifti1Image(data, np.eye(4))
    nifti_path = func_dir / f"{stem}.nii.gz"
    nib.save(img, str(nifti_path))

    sidecar = {"RepetitionTime": 1.49, "EchoTime": 0.015}
    json_path = func_dir / f"{stem}.json"
    json_path.write_text(json.dumps(sidecar))

    return nifti_path, json_path


def test_trim_removes_7_volumes(tmp_path):
    from scripts.trim_bold import trim_bold_directory

    nifti_path, json_path = make_bold(tmp_path, n_vols=163)

    summary = trim_bold_directory(tmp_path)

    img = nib.load(str(nifti_path))
    assert img.shape[3] == 156

    sidecar = json.loads(json_path.read_text())
    assert sidecar["NumberOfVolumesDiscardedByUser"] == 7

    assert summary["trimmed"] == 1
    assert summary["skipped_already_trimmed"] == 0


def test_trim_is_idempotent(tmp_path):
    from scripts.trim_bold import trim_bold_directory

    nifti_path, json_path = make_bold(tmp_path, n_vols=163)

    trim_bold_directory(tmp_path)
    summary = trim_bold_directory(tmp_path)

    img = nib.load(str(nifti_path))
    assert img.shape[3] == 156
    assert summary["trimmed"] == 0
    assert summary["skipped_already_trimmed"] == 1


def test_trim_skips_short_bold(tmp_path):
    from scripts.trim_bold import trim_bold_directory

    nifti_path, json_path = make_bold(tmp_path, n_vols=1)

    summary = trim_bold_directory(tmp_path)

    img = nib.load(str(nifti_path))
    assert img.shape[3] == 1
    assert summary["trimmed"] == 0
    assert summary["skipped_too_short"] == 1
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scripts/test_trim_bold.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.trim_bold'`

**Step 3: Commit**

```bash
git add tests/scripts/test_trim_bold.py
git commit -m "test: add failing tests for trim_bold.py"
```

---

### Task 3: Write trim_bold.py — implementation

**Files:**
- Create: `scripts/trim_bold.py`

**Step 1: Write the implementation**

```python
#!/usr/bin/env python3
"""Trim 7 dummy volumes from BOLD NIfTIs and update sidecar JSONs.

Usage:
    uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
    uv run python scripts/trim_bold.py /scratch/users/logben/validation_bids
"""
import argparse
import json
import logging
from pathlib import Path

import nibabel as nib

log = logging.getLogger(__name__)

N_DUMMY = 7


def trim_bold_directory(bids_dir: Path) -> dict:
    """Trim dummy volumes from all BOLD NIfTIs in a BIDS directory.

    Returns summary dict with counts of trimmed, skipped_already_trimmed,
    skipped_too_short.
    """
    bids_dir = Path(bids_dir)
    summary = {"trimmed": 0, "skipped_already_trimmed": 0, "skipped_too_short": 0}

    for nifti_path in sorted(bids_dir.glob("sub-*/ses-*/func/*_bold.nii.gz")):
        json_path = nifti_path.with_name(
            nifti_path.name.replace(".nii.gz", ".json")
        )

        # Idempotency check: skip if sidecar already records trimming
        if json_path.exists():
            sidecar = json.loads(json_path.read_text())
            if sidecar.get("NumberOfVolumesDiscardedByUser") == N_DUMMY:
                log.debug("Already trimmed: %s", nifti_path.name)
                summary["skipped_already_trimmed"] += 1
                continue
        else:
            sidecar = {}

        img = nib.load(str(nifti_path))
        n_vols = img.shape[3] if len(img.shape) > 3 else 1

        if n_vols <= N_DUMMY:
            log.warning("Too short to trim (dim4=%d): %s", n_vols, nifti_path.name)
            summary["skipped_too_short"] += 1
            continue

        # Trim first N_DUMMY volumes
        trimmed_data = img.slicer[:, :, :, N_DUMMY:]
        nib.save(trimmed_data, str(nifti_path))

        # Update sidecar
        sidecar["NumberOfVolumesDiscardedByUser"] = N_DUMMY
        if "NumVolumes" in sidecar:
            sidecar["NumVolumes"] = n_vols - N_DUMMY
        json_path.write_text(json.dumps(sidecar, indent=2) + "\n")

        log.info("Trimmed %d -> %d volumes: %s", n_vols, n_vols - N_DUMMY, nifti_path.name)
        summary["trimmed"] += 1

    return summary


def main():
    parser = argparse.ArgumentParser(description="Trim 7 dummy volumes from BOLD NIfTIs")
    parser.add_argument("bids_dir", type=Path, help="BIDS directory to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.bids_dir.exists():
        parser.error(f"Directory not found: {args.bids_dir}")

    summary = trim_bold_directory(args.bids_dir)
    print(f"Trimmed: {summary['trimmed']}")
    print(f"Skipped (already trimmed): {summary['skipped_already_trimmed']}")
    print(f"Skipped (too short): {summary['skipped_too_short']}")


if __name__ == "__main__":
    main()
```

**Step 2: Run tests to verify they pass**

```bash
uv run pytest tests/scripts/test_trim_bold.py -v
```

Expected: 3 PASS

**Step 3: Commit**

```bash
git add scripts/trim_bold.py
git commit -m "feat: add trim_bold.py — trim 7 dummy BOLD volumes with idempotency"
```

---

### Task 4: Write reconcile_sessions.py — task name normalization + tests

**Files:**
- Create: `scripts/reconcile_sessions.py`
- Create: `tests/scripts/test_reconcile_sessions.py`

This task covers only the task name normalization layer, tested independently before adding the full reconciliation logic.

**Step 1: Write the test**

```python
"""Tests for scripts/reconcile_sessions.py"""
from scripts.reconcile_sessions import normalize_task_name


def test_dash_separated():
    assert normalize_task_name("go-nogo") == "goNogo"
    assert normalize_task_name("stop-signal") == "stopSignal"
    assert normalize_task_name("spatial-task-switching") == "spatialTS"
    assert normalize_task_name("cued-task-switching") == "cuedTS"
    assert normalize_task_name("directed-forgetting") == "directedForgetting"
    assert normalize_task_name("shape-matching") == "shapeMatching"
    assert normalize_task_name("n-back") == "nBack"


def test_camel_case_passthrough():
    assert normalize_task_name("goNogo") == "goNogo"
    assert normalize_task_name("stopSignal") == "stopSignal"
    assert normalize_task_name("flanker") == "flanker"
    assert normalize_task_name("nBack") == "nBack"
    assert normalize_task_name("rest") == "rest"


def test_underscore_dual_tasks():
    assert normalize_task_name("stop_signal_with_flanker") == "stopSignalWFlanker"
    assert normalize_task_name("directed_forgetting_with_flanker") == "directedForgettingWFlanker"
    assert normalize_task_name("shape_matching_with_cued_task_switching") == "shapeMatchingWCuedTS"
    assert normalize_task_name("flanker_with_cued_task_switching") == "cuedTSWFlanker"


def test_unknown_returns_none():
    assert normalize_task_name("bogus_task") is None
```

**Step 2: Write the normalization code (top of reconcile_sessions.py)**

```python
#!/usr/bin/env python3
"""Reconcile BIDS functional scans with raw behavioral CSVs.

Produces a TSV manifest for human review (optionally Claude-assisted)
before behavioral migration.

Usage:
    uv run python scripts/reconcile_sessions.py \
        --raw-dir /oak/.../behavioral_data/raw_cleaned \
        --bids-dir /scratch/users/logben/discovery_bids \
        --scan-notes docs/SCAN-NOTES.md \
        --output reconciliation_discovery.tsv
"""
import argparse
import csv
import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Canonical mapping from underscore long names to BIDS camelCase
_LONG_NAME_TO_BIDS = {
    "stop_signal": "stopSignal",
    "flanker": "flanker",
    "go_nogo": "goNogo",
    "n_back": "nBack",
    "cued_task_switching": "cuedTS",
    "spatial_task_switching": "spatialTS",
    "directed_forgetting": "directedForgetting",
    "shape_matching": "shapeMatching",
    "rest": "rest",
    # Dual tasks
    "stop_signal_with_flanker": "stopSignalWFlanker",
    "stop_signal_with_directed_forgetting": "stopSignalWDirectedForgetting",
    "directed_forgetting_with_flanker": "directedForgettingWFlanker",
    "directed_forgetting_with_cued_task_switching": "directedForgettingWCuedTS",
    "cued_task_switching_with_directed_forgetting": "directedForgettingWCuedTS",
    "spatial_task_switching_with_cued_task_switching": "spatialTSWCuedTS",
    "flanker_with_shape_matching": "flankerWShapeMatching",
    "flanker_with_cued_task_switching": "cuedTSWFlanker",
    "n_back_with_shape_matching": "nBackWShapeMatching",
    "n_back_with_spatial_task_switching": "nBackWSpatialTS",
    "shape_matching_with_cued_task_switching": "shapeMatchingWCuedTS",
    "shape_matching_with_spatial_task_switching": "spatialTSWShapeMatching",
}

# Dash-separated aliases (from BIDS-style CSV filenames)
_DASH_TO_BIDS = {
    "go-nogo": "goNogo",
    "stop-signal": "stopSignal",
    "shape-matching": "shapeMatching",
    "spatial-task-switching": "spatialTS",
    "cued-task-switching": "cuedTS",
    "directed-forgetting": "directedForgetting",
    "n-back": "nBack",
}

# Build reverse lookup: camelCase -> camelCase (identity, for passthrough)
_CAMEL_CASE_VALID = set(_LONG_NAME_TO_BIDS.values())


def normalize_task_name(raw: str) -> str | None:
    """Normalize any task name variant to BIDS camelCase.

    Handles: dash-separated (go-nogo), underscore (go_nogo),
    camelCase passthrough (goNogo), dual tasks (stop_signal_with_flanker).

    Returns None if unrecognized.
    """
    if raw in _CAMEL_CASE_VALID:
        return raw
    if raw in _DASH_TO_BIDS:
        return _DASH_TO_BIDS[raw]
    underscore = raw.replace("-", "_")
    if underscore in _LONG_NAME_TO_BIDS:
        return _LONG_NAME_TO_BIDS[underscore]
    return None
```

**Step 3: Run tests**

```bash
uv run pytest tests/scripts/test_reconcile_sessions.py -v
```

Expected: 4 PASS

**Step 4: Commit**

```bash
git add scripts/reconcile_sessions.py tests/scripts/test_reconcile_sessions.py
git commit -m "feat: add task name normalization for reconcile_sessions.py"
```

---

### Task 5: Write reconcile_sessions.py — CSV filename parsing + tests

**Files:**
- Modify: `scripts/reconcile_sessions.py`
- Modify: `tests/scripts/test_reconcile_sessions.py`

**Step 1: Add tests for parsing CSV filenames**

Append to `tests/scripts/test_reconcile_sessions.py`:

```python
from scripts.reconcile_sessions import parse_behavioral_csv


def test_parse_descriptive_style():
    """Pattern: cued_task_switching_single_task_network__fmri_results (5).csv"""
    result = parse_behavioral_csv("cued_task_switching_single_task_network__fmri_results (5).csv")
    assert result == "cuedTS"


def test_parse_descriptive_dual_task():
    result = parse_behavioral_csv("stop_signal_with_flanker_single_task_network__fmri_results (3).csv")
    assert result == "stopSignalWFlanker"


def test_parse_bids_dash_style():
    """Pattern: sub-s03_ses-1_task-go-nogo_desc-raw.csv"""
    result = parse_behavioral_csv("sub-s03_ses-1_task-go-nogo_desc-raw.csv")
    assert result == "goNogo"


def test_parse_bids_camel_style():
    """Pattern: sub-s76_ses-01_task-stopSignal_desc-beh.csv"""
    result = parse_behavioral_csv("sub-s76_ses-01_task-stopSignal_desc-beh.csv")
    assert result == "stopSignal"


def test_parse_dual_task_underscore_style():
    """Pattern: sub-s29_ses_11_task-directed_forgetting_with_flanker_desc_raw.csv"""
    result = parse_behavioral_csv("sub-s29_ses_11_task-directed_forgetting_with_flanker_desc_raw.csv")
    assert result == "directedForgettingWFlanker"


def test_parse_practice_returns_none():
    """Practice files should not match."""
    result = parse_behavioral_csv("cued_task_switching_single_task_network__practice_results (6).csv")
    assert result is None


def test_parse_unrecognized_returns_none():
    result = parse_behavioral_csv("random_file.csv")
    assert result is None
```

**Step 2: Add parse_behavioral_csv to reconcile_sessions.py**

```python
def parse_behavioral_csv(filename: str) -> str | None:
    """Extract BIDS task name from a raw behavioral CSV filename.

    Returns None for practice files or unrecognized filenames.

    Handles three naming patterns:
    1. Descriptive: cued_task_switching_single_task_network__fmri_results (5).csv
    2. BIDS dash-separated: sub-s03_ses-1_task-go-nogo_desc-raw.csv
    3. BIDS camelCase: sub-s76_ses-01_task-stopSignal_desc-beh.csv
    4. Dual-task underscore: sub-s29_ses_11_task-directed_forgetting_with_flanker_desc_raw.csv
    """
    # Skip practice files
    if "__practice" in filename or "_practice_" in filename:
        return None

    # Remove copy number like " (3)" and extension
    base = re.sub(r"\s*\(\d+\)", "", filename).replace(".csv", "")

    # Pattern 1: descriptive (contains __fmri)
    if "__fmri" in base:
        long_name = base.split("__fmri")[0]
        if "_single_task_network" in long_name:
            long_name = long_name.split("_single_task_network")[0]
        return normalize_task_name(long_name)

    # Pattern 4: dual-task with underscores in task field
    # e.g., sub-s29_ses_11_task-stop_signal_with_flanker_desc_raw
    m = re.search(r"task-(.+?)_desc", base)
    if m:
        task_raw = m.group(1)
        result = normalize_task_name(task_raw)
        if result:
            return result

    # Pattern 2/3: BIDS-style with task- entity (single token)
    m = re.search(r"task-([^_]+)", base)
    if m:
        return normalize_task_name(m.group(1))

    return None
```

**Step 3: Run tests**

```bash
uv run pytest tests/scripts/test_reconcile_sessions.py -v
```

Expected: 11 PASS

**Step 4: Commit**

```bash
git add scripts/reconcile_sessions.py tests/scripts/test_reconcile_sessions.py
git commit -m "feat: add CSV filename parsing for reconcile_sessions.py"
```

---

### Task 6: Write reconcile_sessions.py — BIDS and raw directory scanning + tests

**Files:**
- Modify: `scripts/reconcile_sessions.py`
- Modify: `tests/scripts/test_reconcile_sessions.py`

**Step 1: Add tests for directory scanning**

Append to test file:

```python
from scripts.reconcile_sessions import scan_bids_bold, scan_raw_behavioral
import json


def _make_bold_file(bids_dir, sub, ses, task, run=1, echo=1):
    func_dir = bids_dir / f"sub-{sub}" / ses / "func"
    func_dir.mkdir(parents=True, exist_ok=True)
    name = f"sub-{sub}_{ses}_task-{task}_run-{run}_echo-{echo}_bold.nii.gz"
    (func_dir / name).touch()
    return func_dir / name


def _make_raw_csv(raw_dir, sub, ses, filename):
    ses_dir = raw_dir / sub / ses
    ses_dir.mkdir(parents=True, exist_ok=True)
    (ses_dir / filename).touch()


def test_scan_bids_bold(tmp_path):
    _make_bold_file(tmp_path, "s03", "ses-01", "goNogo", run=1, echo=1)
    _make_bold_file(tmp_path, "s03", "ses-01", "goNogo", run=1, echo=2)
    _make_bold_file(tmp_path, "s03", "ses-01", "goNogo", run=1, echo=3)
    _make_bold_file(tmp_path, "s03", "ses-01", "nBack", run=1, echo=1)

    result = scan_bids_bold(tmp_path)

    assert ("s03", "ses-01", "goNogo") in result
    assert ("s03", "ses-01", "nBack") in result
    # Deduplicated across echoes
    assert len(result) == 2


def test_scan_raw_behavioral(tmp_path):
    _make_raw_csv(tmp_path, "s03", "ses-01", "sub-s03_ses-1_task-go-nogo_desc-raw.csv")
    _make_raw_csv(tmp_path, "s03", "ses-01", "sub-s03_ses-1_task-shape-matching_desc-raw.csv")
    # Practice file should be excluded
    practice_dir = tmp_path / "s03" / "ses-01" / "practice"
    practice_dir.mkdir(parents=True, exist_ok=True)
    (practice_dir / "some_practice.csv").touch()

    result = scan_raw_behavioral(tmp_path)

    assert ("s03", "ses-01", "goNogo") in result
    assert ("s03", "ses-01", "shapeMatching") in result
    assert len(result) == 2


def test_scan_raw_includes_exclusions(tmp_path):
    _make_raw_csv(tmp_path / "exclusions", "s180", "ses-12",
                  "shape_matching_with_cued_task_switching__fmri_results (3).csv")

    result = scan_raw_behavioral(tmp_path)

    assert ("s180", "ses-12", "shapeMatchingWCuedTS") in result
    assert result[("s180", "ses-12", "shapeMatchingWCuedTS")]["in_exclusions"]
```

**Step 2: Add scan functions to reconcile_sessions.py**

```python
def zero_pad_session(session: str) -> str:
    """Normalize session label: ses-1 -> ses-01."""
    m = re.match(r"ses-(\d+)", session)
    if m:
        return f"ses-{int(m.group(1)):02d}"
    return session


def scan_bids_bold(bids_dir: Path) -> dict:
    """Scan BIDS func/ directories for (subject, session, task) tuples.

    Returns dict keyed by (subject, session, task) with value containing
    bold_path (absolute path to one representative BOLD file).
    Deduplicates across echoes and runs.
    """
    bids_dir = Path(bids_dir)
    result = {}

    for nifti in sorted(bids_dir.glob("sub-*/ses-*/func/*_bold.nii.gz")):
        m = re.match(
            r"sub-(\w+)_(ses-\d+)_task-(\w+)_run-\d+_echo-\d+_bold\.nii\.gz",
            nifti.name,
        )
        if not m:
            continue
        sub, ses, task = m.group(1), m.group(2), m.group(3)
        key = (sub, ses, task)
        if key not in result:
            result[key] = {"bold_path": str(nifti.resolve())}

    return result


def scan_raw_behavioral(raw_dir: Path) -> dict:
    """Scan raw behavioral directories for (subject, session, task) tuples.

    Scans both regular subject directories and the exclusions/ directory.
    Returns dict keyed by (subject, session, task) with value containing
    raw_path and in_exclusions flag.
    """
    raw_dir = Path(raw_dir)
    result = {}

    skip_dirs = {"dropped_subjects", "pretouch", "practice", "extra"}

    def _scan_subject_dirs(base_dir: Path, in_exclusions: bool = False):
        if not base_dir.exists():
            return
        for sub_dir in sorted(base_dir.iterdir()):
            if not sub_dir.is_dir() or sub_dir.name in skip_dirs or sub_dir.name == "exclusions":
                continue
            subject = sub_dir.name
            for ses_dir in sorted(sub_dir.iterdir()):
                if not ses_dir.is_dir() or not ses_dir.name.startswith("ses-"):
                    continue
                session = zero_pad_session(ses_dir.name)
                for csv_file in sorted(ses_dir.glob("*.csv")):
                    task = parse_behavioral_csv(csv_file.name)
                    if task is None:
                        continue
                    key = (subject, session, task)
                    if key not in result:
                        result[key] = {
                            "raw_path": str(csv_file.resolve()),
                            "in_exclusions": in_exclusions,
                        }

    _scan_subject_dirs(raw_dir, in_exclusions=False)
    _scan_subject_dirs(raw_dir / "exclusions", in_exclusions=True)

    return result
```

**Step 3: Run tests**

```bash
uv run pytest tests/scripts/test_reconcile_sessions.py -v
```

Expected: 14 PASS

**Step 4: Commit**

```bash
git add scripts/reconcile_sessions.py tests/scripts/test_reconcile_sessions.py
git commit -m "feat: add BIDS and raw behavioral directory scanning"
```

---

### Task 7: Write reconcile_sessions.py — manifest generation + tests

**Files:**
- Modify: `scripts/reconcile_sessions.py`
- Modify: `tests/scripts/test_reconcile_sessions.py`

**Step 1: Add test for full reconciliation**

Append to test file:

```python
def test_reconcile_full(tmp_path):
    from scripts.reconcile_sessions import reconcile

    bids_dir = tmp_path / "bids"
    raw_dir = tmp_path / "raw"

    # Matched: s03 ses-01 goNogo
    _make_bold_file(bids_dir, "s03", "ses-01", "goNogo")
    _make_raw_csv(raw_dir, "s03", "ses-01", "sub-s03_ses-1_task-go-nogo_desc-raw.csv")

    # BOLD without behavioral: s03 ses-01 nBack
    _make_bold_file(bids_dir, "s03", "ses-01", "nBack")

    # Behavioral without BOLD: s03 ses-02 nBack (cross-session context)
    _make_raw_csv(raw_dir, "s03", "ses-02",
                  "n_back_single_task_network__fmri_results (7).csv")

    rows = reconcile(bids_dir, raw_dir)

    matched = [r for r in rows if r["status"] == "matched"]
    bold_only = [r for r in rows if r["status"] == "bold_without_behavioral"]
    beh_only = [r for r in rows if r["status"] == "behavioral_without_bold"]

    assert len(matched) == 1
    assert matched[0]["task"] == "goNogo"
    assert matched[0]["action"] == "copy"

    assert len(bold_only) == 1
    assert bold_only[0]["task"] == "nBack"
    assert bold_only[0]["action"] == "pending"
    assert "ses-02:behavioral_only" in bold_only[0]["same_task_other_sessions"]

    assert len(beh_only) == 1
    assert beh_only[0]["task"] == "nBack"
    assert beh_only[0]["action"] == "pending"
    assert "ses-01:bold_only" in beh_only[0]["same_task_other_sessions"]
```

**Step 2: Add reconcile function**

```python
def _load_scan_notes(scan_notes_path: Path | None) -> str:
    """Load scan notes file contents for searching."""
    if scan_notes_path and scan_notes_path.exists():
        return scan_notes_path.read_text()
    return ""


def _find_scan_note(notes_text: str, subject: str, session: str, task: str) -> str:
    """Search scan notes for mentions of this subject/session/task."""
    if not notes_text:
        return ""
    hits = []
    for line in notes_text.splitlines():
        line_lower = line.lower()
        if subject.lower() in line_lower:
            if session.lower() in line_lower or task.lower() in line_lower:
                hits.append(line.strip().lstrip("- "))
    return "; ".join(hits[:3]) if hits else ""


def reconcile(
    bids_dir: Path,
    raw_dir: Path,
    scan_notes_path: Path | None = None,
) -> list[dict]:
    """Reconcile BIDS functional scans with raw behavioral CSVs.

    Returns list of row dicts suitable for writing as TSV.
    """
    bold_index = scan_bids_bold(bids_dir)
    beh_index = scan_raw_behavioral(raw_dir)
    notes_text = _load_scan_notes(scan_notes_path)

    # Collect all unique (subject, session, task) keys
    all_keys = set(bold_index.keys()) | set(beh_index.keys())

    # Filter to subjects present in the BIDS directory
    bids_subjects = {k[0] for k in bold_index.keys()}
    all_keys = {k for k in all_keys if k[0] in bids_subjects}

    rows = []
    for subject, session, task in sorted(all_keys):
        key = (subject, session, task)
        has_bold = key in bold_index
        has_beh = key in beh_index

        if has_bold and has_beh:
            status = "matched"
            action = "copy"
        elif has_bold:
            status = "bold_without_behavioral"
            action = "pending"
        else:
            status = "behavioral_without_bold"
            action = "pending"

        # Cross-session context: same subject+task in other sessions
        other_sessions = []
        for (s, ses, t), _ in sorted(all_keys_with_data(bold_index, beh_index)):
            if s == subject and t == task and ses != session:
                in_bold = (s, ses, t) in bold_index
                in_beh = (s, ses, t) in beh_index
                if in_bold and in_beh:
                    other_sessions.append(f"{ses}:matched")
                elif in_bold:
                    other_sessions.append(f"{ses}:bold_only")
                else:
                    other_sessions.append(f"{ses}:behavioral_only")

        rows.append({
            "subject": subject,
            "session": session,
            "task": task,
            "status": status,
            "action": action,
            "dest_session": session,
            "raw_path": beh_index[key]["raw_path"] if has_beh else "",
            "bold_path": bold_index[key]["bold_path"] if has_bold else "",
            "same_task_other_sessions": ", ".join(other_sessions) if other_sessions else "",
            "notes": _find_scan_note(notes_text, subject, session, task),
        })

    return rows


def all_keys_with_data(bold_index, beh_index):
    """Yield all (subject, session, task) keys with their data source."""
    all_keys = set(bold_index.keys()) | set(beh_index.keys())
    for key in sorted(all_keys):
        yield key, None
```

Note: The `all_keys_with_data` helper is used inside `reconcile` for the cross-session lookup. During implementation, this should be simplified — the inner loop can iterate `all_keys` directly. The plan provides the structure; clean up during implementation.

**Step 3: Run tests**

```bash
uv run pytest tests/scripts/test_reconcile_sessions.py -v
```

Expected: 15 PASS

**Step 4: Commit**

```bash
git add scripts/reconcile_sessions.py tests/scripts/test_reconcile_sessions.py
git commit -m "feat: add manifest generation to reconcile_sessions.py"
```

---

### Task 8: Write reconcile_sessions.py — TSV output + CLI

**Files:**
- Modify: `scripts/reconcile_sessions.py`
- Modify: `tests/scripts/test_reconcile_sessions.py`

**Step 1: Add test for TSV output**

```python
def test_write_manifest_tsv(tmp_path):
    from scripts.reconcile_sessions import write_manifest_tsv

    rows = [
        {
            "subject": "s03", "session": "ses-01", "task": "goNogo",
            "status": "matched", "action": "copy", "dest_session": "ses-01",
            "raw_path": "/oak/s03/ses-01/go-nogo.csv",
            "bold_path": "/scratch/sub-s03/ses-01/func/bold.nii.gz",
            "same_task_other_sessions": "", "notes": "",
        },
    ]
    output = tmp_path / "manifest.tsv"
    write_manifest_tsv(rows, output)

    lines = output.read_text().splitlines()
    assert lines[0].startswith("subject\t")
    assert len(lines) == 2
    assert lines[1].startswith("s03\t")
```

**Step 2: Add write_manifest_tsv and CLI main**

```python
TSV_COLUMNS = [
    "subject", "session", "task", "status", "action", "dest_session",
    "raw_path", "bold_path", "same_task_other_sessions", "notes",
]


def write_manifest_tsv(rows: list[dict], output_path: Path) -> None:
    """Write reconciliation manifest as TSV."""
    output_path = Path(output_path)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_COLUMNS, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("Wrote %d rows to %s", len(rows), output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile BIDS functional scans with raw behavioral CSVs"
    )
    parser.add_argument("--raw-dir", required=True, type=Path,
                        help="Path to raw_cleaned behavioral directory")
    parser.add_argument("--bids-dir", required=True, type=Path,
                        help="Path to BIDS directory")
    parser.add_argument("--scan-notes", type=Path, default=None,
                        help="Path to SCAN-NOTES.md for auto-populating notes column")
    parser.add_argument("--output", required=True, type=Path,
                        help="Output TSV manifest path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    rows = reconcile(args.bids_dir, args.raw_dir, args.scan_notes)
    write_manifest_tsv(rows, args.output)

    # Print summary
    matched = sum(1 for r in rows if r["status"] == "matched")
    bold_only = sum(1 for r in rows if r["status"] == "bold_without_behavioral")
    beh_only = sum(1 for r in rows if r["status"] == "behavioral_without_bold")
    print(f"Matched: {matched}")
    print(f"BOLD without behavioral: {bold_only}")
    print(f"Behavioral without BOLD: {beh_only}")
    print(f"Total rows: {len(rows)}")


if __name__ == "__main__":
    main()
```

**Step 3: Run tests**

```bash
uv run pytest tests/scripts/test_reconcile_sessions.py -v
```

Expected: 16 PASS

**Step 4: Commit**

```bash
git add scripts/reconcile_sessions.py tests/scripts/test_reconcile_sessions.py
git commit -m "feat: add TSV output and CLI for reconcile_sessions.py"
```

---

### Task 9: Write migrate_behavioral.py — tests + implementation

**Files:**
- Create: `scripts/migrate_behavioral.py`
- Create: `tests/scripts/test_migrate_behavioral.py`

**Step 1: Write the test**

```python
"""Tests for scripts/migrate_behavioral.py"""
import json
from pathlib import Path


def _write_manifest(tmp_path, rows):
    """Write a TSV manifest file."""
    manifest = tmp_path / "manifest.tsv"
    header = "subject\tsession\ttask\tstatus\taction\tdest_session\traw_path\tbold_path\tsame_task_other_sessions\tnotes"
    lines = [header]
    for r in rows:
        lines.append("\t".join(str(r.get(c, "")) for c in header.split("\t")))
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def test_migrate_copies_matched_files(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    raw_dir = tmp_path / "raw"
    raw_csv = raw_dir / "s03" / "ses-01" / "go-nogo.csv"
    raw_csv.parent.mkdir(parents=True)
    raw_csv.write_text("trial,rt\n1,500\n")

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(tmp_path, [{
        "subject": "s03", "session": "ses-01", "task": "goNogo",
        "status": "matched", "action": "copy", "dest_session": "ses-01",
        "raw_path": str(raw_csv), "bold_path": "", "same_task_other_sessions": "",
        "notes": "",
    }])

    report = migrate_from_manifest(manifest, output_dir)

    expected = output_dir / "in_scanner_behavior" / "sub-s03" / "ses-01" / "beh" / "sub-s03_ses-01_task-goNogo_beh.csv"
    assert expected.exists()
    assert expected.read_text() == "trial,rt\n1,500\n"
    assert report["copied"] == 1


def test_migrate_skips_pending(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(tmp_path, [{
        "subject": "s29", "session": "ses-01", "task": "cuedTS",
        "status": "bold_without_behavioral", "action": "pending",
        "dest_session": "ses-01", "raw_path": "", "bold_path": "",
        "same_task_other_sessions": "", "notes": "",
    }])

    report = migrate_from_manifest(manifest, output_dir)

    assert report["copied"] == 0
    assert report["skipped_pending"] == 1


def test_migrate_fails_on_unresolved_pending(tmp_path):
    import pytest
    from scripts.migrate_behavioral import migrate_from_manifest

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(tmp_path, [{
        "subject": "s29", "session": "ses-01", "task": "cuedTS",
        "status": "bold_without_behavioral", "action": "pending",
        "dest_session": "ses-01", "raw_path": "", "bold_path": "",
        "same_task_other_sessions": "", "notes": "",
    }])

    with pytest.raises(SystemExit):
        migrate_from_manifest(manifest, output_dir, strict=True)


def test_migrate_respects_dest_session_override(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    raw_csv = tmp_path / "raw" / "s03" / "ses-02" / "nback.csv"
    raw_csv.parent.mkdir(parents=True)
    raw_csv.write_text("trial,rt\n1,600\n")

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(tmp_path, [{
        "subject": "s03", "session": "ses-02", "task": "nBack",
        "status": "matched", "action": "copy", "dest_session": "ses-01",
        "raw_path": str(raw_csv), "bold_path": "", "same_task_other_sessions": "",
        "notes": "",
    }])

    migrate_from_manifest(manifest, output_dir)

    expected = output_dir / "in_scanner_behavior" / "sub-s03" / "ses-01" / "beh" / "sub-s03_ses-01_task-nBack_beh.csv"
    assert expected.exists()
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/scripts/test_migrate_behavioral.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

```python
#!/usr/bin/env python3
"""Migrate behavioral data to BIDS sourcedata using a reviewed manifest.

Usage:
    uv run python scripts/migrate_behavioral.py \
        --manifest reconciliation_discovery.tsv \
        --raw-dir /oak/.../behavioral_data/raw_cleaned \
        --output-dir /oak/.../sourcedata \
        --sample discovery
"""
import argparse
import csv
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def migrate_from_manifest(
    manifest_path: Path,
    output_dir: Path,
    strict: bool = False,
) -> dict:
    """Copy in-scanner behavioral files according to the reviewed manifest.

    Args:
        manifest_path: TSV manifest from reconcile_sessions.py
        output_dir: Sourcedata output root
        strict: If True, raise SystemExit if any rows are still 'pending'

    Returns:
        Report dict with counts.
    """
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)

    with open(manifest_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    report = {
        "copied": 0,
        "skipped_pending": 0,
        "skipped_irreconcilable": 0,
        "skipped_skip": 0,
        "skipped_no_raw_path": 0,
        "files": [],
    }

    pending_rows = [r for r in rows if r["action"] == "pending"]
    if strict and pending_rows:
        log.error(
            "%d rows still marked 'pending'. Resolve all discrepancies before migrating.",
            len(pending_rows),
        )
        sys.exit(1)

    for row in rows:
        action = row["action"]

        if action == "pending":
            report["skipped_pending"] += 1
            continue
        if action == "skip":
            report["skipped_skip"] += 1
            continue
        if action == "irreconcilable":
            report["skipped_irreconcilable"] += 1
            continue
        if action != "copy":
            log.warning("Unknown action '%s' for %s %s %s, skipping",
                        action, row["subject"], row["session"], row["task"])
            continue

        raw_path = row.get("raw_path", "")
        if not raw_path or not Path(raw_path).exists():
            log.warning("Raw file not found: %s", raw_path)
            report["skipped_no_raw_path"] += 1
            continue

        subject = row["subject"]
        dest_session = row["dest_session"]
        task = row["task"]

        sub_label = f"sub-{subject}" if not subject.startswith("sub-") else subject
        filename = f"{sub_label}_{dest_session}_task-{task}_beh.csv"
        dest_path = output_dir / "in_scanner_behavior" / sub_label / dest_session / "beh" / filename

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_path, dest_path)

        report["copied"] += 1
        report["files"].append({
            "src": raw_path,
            "dest": str(dest_path),
            "subject": subject,
            "session": dest_session,
            "task": task,
        })

        log.info("Copied %s -> %s", Path(raw_path).name, dest_path)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Migrate behavioral data to BIDS sourcedata using reviewed manifest"
    )
    parser.add_argument("--manifest", required=True, type=Path,
                        help="Reviewed TSV manifest from reconcile_sessions.py")
    parser.add_argument("--raw-dir", required=True, type=Path,
                        help="Path to raw_cleaned behavioral directory (for out-of-scanner, survey, mTurk)")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Sourcedata output root")
    parser.add_argument("--sample", required=True, choices=["discovery", "validation"],
                        help="Sample name (for filtering out-of-scanner/survey subjects)")
    parser.add_argument("--strict", action="store_true",
                        help="Fail if any manifest rows are still 'pending'")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    report = migrate_from_manifest(args.manifest, args.output_dir, strict=args.strict)

    # Write migration report
    report_out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "manifest": str(args.manifest),
        "sample": args.sample,
        **{k: v for k, v in report.items() if k != "files"},
        "files": report["files"],
    }
    report_path = args.output_dir / "migration_report.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_out, indent=2) + "\n")

    print(f"Copied: {report['copied']}")
    print(f"Skipped (pending): {report['skipped_pending']}")
    print(f"Skipped (irreconcilable): {report['skipped_irreconcilable']}")
    print(f"Skipped (skip): {report['skipped_skip']}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```bash
uv run pytest tests/scripts/test_migrate_behavioral.py -v
```

Expected: 4 PASS

**Step 5: Commit**

```bash
git add scripts/migrate_behavioral.py tests/scripts/test_migrate_behavioral.py
git commit -m "feat: add migrate_behavioral.py — manifest-driven behavioral migration"
```

---

### Task 10: Add conftest.py for scripts import path

**Files:**
- Create: `tests/scripts/__init__.py`
- Create: `tests/scripts/conftest.py`

The test imports like `from scripts.trim_bold import ...` need the `scripts/` directory on `sys.path`.

**Step 1: Create conftest**

```python
# tests/scripts/conftest.py
import sys
from pathlib import Path

# Add project root to sys.path so `from scripts.X import Y` works in tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
```

```python
# tests/scripts/__init__.py
```

Note: This task should be done BEFORE running any tests in Tasks 2-9. Move this to the first implementation step.

**Step 2: Commit**

```bash
git add tests/scripts/__init__.py tests/scripts/conftest.py
git commit -m "test: add conftest for scripts/ import path"
```

---

### Task 11: Run full test suite and verify

**Step 1: Run all new tests**

```bash
uv run pytest tests/scripts/ -v
```

Expected: All pass (approximately 20 tests across 3 files)

**Step 2: Run existing tests to verify no regressions**

```bash
uv run pytest tests/ --ignore=tests/analysis -v
```

Expected: Same pass rate as before (331 passed, 1 pre-existing failure in test_rename_script.py)

**Step 3: Commit any fixes if needed**

---

### Task 12: Update documentation

**Files:**
- Modify: `CLAUDE.md` (remove reference to `--dummy-scans 0`, note volumes are now trimmed by `trim_bold.py`)
- Modify: `manual_notes.md` (update Section 2 trimming status to reference `trim_bold.py`)

**Step 1: Update CLAUDE.md**

Change the fMRIPrep example from `--dummy-scans 0` to `--dummy-scans 0` with a note that `trim_bold.py` must be run first:

```markdown
# Preprocessing note: Run trim_bold.py first, then use fMRIPrep with --dummy-scans 0
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
fmriprep --dummy-scans 0 /scratch/users/logben/discovery_bids /derivatives --fs-license /path/to/license
```

**Step 2: Commit**

```bash
git add CLAUDE.md manual_notes.md
git commit -m "docs: update documentation for new scripts workflow"
```

---

## Execution Order Summary

| Order | Task | Description |
|-------|------|-------------|
| 1 | Task 10 | Create conftest.py for import path (prerequisite for all tests) |
| 2 | Task 1 | Delete old scripts and config |
| 3 | Task 2 | trim_bold.py failing tests |
| 4 | Task 3 | trim_bold.py implementation |
| 5 | Task 4 | reconcile_sessions.py task name normalization |
| 6 | Task 5 | reconcile_sessions.py CSV parsing |
| 7 | Task 6 | reconcile_sessions.py directory scanning |
| 8 | Task 7 | reconcile_sessions.py manifest generation |
| 9 | Task 8 | reconcile_sessions.py TSV output + CLI |
| 10 | Task 9 | migrate_behavioral.py tests + implementation |
| 11 | Task 11 | Full test suite verification |
| 12 | Task 12 | Documentation updates |
