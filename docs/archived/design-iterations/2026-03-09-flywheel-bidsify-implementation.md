# Flywheel BIDSify Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pull NIfTI/JSON data from Flywheel, resolve subject label issues, and write clean BIDS datasets.

**Architecture:** A `bidsify/` subpackage under `neuro_workflow` with four modules (config, flywheel_query, file_selector, bids_writer) plus a `run.py` orchestrator, wired into the existing CLI as `neuro-run bidsify`. Uses flywheel-sdk to query and download, writes BIDS with patched sidecars.

**Tech Stack:** Python 3.13, flywheel-sdk>=17.0, existing neuro_workflow CLI (argparse), pytest for tests.

**Design doc:** `docs/plans/2026-03-09-flywheel-bidsify-design.md`

**Source data notes:** `flywheel_sourcedata_notes/` — contains scan tracking CSVs, calendar CSV, and participant tracking CSVs used for cross-validation.

---

### Task 1: Add bidsify dependency and rebuild container

**Files:**
- Modify: `pyproject.toml:13-26`
- Modify: `neuro_workflow.def:11-14`

**Step 1: Add flywheel-sdk optional dependency**

In `pyproject.toml`, add after the `qa` group:

```toml
bidsify = [
    "flywheel-sdk>=17.0",
]
```

**Step 2: Update container def to install bidsify extras**

In `neuro_workflow.def`, change the pip install line:

```
UV_CACHE_DIR=/tmp/uv_cache uv pip install --python /opt/venv/bin/python -e ".[lev1,qa,bidsify]"
```

**Step 3: Commit**

```bash
git add pyproject.toml neuro_workflow.def
git commit -m "feat: add flywheel-sdk dependency for bidsify module"
```

**Step 4: Rebuild container (run later, not blocking)**

```bash
sbatch setup.sh
```

---

### Task 2: Create bidsify config module with acquisition mapping

**Files:**
- Create: `src/neuro_workflow/bidsify/__init__.py`
- Create: `src/neuro_workflow/bidsify/config.py`
- Create: `src/neuro_workflow/bidsify/reconciliation_config.json`
- Test: `tests/bidsify/test_config.py`

**Step 1: Write tests for acquisition mapping**

Create `tests/bidsify/__init__.py` (empty) and `tests/bidsify/test_config.py`:

```python
from neuro_workflow.bidsify.config import map_acquisition, SKIP_ACQUISITIONS


def test_base_task_mapping():
    result = map_acquisition("task-rest_bold")
    assert result["task"] == "rest"
    assert result["modality"] == "func"


def test_typo_correction():
    result = map_acquisition("task-shapeMaching_bold")
    assert result["task"] == "shapeMatching"


def test_underscore_variant():
    result = map_acquisition("task_stopSignal_bold")
    assert result["task"] == "stopSignal"


def test_dual_task_mapping():
    result = map_acquisition("directed_forgetting_w_flanker_bold")
    assert result["task"] == "directedForgettingWFlanker"


def test_dual_task_verbose_variant():
    result = map_acquisition("task-stop_signal_with_directed_forgetting_bold")
    assert result["task"] == "stopSignalWDirectedForgetting"


def test_dual_task_abbreviated():
    result = map_acquisition("task-stop_with_df_bold")
    assert result["task"] == "stopSignalWDirectedForgetting"


def test_fieldmap_mapping():
    result = map_acquisition("fmap-fieldmap")
    assert result["modality"] == "fmap"


def test_t1w_old_protocol():
    result = map_acquisition("T1w MPRAGE PROMO")
    assert result["modality"] == "anat"
    assert result["suffix"] == "T1w"
    assert result["acq"] == "MPRAGEPromo"


def test_t1w_new_protocol():
    result = map_acquisition("NEW Sag_MPRAGE_T1")
    assert result["modality"] == "anat"
    assert result["suffix"] == "T1w"
    assert result["acq"] == "SagMPRAGE"


def test_t2w_mapping():
    result = map_acquisition("T2w CUBE PROMO .8mm sag")
    assert result["modality"] == "anat"
    assert result["suffix"] == "T2w"
    assert result["acq"] == "CubePromo"


def test_dwi_pe0():
    result = map_acquisition("DTI_pe0_g105")
    assert result["modality"] == "dwi"
    assert result["dir"] == "AP"
    assert result["acq"] == "g105"


def test_dwi_pe1():
    result = map_acquisition("DTI_pe1_g105")
    assert result["modality"] == "dwi"
    assert result["dir"] == "PA"


def test_dwi_pe1_g71():
    result = map_acquisition("DTI_pe1_g71")
    assert result["modality"] == "dwi"
    assert result["acq"] == "g71"


def test_skip_localizer():
    assert map_acquisition("3Plane Loc SSFSE") is None


def test_skip_shim():
    assert map_acquisition("GE HOS FOV28") is None
    assert map_acquisition("GE HOS FOV28_1") is None


def test_unknown_acquisition():
    assert map_acquisition("some_unknown_thing") is None
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/bidsify/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_workflow.bidsify'`

**Step 3: Implement config module**

Create `src/neuro_workflow/bidsify/__init__.py` (empty file).

Create `src/neuro_workflow/bidsify/config.py`:

```python
"""Acquisition label -> BIDS name mapping and constants."""

import json
from pathlib import Path

# Acquisition labels to skip (localizer, shim)
SKIP_ACQUISITIONS = {
    "3Plane Loc SSFSE",
    "GE HOS FOV28",
    "GE HOS FOV28_1",
    "GE HOS FOV28_2",
}

# Flywheel acquisition label -> BIDS metadata
# Keys: task (func), modality, suffix, acq, dir
ACQUISITION_MAP = {
    # Base tasks
    "task-rest_bold": {"task": "rest"},
    "task-cuedTS_bold": {"task": "cuedTS"},
    "task-directedForgetting_bold": {"task": "directedForgetting"},
    "task-flanker_bold": {"task": "flanker"},
    "task-goNogo_bold": {"task": "goNogo"},
    "task-nBack_bold": {"task": "nBack"},
    "task-shapeMatching_bold": {"task": "shapeMatching"},
    "task-shapeMaching_bold": {"task": "shapeMatching"},
    "task-spatialTS_bold": {"task": "spatialTS"},
    "task-stopSignal_bold": {"task": "stopSignal"},
    "task_stopSignal_bold": {"task": "stopSignal"},
    # Dual tasks
    "directed_forgetting_w_flanker_bold": {"task": "directedForgettingWFlanker"},
    "stop_signal_w_directed_forgetting_bold": {"task": "stopSignalWDirectedForgetting"},
    "stop_signal_w_flanker_bold": {"task": "stopSignalWFlanker"},
    "task-stop_signal_with_directed_forgetting_bold": {"task": "stopSignalWDirectedForgetting"},
    "task-stop_with_df_bold": {"task": "stopSignalWDirectedForgetting"},
    "task-stop_with_flanker_bold": {"task": "stopSignalWFlanker"},
    # Fieldmap
    "fmap-fieldmap": {"modality": "fmap"},
    # Anatomical
    "T1w MPRAGE PROMO": {"modality": "anat", "suffix": "T1w", "acq": "MPRAGEPromo"},
    "NEW Sag_MPRAGE_T1": {"modality": "anat", "suffix": "T1w", "acq": "SagMPRAGE"},
    "T2w CUBE PROMO .8mm sag": {"modality": "anat", "suffix": "T2w", "acq": "CubePromo"},
    # Diffusion
    "DTI_pe0_g105": {"modality": "dwi", "dir": "AP", "acq": "g105"},
    "DTI_pe1_g105": {"modality": "dwi", "dir": "PA", "acq": "g105"},
    "DTI_pe1_g71": {"modality": "dwi", "dir": "PA", "acq": "g71"},
}


def map_acquisition(label):
    """Map a Flywheel acquisition label to BIDS metadata dict, or None to skip."""
    if label in SKIP_ACQUISITIONS:
        return None
    mapping = ACQUISITION_MAP.get(label)
    if mapping is None:
        return None
    result = dict(mapping)
    # Infer modality for task-based acquisitions
    if "task" in result and "modality" not in result:
        result["modality"] = "func"
    return result


def load_reconciliation_config():
    """Load the reconciliation config from the package directory."""
    config_path = Path(__file__).parent / "reconciliation_config.json"
    with open(config_path) as f:
        return json.load(f)
```

Create `src/neuro_workflow/bidsify/reconciliation_config.json`:

```json
{
    "flywheel_project": "r01network",
    "subject_aliases": {
        "s19-2": "s19",
        "s29-2": "s29",
        "s43-2": "s43"
    },
    "skip_subjects": ["n01", "ex26207"],
    "samples": {
        "discovery": ["s03", "s10", "s19", "s29", "s43"],
        "validation": [
            "s76", "s247", "s214", "s216", "s222", "s250", "s286", "s295",
            "s297", "s300", "s320", "s321", "s336", "s373", "s394", "s415",
            "s432", "s480", "s180", "s599", "s645", "s823", "s874", "s956",
            "s968", "s1035", "s1057", "s1058", "s1127", "s1134", "s1165",
            "s1175", "s1178", "s1189", "s1258", "s1266", "s1267", "s1270",
            "s1273", "s1292", "s1314", "s1320", "s1326", "s1338", "s1351",
            "s1391", "s1399", "s1402", "s1408", "s1445", "s1481", "s1486"
        ]
    }
}
```

**Step 4: Run tests**

```bash
uv run pytest tests/bidsify/test_config.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/ tests/bidsify/
git commit -m "feat(bidsify): add config module with acquisition mapping"
```

---

### Task 3: Create flywheel_query module

**Files:**
- Create: `src/neuro_workflow/bidsify/flywheel_query.py`
- Test: `tests/bidsify/test_flywheel_query.py`

**Step 1: Write tests**

These tests mock the Flywheel SDK to avoid needing a live connection.

Create `tests/bidsify/test_flywheel_query.py`:

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from neuro_workflow.bidsify.flywheel_query import (
    collect_subject_sessions,
    build_session_timeline,
)


def _make_session(label, timestamp, acq_labels):
    ses = MagicMock()
    ses.label = label
    ses.timestamp = timestamp
    acqs = []
    for acq_label in acq_labels:
        acq = MagicMock()
        acq.label = acq_label
        acq.timestamp = timestamp
        acqs.append(acq)
    ses.acquisitions.return_value = acqs
    return ses


def _make_subject(label, sessions):
    sub = MagicMock()
    sub.label = label
    sub.sessions.return_value = sessions
    return sub


def test_collect_merges_aliases():
    """s43 + s43-2 should merge into one timeline."""
    s43_sessions = [
        _make_session("22473", datetime(2020, 11, 19, tzinfo=timezone.utc), ["fmap-fieldmap", "task-rest_bold"]),
    ]
    s43_2_sessions = [
        _make_session("20201112", datetime(2020, 11, 12, tzinfo=timezone.utc), ["fmap-fieldmap", "task-rest_bold"]),
    ]
    subjects = [
        _make_subject("s43", s43_sessions),
        _make_subject("s43-2", s43_2_sessions),
    ]
    aliases = {"s43-2": "s43"}

    result = collect_subject_sessions("s43", subjects, aliases)
    assert len(result) == 2
    # s43-2 session should come first (earlier timestamp)
    assert result[0]["fw_subject"] == "s43-2"
    assert result[1]["fw_subject"] == "s43"


def test_build_session_timeline_assigns_sequential_labels():
    sessions = [
        {"fw_subject": "s43-2", "fw_session": "20201112",
         "timestamp": datetime(2020, 11, 12, tzinfo=timezone.utc), "acquisitions": []},
        {"fw_subject": "s43", "fw_session": "22473",
         "timestamp": datetime(2020, 11, 19, tzinfo=timezone.utc), "acquisitions": []},
    ]
    timeline = build_session_timeline(sessions)
    assert timeline[0]["bids_session"] == "ses-01"
    assert timeline[1]["bids_session"] == "ses-02"


def test_collect_skips_unrelated_subjects():
    subjects = [
        _make_subject("s43", []),
        _make_subject("s10", []),
    ]
    result = collect_subject_sessions("s43", subjects, {})
    assert len(result) == 0  # s43 has 0 sessions, s10 excluded
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/bidsify/test_flywheel_query.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement flywheel_query module**

Create `src/neuro_workflow/bidsify/flywheel_query.py`:

```python
"""Query Flywheel project for subjects, sessions, and acquisitions."""

import logging

logger = logging.getLogger(__name__)


def collect_subject_sessions(canonical_label, all_subjects, aliases):
    """Collect all sessions for a subject, merging aliased FW labels.

    Args:
        canonical_label: The BIDS subject label (e.g., "s43")
        all_subjects: List of all FW subject objects in the project
        aliases: Dict mapping variant labels to canonical (e.g., {"s43-2": "s43"})

    Returns:
        List of session dicts sorted by timestamp, each containing:
            fw_subject, fw_session, timestamp, acquisitions (list of acq labels)
    """
    # Find which FW labels map to this canonical subject
    fw_labels = {canonical_label}
    for variant, canonical in aliases.items():
        if canonical == canonical_label:
            fw_labels.add(variant)

    sessions = []
    for sub in all_subjects:
        if sub.label not in fw_labels:
            continue
        for ses in sub.sessions():
            acq_labels = [a.label for a in ses.acquisitions()]
            sessions.append({
                "fw_subject": sub.label,
                "fw_session": ses.label,
                "timestamp": ses.timestamp,
                "acquisitions": acq_labels,
            })

    sessions.sort(key=lambda s: s["timestamp"] or "")
    return sessions


def build_session_timeline(sessions):
    """Assign sequential BIDS session labels to sorted sessions.

    Args:
        sessions: List of session dicts sorted by timestamp.

    Returns:
        Same list with "bids_session" key added (e.g., "ses-01").
    """
    for i, ses in enumerate(sessions):
        ses["bids_session"] = f"ses-{i + 1:02d}"
    return sessions


def query_project_subjects(fw_client, project_label):
    """Get all subjects from a Flywheel project.

    Args:
        fw_client: Authenticated flywheel.Client
        project_label: Project label (e.g., "r01network")

    Returns:
        List of FW subject objects, project object
    """
    projects = [p for p in fw_client.projects() if p.label == project_label]
    if not projects:
        raise ValueError(f"Project '{project_label}' not found on Flywheel")
    project = projects[0]
    return list(project.subjects()), project
```

**Step 4: Run tests**

```bash
uv run pytest tests/bidsify/test_flywheel_query.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/flywheel_query.py tests/bidsify/test_flywheel_query.py
git commit -m "feat(bidsify): add flywheel_query module for session enumeration"
```

---

### Task 4: Create file_selector module

**Files:**
- Create: `src/neuro_workflow/bidsify/file_selector.py`
- Test: `tests/bidsify/test_file_selector.py`

**Step 1: Write tests**

Create `tests/bidsify/test_file_selector.py`:

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from neuro_workflow.bidsify.file_selector import select_files


def _make_file(name, file_type="nifti", size=100, created=None):
    f = MagicMock()
    f.name = name
    f.type = file_type
    f.size = size
    f.created = created or datetime(2021, 1, 1, tzinfo=timezone.utc)
    return f


def test_select_bold_multiecho():
    """Should select _e1, _e2, _e3 NIfTI + JSON pairs."""
    files = [
        _make_file("22461_4_1.nii.gz", size=168),  # combined, skip
        _make_file("22461_4_1_e1.nii.gz", size=60),
        _make_file("22461_4_1_e1.json", "source code", size=1),
        _make_file("22461_4_1_e2.nii.gz", size=54),
        _make_file("22461_4_1_e2.json", "source code", size=1),
        _make_file("22461_4_1_e3.nii.gz", size=50),
        _make_file("22461_4_1_e3.json", "source code", size=1),
        _make_file("22461_4_1.qa.png", "qa"),  # skip
    ]
    result = select_files(files, "func")
    assert len(result) == 3  # 3 echoes
    assert all(r["echo"] in (1, 2, 3) for r in result)
    assert all(r["nifti"] is not None for r in result)
    assert all(r["json"] is not None for r in result)


def test_select_bold_prefers_newest_duplicate():
    """When duplicate echo files exist, prefer the newest."""
    old = datetime(2021, 1, 1, tzinfo=timezone.utc)
    new = datetime(2021, 6, 1, tzinfo=timezone.utc)
    files = [
        _make_file("22461_4_1_e1.nii.gz", size=60, created=old),
        _make_file("22461_4_1_e1.json", "source code", size=1, created=old),
        _make_file("22461_4_1_e1_t718881.nii.gz", size=60, created=new),
        _make_file("22461_4_1_e1_t718881.json", "source code", size=1, created=new),
        _make_file("22461_4_1_e2.nii.gz", size=54, created=old),
        _make_file("22461_4_1_e2.json", "source code", size=1, created=old),
        _make_file("22461_4_1_e3.nii.gz", size=50, created=old),
        _make_file("22461_4_1_e3.json", "source code", size=1, created=old),
    ]
    result = select_files(files, "func")
    echo1 = [r for r in result if r["echo"] == 1][0]
    assert "t718881" in echo1["nifti"].name


def test_select_fieldmap():
    """Should return fieldmap + magnitude pair."""
    files = [
        _make_file("22461_3_1.json", "source code"),
        _make_file("22461_3_1.nii.gz"),
        _make_file("22461_3_1_fieldmap.json", "source code"),
        _make_file("22461_3_1_fieldmap.nii.gz"),
    ]
    result = select_files(files, "fmap")
    assert result["fieldmap_nifti"] is not None
    assert result["fieldmap_json"] is not None
    assert result["magnitude_nifti"] is not None


def test_select_anat():
    """Should return single NIfTI + JSON."""
    files = [
        _make_file("22461_9_1.nii.gz", size=390),
        _make_file("22461_9_1.json", "source code"),
        _make_file("22461_9_1.dicom.zip", "dicom"),  # skip
        _make_file("22461_9_1.qa.png", "qa"),  # skip
    ]
    result = select_files(files, "anat")
    assert result["nifti"] is not None
    assert result["json"] is not None


def test_select_dwi():
    """Should return NIfTI + JSON + bval + bvec."""
    files = [
        _make_file("22461_10_1.nii.gz"),
        _make_file("22461_10_1.json", "source code"),
        _make_file("22461_10_1.bval", "bval"),
        _make_file("22461_10_1.bvec", "bvec"),
        _make_file("22461_10_1.dicom.zip", "dicom"),
    ]
    result = select_files(files, "dwi")
    assert result["nifti"] is not None
    assert result["json"] is not None
    assert result["bval"] is not None
    assert result["bvec"] is not None
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/bidsify/test_file_selector.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement file_selector module**

Create `src/neuro_workflow/bidsify/file_selector.py`:

```python
"""Select the correct NIfTI/JSON files from duplicate Flywheel gear outputs."""

import logging
import re

logger = logging.getLogger(__name__)


def _is_nifti(f):
    return f.name.endswith(".nii.gz")


def _is_json(f):
    return f.name.endswith(".json") and f.type == "source code"


def _is_bval(f):
    return f.name.endswith(".bval")


def _is_bvec(f):
    return f.name.endswith(".bvec")


def _skip_file(f):
    return f.type in ("dicom", "qa", "montage", "pfile")


def _echo_number(filename):
    """Extract echo number from filename like '*_e2.nii.gz' or '*_e2.json'."""
    m = re.search(r"_e(\d+)(?:\.|_)", filename)
    return int(m.group(1)) if m else None


def _pick_newest(candidates):
    """From a list of file objects, return the one with most recent created timestamp."""
    return max(candidates, key=lambda f: f.created or "")


def select_files(files, modality):
    """Select the correct files for a given modality from a Flywheel acquisition.

    Args:
        files: List of Flywheel file objects from an acquisition
        modality: One of "func", "fmap", "anat", "dwi"

    Returns:
        For func: list of dicts with keys {echo, nifti, json}
        For fmap: dict with keys {fieldmap_nifti, fieldmap_json, magnitude_nifti}
        For anat: dict with keys {nifti, json}
        For dwi: dict with keys {nifti, json, bval, bvec}
    """
    # Filter out non-data files
    files = [f for f in files if not _skip_file(f)]

    if modality == "func":
        return _select_multiecho(files)
    elif modality == "fmap":
        return _select_fieldmap(files)
    elif modality == "anat":
        return _select_single(files)
    elif modality == "dwi":
        return _select_dwi(files)
    else:
        raise ValueError(f"Unknown modality: {modality}")


def _select_multiecho(files):
    """Select multi-echo BOLD files (_e1, _e2, _e3)."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]

    # Group by echo number
    echo_niftis = {}
    for f in niftis:
        echo = _echo_number(f.name)
        if echo is None:
            continue  # skip combined volumes
        echo_niftis.setdefault(echo, []).append(f)

    echo_jsons = {}
    for f in jsons:
        echo = _echo_number(f.name)
        if echo is None:
            continue
        echo_jsons.setdefault(echo, []).append(f)

    results = []
    for echo in sorted(echo_niftis.keys()):
        nifti_candidates = echo_niftis[echo]
        json_candidates = echo_jsons.get(echo, [])

        nifti = _pick_newest(nifti_candidates)
        json_file = _pick_newest(json_candidates) if json_candidates else None

        # Warn if duplicates have different sizes
        if len(nifti_candidates) > 1:
            sizes = {f.size for f in nifti_candidates}
            if len(sizes) > 1:
                logger.warning(
                    "Echo %d has duplicates with different sizes: %s",
                    echo, [(f.name, f.size) for f in nifti_candidates],
                )

        results.append({"echo": echo, "nifti": nifti, "json": json_file})

    return results


def _select_fieldmap(files):
    """Select fieldmap + magnitude pair."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]

    fieldmap_nifti = None
    magnitude_nifti = None
    fieldmap_json = None

    for f in niftis:
        if "_fieldmap" in f.name:
            fieldmap_nifti = f
        else:
            magnitude_nifti = f

    for f in jsons:
        if "_fieldmap" in f.name:
            fieldmap_json = f

    return {
        "fieldmap_nifti": fieldmap_nifti,
        "fieldmap_json": fieldmap_json,
        "magnitude_nifti": magnitude_nifti,
    }


def _select_single(files):
    """Select single NIfTI + JSON for anat."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]

    nifti = _pick_newest(niftis) if niftis else None
    json_file = _pick_newest(jsons) if jsons else None

    return {"nifti": nifti, "json": json_file}


def _select_dwi(files):
    """Select NIfTI + JSON + bval + bvec for diffusion."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]
    bvals = [f for f in files if _is_bval(f)]
    bvecs = [f for f in files if _is_bvec(f)]

    return {
        "nifti": _pick_newest(niftis) if niftis else None,
        "json": _pick_newest(jsons) if jsons else None,
        "bval": _pick_newest(bvals) if bvals else None,
        "bvec": _pick_newest(bvecs) if bvecs else None,
    }
```

**Step 4: Run tests**

```bash
uv run pytest tests/bidsify/test_file_selector.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/file_selector.py tests/bidsify/test_file_selector.py
git commit -m "feat(bidsify): add file_selector module for duplicate resolution"
```

---

### Task 5: Create bids_writer module

**Files:**
- Create: `src/neuro_workflow/bidsify/bids_writer.py`
- Test: `tests/bidsify/test_bids_writer.py`

**Step 1: Write tests**

Create `tests/bidsify/test_bids_writer.py`:

```python
import json
import pytest
from pathlib import Path
from neuro_workflow.bidsify.bids_writer import (
    bids_filename,
    patch_sidecar,
    write_dataset_description,
)


def test_bids_filename_bold_echo():
    name = bids_filename("s03", "ses-01", task="rest", run=1, echo=1, suffix="bold")
    assert name == "sub-s03_ses-01_task-rest_run-1_echo-1_bold"


def test_bids_filename_fieldmap():
    name = bids_filename("s03", "ses-01", run=1, suffix="fieldmap")
    assert name == "sub-s03_ses-01_run-1_fieldmap"


def test_bids_filename_magnitude():
    name = bids_filename("s03", "ses-01", run=1, suffix="magnitude")
    assert name == "sub-s03_ses-01_run-1_magnitude"


def test_bids_filename_t1w_with_acq():
    name = bids_filename("s03", "ses-04", acq="MPRAGEPromo", suffix="T1w")
    assert name == "sub-s03_ses-04_acq-MPRAGEPromo_T1w"


def test_bids_filename_dwi():
    name = bids_filename("s03", "ses-01", acq="g105", dir="AP", run=1, suffix="dwi")
    assert name == "sub-s03_ses-01_acq-g105_dir-AP_run-1_dwi"


def test_patch_sidecar_adds_b0field_to_fieldmap(tmp_path):
    sidecar = tmp_path / "fieldmap.json"
    sidecar.write_text(json.dumps({"EchoTime": 0.005}))
    patch_sidecar(sidecar, b0_field_identifier="sub-s03_ses-01_run-1_fieldmap")
    data = json.loads(sidecar.read_text())
    assert data["B0FieldIdentifier"] == "sub-s03_ses-01_run-1_fieldmap"
    assert data["EchoTime"] == 0.005


def test_patch_sidecar_adds_b0field_source_to_bold(tmp_path):
    sidecar = tmp_path / "bold.json"
    sidecar.write_text(json.dumps({"RepetitionTime": 1.5}))
    patch_sidecar(sidecar, b0_field_source="sub-s03_ses-01_run-1_fieldmap")
    data = json.loads(sidecar.read_text())
    assert data["B0FieldSource"] == "sub-s03_ses-01_run-1_fieldmap"
    assert data["RepetitionTime"] == 1.5


def test_write_dataset_description(tmp_path):
    write_dataset_description(tmp_path, "Network Discovery Sample")
    desc = json.loads((tmp_path / "dataset_description.json").read_text())
    assert desc["Name"] == "Network Discovery Sample"
    assert desc["BIDSVersion"] == "1.10.0"
    assert desc["DatasetType"] == "raw"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/bidsify/test_bids_writer.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement bids_writer module**

Create `src/neuro_workflow/bidsify/bids_writer.py`:

```python
"""Write BIDS-formatted files from Flywheel downloads."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# BIDS entity ordering per the spec
_ENTITY_ORDER = ["sub", "ses", "task", "acq", "dir", "run", "echo"]


def bids_filename(subject, session, **entities):
    """Build a BIDS filename stem (without extension).

    Args:
        subject: Subject label without "sub-" prefix (e.g., "s03")
        session: Session label (e.g., "ses-01")
        **entities: BIDS entities (task, acq, dir, run, echo, suffix)

    Returns:
        BIDS filename stem like "sub-s03_ses-01_task-rest_run-1_echo-1_bold"
    """
    suffix = entities.pop("suffix", None)
    parts = [f"sub-{subject}", session]
    for key in _ENTITY_ORDER:
        if key in ("sub", "ses"):
            continue
        val = entities.get(key)
        if val is not None:
            parts.append(f"{key}-{val}")
    if suffix:
        parts.append(suffix)
    return "_".join(parts)


def patch_sidecar(sidecar_path, b0_field_identifier=None, b0_field_source=None):
    """Patch a JSON sidecar with B0 field metadata.

    Args:
        sidecar_path: Path to the JSON sidecar file
        b0_field_identifier: Value for B0FieldIdentifier (fieldmap sidecars)
        b0_field_source: Value for B0FieldSource (BOLD sidecars)
    """
    with open(sidecar_path) as f:
        data = json.load(f)
    if b0_field_identifier:
        data["B0FieldIdentifier"] = b0_field_identifier
    if b0_field_source:
        data["B0FieldSource"] = b0_field_source
    with open(sidecar_path, "w") as f:
        json.dump(data, f, indent=4)


def write_dataset_description(output_dir, name):
    """Write dataset_description.json to the output directory.

    Args:
        output_dir: Path to BIDS root directory
        name: Dataset name
    """
    desc = {
        "Name": name,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "Authors": ["Patrick Bissett", "Russell Poldrack", "Logan Bennett"],
        "GeneratedBy": [
            {"Name": "neuro-workflow bidsify", "Version": "0.2.0"}
        ],
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "dataset_description.json", "w") as f:
        json.dump(desc, f, indent=4)


def download_and_place(acq, file_obj, dest_path):
    """Download a file from Flywheel and save to dest_path.

    Args:
        acq: Flywheel acquisition object (has download_file method)
        file_obj: Flywheel file object (has .name)
        dest_path: Path where the file should be saved

    Returns:
        dict with download provenance info
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    acq.download_file(file_obj.name, str(dest_path))
    return {
        "fw_filename": file_obj.name,
        "bids_path": str(dest_path),
        "size": file_obj.size,
        "created": str(file_obj.created) if file_obj.created else None,
    }
```

**Step 4: Run tests**

```bash
uv run pytest tests/bidsify/test_bids_writer.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/bids_writer.py tests/bidsify/test_bids_writer.py
git commit -m "feat(bidsify): add bids_writer module for file placement and sidecar patching"
```

---

### Task 6: Create run.py orchestrator

**Files:**
- Create: `src/neuro_workflow/bidsify/run.py`
- Test: `tests/bidsify/test_run.py`

**Step 1: Write integration test**

Create `tests/bidsify/test_run.py`:

```python
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from neuro_workflow.bidsify.run import build_reconciliation, process_subject_session


def test_build_reconciliation():
    """Test reconciliation output structure."""
    sessions = [
        {
            "fw_subject": "s43-2",
            "fw_session": "20201112",
            "timestamp": datetime(2020, 11, 12, tzinfo=timezone.utc),
            "bids_session": "ses-01",
            "acquisitions": ["fmap-fieldmap", "task-rest_bold"],
        },
        {
            "fw_subject": "s43",
            "fw_session": "22473",
            "timestamp": datetime(2020, 11, 19, tzinfo=timezone.utc),
            "bids_session": "ses-02",
            "acquisitions": ["fmap-fieldmap", "task-rest_bold"],
        },
    ]
    recon = build_reconciliation("s43", sessions, ["s43", "s43-2"])
    assert recon["total_sessions"] == 2
    assert recon["flywheel_sources"] == ["s43", "s43-2"]
    assert recon["sessions"][0]["bids_session"] == "ses-01"
    assert recon["sessions"][0]["fw_subject"] == "s43-2"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/bidsify/test_run.py -v
```

Expected: FAIL

**Step 3: Implement run.py**

Create `src/neuro_workflow/bidsify/run.py`:

```python
"""Orchestrate Flywheel -> BIDS conversion."""

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from neuro_workflow.bidsify.config import map_acquisition, load_reconciliation_config
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
    download_and_place,
)

logger = logging.getLogger(__name__)


def build_reconciliation(canonical_label, sessions, fw_sources):
    """Build reconciliation record for a subject.

    Args:
        canonical_label: BIDS subject label
        sessions: List of session dicts with bids_session assigned
        fw_sources: List of FW subject labels that contributed

    Returns:
        Dict with reconciliation info for this subject
    """
    return {
        "flywheel_sources": sorted(set(fw_sources)),
        "total_sessions": len(sessions),
        "sessions": [
            {
                "bids_session": s["bids_session"],
                "fw_subject": s["fw_subject"],
                "fw_session_label": s["fw_session"],
                "timestamp": s["timestamp"].isoformat() if s["timestamp"] else None,
                "acquisitions": s["acquisitions"],
            }
            for s in sessions
        ],
        "warnings": [],
    }


def process_subject_session(
    subject_label, session_info, acq_objects, output_dir, log_entries
):
    """Process a single session: select files, download, rename, patch sidecars.

    Args:
        subject_label: BIDS subject label (e.g., "s03")
        session_info: Dict with bids_session, fw_session, acquisitions, etc.
        acq_objects: List of Flywheel acquisition objects for this session
        output_dir: BIDS root directory
        log_entries: List to append download log entries to
    """
    bids_ses = session_info["bids_session"]
    sub_dir = Path(output_dir) / f"sub-{subject_label}" / bids_ses

    # Track fieldmap identifier for B0FieldSource patching
    fieldmap_id = None
    bold_sidecars = []
    task_run_counter = Counter()

    # Sort acquisitions by timestamp so duplicate tasks get correct run numbering
    acq_objects_sorted = sorted(acq_objects, key=lambda a: a.timestamp or "")

    for acq in acq_objects_sorted:
        acq = acq.reload()
        mapping = map_acquisition(acq.label)
        if mapping is None:
            if acq.label not in (
                "3Plane Loc SSFSE", "GE HOS FOV28", "GE HOS FOV28_1", "GE HOS FOV28_2"
            ):
                logger.warning("Unknown acquisition '%s', skipping", acq.label)
            continue

        modality = mapping["modality"]
        selected = select_files(acq.files, modality)

        if modality == "func":
            task_name = mapping["task"]
            task_run_counter[task_name] += 1
            run = task_run_counter[task_name]

            if not selected:
                logger.error(
                    "No echo files found for %s %s %s, skipping",
                    subject_label, bids_ses, acq.label,
                )
                continue

            for echo_info in selected:
                stem = bids_filename(
                    subject_label, bids_ses,
                    task=task_name, run=run, echo=echo_info["echo"], suffix="bold",
                )
                dest_dir = sub_dir / "func"
                if echo_info["nifti"]:
                    info = download_and_place(
                        acq, echo_info["nifti"], dest_dir / f"{stem}.nii.gz"
                    )
                    log_entries.append(info)
                if echo_info["json"]:
                    json_path = dest_dir / f"{stem}.json"
                    info = download_and_place(acq, echo_info["json"], json_path)
                    log_entries.append(info)
                    bold_sidecars.append(json_path)

        elif modality == "fmap":
            run = 1  # one fieldmap per session
            fmap_id = bids_filename(
                subject_label, bids_ses, run=run, suffix="fieldmap"
            )
            fieldmap_id = fmap_id
            dest_dir = sub_dir / "fmap"

            if selected.get("fieldmap_nifti"):
                stem = bids_filename(subject_label, bids_ses, run=run, suffix="fieldmap")
                info = download_and_place(
                    acq, selected["fieldmap_nifti"], dest_dir / f"{stem}.nii.gz"
                )
                log_entries.append(info)
            if selected.get("fieldmap_json"):
                stem = bids_filename(subject_label, bids_ses, run=run, suffix="fieldmap")
                json_path = dest_dir / f"{stem}.json"
                info = download_and_place(acq, selected["fieldmap_json"], json_path)
                log_entries.append(info)
                patch_sidecar(json_path, b0_field_identifier=fmap_id)
            if selected.get("magnitude_nifti"):
                stem = bids_filename(subject_label, bids_ses, run=run, suffix="magnitude")
                info = download_and_place(
                    acq, selected["magnitude_nifti"], dest_dir / f"{stem}.nii.gz"
                )
                log_entries.append(info)

        elif modality == "anat":
            suffix = mapping["suffix"]
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "anat"
            stem = bids_filename(subject_label, bids_ses, acq=acq_label, suffix=suffix)

            if selected.get("nifti"):
                info = download_and_place(
                    acq, selected["nifti"], dest_dir / f"{stem}.nii.gz"
                )
                log_entries.append(info)
            if selected.get("json"):
                info = download_and_place(
                    acq, selected["json"], dest_dir / f"{stem}.json"
                )
                log_entries.append(info)

        elif modality == "dwi":
            dir_label = mapping.get("dir")
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "dwi"
            stem = bids_filename(
                subject_label, bids_ses, acq=acq_label, dir=dir_label, run=1, suffix="dwi"
            )

            for ext in ("nifti", "json", "bval", "bvec"):
                if selected.get(ext):
                    file_ext = {"nifti": ".nii.gz", "json": ".json", "bval": ".bval", "bvec": ".bvec"}[ext]
                    info = download_and_place(
                        acq, selected[ext], dest_dir / f"{stem}{file_ext}"
                    )
                    log_entries.append(info)

    # Patch all BOLD sidecars with B0FieldSource
    if fieldmap_id:
        for sidecar_path in bold_sidecars:
            if sidecar_path.exists():
                patch_sidecar(sidecar_path, b0_field_source=fieldmap_id)


def run_bidsify(sample_name, output_dir, subjects=None, flywheel_project=None, overwrite=False):
    """Main entry point for Flywheel -> BIDS conversion.

    Args:
        sample_name: "discovery" or "validation"
        output_dir: Path to BIDS output directory
        subjects: Optional list of subject labels to process (default: all in sample)
        flywheel_project: Flywheel project label (default from config)
        overwrite: Whether to overwrite existing output
    """
    import flywheel

    config = load_reconciliation_config()
    project_label = flywheel_project or config["flywheel_project"]
    aliases = config["subject_aliases"]
    skip = set(config["skip_subjects"])

    if subjects is None:
        subjects = config["samples"].get(sample_name, [])

    output_dir = Path(output_dir)
    if output_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Output directory exists: {output_dir}. Use --overwrite to replace."
        )

    fw = flywheel.Client()
    all_subjects, project = query_project_subjects(fw, project_label)

    reconciliation = {"generated": datetime.now(timezone.utc).isoformat(), "subjects": {}}
    all_log_entries = []

    for subject_label in subjects:
        if subject_label in skip:
            logger.info("Skipping %s (in skip list)", subject_label)
            continue

        logger.info("Processing %s...", subject_label)
        sessions = collect_subject_sessions(subject_label, all_subjects, aliases)
        sessions = build_session_timeline(sessions)

        fw_sources = [subject_label]
        for variant, canonical in aliases.items():
            if canonical == subject_label:
                fw_sources.append(variant)

        reconciliation["subjects"][subject_label] = build_reconciliation(
            subject_label, sessions, fw_sources
        )

        for session_info in sessions:
            # Get actual FW acquisition objects for this session
            fw_sub_label = session_info["fw_subject"]
            fw_ses_label = session_info["fw_session"]

            # Find the FW subject and session objects
            fw_sub = next(s for s in all_subjects if s.label == fw_sub_label)
            fw_ses = next(s for s in fw_sub.sessions() if s.label == fw_ses_label)
            acq_objects = list(fw_ses.acquisitions())

            process_subject_session(
                subject_label, session_info, acq_objects, output_dir, all_log_entries
            )

    # Write dataset description
    dataset_names = {
        "discovery": "Network Discovery Sample",
        "validation": "Network Validation Sample",
    }
    write_dataset_description(output_dir, dataset_names.get(sample_name, sample_name))

    # Write reconciliation and log
    sourcedata_dir = output_dir / "sourcedata"
    sourcedata_dir.mkdir(parents=True, exist_ok=True)

    with open(sourcedata_dir / "reconciliation.json", "w") as f:
        json.dump(reconciliation, f, indent=2)

    log = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_files": len(all_log_entries),
        "files": all_log_entries,
    }
    with open(sourcedata_dir / "bidsify_log.json", "w") as f:
        json.dump(log, f, indent=2)

    logger.info(
        "Done. %d subjects, %d files written to %s",
        len(subjects), len(all_log_entries), output_dir,
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/bidsify/test_run.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/run.py tests/bidsify/test_run.py
git commit -m "feat(bidsify): add run.py orchestrator for Flywheel -> BIDS conversion"
```

---

### Task 7: Wire into CLI

**Files:**
- Modify: `src/neuro_workflow/cli.py:197-261`
- Test: `tests/bidsify/test_cli_integration.py`

**Step 1: Write CLI integration test**

Create `tests/bidsify/test_cli_integration.py`:

```python
import sys
import pytest
from unittest.mock import patch, MagicMock
from neuro_workflow.cli import main


def test_bidsify_cli_parses_args(monkeypatch):
    """Test that the bidsify subcommand parses correctly."""
    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "bidsify", "discovery",
        "--output-dir", "/tmp/test_bids",
        "--subjects", "s03", "s10",
    ])
    with patch("neuro_workflow.cli.cmd_bidsify") as mock_cmd:
        mock_cmd.return_value = None
        main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.sample == "discovery"
        assert args.output_dir == "/tmp/test_bids"
        assert args.subjects == ["s03", "s10"]
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/bidsify/test_cli_integration.py -v
```

Expected: FAIL

**Step 3: Add bidsify subcommand to CLI**

Add to `src/neuro_workflow/cli.py`:

After the existing imports at the top, add:

```python
from neuro_workflow.bidsify.run import run_bidsify
```

Add the `cmd_bidsify` function before `main()`:

```python
def cmd_bidsify(args):
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    subjects = args.subjects if args.subjects else None
    run_bidsify(
        sample_name=args.sample,
        output_dir=args.output_dir,
        subjects=subjects,
        flywheel_project=args.flywheel_project,
        overwrite=args.overwrite,
    )
```

Inside `main()`, add the bidsify subparser after the exclusions block:

```python
    # bidsify
    bidsify_p = subparsers.add_parser("bidsify", help="Pull and BIDSify data from Flywheel")
    bidsify_p.add_argument("sample", help="Sample name (discovery, validation)")
    bidsify_p.add_argument("--output-dir", required=True, help="BIDS output directory")
    bidsify_p.add_argument("--subjects", nargs="+", help="Subject labels to process (default: all in sample)")
    bidsify_p.add_argument("--flywheel-project", default=None, help="Flywheel project label")
    bidsify_p.add_argument("--overwrite", action="store_true", help="Overwrite existing output")
    bidsify_p.set_defaults(func=lambda args, remaining: cmd_bidsify(args))
```

**Step 4: Run tests**

```bash
uv run pytest tests/bidsify/test_cli_integration.py -v
```

Expected: All pass.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All existing + new tests pass.

**Step 6: Commit**

```bash
git add src/neuro_workflow/cli.py tests/bidsify/test_cli_integration.py
git commit -m "feat(bidsify): wire bidsify subcommand into CLI"
```

---

### Task 8: Rebuild container and run on discovery sample

**Step 1: Rebuild container with bidsify deps**

```bash
sbatch setup.sh
```

Wait for completion, check `seff <job_id>`.

**Step 2: Run bidsify on discovery sample**

```bash
neuro-run bidsify discovery \
  --output-dir /scratch/users/logben/discovery_BIDS \
  --subjects s03 s10 s19 s29 s43
```

**Step 3: Verify output structure**

```bash
# Check BIDS structure
ls /scratch/users/logben/discovery_BIDS/
ls /scratch/users/logben/discovery_BIDS/sub-s03/
ls /scratch/users/logben/discovery_BIDS/sub-s43/ses-01/  # should be from s43-2

# Check reconciliation
cat /scratch/users/logben/discovery_BIDS/sourcedata/reconciliation.json | python3 -m json.tool | head -40

# Check sidecar patching
cat /scratch/users/logben/discovery_BIDS/sub-s03/ses-01/fmap/sub-s03_ses-01_run-1_fieldmap.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('B0FieldIdentifier'))"
cat /scratch/users/logben/discovery_BIDS/sub-s03/ses-01/func/sub-s03_ses-01_task-rest_run-1_echo-1_bold.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('B0FieldSource'))"
```

**Step 4: Run BIDS validator**

```bash
# Pull validator image (add to pull_image.sh or run directly)
apptainer pull /home/groups/russpold/singularity_images/bids-validator_2.4.1.sif docker://bids/validator:2.4.1

# Validate
apptainer run /home/groups/russpold/singularity_images/bids-validator_2.4.1.sif /scratch/users/logben/discovery_BIDS
```

**Step 5: Commit final state**

```bash
git add -A
git commit -m "feat(bidsify): complete Flywheel BIDSify module for discovery sample"
```
