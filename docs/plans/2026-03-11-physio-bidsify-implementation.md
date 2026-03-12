# Physio Data Integration into Bidsify Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Download gephysio gear analysis outputs from Flywheel and convert them to BIDS-formatted physio files alongside existing BOLD data.

**Architecture:** For each BOLD/DWI acquisition that has a `.gephysio.zip` input on Flywheel, find the corresponding gephysio analysis on the session, download its processed CSVs (`PPG_FltData.csv`, `RESP_FltData.csv`, trigger files), and convert them to BIDS physio format (`_recording-cardiac_physio.tsv.gz` + `_recording-respiratory_physio.tsv.gz` with JSON sidecars). The conversion is added as a new module `physio.py` that the existing `run.py` calls after processing each session's acquisitions.

**Tech Stack:** Python, Flywheel SDK, gzip, csv (stdlib only — no numpy/pandas needed)

---

## Background

### Flywheel Data Structure

Each BOLD acquisition on Flywheel has a `.gephysio.zip` file (type `"gephysio"`) containing raw GE physiological recordings. The `gephysio` Flywheel gear (v0.3.2, from [cni/gephysio](https://github.com/cni/gephysio)) processes these and produces **session-level analyses** with output files:

- `PPG_FltData.csv` — cardiac waveform, format: `timestamp_ms,amplitude` (10ms intervals = 100 Hz)
- `RESP_FltData.csv` — respiratory waveform, format: `timestamp_ms,amplitude` (40ms intervals = 25 Hz)
- `PPG_FltTrig.csv` — cardiac peak timestamps in ms (one per line)
- `RESP_FltTrig.csv` — respiratory peak timestamps in ms (one per line)
- `PPG_Stat.csv`, `RESP_Stat.csv` — summary statistics
- `PPG_SampSig.png`, `RESP_SampSig.png` — QC plots

Each analysis links to its source acquisition via `analysis.inputs[0]._parents['acquisition']`.

### Target BIDS Format

Per BIDS spec, physio files go in `func/` alongside their BOLD data:

```
sub-s1175/ses-02/func/
  sub-s1175_ses-02_task-rest_run-1_echo-1_bold.nii.gz
  sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.tsv.gz
  sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.json
  sub-s1175_ses-02_task-rest_run-1_recording-respiratory_physio.tsv.gz
  sub-s1175_ses-02_task-rest_run-1_recording-respiratory_physio.json
```

**Cardiac TSV** (tab-separated, gzipped, no header row in data but BIDS requires header):
```
cardiac	trigger
0.3970217	0
0.4125924	0
```
JSON sidecar: `{"SamplingFrequency": 100, "StartTime": 0.0, "Columns": ["cardiac", "trigger"], ...}`

**Respiratory TSV:**
```
respiratory	trigger
0.9398347	0
0.9393443	0
```
JSON sidecar: `{"SamplingFrequency": 25, "StartTime": 0.0, "Columns": ["respiratory", "trigger"], ...}`

### Key Details

- Cardiac is sampled at **100 Hz** (PPG_FltData has 10ms intervals)
- Respiratory is sampled at **25 Hz** (RESP_FltData has 40ms intervals)
- Trigger column: `1` at timestamps from the FltTrig file, `0` elsewhere
- The gear was run multiple times (Oct 2025, Jan 2026); use the **most recent** analysis batch
- Some acquisitions (DWI) may have no gear output (empty files list) — skip gracefully
- Discovery has 118 physio files in old BIDS; validation has 9228
- Not all acquisitions have gephysio.zip (e.g., s29 session 2 BOLD has no physio)

---

### Task 1: Add `recording` to BIDS filename entity order

**Files:**
- Modify: `src/neuro_workflow/bidsify/bids_writer.py:11`
- Test: `tests/bidsify/test_bids_writer.py`

**Step 1: Write the failing test**

Add to `tests/bidsify/test_bids_writer.py` inside `TestBidsFilename`:

```python
def test_bids_filename_physio(self):
    result = bids_filename(
        "s1175", "ses-02", task="rest", run=1, recording="cardiac", suffix="physio"
    )
    assert result == "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bidsify/test_bids_writer.py::TestBidsFilename::test_bids_filename_physio -v`
Expected: FAIL — `recording` entity is not in `ENTITY_ORDER`, so it gets dropped

**Step 3: Implement — add `recording` to entity order**

In `src/neuro_workflow/bidsify/bids_writer.py`, change line 11:

```python
ENTITY_ORDER = ("task", "acq", "dir", "run", "echo", "recording")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/bidsify/test_bids_writer.py::TestBidsFilename -v`
Expected: All PASS (existing tests unaffected since they don't use `recording`)

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/bids_writer.py tests/bidsify/test_bids_writer.py
git commit -m "feat(bidsify): add recording entity to BIDS filename generation"
```

---

### Task 2: Create `physio.py` — CSV-to-BIDS conversion logic

**Files:**
- Create: `src/neuro_workflow/bidsify/physio.py`
- Create: `tests/bidsify/test_physio.py`

This is the core conversion module. It takes gephysio gear CSV outputs and produces BIDS physio files. No Flywheel dependency — pure data transformation.

**Step 1: Write the failing tests**

Create `tests/bidsify/test_physio.py`:

```python
"""Tests for physio CSV-to-BIDS conversion."""

import csv
import gzip
import json
from pathlib import Path

import pytest

from neuro_workflow.bidsify.physio import (
    convert_physio_to_bids,
    parse_flt_data,
    parse_flt_trig,
    build_trigger_column,
)


class TestParseFltData:
    def test_parse_basic(self, tmp_path):
        """Parse PPG_FltData.csv: timestamp_ms,amplitude rows."""
        csv_path = tmp_path / "PPG_FltData.csv"
        csv_path.write_text("10,0.453789\n20,0.445052\n30,0.436389\n")

        timestamps, amplitudes = parse_flt_data(csv_path)

        assert timestamps == [10, 20, 30]
        assert len(amplitudes) == 3
        assert abs(amplitudes[0] - 0.453789) < 1e-6

    def test_parse_empty(self, tmp_path):
        """Empty file returns empty lists."""
        csv_path = tmp_path / "PPG_FltData.csv"
        csv_path.write_text("")

        timestamps, amplitudes = parse_flt_data(csv_path)

        assert timestamps == []
        assert amplitudes == []


class TestParseFltTrig:
    def test_parse_triggers(self, tmp_path):
        """Parse PPG_FltTrig.csv: one timestamp per line."""
        trig_path = tmp_path / "PPG_FltTrig.csv"
        trig_path.write_text("440\n1230\n2040\n")

        triggers = parse_flt_trig(trig_path)

        assert triggers == [440, 1230, 2040]

    def test_parse_empty_triggers(self, tmp_path):
        """Empty trigger file returns empty list."""
        trig_path = tmp_path / "PPG_FltTrig.csv"
        trig_path.write_text("")

        triggers = parse_flt_trig(trig_path)

        assert triggers == []


class TestBuildTriggerColumn:
    def test_trigger_at_matching_timestamps(self):
        """Trigger column is 1 at matching timestamps, 0 elsewhere."""
        timestamps = [10, 20, 30, 40, 50]
        trigger_times = [20, 40]

        result = build_trigger_column(timestamps, trigger_times)

        assert result == [0, 1, 0, 1, 0]

    def test_no_triggers(self):
        """All zeros when no trigger times."""
        timestamps = [10, 20, 30]
        trigger_times = []

        result = build_trigger_column(timestamps, trigger_times)

        assert result == [0, 0, 0]


class TestConvertPhysioToBids:
    def test_converts_cardiac(self, tmp_path):
        """Full cardiac conversion: CSV -> tsv.gz + JSON sidecar."""
        # Create input CSVs
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "PPG_FltData.csv").write_text(
            "10,0.40\n20,0.45\n30,0.50\n40,0.55\n50,0.60\n"
        )
        (input_dir / "PPG_FltTrig.csv").write_text("20\n40\n")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="cardiac",
        )

        # Check TSV
        tsv_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.tsv.gz"
        assert tsv_path.exists()
        content = gzip.decompress(tsv_path.read_bytes()).decode()
        lines = content.strip().split("\n")
        assert lines[0] == "cardiac\ttrigger"
        assert lines[1] == "0.40\t0"
        assert lines[2] == "0.45\t1"  # trigger at timestamp 20

        # Check JSON
        json_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.json"
        assert json_path.exists()
        meta = json.loads(json_path.read_text())
        assert meta["SamplingFrequency"] == 100
        assert meta["StartTime"] == 0.0
        assert meta["Columns"] == ["cardiac", "trigger"]

    def test_converts_respiratory(self, tmp_path):
        """Full respiratory conversion: CSV -> tsv.gz + JSON sidecar."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "RESP_FltData.csv").write_text(
            "40,0.73\n80,0.74\n120,0.75\n"
        )
        (input_dir / "RESP_FltTrig.csv").write_text("80\n")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="respiratory",
        )

        tsv_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-respiratory_physio.tsv.gz"
        assert tsv_path.exists()
        content = gzip.decompress(tsv_path.read_bytes()).decode()
        lines = content.strip().split("\n")
        assert lines[0] == "respiratory\ttrigger"
        assert lines[2] == "0.74\t1"  # trigger at timestamp 80

        json_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-respiratory_physio.json"
        meta = json.loads(json_path.read_text())
        assert meta["SamplingFrequency"] == 25

    def test_skips_missing_data_file(self, tmp_path):
        """Returns False when data CSV is missing."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="cardiac",
        )

        assert result is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bidsify/test_physio.py -v`
Expected: FAIL — `neuro_workflow.bidsify.physio` does not exist

**Step 3: Implement `physio.py`**

Create `src/neuro_workflow/bidsify/physio.py`:

```python
"""Convert gephysio gear CSV outputs to BIDS physio format."""

from __future__ import annotations

import csv
import gzip
import json
import logging
from pathlib import Path

from neuro_workflow.bidsify.bids_writer import bids_filename

logger = logging.getLogger(__name__)

# Gephysio gear output file naming
_CHANNEL_CONFIG = {
    "cardiac": {
        "data_file": "PPG_FltData.csv",
        "trig_file": "PPG_FltTrig.csv",
        "sampling_frequency": 100,
        "description": "continuous pulse measurement, amplitude normalized by gephysio gear to range [0, 1]",
    },
    "respiratory": {
        "data_file": "RESP_FltData.csv",
        "trig_file": "RESP_FltTrig.csv",
        "sampling_frequency": 25,
        "description": "continuous measurements by respiration belt, amplitude normalized by gephysio gear to range [0, 1]",
    },
}


def parse_flt_data(csv_path: Path) -> tuple[list[int], list[float]]:
    """Parse a gephysio FltData CSV file.

    Format: ``timestamp_ms,amplitude`` per line (no header).

    Returns:
        (timestamps_ms, amplitudes) — parallel lists.
    """
    timestamps: list[int] = []
    amplitudes: list[float] = []
    text = csv_path.read_text().strip()
    if not text:
        return timestamps, amplitudes
    for line in text.split("\n"):
        parts = line.split(",")
        timestamps.append(int(parts[0]))
        amplitudes.append(float(parts[1]))
    return timestamps, amplitudes


def parse_flt_trig(trig_path: Path) -> list[int]:
    """Parse a gephysio FltTrig CSV file.

    Format: one timestamp_ms per line (no header).
    """
    text = trig_path.read_text().strip()
    if not text:
        return []
    return [int(line) for line in text.split("\n") if line.strip()]


def build_trigger_column(
    timestamps: list[int], trigger_times: list[int]
) -> list[int]:
    """Build a binary trigger column: 1 at trigger timestamps, 0 elsewhere."""
    trigger_set = set(trigger_times)
    return [1 if ts in trigger_set else 0 for ts in timestamps]


def convert_physio_to_bids(
    input_dir: Path,
    output_dir: Path,
    subject: str,
    session: str,
    task: str,
    run: int,
    channel: str,
) -> bool:
    """Convert one channel of gephysio output to BIDS physio files.

    Args:
        input_dir: Directory containing gephysio CSV outputs.
        output_dir: BIDS func/ directory to write to.
        subject: Subject label (e.g. "s1175").
        session: Session label (e.g. "ses-02").
        task: Task name (e.g. "rest").
        run: Run number.
        channel: "cardiac" or "respiratory".

    Returns:
        True if files were written, False if source data was missing.
    """
    cfg = _CHANNEL_CONFIG[channel]
    data_path = input_dir / cfg["data_file"]
    trig_path = input_dir / cfg["trig_file"]

    if not data_path.exists():
        logger.debug("No %s data file at %s", channel, data_path)
        return False

    timestamps, amplitudes = parse_flt_data(data_path)
    if not timestamps:
        logger.warning("Empty %s data file: %s", channel, data_path)
        return False

    trigger_times = parse_flt_trig(trig_path) if trig_path.exists() else []
    triggers = build_trigger_column(timestamps, trigger_times)

    # Build BIDS filename
    stem = bids_filename(
        subject, session, task=task, run=run, recording=channel, suffix="physio"
    )

    # Write gzipped TSV
    output_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = output_dir / f"{stem}.tsv.gz"
    with gzip.open(tsv_path, "wt") as f:
        f.write(f"{channel}\ttrigger\n")
        for amp, trig in zip(amplitudes, triggers):
            f.write(f"{amp}\t{trig}\n")

    # Write JSON sidecar
    json_path = output_dir / f"{stem}.json"
    sidecar = {
        "SamplingFrequency": cfg["sampling_frequency"],
        "StartTime": 0.0,
        "Columns": [channel, "trigger"],
        "Manufacturer": "BIOPAC",
        channel: {
            "Description": cfg["description"],
            "Units": "arbitrary",
        },
        "trigger": {
            "Description": "continuous measurement of the scanner trigger signal",
        },
    }
    json_path.write_text(json.dumps(sidecar, indent=2))

    return True
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bidsify/test_physio.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/physio.py tests/bidsify/test_physio.py
git commit -m "feat(bidsify): add physio CSV-to-BIDS conversion module"
```

---

### Task 3: Create `physio_query.py` — Flywheel analysis querying

**Files:**
- Create: `src/neuro_workflow/bidsify/physio_query.py`
- Create: `tests/bidsify/test_physio_query.py`

This module queries Flywheel session analyses to find gephysio outputs and match them to acquisitions. Separated from `physio.py` to keep Flywheel SDK dependency isolated.

**Step 1: Write the failing tests**

Create `tests/bidsify/test_physio_query.py`:

```python
"""Tests for physio Flywheel query module."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from neuro_workflow.bidsify.physio_query import (
    find_gephysio_analyses,
    match_analyses_to_acquisitions,
)


def _make_analysis(label, gear_name, input_name, input_acq_id, files=None, created=None):
    """Create a mock Flywheel analysis object."""
    a = MagicMock()
    a.label = label
    a.gear_info = {"name": gear_name}
    a.created = created or datetime(2026, 1, 29, tzinfo=timezone.utc)
    a.files = files or []

    # Mock the input object
    inp = MagicMock()
    inp._name = input_name
    inp._parents = {"acquisition": input_acq_id}
    a.inputs = [inp]

    # reload returns self
    a.reload.return_value = a

    return a


def _make_file(name, ftype="tabular data", size=100):
    f = MagicMock()
    f.name = name
    f.type = ftype
    f.size = size
    return f


class TestFindGephysioAnalyses:
    def test_finds_gephysio_analyses(self):
        """Filters to only gephysio gear analyses with files."""
        gephysio_a = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq123",
            files=[_make_file("PPG_FltData.csv")],
        )
        other_a = _make_analysis(
            "mriqc 01/28/2026",
            "mriqc",
            "scan.nii.gz",
            "acq123",
            files=[_make_file("report.html")],
        )
        empty_a = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq456",
            files=[],
        )

        session = MagicMock()
        session.analyses = [gephysio_a, other_a, empty_a]

        result = find_gephysio_analyses(session)

        assert len(result) == 1
        assert result[0].label == "gephysio 01/28/2026"

    def test_picks_most_recent_batch(self):
        """When multiple runs exist, picks the most recently created."""
        old = _make_analysis(
            "gephysio 10/17/2025",
            "gephysio",
            "scan.gephysio.zip",
            "acq123",
            files=[_make_file("PPG_FltData.csv")],
            created=datetime(2025, 10, 17, tzinfo=timezone.utc),
        )
        new = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq123",
            files=[_make_file("PPG_FltData.csv")],
            created=datetime(2026, 1, 28, tzinfo=timezone.utc),
        )

        session = MagicMock()
        session.analyses = [old, new]

        result = find_gephysio_analyses(session)

        assert len(result) == 1
        assert result[0].created == datetime(2026, 1, 28, tzinfo=timezone.utc)


class TestMatchAnalysesToAcquisitions:
    def test_matches_by_acquisition_id(self):
        """Maps analysis to acquisition via input._parents['acquisition']."""
        analysis = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq_rest",
            files=[_make_file("PPG_FltData.csv")],
        )

        acq_map = {"acq_rest": {"task": "rest", "run": 1}}

        result = match_analyses_to_acquisitions([analysis], acq_map)

        assert len(result) == 1
        assert result[0]["task"] == "rest"
        assert result[0]["run"] == 1
        assert result[0]["analysis"] is analysis

    def test_skips_unmatched_acquisition(self):
        """Analyses for unknown acquisitions are skipped."""
        analysis = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq_unknown",
            files=[_make_file("PPG_FltData.csv")],
        )

        acq_map = {"acq_rest": {"task": "rest", "run": 1}}

        result = match_analyses_to_acquisitions([analysis], acq_map)

        assert len(result) == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bidsify/test_physio_query.py -v`
Expected: FAIL — module does not exist

**Step 3: Implement `physio_query.py`**

Create `src/neuro_workflow/bidsify/physio_query.py`:

```python
"""Query Flywheel for gephysio gear analysis outputs."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def find_gephysio_analyses(session: Any) -> list[Any]:
    """Find gephysio analyses on a Flywheel session.

    When the gear has been run multiple times, returns only the most
    recent batch (by created timestamp). Skips analyses with no output files.

    Args:
        session: A reloaded Flywheel session object.

    Returns:
        List of Flywheel analysis objects from the latest gear run.
    """
    all_analyses = session.analyses or []
    gephysio = [
        a for a in all_analyses
        if a.gear_info
        and a.gear_info.get("name") == "gephysio"
        and a.files
    ]

    if not gephysio:
        return []

    # Group by acquisition ID to find duplicates, keep newest per acquisition
    by_acq: dict[str, list[Any]] = defaultdict(list)
    for a in gephysio:
        a = a.reload()
        if not a.inputs:
            continue
        acq_id = a.inputs[0]._parents.get("acquisition", "unknown")
        by_acq[acq_id].append(a)

    # For each acquisition, keep only the most recently created analysis
    latest = []
    for acq_id, analyses in by_acq.items():
        newest = max(analyses, key=lambda a: a.created or "")
        latest.append(newest)

    return latest


def match_analyses_to_acquisitions(
    analyses: list[Any],
    acq_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match gephysio analyses to their source acquisitions.

    Args:
        analyses: List of gephysio analysis objects.
        acq_map: Mapping of acquisition ID -> {"task": str, "run": int}.

    Returns:
        List of dicts with keys: task, run, analysis.
    """
    matched = []
    for a in analyses:
        if not a.inputs:
            continue
        acq_id = a.inputs[0]._parents.get("acquisition")
        if acq_id not in acq_map:
            logger.debug(
                "Gephysio analysis for unknown acquisition %s, skipping", acq_id
            )
            continue
        info = acq_map[acq_id]
        matched.append({
            "task": info["task"],
            "run": info["run"],
            "analysis": a,
        })
    return matched
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bidsify/test_physio_query.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/bidsify/physio_query.py tests/bidsify/test_physio_query.py
git commit -m "feat(bidsify): add Flywheel gephysio analysis query module"
```

---

### Task 4: Integrate physio into `run.py` session processing

**Files:**
- Modify: `src/neuro_workflow/bidsify/run.py:72-248`
- Modify: `tests/bidsify/test_run.py`

This task wires the physio modules into the existing session processing loop. The key change: after processing all acquisitions for a session, query for gephysio analyses, download their CSVs to a temp dir, and convert to BIDS.

**Step 1: Write the failing test**

Add to `tests/bidsify/test_run.py`:

```python
from unittest.mock import patch, MagicMock, call
import tempfile


def test_process_subject_session_downloads_physio(tmp_path):
    """Physio CSVs are downloaded and converted when gephysio analyses exist."""
    # Build a minimal session with one BOLD acquisition
    session_info = {
        "bids_session": "ses-01",
        "fw_session": MagicMock(),
    }
    session_info["fw_session"].reload.return_value = session_info["fw_session"]

    # Mock acquisition
    acq = MagicMock()
    acq.label = "task-rest_bold"
    acq.id = "acq_rest_id"
    acq.timestamp = "2025-01-01T00:00:00"
    acq.reload.return_value = acq

    # Multi-echo files
    nifti = MagicMock()
    nifti.name = "bold_e1.nii.gz"
    nifti.type = "nifti"
    nifti.size = 100
    nifti.created = "2025-01-01T00:00:00"

    json_f = MagicMock()
    json_f.name = "bold_e1.json"
    json_f.type = "source code"
    json_f.size = 50
    json_f.created = "2025-01-01T00:00:00"

    acq.files = [nifti, json_f]

    # Mock gephysio analysis
    physio_analysis = MagicMock()
    ppg_file = MagicMock()
    ppg_file.name = "PPG_FltData.csv"
    resp_file = MagicMock()
    resp_file.name = "RESP_FltData.csv"
    physio_analysis.files = [ppg_file, resp_file]

    log_entries = []
    bidsignore_entries = []

    with patch("neuro_workflow.bidsify.run.find_gephysio_analyses") as mock_find, \
         patch("neuro_workflow.bidsify.run.match_analyses_to_acquisitions") as mock_match, \
         patch("neuro_workflow.bidsify.run.download_physio_analysis") as mock_dl, \
         patch("neuro_workflow.bidsify.run.convert_physio_to_bids") as mock_convert, \
         patch("neuro_workflow.bidsify.run._check_bold_4d", return_value=True), \
         patch("neuro_workflow.bidsify.run.download_and_place") as mock_download:

        mock_download.return_value = {
            "fw_filename": "bold_e1.nii.gz",
            "bids_path": str(tmp_path / "bold_e1.nii.gz"),
            "size": 100,
            "created": "2025-01-01T00:00:00",
        }

        mock_find.return_value = [physio_analysis]
        mock_match.return_value = [
            {"task": "rest", "run": 1, "analysis": physio_analysis}
        ]
        mock_dl.return_value = tmp_path / "physio_tmp"

        process_subject_session(
            "s1175", session_info, [acq], tmp_path, log_entries,
            bidsignore_entries=bidsignore_entries,
        )

        mock_find.assert_called_once()
        mock_match.assert_called_once()
        assert mock_convert.call_count == 2  # cardiac + respiratory
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bidsify/test_run.py::test_process_subject_session_downloads_physio -v`
Expected: FAIL — `find_gephysio_analyses` not imported in `run.py`

**Step 3: Implement the integration**

Modify `src/neuro_workflow/bidsify/run.py`:

**Add imports** (after existing imports, around line 10):

```python
import tempfile
from neuro_workflow.bidsify.physio import convert_physio_to_bids
from neuro_workflow.bidsify.physio_query import (
    find_gephysio_analyses,
    match_analyses_to_acquisitions,
)
```

**Add helper function** (before `process_subject_session`, around line 70):

```python
def download_physio_analysis(analysis, dest_dir):
    """Download gephysio analysis CSV files to a local directory.

    Args:
        analysis: Flywheel analysis object.
        dest_dir: Path to download files into.

    Returns:
        Path to the directory containing downloaded files.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in analysis.files:
        if f.name.endswith(".csv"):
            analysis.download_file(f.name, str(dest_dir / f.name))
    return dest_dir
```

**Modify `process_subject_session`**: Add two things:

1. Track acquisition IDs alongside task/run counters (inside the acquisition loop, after the `mapping = map_acquisition(acq.label)` block succeeds for `func` modality). Add to the `if modality == "func":` block, right after `bold_acq_count += 1` (around line 123):

```python
            # Track acq ID for physio matching
            acq_id_to_task[acq.id] = {"task": task_name, "run": run}
```

And declare `acq_id_to_task = {}` at the top of the function alongside the other state (around line 97):

```python
    acq_id_to_task = {}
```

2. After the existing B0FieldSource patching block (after line 237), add physio processing:

```python
    # Process physio data from gephysio analyses
    if acq_id_to_task:
        try:
            fw_session = session_info["fw_session"].reload()
            physio_analyses = find_gephysio_analyses(fw_session)
            if physio_analyses:
                matched = match_analyses_to_acquisitions(
                    physio_analyses, acq_id_to_task
                )
                func_dir = sub_dir / "func"
                for match in matched:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        dl_dir = download_physio_analysis(
                            match["analysis"], tmpdir
                        )
                        for channel in ("cardiac", "respiratory"):
                            convert_physio_to_bids(
                                input_dir=dl_dir,
                                output_dir=func_dir,
                                subject=subject_label,
                                session=bids_ses,
                                task=match["task"],
                                run=match["run"],
                                channel=channel,
                            )
        except Exception:
            logger.exception(
                "Failed to process physio for %s %s", subject_label, bids_ses
            )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bidsify/test_run.py -v`
Expected: All PASS (existing + new test)

**Step 5: Run full bidsify test suite**

Run: `uv run pytest tests/bidsify/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/neuro_workflow/bidsify/run.py tests/bidsify/test_run.py
git commit -m "feat(bidsify): integrate physio download and conversion into session processing"
```

---

### Task 5: Run bidsify for one subject to verify end-to-end

**Files:**
- Create: `/tmp/test_physio_e2e.py` (temporary, not committed)

This task verifies the physio integration works against real Flywheel data by running a single subject (s1175, 1 session).

**Step 1: Write and run a one-subject test script**

Create `/tmp/test_physio_e2e.py`:

```python
#!/usr/bin/env python3
"""Quick e2e: run bidsify for s1175 ses-01 only, check physio output."""
import json
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/tmp/physio_test_bids")

def main():
    import flywheel
    from neuro_workflow.bidsify.config import load_reconciliation_config
    from neuro_workflow.bidsify.flywheel_query import query_project_subjects
    from neuro_workflow.bidsify.run import _process_one_subject

    config = load_reconciliation_config()
    aliases = config["subject_aliases"]
    session_overrides = config.get("session_overrides", {})

    # Clean output
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    fw = flywheel.Client()
    all_subjects, project = query_project_subjects(fw, config["flywheel_project"])

    result = _process_one_subject(
        "s1175", all_subjects, aliases, OUTPUT_DIR,
        session_overrides=session_overrides,
    )

    # Check for physio files
    physio_files = list(OUTPUT_DIR.rglob("*physio*"))
    logger.info("Found %d physio files:", len(physio_files))
    for f in sorted(physio_files):
        logger.info("  %s (%d bytes)", f.relative_to(OUTPUT_DIR), f.stat().st_size)

    # Verify BIDS structure of first physio file
    json_files = [f for f in physio_files if f.suffix == ".json"]
    if json_files:
        meta = json.loads(json_files[0].read_text())
        logger.info("Sample sidecar: %s", json.dumps(meta, indent=2))

    logger.info("Total files downloaded: %d", len(result["log_entries"]))

if __name__ == "__main__":
    main()
```

Run: `uv run --extra bidsify python /tmp/test_physio_e2e.py`

Expected: Physio tsv.gz + JSON files appear in `sub-s1175/ses-01/func/` alongside BOLD files.

**Step 2: Verify output matches old BIDS format**

Compare against old BIDS:

```bash
# Check new output
ls /tmp/physio_test_bids/sub-s1175/ses-01/func/*physio*

# Compare sidecar format with old
diff <(cat /tmp/physio_test_bids/sub-s1175/ses-01/func/*cardiac_physio.json | python3 -m json.tool) \
     <(cat /oak/stanford/groups/russpold/data/network_grant/validation_BIDS/sub-s1175/ses-01/func/*cardiac_physio.json | python3 -m json.tool)

# Compare TSV headers
zcat /tmp/physio_test_bids/sub-s1175/ses-01/func/*cardiac_physio.tsv.gz | head -3
zcat /oak/stanford/groups/russpold/data/network_grant/validation_BIDS/sub-s1175/ses-01/func/*cardiac_physio.tsv.gz | head -3
```

**Step 3: Clean up test output**

```bash
rm -rf /tmp/physio_test_bids
rm /tmp/test_physio_e2e.py
```

---

### Task 6: Run full bidsify for both samples

This is the production run. Since the existing BIDS directories already have all non-physio data, we have two options:

**Option A (recommended): Run physio-only on existing directories**

Write a script that iterates over existing subjects and only processes physio (skips BOLD/anat/fmap/dwi). This avoids re-downloading ~100GB of imaging data.

Create `/tmp/run_physio_only.py`:

```python
#!/usr/bin/env python3
"""Add physio data to existing BIDS directories without re-downloading imaging."""
import json
import logging
import tempfile
from collections import Counter
from pathlib import Path

import flywheel

from neuro_workflow.bidsify.config import load_reconciliation_config, map_acquisition
from neuro_workflow.bidsify.flywheel_query import (
    collect_subject_sessions,
    build_session_timeline,
    query_project_subjects,
)
from neuro_workflow.bidsify.physio import convert_physio_to_bids
from neuro_workflow.bidsify.physio_query import (
    find_gephysio_analyses,
    match_analyses_to_acquisitions,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def download_physio_analysis(analysis, dest_dir):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in analysis.files:
        if f.name.endswith(".csv"):
            analysis.download_file(f.name, str(dest_dir / f.name))
    return dest_dir


def process_physio_for_subject(subject_label, all_subjects, aliases, output_dir, session_overrides):
    """Process physio only for an existing BIDS subject."""
    sessions = collect_subject_sessions(
        subject_label, all_subjects, aliases, session_overrides=session_overrides,
    )
    sessions = build_session_timeline(sessions)

    total_files = 0
    for session_info in sessions:
        bids_ses = session_info["bids_session"]
        func_dir = Path(output_dir) / f"sub-{subject_label}" / bids_ses / "func"

        # Build acq_id -> task/run mapping by replaying the same logic as run.py
        acq_objects = sorted(
            session_info["acquisitions"],
            key=lambda a: a.timestamp or "",
        )
        task_run_counter = Counter()
        acq_id_to_task = {}
        for acq in acq_objects:
            acq = acq.reload()
            mapping = map_acquisition(acq.label)
            if mapping and mapping["modality"] == "func":
                task_name = mapping["task"]
                task_run_counter[task_name] += 1
                acq_id_to_task[acq.id] = {
                    "task": task_name,
                    "run": task_run_counter[task_name],
                }

        if not acq_id_to_task:
            continue

        # Find and process physio analyses
        fw_session = session_info["fw_session"].reload()
        physio_analyses = find_gephysio_analyses(fw_session)
        if not physio_analyses:
            continue

        matched = match_analyses_to_acquisitions(physio_analyses, acq_id_to_task)
        for match in matched:
            with tempfile.TemporaryDirectory() as tmpdir:
                dl_dir = download_physio_analysis(match["analysis"], tmpdir)
                for channel in ("cardiac", "respiratory"):
                    if convert_physio_to_bids(
                        input_dir=dl_dir,
                        output_dir=func_dir,
                        subject=subject_label,
                        session=bids_ses,
                        task=match["task"],
                        run=match["run"],
                        channel=channel,
                    ):
                        total_files += 1

    return total_files


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True, choices=["discovery", "validation"])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--subjects", nargs="*", help="Specific subjects (default: all)")
    args = parser.parse_args()

    config = load_reconciliation_config()
    aliases = config["subject_aliases"]
    session_overrides = config.get("session_overrides", {})

    fw = flywheel.Client()
    all_subjects, project = query_project_subjects(fw, config["flywheel_project"])

    subjects = args.subjects or config["samples"].get(args.sample, [])
    skip = set(config["skip_subjects"])
    subjects = [s for s in subjects if s not in skip]

    grand_total = 0
    for subject in subjects:
        sub_dir = args.output_dir / f"sub-{subject}"
        if not sub_dir.exists():
            logger.warning("Skipping %s: not in BIDS directory", subject)
            continue

        n = process_physio_for_subject(
            subject, all_subjects, aliases, args.output_dir, session_overrides
        )
        if n > 0:
            logger.info("%s: wrote %d physio files", subject, n)
        grand_total += n

    logger.info("Done: %d total physio files across %d subjects", grand_total, len(subjects))


if __name__ == "__main__":
    main()
```

Run discovery:
```bash
uv run --extra bidsify python /tmp/run_physio_only.py \
    --sample discovery \
    --output-dir /scratch/users/logben/discovery_bids
```

Run validation:
```bash
uv run --extra bidsify python /tmp/run_physio_only.py \
    --sample validation \
    --output-dir /scratch/users/logben/validation_bids
```

**Expected:**
- Discovery: ~118 physio files (matching old BIDS count)
- Validation: ~9228 physio files (matching old BIDS count) — this will take a while

**Verify:**
```bash
find /scratch/users/logben/discovery_bids -name "*physio*" | wc -l
find /scratch/users/logben/validation_bids -name "*physio*" | wc -l
```

**Clean up temp script and commit any final adjustments:**
```bash
rm /tmp/run_physio_only.py
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Add `recording` entity to BIDS filenames | `bids_writer.py`, `test_bids_writer.py` |
| 2 | CSV-to-BIDS conversion module | `physio.py`, `test_physio.py` |
| 3 | Flywheel analysis query module | `physio_query.py`, `test_physio_query.py` |
| 4 | Wire physio into `run.py` | `run.py`, `test_run.py` |
| 5 | Single-subject e2e verification | `/tmp/test_physio_e2e.py` |
| 6 | Full production run (both samples) | `/tmp/run_physio_only.py` |
