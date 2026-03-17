# Behavioral Archive Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Create a unified migration script that moves behavioral data (mTurk, out_of_scanner, survey_data) from archive to properly structured BIDS-format locations, with sample-based filtering and comprehensive reporting.

**Architecture:** Modular script with three layers: (1) filename normalization utilities, (2) sample validation against config, (3) unified migration orchestrator with logging and JSON reporting. Leverages existing `config/behavioral_session_mapping.json` for sample lists. One-time migration but written as maintainable, re-runnable script.

**Tech Stack:** Python 3.10+, pathlib, json, logging, argparse. No external dependencies beyond stdlib.

---

## Task 1: Filename Normalization Module

Create utility functions to convert archive filenames to BIDS format. This is the foundational piece used by all other tasks.

**Files:**
- Create: `src/neuro_workflow/behavioral_archive/normalize_filenames.py`
- Test: `tests/behavioral_archive/test_normalize_filenames.py`

**Step 1: Write failing tests for task name normalization**

Create `tests/behavioral_archive/test_normalize_filenames.py`:

```python
import pytest
from neuro_workflow.behavioral_archive.normalize_filenames import normalize_task_name


def test_normalize_task_name_basic():
    """Strip _single_task_network suffix."""
    assert normalize_task_name("flanker_single_task_network") == "flanker"


def test_normalize_task_name_with_with():
    """Keep _with_ pairings, only strip suffixes."""
    assert normalize_task_name("go_nogo_with_shape_matching_single_task_network") == "goNogoWShapeMatching"


def test_normalize_task_name_strip_variants():
    """Remove various excess suffix variants."""
    assert normalize_task_name("directed_forgetting_single_task") == "directedForgetting"
    assert normalize_task_name("n_back_network") == "nBack"


def test_normalize_task_name_camelcase():
    """Convert to proper camelCase."""
    assert normalize_task_name("go_nogo") == "goNogo"
    assert normalize_task_name("stop_signal") == "stopSignal"


def test_normalize_task_name_dual_task():
    """Preserve dual-task combinations."""
    assert normalize_task_name("stop_signal_with_directed_forgetting") == "stopSignalWDirectedForgetting"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/behavioral_archive/test_normalize_filenames.py -v`

Expected: FAIL - module doesn't exist

**Step 3: Create the module and implement normalize_task_name**

Create `src/neuro_workflow/behavioral_archive/__init__.py` (empty):
```python
```

Create `src/neuro_workflow/behavioral_archive/normalize_filenames.py`:

```python
"""Utilities for normalizing behavioral archive filenames to BIDS format."""

import re


def normalize_task_name(task_str: str) -> str:
    """
    Convert snake_case archive task name to camelCase BIDS format.

    Removes excess suffixes (_single_task_network, _single_task, _network)
    while preserving meaningful _with_ combinations.

    Args:
        task_str: Archive filename or task name in snake_case

    Returns:
        Normalized task name in camelCase (BIDS format)

    Examples:
        "flanker_single_task_network" -> "flanker"
        "stop_signal_with_directed_forgetting" -> "stopSignalWDirectedForgetting"
    """
    # Remove excess suffixes
    task = re.sub(r"_single_task_network$|_single_task$|_network$", "", task_str)

    # Split on underscores
    parts = task.split("_")

    # Convert to camelCase
    if not parts:
        return ""

    camel = parts[0]  # First part stays lowercase
    for part in parts[1:]:
        if part == "with":
            # Special case: _with_ becomes W
            camel += "W"
        else:
            # Capitalize first letter
            camel += part.capitalize()

    return camel
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_normalize_filenames.py -v`

Expected: PASS (6 tests)

**Step 5: Write failing tests for archive filename patterns**

Add to `tests/behavioral_archive/test_normalize_filenames.py`:

```python
def test_normalize_mturk_filename():
    """Convert mTurk archive filename: s528_task.csv -> sub-s528_task-X_behavior.csv"""
    input_name = "s528_go_nogo_with_shape_matching.csv"
    # This will be tested in next task but we establish the pattern here
    pass


def test_normalize_out_of_scanner_filename():
    """Convert out_of_scanner filename."""
    input_name = "s247_flanker_single_task.csv"
    pass


def test_normalize_survey_filename():
    """Convert survey filename: prescan_1.json -> sub-XXX_prescan-01_survey.json"""
    input_name = "prescan_1.json"
    pass
```

**Step 6: Commit**

```bash
mkdir -p tests/behavioral_archive
git add src/neuro_workflow/behavioral_archive/ tests/behavioral_archive/test_normalize_filenames.py
git commit -m "feat(behavioral_archive): add task name normalization"
```

---

## Task 2: Filename Builders for Each Data Type

Create functions that build complete BIDS filenames from archive patterns.

**Files:**
- Modify: `src/neuro_workflow/behavioral_archive/normalize_filenames.py`
- Modify: `tests/behavioral_archive/test_normalize_filenames.py`

**Step 1: Write failing tests for mTurk, out_of_scanner, survey patterns**

Add to `tests/behavioral_archive/test_normalize_filenames.py`:

```python
from neuro_workflow.behavioral_archive.normalize_filenames import (
    normalize_mturk_filename,
    normalize_out_of_scanner_filename,
    normalize_survey_filename,
)


def test_normalize_mturk_filename_basic():
    """mTurk: s528_go_nogo_with_shape_matching.csv -> sub-s528_task-goNogoWShapeMatching_behavior.csv"""
    result = normalize_mturk_filename("s528_go_nogo_with_shape_matching.csv")
    assert result == "sub-s528_task-goNogoWShapeMatching_behavior.csv"


def test_normalize_mturk_filename_single_task_variant():
    """mTurk with single_task variant."""
    result = normalize_mturk_filename("s247_flanker_single_task_network.csv")
    assert result == "sub-s247_task-flanker_behavior.csv"


def test_normalize_out_of_scanner_filename():
    """out_of_scanner: s247_flanker.csv -> sub-s247_task-flanker_behavior.csv"""
    result = normalize_out_of_scanner_filename("s247_flanker_single_task.csv")
    assert result == "sub-s247_task-flanker_behavior.csv"


def test_normalize_survey_filename_basic():
    """survey: prescan_1.json -> sub-s247_prescan-01_survey.json (subject added later)"""
    result = normalize_survey_filename("prescan_1.json")
    assert result == "prescan-01_survey.json"


def test_normalize_survey_filename_with_subject():
    """survey with subject embedded."""
    result = normalize_survey_filename("prescan_2.json", subject="s247")
    assert result == "sub-s247_prescan-02_survey.json"


def test_normalize_survey_filename_padding():
    """survey numbers are zero-padded."""
    result = normalize_survey_filename("prescan_10.json", subject="s528")
    assert result == "sub-s528_prescan-10_survey.json"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/behavioral_archive/test_normalize_filenames.py::test_normalize_mturk_filename_basic -v`

Expected: FAIL - functions not defined

**Step 3: Implement the three filename builders**

Add to `src/neuro_workflow/behavioral_archive/normalize_filenames.py`:

```python
def normalize_mturk_filename(filename: str) -> str:
    """
    Normalize mTurk filename: s528_go_nogo_with_shape_matching.csv
    -> sub-s528_task-goNogoWShapeMatching_behavior.csv

    Args:
        filename: Archive filename (e.g., "s528_go_nogo_with_shape_matching.csv")

    Returns:
        BIDS-normalized filename with sub- prefix
    """
    # Remove extension
    stem = filename.rsplit(".", 1)[0]

    # Parse subject and task
    # Format: [s###]_[task_name] or [task_name]_[s###]
    parts = stem.split("_")

    subject = None
    task_parts = []

    for part in parts:
        if part.startswith("s") and part[1:].isdigit():
            subject = part
        else:
            task_parts.append(part)

    if not subject or not task_parts:
        raise ValueError(f"Could not parse mTurk filename: {filename}")

    task_name = "_".join(task_parts)
    normalized_task = normalize_task_name(task_name)

    # Get extension
    ext = filename.rsplit(".", 1)[1]

    return f"sub-{subject}_task-{normalized_task}_behavior.{ext}"


def normalize_out_of_scanner_filename(filename: str) -> str:
    """
    Normalize out_of_scanner filename: s247_flanker_single_task.csv
    -> sub-s247_task-flanker_behavior.csv

    Args:
        filename: Archive filename (e.g., "s247_flanker_single_task.csv")

    Returns:
        BIDS-normalized filename with sub- prefix
    """
    # Same logic as mTurk
    return normalize_mturk_filename(filename)


def normalize_survey_filename(filename: str, subject: str = None) -> str:
    """
    Normalize survey filename: prescan_1.json
    -> prescan-01_survey.json (or sub-s247_prescan-01_survey.json if subject given)

    Args:
        filename: Archive filename (e.g., "prescan_1.json")
        subject: Optional subject ID to include in output

    Returns:
        BIDS-normalized filename
    """
    # Extract number and extension
    match = re.match(r"prescan_(\d+)\.(.+)", filename)
    if not match:
        raise ValueError(f"Could not parse survey filename: {filename}")

    number = match.group(1)
    ext = match.group(2)

    # Zero-pad to 2 digits
    padded_number = number.zfill(2)

    # Build output
    if subject:
        return f"sub-{subject}_prescan-{padded_number}_survey.{ext}"
    else:
        return f"prescan-{padded_number}_survey.{ext}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_normalize_filenames.py -v`

Expected: PASS (13 tests)

**Step 5: Commit**

```bash
git add src/neuro_workflow/behavioral_archive/normalize_filenames.py tests/behavioral_archive/test_normalize_filenames.py
git commit -m "feat(behavioral_archive): add filename builders for each data type"
```

---

## Task 3: Sample Validation Module

Create utilities to load and validate subject samples from config.

**Files:**
- Create: `src/neuro_workflow/behavioral_archive/sample_validation.py`
- Test: `tests/behavioral_archive/test_sample_validation.py`

**Step 1: Write failing tests**

Create `tests/behavioral_archive/test_sample_validation.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from neuro_workflow.behavioral_archive.sample_validation import (
    load_samples_from_config,
    is_subject_in_sample,
)


def test_load_samples_from_config(tmp_path):
    """Load discovery and validation sample lists from behavioral_session_mapping.json"""
    config_file = tmp_path / "behavioral_session_mapping.json"
    config_data = {
        "discovery": ["s03", "s10", "s19"],
        "validation": ["s247", "s528"],
    }
    config_file.write_text(json.dumps(config_data))

    samples = load_samples_from_config(str(config_file))

    assert set(samples["discovery"]) == {"s03", "s10", "s19"}
    assert set(samples["validation"]) == {"s247", "s528"}


def test_load_samples_missing_file():
    """Raise error if config file not found."""
    with pytest.raises(FileNotFoundError):
        load_samples_from_config("/nonexistent/path/config.json")


def test_is_subject_in_sample_discovery():
    """Check if subject is in discovery sample."""
    samples = {"discovery": ["s03", "s10"], "validation": ["s247"]}

    assert is_subject_in_sample("s03", samples) is True
    assert is_subject_in_sample("s10", samples) is True
    assert is_subject_in_sample("s247", samples) is True
    assert is_subject_in_sample("s999", samples) is False


def test_is_subject_in_sample_with_subject_prefix():
    """Handle both with and without sub- prefix."""
    samples = {"discovery": ["s03", "s10"], "validation": []}

    assert is_subject_in_sample("s03", samples) is True
    assert is_subject_in_sample("sub-s03", samples) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/behavioral_archive/test_sample_validation.py -v`

Expected: FAIL - module doesn't exist

**Step 3: Implement sample validation module**

Create `src/neuro_workflow/behavioral_archive/sample_validation.py`:

```python
"""Utilities for validating subjects against discovery/validation samples."""

import json
from pathlib import Path
from typing import Dict, List, Set


def load_samples_from_config(config_path: str | Path) -> Dict[str, List[str]]:
    """
    Load discovery and validation sample lists from behavioral_session_mapping.json.

    Args:
        config_path: Path to config/behavioral_session_mapping.json

    Returns:
        Dict with 'discovery' and 'validation' keys containing subject lists

    Raises:
        FileNotFoundError: If config file doesn't exist
        KeyError: If required keys missing from config
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text())

    # Extract sample lists - support different config formats
    samples = {
        "discovery": data.get("discovery", []),
        "validation": data.get("validation", []),
    }

    # If config has session mappings, extract unique subjects
    if "discovery" not in data and "sessions" in data:
        discovery = set()
        validation = set()
        for session_info in data.get("sessions", []):
            subject = session_info.get("subject")
            sample = session_info.get("sample")
            if subject and sample:
                if sample == "discovery":
                    discovery.add(subject)
                elif sample == "validation":
                    validation.add(subject)
        samples["discovery"] = list(discovery)
        samples["validation"] = list(validation)

    return samples


def is_subject_in_sample(subject: str, samples: Dict[str, List[str]]) -> bool:
    """
    Check if subject is in discovery or validation sample.

    Args:
        subject: Subject ID (with or without 'sub-' prefix)
        samples: Dict from load_samples_from_config

    Returns:
        True if subject in either sample, False otherwise
    """
    # Normalize subject (remove sub- prefix if present)
    clean_subject = subject.replace("sub-", "")

    discovery = [s.replace("sub-", "") for s in samples.get("discovery", [])]
    validation = [s.replace("sub-", "") for s in samples.get("validation", [])]

    return clean_subject in discovery or clean_subject in validation
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_sample_validation.py -v`

Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/neuro_workflow/behavioral_archive/sample_validation.py tests/behavioral_archive/test_sample_validation.py
git commit -m "feat(behavioral_archive): add sample validation module"
```

---

## Task 4: File Copy Utilities with Error Handling

Create robust file copying with retry logic and permission handling.

**Files:**
- Create: `src/neuro_workflow/behavioral_archive/copy_utils.py`
- Test: `tests/behavioral_archive/test_copy_utils.py`

**Step 1: Write failing tests**

Create `tests/behavioral_archive/test_copy_utils.py`:

```python
import pytest
from pathlib import Path
from neuro_workflow.behavioral_archive.copy_utils import copy_file_with_retries


def test_copy_file_basic(tmp_path):
    """Copy file successfully."""
    src = tmp_path / "source.txt"
    src.write_text("content")
    dest = tmp_path / "dest" / "source.txt"

    copy_file_with_retries(src, dest, max_retries=1)

    assert dest.exists()
    assert dest.read_text() == "content"


def test_copy_file_creates_parents(tmp_path):
    """Create parent directories as needed."""
    src = tmp_path / "source.txt"
    src.write_text("content")
    dest = tmp_path / "a" / "b" / "c" / "source.txt"

    copy_file_with_retries(src, dest)

    assert dest.exists()
    assert dest.parent.exists()


def test_copy_file_skips_existing(tmp_path):
    """Skip if destination already exists."""
    src = tmp_path / "source.txt"
    src.write_text("new content")

    dest = tmp_path / "dest.txt"
    dest.write_text("old content")

    result = copy_file_with_retries(src, dest, skip_existing=True)

    assert result == "skipped"
    assert dest.read_text() == "old content"


def test_copy_file_raises_if_exists_and_no_skip(tmp_path):
    """Raise error if destination exists and skip=False."""
    src = tmp_path / "source.txt"
    src.write_text("new")

    dest = tmp_path / "dest.txt"
    dest.write_text("old")

    with pytest.raises(FileExistsError):
        copy_file_with_retries(src, dest, skip_existing=False)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/behavioral_archive/test_copy_utils.py -v`

Expected: FAIL - module doesn't exist

**Step 3: Implement copy utilities**

Create `src/neuro_workflow/behavioral_archive/copy_utils.py`:

```python
"""File copy utilities with retry logic and permission handling."""

import logging
import shutil
import time
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


def copy_file_with_retries(
    src: Path | str,
    dest: Path | str,
    max_retries: int = 3,
    skip_existing: bool = True,
) -> Literal["success", "skipped"]:
    """
    Copy file from src to dest with retry logic.

    Args:
        src: Source file path
        dest: Destination file path
        max_retries: Number of retry attempts
        skip_existing: If True, skip if dest exists; if False, raise error

    Returns:
        "success" if copied, "skipped" if destination exists and skip_existing=True

    Raises:
        FileExistsError: If dest exists and skip_existing=False
        Exception: On final retry failure
    """
    src = Path(src)
    dest = Path(dest)

    # Check if destination exists
    if dest.exists():
        if skip_existing:
            logger.debug(f"Skipping existing file: {dest}")
            return "skipped"
        else:
            raise FileExistsError(f"Destination already exists: {dest}")

    # Create parent directory
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Attempt copy with retries
    for attempt in range(max_retries):
        try:
            shutil.copy2(src, dest)
            logger.debug(f"Copied {src} -> {dest}")
            return "success"
        except Exception as exc:
            # Clean up partial file
            if dest.exists():
                try:
                    dest.unlink()
                except Exception:
                    pass

            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    f"Copy failed for {src} (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait}s: {exc}"
                )
                time.sleep(wait)
            else:
                logger.error(f"Copy failed for {src} after {max_retries} attempts: {exc}")
                raise

    return "success"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_copy_utils.py -v`

Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/neuro_workflow/behavioral_archive/copy_utils.py tests/behavioral_archive/test_copy_utils.py
git commit -m "feat(behavioral_archive): add file copy utilities with retry logic"
```

---

## Task 5: Main Migration Script

Create the unified migration orchestrator.

**Files:**
- Create: `scripts/migrate_archive_behavioral_data.py`
- Test: `tests/behavioral_archive/test_migrate_archive.py`

**Step 1: Write failing test for mTurk migration**

Create `tests/behavioral_archive/test_migrate_archive.py`:

```python
import json
import pytest
from pathlib import Path
from neuro_workflow.behavioral_archive.migrate import (
    migrate_mturk_data,
    migrate_out_of_scanner_data,
    migrate_survey_data,
)


def test_migrate_mturk_data(tmp_path):
    """Migrate all mTurk files to mTurk destination."""
    # Setup archive
    archive_mturk = tmp_path / "archive" / "mTurk" / "all_data"
    (archive_mturk / "s528").mkdir(parents=True)
    (archive_mturk / "s528" / "task1.csv").write_text("data")
    (archive_mturk / "s528" / "go_nogo_single_task.csv").write_text("more")
    (archive_mturk / "s999").mkdir(parents=True)
    (archive_mturk / "s999" / "task.csv").write_text("other")

    # Setup destination
    dest_mturk = tmp_path / "mturk"

    # Migrate
    stats = migrate_mturk_data(archive_mturk, dest_mturk, dry_run=False)

    # Verify
    assert stats["migrated"] == 3
    assert (dest_mturk / "sub-s528" / "task1_behavior.csv").exists()
    assert (dest_mturk / "sub-s999" / "task_behavior.csv").exists()


def test_migrate_mturk_data_dry_run(tmp_path):
    """Dry-run mode shows what would happen without copying."""
    archive_mturk = tmp_path / "archive" / "mTurk" / "all_data"
    (archive_mturk / "s528").mkdir(parents=True)
    (archive_mturk / "s528" / "task.csv").write_text("data")

    dest_mturk = tmp_path / "mturk"

    stats = migrate_mturk_data(archive_mturk, dest_mturk, dry_run=True)

    # Stats should show action but files should not be copied
    assert stats["migrated"] == 1
    assert not (dest_mturk / "sub-s528" / "task_behavior.csv").exists()


def test_migrate_out_of_scanner_data(tmp_path):
    """Migrate out_of_scanner data only for subjects in sample."""
    # Setup archive
    archive_out = tmp_path / "archive" / "out_of_scanner"
    (archive_out / "s247").mkdir(parents=True)
    (archive_out / "s247" / "flanker.csv").write_text("data")
    (archive_out / "s999").mkdir(parents=True)  # Not in sample
    (archive_out / "s999" / "task.csv").write_text("data")

    # Setup config with only s247
    config = {"discovery": ["s247"], "validation": []}

    dest_out = tmp_path / "sourcedata" / "out_scanner_behavior"

    stats = migrate_out_of_scanner_data(archive_out, dest_out, config, dry_run=False)

    # Should migrate s247 but skip s999
    assert stats["migrated"] == 1
    assert stats["skipped_not_in_sample"] == 1
    assert (dest_out / "sub-s247" / "flanker_behavior.csv").exists()
    assert not (dest_out / "sub-s999").exists()


def test_migrate_survey_data(tmp_path):
    """Migrate survey data only for subjects in sample."""
    # Setup archive
    archive_survey = tmp_path / "archive" / "survey_data" / "prescan_surveys" / "raw"
    (archive_survey / "s247").mkdir(parents=True)
    (archive_survey / "s247" / "prescan_1.json").write_text("{}")
    (archive_survey / "s247" / "prescan_2.json").write_text("{}")
    (archive_survey / "s528").mkdir(parents=True)
    (archive_survey / "s528" / "prescan_1.json").write_text("{}")

    config = {"discovery": ["s247"], "validation": ["s528"]}

    dest_survey = tmp_path / "sourcedata" / "survey_data"

    stats = migrate_survey_data(archive_survey, dest_survey, config, dry_run=False)

    # Should migrate both (both in sample)
    assert stats["migrated"] == 3
    assert (dest_survey / "sub-s247" / "prescan-01_survey.json").exists()
    assert (dest_survey / "sub-s247" / "prescan-02_survey.json").exists()
    assert (dest_survey / "sub-s528" / "prescan-01_survey.json").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/behavioral_archive/test_migrate_archive.py::test_migrate_mturk_data -v`

Expected: FAIL - module doesn't exist

**Step 3: Create migration module (core logic)**

Create `src/neuro_workflow/behavioral_archive/migrate.py`:

```python
"""Core migration logic for each data type."""

import logging
from pathlib import Path
from typing import Dict, Any

from .copy_utils import copy_file_with_retries
from .normalize_filenames import (
    normalize_mturk_filename,
    normalize_out_of_scanner_filename,
    normalize_survey_filename,
)
from .sample_validation import is_subject_in_sample

logger = logging.getLogger(__name__)


def migrate_mturk_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate all mTurk files (no sample filtering).

    Args:
        archive_dir: Path to archive/mTurk/all_data
        dest_dir: Path to output mTurk directory
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped": 0, "errors": 0}

    # Iterate subject directories
    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        subject = subject_dir.name
        dest_subject = dest_dir / f"sub-{subject}"

        # Copy all files from this subject
        for src_file in subject_dir.iterdir():
            if not src_file.is_file():
                continue

            # Normalize filename
            try:
                normalized_name = normalize_mturk_filename(src_file.name)
            except ValueError as e:
                logger.warning(f"Could not normalize {src_file.name}: {e}")
                stats["errors"] += 1
                continue

            dest_file = dest_subject / normalized_name

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1

    return stats


def migrate_out_of_scanner_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    samples: Dict[str, list],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate out_of_scanner files (sample-filtered).

    Args:
        archive_dir: Path to archive/out_of_scanner
        dest_dir: Path to output sourcedata/out_scanner_behavior
        samples: Sample dict from load_samples_from_config
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped_not_in_sample', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped_not_in_sample": 0, "errors": 0}

    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        subject = subject_dir.name

        # Check if in sample
        if not is_subject_in_sample(subject, samples):
            logger.info(f"Subject {subject} not in discovery/validation sample, skipping")
            # Count all files in this subject
            stats["skipped_not_in_sample"] += len(list(subject_dir.iterdir()))
            continue

        dest_subject = dest_dir / f"sub-{subject}"

        for src_file in subject_dir.iterdir():
            if not src_file.is_file():
                continue

            try:
                normalized_name = normalize_out_of_scanner_filename(src_file.name)
            except ValueError as e:
                logger.warning(f"Could not normalize {src_file.name}: {e}")
                stats["errors"] += 1
                continue

            dest_file = dest_subject / normalized_name

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1

    return stats


def migrate_survey_data(
    archive_dir: Path | str,
    dest_dir: Path | str,
    samples: Dict[str, list],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate survey data files (sample-filtered).

    Args:
        archive_dir: Path to archive/survey_data/prescan_surveys/raw
        dest_dir: Path to output sourcedata/survey_data
        samples: Sample dict from load_samples_from_config
        dry_run: If True, don't actually copy files

    Returns:
        Stats dict with 'migrated', 'skipped_not_in_sample', 'errors'
    """
    archive_dir = Path(archive_dir)
    dest_dir = Path(dest_dir)

    stats = {"migrated": 0, "skipped_not_in_sample": 0, "errors": 0}

    for subject_dir in sorted(archive_dir.iterdir()):
        if not subject_dir.is_dir():
            continue

        subject = subject_dir.name

        if not is_subject_in_sample(subject, samples):
            logger.info(f"Subject {subject} not in discovery/validation sample, skipping")
            stats["skipped_not_in_sample"] += len(list(subject_dir.iterdir()))
            continue

        dest_subject = dest_dir / f"sub-{subject}"

        for src_file in subject_dir.iterdir():
            if not src_file.is_file():
                continue

            try:
                normalized_name = normalize_survey_filename(src_file.name, subject=subject)
            except ValueError as e:
                logger.warning(f"Could not normalize {src_file.name}: {e}")
                stats["errors"] += 1
                continue

            dest_file = dest_subject / normalized_name

            if not dry_run:
                try:
                    copy_file_with_retries(src_file, dest_file, skip_existing=True)
                    stats["migrated"] += 1
                except Exception as e:
                    logger.error(f"Failed to copy {src_file}: {e}")
                    stats["errors"] += 1
            else:
                stats["migrated"] += 1

    return stats
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_migrate_archive.py -v`

Expected: PASS (4 tests)

**Step 5: Create the CLI script**

Create `scripts/migrate_archive_behavioral_data.py`:

```python
#!/usr/bin/env python
"""
Migrate behavioral data from archive to properly structured BIDS-format locations.

Usage:
    python migrate_archive_behavioral_data.py \\
        --archive-dir /oak/.../behavioral_data \\
        --sourcedata-dir /oak/.../sourcedata \\
        --mturk-dir /oak/.../mTurk \\
        --config /home/users/logben/neuro_workflow/config/behavioral_session_mapping.json
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime

from src.neuro_workflow.behavioral_archive.migrate import (
    migrate_mturk_data,
    migrate_out_of_scanner_data,
    migrate_survey_data,
)
from src.neuro_workflow.behavioral_archive.sample_validation import load_samples_from_config


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Migrate behavioral archive data to BIDS-format sourcedata."
    )
    parser.add_argument(
        "--archive-dir",
        required=True,
        type=Path,
        help="Path to archive behavioral_data directory",
    )
    parser.add_argument(
        "--sourcedata-dir",
        required=True,
        type=Path,
        help="Path to output sourcedata directory",
    )
    parser.add_argument(
        "--mturk-dir",
        required=True,
        type=Path,
        help="Path to output mTurk directory",
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to behavioral_session_mapping.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without copying files",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Load samples
    logger.info("Loading sample configuration...")
    samples = load_samples_from_config(args.config)
    logger.info(
        f"Loaded samples: {len(samples['discovery'])} discovery, "
        f"{len(samples['validation'])} validation"
    )

    # Run migrations
    logger.info("=" * 60)
    logger.info("MTURK MIGRATION")
    logger.info("=" * 60)

    archive_mturk = args.archive_dir / "mTurk" / "all_data"
    mturk_stats = migrate_mturk_data(archive_mturk, args.mturk_dir, dry_run=args.dry_run)
    logger.info(f"mTurk: {mturk_stats['migrated']} migrated, {mturk_stats['errors']} errors")

    logger.info("=" * 60)
    logger.info("OUT-OF-SCANNER BEHAVIOR MIGRATION")
    logger.info("=" * 60)

    archive_out = args.archive_dir / "out_of_scanner"
    dest_out = args.sourcedata_dir / "out_scanner_behavior"
    out_stats = migrate_out_of_scanner_data(
        archive_out, dest_out, samples, dry_run=args.dry_run
    )
    logger.info(
        f"Out-of-scanner: {out_stats['migrated']} migrated, "
        f"{out_stats['skipped_not_in_sample']} skipped (not in sample), "
        f"{out_stats['errors']} errors"
    )

    logger.info("=" * 60)
    logger.info("SURVEY DATA MIGRATION")
    logger.info("=" * 60)

    archive_survey = args.archive_dir / "survey_data" / "prescan_surveys" / "raw"
    dest_survey = args.sourcedata_dir / "survey_data"
    survey_stats = migrate_survey_data(
        archive_survey, dest_survey, samples, dry_run=args.dry_run
    )
    logger.info(
        f"Survey: {survey_stats['migrated']} migrated, "
        f"{survey_stats['skipped_not_in_sample']} skipped (not in sample), "
        f"{survey_stats['errors']} errors"
    )

    # Generate report
    report = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "mturk": mturk_stats,
        "out_of_scanner": out_stats,
        "survey": survey_stats,
        "total_migrated": mturk_stats["migrated"] + out_stats["migrated"] + survey_stats["migrated"],
    }

    report_path = args.sourcedata_dir / "behavioral_migration_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_migrate_archive.py -v`

Expected: PASS (4 tests)

**Step 7: Commit**

```bash
git add src/neuro_workflow/behavioral_archive/migrate.py \
         scripts/migrate_archive_behavioral_data.py \
         tests/behavioral_archive/test_migrate_archive.py
git commit -m "feat(behavioral_archive): add main migration script"
```

---

## Task 6: Update Existing Pipeline Script

Update `rename_behavioral_to_sourcedata.py` to use `in_scanner_behavior` instead of `behavioral_data`.

**Files:**
- Modify: `scripts/rename_behavioral_to_sourcedata.py`

**Step 1: Read the existing script**

Run: `head -100 scripts/rename_behavioral_to_sourcedata.py` to understand its structure

**Step 2: Make the directory change**

Find the line with `"behavioral_data"` and replace with `"in_scanner_behavior"`. Expected location around line 150-160.

**Step 3: Verify no tests are affected**

Run: `pytest tests/ -k behavioral -v` to ensure related tests still pass

**Step 4: Commit**

```bash
git add scripts/rename_behavioral_to_sourcedata.py
git commit -m "feat: update pipeline to use in_scanner_behavior directory naming"
```

---

## Task 7: Update Documentation

Update `README.md` to document the new directory structure and migration process.

**Files:**
- Modify: `README.md`

**Step 1: Update Stage 2 section with new directories**

Find the section on "Stage 2: Behavioral Events" and add note about new directory structure:

```markdown
### Directory Structure

Behavioral data is organized into three separate locations:

1. **in_scanner_behavior** — Behavioral task data collected during fMRI scanning (discovery/validation subjects only)
   - Source: `scripts/rename_behavioral_to_sourcedata.py`
   - Location: `sourcedata/in_scanner_behavior/sub-XXX/`

2. **out_scanner_behavior** — Behavioral data collected outside scanner (discovery/validation subjects only)
   - Source: `scripts/migrate_archive_behavioral_data.py` (one-time migration)
   - Location: `sourcedata/out_scanner_behavior/sub-XXX/`

3. **survey_data** — Prescan survey responses (discovery/validation subjects only)
   - Source: `scripts/migrate_archive_behavioral_data.py` (one-time migration)
   - Location: `sourcedata/survey_data/sub-XXX/`

4. **mTurk** — Behavioral data from separate mTurk sample (all subjects)
   - Source: `scripts/migrate_archive_behavioral_data.py` (one-time migration)
   - Location: `mTurk/sub-XXX/`
```

**Step 2: Add section on one-time archive migration**

Add before "Stage 3" section:

```markdown
## One-Time Archive Migration

Behavioral data from the archive directory must be migrated once to organize it into the proper structure above. This is done via:

```bash
python scripts/migrate_archive_behavioral_data.py \
    --archive-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data \
    --sourcedata-dir /oak/stanford/groups/russpold/data/network_grant/sourcedata \
    --mturk-dir /oak/stanford/groups/russpold/data/network_grant/mTurk \
    --config config/behavioral_session_mapping.json \
    --dry-run  # optional: preview without copying
```

This script:
- Validates subjects against discovery/validation sample lists
- Normalizes filenames to BIDS camelCase format
- Copies files to appropriate locations
- Generates a report of migration statistics and missing data
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add behavioral data directory structure and archive migration guide"
```

---

## Task 8: Integration Testing

Test the complete migration end-to-end.

**Files:**
- Test: `tests/behavioral_archive/test_integration.py`

**Step 1: Write integration test**

Create `tests/behavioral_archive/test_integration.py`:

```python
import json
import pytest
from pathlib import Path
import subprocess


def test_migration_end_to_end(tmp_path):
    """Full migration test with real CLI."""
    # Create realistic archive structure
    archive_root = tmp_path / "archive"

    # mTurk data
    mturk_data = archive_root / "behavioral_data" / "mTurk" / "all_data"
    (mturk_data / "s528").mkdir(parents=True)
    (mturk_data / "s528" / "go_nogo_with_shape_matching.csv").write_text("s528,data")
    (mturk_data / "s999").mkdir(parents=True)
    (mturk_data / "s999" / "flanker_single_task_network.csv").write_text("s999,data")

    # out_of_scanner data
    out_data = archive_root / "behavioral_data" / "out_of_scanner"
    (out_data / "s247").mkdir(parents=True)
    (out_data / "s247" / "flanker.csv").write_text("s247,data")
    (out_data / "s528").mkdir(parents=True)
    (out_data / "s528" / "stop_signal_single_task.csv").write_text("s528,data")

    # survey data
    survey_data = archive_root / "behavioral_data" / "survey_data" / "prescan_surveys" / "raw"
    (survey_data / "s247").mkdir(parents=True)
    (survey_data / "s247" / "prescan_1.json").write_text("{}")
    (survey_data / "s247" / "prescan_2.json").write_text("{}")

    # Create config
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "discovery": ["s247", "s528"],
        "validation": [],
    }))

    # Create output dirs
    sourcedata = tmp_path / "sourcedata"
    mturk_out = tmp_path / "mturk"

    # Run migration
    cmd = [
        "python", "scripts/migrate_archive_behavioral_data.py",
        "--archive-dir", str(archive_root / "behavioral_data"),
        "--sourcedata-dir", str(sourcedata),
        "--mturk-dir", str(mturk_out),
        "--config", str(config),
    ]

    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent.parent)
    assert result.returncode == 0

    # Verify output
    assert (mturk_out / "sub-s528" / "task-goNogoWShapeMatching_behavior.csv").exists()
    assert (mturk_out / "sub-s999" / "task-flanker_behavior.csv").exists()

    assert (sourcedata / "out_scanner_behavior" / "sub-s247" / "flanker_behavior.csv").exists()
    assert (sourcedata / "out_scanner_behavior" / "sub-s528" / "task-stopSignal_behavior.csv").exists()

    assert (sourcedata / "survey_data" / "sub-s247" / "prescan-01_survey.json").exists()
    assert (sourcedata / "survey_data" / "sub-s247" / "prescan-02_survey.json").exists()

    # Verify report
    report = sourcedata / "behavioral_migration_report.json"
    assert report.exists()
    report_data = json.loads(report.read_text())
    assert report_data["total_migrated"] == 7  # 2 mturk + 2 out + 2 survey + 1 more survey
    assert report_data["mturk"]["migrated"] == 2
    assert report_data["out_of_scanner"]["migrated"] == 2
    assert report_data["survey"]["migrated"] == 2
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/behavioral_archive/test_integration.py -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/behavioral_archive/test_integration.py
git commit -m "test: add end-to-end integration test for archive migration"
```

---

## Summary

This plan breaks down the behavioral archive migration into 8 bite-sized tasks:

1. **Filename Normalization** — Core task name conversion (snake_case → camelCase)
2. **Filename Builders** — Format-specific filename generation (mTurk, out_of_scanner, survey)
3. **Sample Validation** — Load and check subjects against discovery/validation config
4. **Copy Utilities** — Robust file copying with retry logic
5. **Migration Script** — Unified orchestrator for all three data types
6. **Pipeline Update** — Change `behavioral_data` → `in_scanner_behavior` in existing script
7. **Documentation** — Update README with new directory structure
8. **Integration Testing** — End-to-end validation

Each task includes complete code, exact test commands, and focused commits for easy review and rollback.

---

Plan saved to `docs/plans/2026-03-12-behavioral-archive-migration-impl.md`.

## Execution Options

**Two approaches:**

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review code against spec and quality standards, and handle iterations. Fast feedback loops, visible progress here.

**2. Parallel Session (separate)** — You open a new session in the worktree, using the executing-plans skill for batch execution with checkpoints.

**Which approach would you prefer?**