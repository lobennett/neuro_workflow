# Behavioral Events Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Port event file creation from `discovery_wm/events/`, behavioral QC from `network-behavior-qc/`, and NIfTI trimming into `neuro_workflow` as three CLI commands (`neuro-run events create/qc/trim`) plus a one-shot rename script.

**Architecture:** Three modules under `src/neuro_workflow/events/` (create, qc, trim) with shared utilities. A standalone rename script copies raw behavioral CSVs into BIDS `sourcedata/` layout. The QC module produces exclusion entries that integrate with the existing `neuro-run exclusions` system via a generator in `src/neuro_workflow/exclusions/behavioral.py` (replacing the current stub). CLI wiring adds an `events` subcommand group to `cli.py`.

**Tech Stack:** Python 3.13, pandas, numpy, nibabel (for NIfTI trimming), existing neuro_workflow CLI framework.

---

## Task 1: Rename Script — Task Name Mapping and File Discovery

**Files:**
- Create: `scripts/rename_behavioral_to_sourcedata.py`
- Test: `tests/events/test_rename_script.py`

**Step 1: Write the failing test for filename parsing**

```python
# tests/events/test_rename_script.py
import pytest

# We'll test the parsing/mapping functions that will be importable from the script
# For now, test as module-level functions

def test_descriptive_single_task_parsing():
    """Descriptive filenames like stop_signal_single_task_network__fmri_results.csv"""
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("stop_signal_single_task_network__fmri_results.csv")
    assert result == "stopSignal"

def test_descriptive_single_task_with_copy_number():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("stop_signal_single_task_network__fmri_results (3).csv")
    assert result == "stopSignal"

def test_descriptive_dual_task_parsing():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("stop_signal_with_flanker__fmri_results.csv")
    assert result == "stopSignalWFlanker"

def test_bids_style_dash_separated():
    """BIDS-style like sub-s29_ses-01_task-stop-signal_desc-raw.csv"""
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("sub-s29_ses-01_task-stop-signal_desc-raw.csv")
    assert result == "stopSignal"

def test_bids_style_camelcase():
    """BIDS-style like sub-s76_ses-01_task-stopSignal_desc-beh.csv"""
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("sub-s76_ses-01_task-stopSignal_desc-beh.csv")
    assert result == "stopSignal"

def test_all_single_tasks():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    cases = {
        "flanker_single_task_network__fmri_results.csv": "flanker",
        "go_nogo_single_task_network__fmri_results.csv": "goNogo",
        "n_back_single_task_network__fmri_results.csv": "nBack",
        "cued_task_switching_single_task_network__fmri_results.csv": "cuedTS",
        "spatial_task_switching_single_task_network__fmri_results.csv": "spatialTS",
        "directed_forgetting_single_task_network__fmri_results.csv": "directedForgetting",
        "shape_matching_single_task_network__fmri_results.csv": "shapeMatching",
    }
    for filename, expected in cases.items():
        assert parse_csv_filename(filename) == expected, f"Failed for {filename}"

def test_all_dual_tasks():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    cases = {
        "stop_signal_with_directed_forgetting__fmri_results.csv": "stopSignalWDirectedForgetting",
        "directed_forgetting_with_flanker__fmri_results.csv": "directedForgettingWFlanker",
        "spatial_task_switching_with_cued_task_switching__fmri_results.csv": "spatialTSWCuedTS",
        "flanker_with_shape_matching__fmri_results.csv": "flankerWShapeMatching",
        "flanker_with_cued_task_switching__fmri_results.csv": "cuedTSWFlanker",
        "n_back_with_shape_matching__fmri_results.csv": "nBackWShapeMatching",
        "n_back_with_spatial_task_switching__fmri_results.csv": "nBackWSpatialTS",
        "shape_matching_with_cued_task_switching__fmri_results.csv": "shapeMatchingWCuedTS",
        "shape_matching_with_spatial_task_switching__fmri_results.csv": "spatialTSWShapeMatching",
        "cued_task_switching_with_directed_forgetting__fmri_results.csv": "directedForgettingWCuedTS",
    }
    for filename, expected in cases.items():
        assert parse_csv_filename(filename) == expected, f"Failed for {filename}"

def test_bids_style_dual_task():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("sub-s29_ses_11_task-stop_signal_with_flanker_desc_raw.csv")
    assert result == "stopSignalWFlanker"

def test_build_output_path():
    from scripts.rename_behavioral_to_sourcedata import build_output_path
    from pathlib import Path
    result = build_output_path(
        output_root=Path("/oak/data/sourcedata"),
        subject="s1035",
        session="ses-1",
        task_name="stopSignal",
    )
    assert result == Path("/oak/data/sourcedata/sub-s1035/ses-01/beh/sub-s1035_ses-01_task-stopSignal_beh.csv")

def test_build_output_path_already_padded():
    from scripts.rename_behavioral_to_sourcedata import build_output_path
    from pathlib import Path
    result = build_output_path(
        output_root=Path("/oak/data/sourcedata"),
        subject="s03",
        session="ses-01",
        task_name="flanker",
    )
    assert result == Path("/oak/data/sourcedata/sub-s03/ses-01/beh/sub-s03_ses-01_task-flanker_beh.csv")
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_rename_script.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError` since the script doesn't exist yet.

**Step 3: Write the rename script**

```python
#!/usr/bin/env python3
"""One-time migration: standardize raw behavioral CSV filenames to BIDS sourcedata layout.

Usage:
    python scripts/rename_behavioral_to_sourcedata.py \
        --input-dir /oak/.../behavioral_data/raw_cleaned \
        --output-dir /oak/.../behavioral_data/sourcedata \
        [--dry-run]
"""
import argparse
import logging
import re
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Canonical mapping from raw long names to BIDS camelCase task names
LONG_NAME_TO_BIDS = {
    "stop_signal": "stopSignal",
    "flanker": "flanker",
    "go_nogo": "goNogo",
    "n_back": "nBack",
    "cued_task_switching": "cuedTS",
    "spatial_task_switching": "spatialTS",
    "directed_forgetting": "directedForgetting",
    "shape_matching": "shapeMatching",
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

# Reverse mapping for BIDS-style filenames (camelCase and dash-separated)
_BIDS_TASK_ALIASES = {
    "go-nogo": "goNogo",
    "stop-signal": "stopSignal",
    "shape-matching": "shapeMatching",
    "spatial-task-switching": "spatialTS",
    "cued-task-switching": "cuedTS",
    "directed-forgetting": "directedForgetting",
    "n-back": "nBack",
    "nBack": "nBack",
    "stopSignal": "stopSignal",
    "goNogo": "goNogo",
    "shapeMatching": "shapeMatching",
    "spatialTaskSwitching": "spatialTS",
    "cuedTaskSwitching": "cuedTS",
    "directedForgetting": "directedForgetting",
    "flanker": "flanker",
    # Dual tasks in BIDS-style
    "stop_signal_with_flanker": "stopSignalWFlanker",
    "stop_signal_with_directed_forgetting": "stopSignalWDirectedForgetting",
    "directed_forgetting_with_flanker": "directedForgettingWFlanker",
}


def parse_csv_filename(filename: str) -> str | None:
    """Extract canonical BIDS task name from any of the three naming patterns.

    Patterns:
    1. Descriptive: stop_signal_single_task_network__fmri_results (3).csv
    2. BIDS dash-separated: sub-s29_ses-01_task-stop-signal_desc-raw.csv
    3. BIDS camelCase: sub-s76_ses-01_task-stopSignal_desc-beh.csv

    Returns the camelCase BIDS task name, or None if not recognized.
    """
    # Pattern 1: descriptive style (with or without copy number)
    # Remove copy number like " (3)" and .csv extension
    base = re.sub(r"\s*\(\d+\)", "", filename)
    base = re.sub(r"\s*copy", "", base)
    base = base.replace(".csv", "")

    if "__fmri" in base:
        long_name = base.split("__fmri")[0]
        if "_single_task_network" in long_name:
            long_name = long_name.split("_single_task_network")[0]
        return LONG_NAME_TO_BIDS.get(long_name)

    # Pattern 2/3: BIDS-style with task- entity
    m = re.search(r"task-([^_]+)", base)
    if m:
        task_raw = m.group(1)
        # Check direct alias
        if task_raw in _BIDS_TASK_ALIASES:
            return _BIDS_TASK_ALIASES[task_raw]
        # Check if it's already a valid BIDS name
        if task_raw in LONG_NAME_TO_BIDS.values():
            return task_raw
        # Try converting dashes to underscores for dual task lookup
        task_underscore = task_raw.replace("-", "_")
        if task_underscore in LONG_NAME_TO_BIDS:
            return LONG_NAME_TO_BIDS[task_underscore]
        return None

    # Pattern for BIDS-style dual tasks with underscores in task field
    # e.g., sub-s29_ses_11_task-stop_signal_with_flanker_desc_raw.csv
    m2 = re.search(r"task-(.+?)_desc", base)
    if m2:
        task_raw = m2.group(1)
        task_underscore = task_raw.replace("-", "_")
        if task_underscore in LONG_NAME_TO_BIDS:
            return LONG_NAME_TO_BIDS[task_underscore]
        if task_raw in _BIDS_TASK_ALIASES:
            return _BIDS_TASK_ALIASES[task_raw]

    return None


def zero_pad_session(session: str) -> str:
    """Zero-pad session label: ses-1 -> ses-01, ses-01 stays ses-01."""
    m = re.match(r"ses-(\d+)", session)
    if m:
        return f"ses-{int(m.group(1)):02d}"
    return session


def build_output_path(
    output_root: Path, subject: str, session: str, task_name: str
) -> Path:
    """Build BIDS sourcedata output path."""
    sub_label = subject if subject.startswith("sub-") else f"sub-{subject}"
    ses_label = zero_pad_session(session)
    filename = f"{sub_label}_{ses_label}_task-{task_name}_beh.csv"
    return output_root / sub_label / ses_label / "beh" / filename


SKIP_DIRS = {"dropped_subjects", "exclusions", "pretouch", "practice", "extra"}


def discover_csvs(input_dir: Path):
    """Yield (csv_path, subject_label, session_label) for all behavioral CSVs."""
    for subj_dir in sorted(input_dir.iterdir()):
        if not subj_dir.is_dir() or subj_dir.name in SKIP_DIRS:
            continue
        for ses_dir in sorted(subj_dir.iterdir()):
            if not ses_dir.is_dir() or ses_dir.name in SKIP_DIRS:
                continue
            if not ses_dir.name.startswith("ses-"):
                continue
            for csv_file in sorted(ses_dir.glob("*.csv")):
                # Skip practice files and extra directories
                if "practice" in str(csv_file).lower():
                    continue
                yield csv_file, subj_dir.name, ses_dir.name


def main():
    parser = argparse.ArgumentParser(description="Rename behavioral CSVs to BIDS sourcedata layout")
    parser.add_argument("--input-dir", required=True, type=Path, help="raw_cleaned directory")
    parser.add_argument("--output-dir", required=True, type=Path, help="sourcedata output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print mapping without copying")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    copied = 0
    skipped = 0
    for csv_path, subject, session in discover_csvs(args.input_dir):
        task_name = parse_csv_filename(csv_path.name)
        if task_name is None:
            log.warning("Skipping unrecognized file: %s", csv_path)
            skipped += 1
            continue
        out_path = build_output_path(args.output_dir, subject, session, task_name)
        log.info("%s -> %s", csv_path, out_path)
        if not args.dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(csv_path, out_path)
        copied += 1

    log.info("Done: %d copied, %d skipped", copied, skipped)


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_rename_script.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/rename_behavioral_to_sourcedata.py tests/events/test_rename_script.py
git commit -m "feat(events): add rename script for behavioral data to BIDS sourcedata layout"
```

---

## Task 2: Event Utilities Module — Timing and Column Processing

**Files:**
- Create: `src/neuro_workflow/events/__init__.py`
- Create: `src/neuro_workflow/events/utils.py`
- Test: `tests/events/test_utils.py`

**Step 1: Write the failing tests**

```python
# tests/events/test_utils.py
import pandas as pd
import numpy as np
import pytest


def _make_basic_df():
    """Minimal behavioral CSV dataframe with timing columns."""
    return pd.DataFrame({
        "trial_id": ["fmri_trigger_initial", "test_trial", "test_trial", "test_trial"],
        "time_elapsed": [5000.0, 7000.0, 9000.0, 11000.0],
        "block_duration": [100.0, 2000.0, 2000.0, 2000.0],
        "rt": [0.0, 450.0, 520.0, -1.0],
        "key_press": [-1, 37, 39, -1],
        "correct_response": [-1, 37, 39, 37],
        "stim_duration": [0, 1500, 1500, 1500],
        "exp_id": ["stop_signal_single_task_network__fmri"] * 4,
        "stop_signal_condition": ["", "go", "go", "stop"],
    })


class TestCalTimeElapsed:
    def test_subtracts_trigger_time(self):
        from neuro_workflow.events.utils import cal_time_elapsed
        df = _make_basic_df()
        result = cal_time_elapsed(df)
        # trigger row: time_elapsed=5000, so subtract 5000, then subtract block_duration
        # row 0: 5000 - 5000 - 100 = -100
        # row 1: 7000 - 5000 - 2000 = 0
        # row 2: 9000 - 5000 - 2000 = 2000
        # row 3: 11000 - 5000 - 2000 = 4000
        assert result["time_elapsed"].iloc[1] == 0.0
        assert result["time_elapsed"].iloc[2] == 2000.0

    def test_no_trigger_raises(self):
        from neuro_workflow.events.utils import cal_time_elapsed
        df = _make_basic_df()
        df["trial_id"] = ["test_trial"] * 4
        with pytest.raises(IndexError):
            cal_time_elapsed(df)


class TestGetNegRtCorrection:
    def test_no_negative_rt_passthrough(self):
        from neuro_workflow.events.utils import get_neg_rt_correction
        df = _make_basic_df()
        result = get_neg_rt_correction(df)
        assert list(result["time_elapsed"]) == list(df["time_elapsed"])

    def test_negative_rt_corrected(self):
        from neuro_workflow.events.utils import get_neg_rt_correction
        df = _make_basic_df()
        # Introduce a negative RT to trigger correction
        df.loc[2, "rt"] = -500.0
        result = get_neg_rt_correction(df)
        # After correction, time_elapsed for rows 2+ should be recalculated
        assert result["time_elapsed"].iloc[2] == result["time_elapsed"].iloc[1] + df["block_duration"].iloc[2]


class TestAddChoiceAcc:
    def test_correct_responses(self):
        from neuro_workflow.events.utils import add_choice_acc
        df = _make_basic_df()
        result = add_choice_acc(df)
        assert result["choice_acc"].iloc[1] == 1  # 37 == 37
        assert result["choice_acc"].iloc[2] == 1  # 39 == 39
        assert result["choice_acc"].iloc[3] == 0  # -1 != 37


class TestAddCols:
    def test_stop_signal_columns(self):
        from neuro_workflow.events.utils import add_cols
        df = _make_basic_df()
        df["choice_acc"] = [0, 1, 1, 0]
        df["SS_delay"] = [0, 0, 0, 250]
        df["SS_duration"] = [0, 0, 0, 500]
        df["stop_acc"] = [0, 0, 0, 1]
        df["go_acc"] = [0, 1, 1, 0]
        df["stim"] = ["", "arrow_left", "arrow_right", "arrow_left"]
        result = add_cols(df, "stop_signal_single_task_network__fmri")
        assert "trial_type" in result.columns
        assert "SS_delay" in result.columns


class TestResponseTimeAndJunk:
    def test_stop_signal_trial_types(self):
        from neuro_workflow.events.utils import response_time_and_junk
        df = pd.DataFrame({
            "trial_id": ["test_trial", "test_trial", "test_trial"],
            "trial_type": ["go", "stop", "stop"],
            "choice_acc": [1, 1, 0],
            "stop_acc": [0, 1, 0],
        })
        result = response_time_and_junk(df, "stopSignal")
        assert result["trial_type"].iloc[0] == "go"
        assert result["trial_type"].iloc[1] == "stop_success"
        assert result["trial_type"].iloc[2] == "stop_failure"
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_workflow.events'`

**Step 3: Write the utils module**

Port `cal_time_elapsed`, `get_neg_rt_correction`, `add_choice_acc`, `get_cols_list`, `get_trial_type`, `add_cols`, and `response_time_and_junk` from `discovery_wm/events/utils.py` into `src/neuro_workflow/events/utils.py`.

Also port the task-specific cleanup functions (`stopSignal`, `goNogo`, `stopSignalWDirectedForgetting`, `stopSignalWFlanker`) from the same file.

Key changes from the original:
- Replace `globals()[task](df)` dispatch with an explicit dict mapping
- Keep the same logic for all functions

```python
# src/neuro_workflow/events/__init__.py
# (empty)
```

```python
# src/neuro_workflow/events/utils.py
"""Event processing utilities — ported from discovery_wm/events/utils.py."""
import numpy as np
import pandas as pd


def cal_time_elapsed(df: pd.DataFrame) -> pd.DataFrame:
    """Adjust time_elapsed relative to fMRI trigger."""
    start_point = df.loc[df["trial_id"] == "fmri_trigger_initial"]
    start = start_point["time_elapsed"].values[0]
    df["time_elapsed"] = df["time_elapsed"] - start
    df["time_elapsed"] = df["time_elapsed"] - df["block_duration"]
    return df


def get_neg_rt_correction(df: pd.DataFrame) -> pd.DataFrame:
    """Fix RT estimation errors from cumulative timing drift."""
    df.dropna(subset=["block_duration"], inplace=True)
    negative_rt = df.loc[df["rt"] < -1]
    if not negative_rt.empty:
        i = df.loc[df.rt < -1].index.values.astype(int)[0]
        trial_before = df.loc[i - 1]["time_elapsed"]
        problematic = df.loc[i:]
        block_durations = problematic["block_duration"].to_list()
        new_time_elapsed = []
        for n in range(len(block_durations)):
            if block_durations[n] != np.nan:
                new_time_elapsed.append(trial_before + block_durations[n])
                trial_before = trial_before + block_durations[n]
            else:
                new_time_elapsed.append(np.nan)
        new_time = df.loc[: i - 1].time_elapsed.to_list() + new_time_elapsed
        df["time_elapsed"] = new_time
    return df


def add_choice_acc(df: pd.DataFrame) -> pd.DataFrame:
    """Compute binary accuracy column from key_press vs correct_response."""
    df["choice_acc"] = np.where(df["key_press"] == df["correct_response"], 1, 0)
    return df


# --- Column selection and trial_type construction ---
# (Ported directly from discovery_wm/events/utils.py get_cols_list / get_trial_type / add_cols)

_COMMON_COLS = ["trial_id", "time_elapsed", "rt", "stim_duration", "choice_acc", "key_press", "correct_response"]

_COLS_LOOKUP = {
    "stop_signal_single_task_network__fmri": _COMMON_COLS + ["SS_delay", "SS_duration", "stop_signal_condition", "stop_acc", "go_acc", "stim"],
    "shape_matching_single_task_network__fmri": _COMMON_COLS + ["shape_matching_condition", "probe_id", "target_id", "distractor_id"],
    "n_back_single_task_network__fmri": _COMMON_COLS + ["n_back_condition", "delay", "probe", "letter_case"],
    "go_nogo_single_task_network__fmri": _COMMON_COLS + ["go_nogo_condition"],
    "spatial_task_switching_single_task_network__fmri": _COMMON_COLS + ["task_switch", "whichQuadrant", "predictable_dimension", "number"],
    "cued_task_switching_single_task_network__fmri": _COMMON_COLS + ["cue", "task", "task_condition", "cue_condition", "stim_number"],
    "directed_forgetting_single_task_network__fmri": _COMMON_COLS + ["directed_forgetting_condition", "cue", "top_stim", "bottom_stim"],
    "flanker_single_task_network__fmri": _COMMON_COLS + ["flanker_condition", "center_letter"],
    "directed_forgetting_with_flanker__fmri": _COMMON_COLS + ["flanker_condition", "directed_forgetting_condition"],
    "stop_signal_with_directed_forgetting__fmri": _COMMON_COLS + ["SS_delay", "SS_duration", "stop_signal_condition", "directed_forgetting_condition", "stop_acc"],
    "stop_signal_with_flanker__fmri": _COMMON_COLS + ["SS_delay", "SS_duration", "stop_signal_condition", "flanker_condition", "SSD_congruent", "SSD_incongruent", "stop_acc"],
    "cued_task_switching_with_directed_forgetting__fmri": _COMMON_COLS + ["task_condition", "cue_condition", "task_cue", "directed_forgetting_condition"],
    "spatial_task_switching_with_cued_task_switching__fmri": _COMMON_COLS + ["task_switch", "whichQuadrant", "left_number", "right_number", "curr_cue"],
    "flanker_with_shape_matching__fmri": _COMMON_COLS + ["flanker_condition", "shape_matching_condition", "flankers", "probe", "target", "distractor"],
    "flanker_with_cued_task_switching__fmri": _COMMON_COLS + ["flanker_condition", "cue", "task_condition", "cue_condition", "flanking_number"],
    "flanker_with_cued_task_switching": _COMMON_COLS + ["flanker_condition", "cue", "task_condition", "cue_condition", "flanking_number"],
    "n_back_with_shape_matching__fmri": _COMMON_COLS + ["n_back_condition", "shape_matching_condition", "probe", "distractor", "delay"],
    "shape_matching_with_spatial_task_switching__fmri": _COMMON_COLS + ["shape_matching_condition", "task_switch", "probe", "target", "distractor", "whichQuadrant"],
    "shape_matching_with_cued_task_switching__fmri": _COMMON_COLS + ["cue", "task_condition", "cue_condition", "shape_matching_condition", "probe", "target", "distractor"],
    "shape_matching_with_cued_task_switching": _COMMON_COLS + ["cue", "task_condition", "cue_condition", "shape_matching_condition", "probe", "target", "distractor"],
    "n_back_with_spatial_task_switching__fmri": _COMMON_COLS + ["n_back_condition", "task", "probe", "whichQuadrant"],
}

_TRIAL_TYPE_LOOKUP = {
    "stop_signal_single_task_network__fmri": ["stop_signal_condition"],
    "shape_matching_single_task_network__fmri": ["shape_matching_condition"],
    "n_back_single_task_network__fmri": ["n_back_condition"],
    "go_nogo_single_task_network__fmri": ["go_nogo_condition"],
    "spatial_task_switching_single_task_network__fmri": ["task_switch"],
    "cued_task_switching_single_task_network__fmri": ["task_condition", "cue_condition"],
    "directed_forgetting_single_task_network__fmri": ["directed_forgetting_condition"],
    "flanker_single_task_network__fmri": ["flanker_condition"],
    "directed_forgetting_with_flanker__fmri": ["flanker_condition", "directed_forgetting_condition"],
    "stop_signal_with_directed_forgetting__fmri": ["stop_signal_condition", "directed_forgetting_condition"],
    "stop_signal_with_flanker__fmri": ["stop_signal_condition", "flanker_condition"],
    "cued_task_switching_with_directed_forgetting__fmri": ["directed_forgetting_condition", "task_condition", "cue_condition"],
    "spatial_task_switching_with_cued_task_switching__fmri": ["task_switch"],
    "flanker_with_shape_matching__fmri": ["flanker_condition", "shape_matching_condition"],
    "flanker_with_cued_task_switching__fmri": ["cue_condition", "task_condition", "flanker_condition"],
    "flanker_with_cued_task_switching": ["cue_condition", "task_condition", "flanker_condition"],
    "n_back_with_shape_matching__fmri": ["n_back_condition", "shape_matching_condition", "delay"],
    "shape_matching_with_spatial_task_switching__fmri": ["predictable_condition", "shape_matching_condition"],
    "shape_matching_with_spatial_task_switching": ["predictable_condition", "shape_matching_condition"],
    "shape_matching_with_cued_task_switching__fmri": ["task_condition", "cue_condition", "shape_matching_condition"],
    "n_back_with_spatial_task_switching__fmri": ["n_back_condition", "task_switch_condition"],
}


def add_cols(df: pd.DataFrame, exp_id: str) -> pd.DataFrame:
    """Select task-specific columns and construct trial_type."""
    if "cued_task_switching" in exp_id:
        df["task_condition"] = df["task_condition"].replace("na", "n/a")
        df["cue_condition"] = df["cue_condition"].replace("na", "n/a")
    if exp_id == "spatial_task_switching_with_cued_task_switching__fmri":
        df["task_switch"] = df["task_switch"].replace("na", "n/a")

    to_add = _COLS_LOOKUP.get(exp_id)
    if to_add is None:
        raise ValueError(f"Unknown exp_id: {exp_id}")
    final = df[to_add]
    trial_types = _TRIAL_TYPE_LOOKUP.get(exp_id)

    df2 = pd.DataFrame()
    if len(trial_types) > 1:
        if exp_id == "cued_task_switching_single_task_network__fmri":
            df2["trial_type"] = "t" + df[trial_types[0]] + "_c" + df[trial_types[1]]
        elif exp_id == "cued_task_switching_with_directed_forgetting__fmri":
            df2["trial_type"] = df[trial_types[0]] + "_t" + df[trial_types[1]] + "_c" + df[trial_types[2]]
        elif exp_id == "shape_matching_with_cued_task_switching__fmri":
            df2["trial_type"] = "t" + df[trial_types[0]] + "_c" + df[trial_types[1]]
        elif exp_id == "flanker_with_cued_task_switching__fmri":
            df2["trial_type"] = "c" + df[trial_types[0]] + "_t" + df[trial_types[1]] + "_" + df[trial_types[2]]
        elif exp_id == "n_back_with_shape_matching__fmri":
            df2["trial_type"] = df[trial_types[0]] + "_" + df[trial_types[1]] + "_" + df[trial_types[2]].astype(str) + "back"
            df2["trial_type"] = df2["trial_type"].str.replace(".0back", "back")
        else:
            df2["trial_type"] = df[trial_types[0]] + "_" + df[trial_types[1]]
    if exp_id == "flanker_with_cued_task_switching__fmri":
        df2["trial_type"] = df2["trial_type"].shift(1)
    if len(trial_types) == 1:
        df2["trial_type"] = df[trial_types[0]]
    if exp_id == "shape_matching_with_spatial_task_switching__fmri":
        df2["trial_type"] = df2["trial_type"].str.split("_").str[2:].str.join("_")
    if exp_id == "spatial_task_switching_single_task_network__fmri":
        final = final.rename(columns={"predictable_dimension": "task_set"})
    if exp_id == "cued_task_switching_with_directed_forgetting__fmri":
        final.loc[final["key_press"] == 84.0, ["rt"]] = pd.NA
        final.loc[final["key_press"] == 84.0, ["key_press"]] = -1

    final = final.assign(trial_type=df2)
    return final


# --- Task-specific cleanup (trial_type relabeling) ---

def _cleanup_stop_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    mask = df["trial_id"] == "test_trial"
    trial_rows = df[mask]
    choice_acc_str = trial_rows["choice_acc"].astype(str)
    conditions = [
        (trial_rows["trial_type"] == "go"),
        (trial_rows["trial_type"] == "stop") & (choice_acc_str == "1"),
        (trial_rows["trial_type"] == "stop") & (choice_acc_str == "0"),
    ]
    values = ["go", "stop_success", "stop_failure"]
    result = np.select(conditions, values, default="unknown")
    df.loc[mask, "trial_type"] = result
    fixation_mask = df["trial_id"] == "test_fixation"
    df.loc[fixation_mask, "trial_type"] = "fixation"
    return df


def _cleanup_go_nogo(df: pd.DataFrame) -> pd.DataFrame:
    choice_acc_str = df["choice_acc"].astype(str)
    conditions = [
        (df["trial_type"] == "nogo") & (choice_acc_str == "1"),
        (df["trial_type"] == "nogo") & (choice_acc_str == "0"),
        (df["trial_type"] == "go"),
    ]
    values = ["nogo_success", "nogo_failure", "go"]
    result = np.select(conditions, values, default="unknown")
    df["trial_type"] = pd.Series(result).astype(object)
    return df


def _cleanup_stop_signal_w_directed_forgetting(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["trial_id"] == "test_trial"
    trial_rows = df[mask]
    conditions = [
        (trial_rows["stop_signal_condition"] == "go") & (trial_rows["directed_forgetting_condition"] == "con"),
        (trial_rows["stop_signal_condition"] == "go") & (trial_rows["directed_forgetting_condition"] == "pos"),
        (trial_rows["stop_signal_condition"] == "go") & (trial_rows["directed_forgetting_condition"] == "neg"),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["directed_forgetting_condition"] == "con") & (trial_rows["stop_acc"] == 1),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["directed_forgetting_condition"] == "pos") & (trial_rows["stop_acc"] == 1),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["directed_forgetting_condition"] == "neg") & (trial_rows["stop_acc"] == 1),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["directed_forgetting_condition"] == "con") & (trial_rows["stop_acc"] == 0),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["directed_forgetting_condition"] == "pos") & (trial_rows["stop_acc"] == 0),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["directed_forgetting_condition"] == "neg") & (trial_rows["stop_acc"] == 0),
        (trial_rows["trial_type"] == "memory_cue"),
    ]
    values = ["go_con", "go_pos", "go_neg", "stop_success_con", "stop_success_pos", "stop_success_neg", "stop_failure_con", "stop_failure_pos", "stop_failure_neg", "memory_cue"]
    result = np.select(conditions, values, default="unknown")
    df.loc[mask, "trial_type"] = result
    fixation_mask = df["trial_id"] == "test_fixation"
    df.loc[fixation_mask, "trial_type"] = "fixation"
    return df


def _cleanup_stop_signal_w_flanker(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["trial_id"] == "test_trial"
    trial_rows = df[mask]
    conditions = [
        (trial_rows["stop_signal_condition"] == "go") & (trial_rows["flanker_condition"] == "congruent"),
        (trial_rows["stop_signal_condition"] == "go") & (trial_rows["flanker_condition"] == "incongruent"),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["flanker_condition"] == "congruent") & (trial_rows["stop_acc"] == 1),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["flanker_condition"] == "incongruent") & (trial_rows["stop_acc"] == 1),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["flanker_condition"] == "congruent") & (trial_rows["stop_acc"] == 0),
        (trial_rows["stop_signal_condition"] == "stop") & (trial_rows["flanker_condition"] == "incongruent") & (trial_rows["stop_acc"] == 0),
    ]
    values = ["go_congruent", "go_incongruent", "stop_success_congruent", "stop_success_incongruent", "stop_failure_congruent", "stop_failure_incongruent"]
    result = np.select(conditions, values, default="unknown")
    df.loc[mask, "trial_type"] = result
    fixation_mask = df["trial_id"] == "test_fixation"
    df.loc[fixation_mask, "trial_type"] = "fixation"
    return df


_CLEANUP_DISPATCH = {
    "stopSignal": _cleanup_stop_signal,
    "goNogo": _cleanup_go_nogo,
    "stopSignalWDirectedForgetting": _cleanup_stop_signal_w_directed_forgetting,
    "stopSignalWFlanker": _cleanup_stop_signal_w_flanker,
}


def response_time_and_junk(df: pd.DataFrame, task: str) -> pd.DataFrame:
    """Apply task-specific cleanup and replace empty strings with NaN."""
    cleanup_fn = _CLEANUP_DISPATCH.get(task)
    if cleanup_fn is not None:
        df = cleanup_fn(df)
    df.replace("", np.nan, inplace=True)
    return df
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_utils.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/events/__init__.py src/neuro_workflow/events/utils.py tests/events/test_utils.py
git commit -m "feat(events): add event processing utilities ported from discovery_wm"
```

---

## Task 3: Event Creation Module — create_events_df and CLI Command

**Files:**
- Create: `src/neuro_workflow/events/create.py`
- Test: `tests/events/test_create.py`

**Step 1: Write the failing tests**

```python
# tests/events/test_create.py
import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_stop_signal_csv(tmp_path):
    """Create a minimal stop signal behavioral CSV."""
    df = pd.DataFrame({
        "trial_id": ["design_setup", "fmri_trigger_initial", "test_fixation", "test_trial", "test_trial", "test_trial"],
        "time_elapsed": [1000, 5000, 5500, 7000, 9000, 11000],
        "block_duration": [1000, 100, 500, 1500, 1500, 1500],
        "rt": [0, 0, 0, 450, 520, -1],
        "key_press": [-1, -1, -1, 37, 39, -1],
        "correct_response": [-1, -1, -1, 37, 39, 37],
        "stim_duration": [0, 0, 0, 1500, 1500, 1500],
        "exp_id": ["stop_signal_single_task_network__fmri"] * 6,
        "stop_signal_condition": ["", "", "", "go", "go", "stop"],
        "SS_delay": [0, 0, 0, 0, 0, 250],
        "SS_duration": [0, 0, 0, 0, 0, 500],
        "stop_acc": [0, 0, 0, 0, 0, 1],
        "go_acc": [0, 0, 0, 1, 1, 0],
        "stim": ["", "", "", "left", "right", "left"],
        "stimulus": ["", "", "", "", "", ""],
        "text": ["", "", "", "", "", ""],
    })
    csv_path = tmp_path / "stop_signal_single_task_network__fmri_results.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


class TestCreateEventsDf:
    def test_produces_bids_columns(self, tmp_path):
        from neuro_workflow.events.create import create_events_df
        csv_path = _make_stop_signal_csv(tmp_path)
        result = create_events_df(csv_path, "stopSignal")
        assert "onset" in result.columns
        assert "duration" in result.columns
        assert "response_time" in result.columns
        assert "trial_type" in result.columns

    def test_onset_in_seconds(self, tmp_path):
        from neuro_workflow.events.create import create_events_df
        csv_path = _make_stop_signal_csv(tmp_path)
        result = create_events_df(csv_path, "stopSignal")
        # All onsets should be > 0 (trigger time subtracted, negative filtered)
        assert (result["onset"] > 0).all() or len(result) == 0

    def test_na_for_missing_values(self, tmp_path):
        from neuro_workflow.events.create import create_events_df
        csv_path = _make_stop_signal_csv(tmp_path)
        result = create_events_df(csv_path, "stopSignal")
        # NaN values should be filled with 'n/a'
        assert not result.isnull().any().any()


class TestGetTaskFromFilename:
    def test_descriptive_single(self):
        from neuro_workflow.events.create import get_task_from_filename
        assert get_task_from_filename("stop_signal_single_task_network__fmri_results.csv") == "stop_signal"

    def test_descriptive_dual(self):
        from neuro_workflow.events.create import get_task_from_filename
        assert get_task_from_filename("stop_signal_with_flanker__fmri_results.csv") == "stop_signal_with_flanker"


class TestLongNameToShortName:
    def test_single_task(self):
        from neuro_workflow.events.create import long_name_to_short_name
        assert long_name_to_short_name("stop_signal") == "stopSignal"

    def test_dual_task(self):
        from neuro_workflow.events.create import long_name_to_short_name
        assert long_name_to_short_name("stop_signal_with_flanker") == "stopSignalWFlanker"
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_create.py -v`
Expected: FAIL — `ImportError`

**Step 3: Write the create module**

Port from `discovery_wm/events/create_events.py`. Key differences:
- `create_events_df()` is a pure function taking a CSV path and task short name
- `run_create_events()` is the CLI entry point that walks sourcedata and matches to BIDS NIfTIs
- `long_name_to_short_name` and `get_task_from_filename` are ported directly
- `set_default_event_cols` and `rename_cells` and `get_rows_with_feedback` are ported directly
- Feedback block detection writes to log instead of a file

```python
# src/neuro_workflow/events/create.py
"""Generate BIDS _events.tsv files from behavioral CSVs."""
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from neuro_workflow.events.utils import (
    get_neg_rt_correction,
    cal_time_elapsed,
    add_choice_acc,
    add_cols,
    response_time_and_junk,
)

log = logging.getLogger(__name__)

# --- Name mapping (same as rename script, also used by create_events) ---

LONG_NAME_TO_SHORT = {
    "stop_signal": "stopSignal",
    "flanker": "flanker",
    "go_nogo": "goNogo",
    "n_back": "nBack",
    "cued_task_switching": "cuedTS",
    "spatial_task_switching": "spatialTS",
    "directed_forgetting": "directedForgetting",
    "shape_matching": "shapeMatching",
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


def long_name_to_short_name(long_name: str) -> str:
    return LONG_NAME_TO_SHORT[long_name]


def get_task_from_filename(filename: str) -> str:
    """Extract long task name from behavioral CSV filename."""
    long_name = filename.split("__fmri")[0]
    if "_single_task_network" in long_name:
        long_name = long_name.split("_single_task_network")[0]
    elif "task-" in long_name:
        parts = long_name.split("_")
        for p in parts:
            if p.startswith("task-"):
                long_name = p.replace("task-", "").replace("-", "_")
                break
    return long_name


# --- Rename cells (trial_id label standardization) ---

_RENAME_CELLS_LOOKUP = {
    "stop_signal_single_task_network__fmri": {"fixation": "test_fixation", "practice-no-stop-feedback": "break"},
    "shape_matching_single_task_network__fmri": {"fixation": "test_fixation", "mask": "test_mask", "practice-no-stop-feedback": "break"},
    "n_back_single_task_network__fmri": {"practice-no-stop-feedback": "break", "fixation": "test_fixation"},
    "go_nogo_single_task_network__fmri": {"update_correct_response": "test_fixation", "feedback_block": "break"},
    "spatial_task_switching_single_task_network__fmri": {"feedback_block": "break", "practice_cue": "blank_screen"},
    "cued_task_switching_single_task_network__fmri": {"practice-stop-feedback": "break"},
    "directed_forgetting_single_task_network__fmri": {"fixation": "test_fixation", "stim": "test_stim", "cue": "test_cue", "test_feedback": "break"},
    "flanker_single_task_network__fmri": {"practice-no-stop-feedback": "break"},
    "directed_forgetting_with_flanker__fmri": {"test_start_fixation": "test_fixation", "test_feedback": "break"},
    "stop_signal_with_directed_forgetting__fmri": {"ITI_fixation": "test_fixation", "stim": "test_stim", "cue": "test_cue", "fixation": "test_fixation", "feedback_block": "break"},
    "stop_signal_with_flanker__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
    "cued_task_switching_with_directed_forgetting__fmri": {"test_start_fixation": "test_fixation", "test_feedback": "break"},
    "spatial_task_switching_with_cued_task_switching__fmri": {"test_cue_block": "test_cue", "fixation": "test_fixation", "feedback_block": "break"},
    "flanker_with_shape_matching__fmri": {"feedback_block": "break"},
    "flanker_with_cued_task_switching__fmri": {"practice-stop-feedback": "break"},
    "flanker_with_cued_task_switching": {"practice-stop-feedback": "break"},
    "n_back_with_shape_matching__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
    "shape_matching_with_spatial_task_switching__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
    "shape_matching_with_cued_task_switching__fmri": {"fixation": "test_fixation", "cue": "test_cue", "feedback_block": "break"},
    "shape_matching_with_cued_task_switching": {"fixation": "test_fixation", "cue": "test_cue", "feedback_block": "break"},
    "n_back_with_spatial_task_switching__fmri": {"feedback_block": "break", "fixation": "test_fixation"},
}


def _rename_cells(df: pd.DataFrame, exp_id: str) -> pd.DataFrame:
    change = _RENAME_CELLS_LOOKUP.get(exp_id)
    if change is None:
        log.warning("No rename_cells mapping for exp_id: %s", exp_id)
        return df
    for key, value in change.items():
        df["trial_id"] = df["trial_id"].replace(key, value)
    if "cued_task_switching_" in exp_id:
        df.loc[df["trial_id"] == "test_cue", "correct_response"] = "n/a"
    return df


def _set_default_event_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df.time_elapsed > 0]
    df = df.rename(columns={"time_elapsed": "onset", "choice_acc": "acc", "stim_duration": "duration", "rt": "response_time"})
    df["onset"] = df["onset"] / 1000
    df["duration"] = df["duration"] / 1000
    df["response_time"] = df["response_time"] / 1000
    df["response_time"] = df["response_time"].replace(-0.001, np.nan)
    first_columns = ["onset", "duration", "response_time", "trial_id", "trial_type", "key_press", "correct_response"]
    new_column_order = first_columns + [col for col in df.columns if col not in first_columns]
    df = df[new_column_order]
    return df


def _flagged_feedback(text_content: str) -> bool:
    keywords = ["accuracy", "slowly", "respond", "response"]
    return any(keyword in text_content.lower() for keyword in keywords)


def _get_rows_with_feedback(df: pd.DataFrame, original_df: pd.DataFrame):
    feedback_block_rows = original_df[original_df["trial_id"] == "test_feedback"]
    if len(feedback_block_rows) == 0:
        feedback_block_rows = original_df[original_df["trial_id"] == "feedback_block"]
    if len(feedback_block_rows) == 0:
        feedback_block_rows = original_df[original_df["stimulus"].str.contains("completed", na=False)]
    indices_to_change = []
    for index, row in feedback_block_rows.iterrows():
        stimulus = row["stimulus"]
        if _flagged_feedback(stimulus):
            indices_to_change.append(index)
    return feedback_block_rows, indices_to_change


def create_events_df(filename: Path, short_name: str) -> pd.DataFrame:
    """Create a BIDS events dataframe from a behavioral CSV."""
    original_df = pd.read_csv(filename)
    exp_id = original_df["exp_id"][0]
    log.info("Processing %s for %s", filename, exp_id)
    df = original_df.copy()
    df = get_neg_rt_correction(df)
    df = cal_time_elapsed(df)
    df = add_choice_acc(df)
    df = add_cols(df, exp_id)
    df = response_time_and_junk(df, short_name)
    df = _set_default_event_cols(df)
    df = _rename_cells(df, exp_id)

    df.fillna("n/a", inplace=True)

    # Fix spatialTS "na" trial_type
    if "spatial_task_switching" in exp_id:
        df.loc[(df["trial_id"] == "test_trial") & (df["trial_type"] == "na"), "trial_type"] = "tn/a_cn/a"
        df.loc[(df["trial_id"] == "test_trial") & (df["trial_type"] == "tn/a_cn/a"), "task_switch"] = "tn/a_cn/a"

    # Detect performance feedback blocks
    feedback_block_rows, indices_to_change = _get_rows_with_feedback(df, original_df)
    for index in indices_to_change:
        df.loc[index, "trial_id"] = "break_with_performance_feedback"

    return df


def run_create_events(
    behavioral_dir: Path,
    bids_dir: Path,
    subjects: list[str] | None = None,
    sessions: list[str] | None = None,
) -> None:
    """Walk sourcedata behavioral CSVs and write BIDS event files.

    Args:
        behavioral_dir: Path to sourcedata/ with sub-*/ses-*/beh/*.csv
        bids_dir: Path to BIDS dataset root (events written to func/ dirs)
        subjects: Optional list of subjects to process (default: all)
        sessions: Optional list of sessions to process (default: all)
    """
    for sub_dir in sorted(behavioral_dir.glob("sub-*")):
        if subjects and sub_dir.name not in subjects:
            continue
        for ses_dir in sorted(sub_dir.glob("ses-*")):
            if sessions and ses_dir.name not in sessions:
                continue
            beh_dir = ses_dir / "beh"
            if not beh_dir.exists():
                continue
            func_dir = bids_dir / sub_dir.name / ses_dir.name / "func"
            if not func_dir.exists():
                log.warning("No func dir for %s %s, skipping", sub_dir.name, ses_dir.name)
                continue

            # Get tasks that have NIfTIs
            nifti_tasks = set()
            for nii in func_dir.glob("*.nii.gz"):
                m = re.search(r"task-(\w+)", nii.name)
                if m and m.group(1) != "rest":
                    nifti_tasks.add(m.group(1))

            # Group CSVs by task
            csv_files = sorted(beh_dir.glob("*.csv"))
            task_to_files: dict[str, list[Path]] = {}
            for csv_file in csv_files:
                # Extract task from BIDS-style sourcedata filename
                m = re.search(r"task-(\w+)", csv_file.name)
                if m:
                    task_name = m.group(1)
                    if task_name in nifti_tasks:
                        task_to_files.setdefault(task_name, []).append(csv_file)

            for task_name, files in task_to_files.items():
                for run_idx, csv_file in enumerate(files, 1):
                    df = create_events_df(csv_file, task_name)
                    outname = f"{sub_dir.name}_{ses_dir.name}_task-{task_name}_run-{run_idx}_events.tsv"
                    outpath = func_dir / outname
                    log.info("Writing %s", outpath)
                    df.to_csv(outpath, sep="\t", index=False)
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_create.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/events/create.py tests/events/test_create.py
git commit -m "feat(events): add event file creation module ported from discovery_wm"
```

---

## Task 4: QC Globals — Thresholds and Task Definitions

**Files:**
- Create: `src/neuro_workflow/events/qc_globals.py`
- Test: `tests/events/test_qc_globals.py`

**Step 1: Write the failing test**

```python
# tests/events/test_qc_globals.py
def test_thresholds_exist():
    from neuro_workflow.events.qc_globals import (
        STOP_SUCCESS_ACC_LOW_THRESHOLD,
        STOP_SUCCESS_ACC_HIGH_THRESHOLD,
        GO_RT_THRESHOLD_FMRI,
        GONOGO_GO_ACC_THRESHOLD_1,
        GONOGO_NOGO_ACC_THRESHOLD_1,
        ACC_THRESHOLD,
        OMISSION_RATE_THRESHOLD,
        LAST_N_TEST_TRIALS,
    )
    assert STOP_SUCCESS_ACC_LOW_THRESHOLD == 0.25
    assert STOP_SUCCESS_ACC_HIGH_THRESHOLD == 0.75
    assert GO_RT_THRESHOLD_FMRI == 1000
    assert ACC_THRESHOLD == 0.55
    assert OMISSION_RATE_THRESHOLD == 0.25
    assert LAST_N_TEST_TRIALS == 10

def test_nback_thresholds():
    from neuro_workflow.events.qc_globals import (
        NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1,
        NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1,
        NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_1,
        NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1,
    )
    assert NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1 == 0.2
    assert NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 == 0.75
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_qc_globals.py -v`
Expected: FAIL

**Step 3: Write the module**

Port `network-behavior-qc/globals.py` directly. Keep only the fMRI-relevant thresholds.

```python
# src/neuro_workflow/events/qc_globals.py
"""QC thresholds and task definitions — ported from network-behavior-qc/globals.py."""

# Stop signal task
STOP_SUCCESS_ACC_LOW_THRESHOLD = 0.25
STOP_SUCCESS_ACC_HIGH_THRESHOLD = 0.75
GO_RT_THRESHOLD_FMRI = 1000
GO_RT_THRESHOLD_FMRI_DUAL_TASK = 1050

# Go/nogo fMRI exclusion thresholds (both conditions must be met)
GONOGO_GO_ACC_THRESHOLD_1 = 0.75
GONOGO_NOGO_ACC_THRESHOLD_1 = 0.2
GONOGO_GO_ACC_THRESHOLD_2 = 0.5
GONOGO_NOGO_ACC_THRESHOLD_2 = 0.5

# N-back fMRI exclusion thresholds (both conditions must be met)
NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1 = 0.2
NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 = 0.75
NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_2 = 0.5
NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2 = 0.5
NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_1 = 0.2
NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 = 0.75
NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_2 = 0.5
NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2 = 0.5

# All other tasks
ACC_THRESHOLD = 0.55
OMISSION_RATE_THRESHOLD = 0.25

# Trimming detection
LAST_N_TEST_TRIALS = 10
SUMMARY_ROWS = 4
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_qc_globals.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/events/qc_globals.py tests/events/test_qc_globals.py
git commit -m "feat(events): add QC threshold constants ported from network-behavior-qc"
```

---

## Task 5: QC Module — Behavioral Metrics and Trimming Detection

**Files:**
- Create: `src/neuro_workflow/events/qc.py`
- Test: `tests/events/test_qc.py`

**Step 1: Write the failing tests**

```python
# tests/events/test_qc.py
import pandas as pd
import numpy as np
import pytest
from pathlib import Path


def _make_stop_signal_events():
    """Minimal stop signal events TSV as DataFrame."""
    return pd.DataFrame({
        "trial_id": ["test_trial"] * 10,
        "trial_type": ["go"] * 5 + ["stop_success"] * 3 + ["stop_failure"] * 2,
        "onset": [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 15.0, 17.0, 19.0],
        "response_time": [0.4, 0.5, 0.45, 0.42, 0.48, "n/a", "n/a", "n/a", 0.6, 0.55],
        "acc": [1, 1, 1, 0, 1, 1, 1, 1, 0, 0],
    })


class TestRtTailCutoff:
    def test_no_cutoff_when_all_respond(self):
        from neuro_workflow.events.qc import detect_rt_tail_cutoff
        df = pd.DataFrame({
            "trial_id": ["test_trial"] * 5,
            "rt": [400, 500, 450, 420, 480],
        })
        result = detect_rt_tail_cutoff(df)
        assert result is None

    def test_detects_tail_cutoff(self):
        from neuro_workflow.events.qc import detect_rt_tail_cutoff
        # 5 good responses, then 10 non-responses
        rts = [400, 500, 450, 420, 480] + [-1] * 10
        df = pd.DataFrame({
            "trial_id": ["test_trial"] * 15,
            "rt": rts,
            "time_elapsed": list(range(1000, 16000, 1000)),
        })
        result = detect_rt_tail_cutoff(df)
        assert result is not None
        assert "cutoff_index" in result
        assert "cutoff_before_halfway" in result

    def test_cutoff_before_halfway_flags_exclude(self):
        from neuro_workflow.events.qc import detect_rt_tail_cutoff
        # 2 good, 10 bad -> cutoff is before halfway
        rts = [400, 500] + [-1] * 10
        df = pd.DataFrame({
            "trial_id": ["test_trial"] * 12,
            "rt": rts,
            "time_elapsed": list(range(1000, 13000, 1000)),
        })
        result = detect_rt_tail_cutoff(df)
        assert result is not None
        assert result["cutoff_before_halfway"] is True


class TestCheckStopSignalExclusion:
    def test_valid_stop_signal_not_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion
        # 50% stop success, go_rt < 1000ms -> valid
        metrics = {
            "stop_success_rate": 0.5,
            "go_rt": 800.0,
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is None

    def test_low_stop_success_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion
        metrics = {
            "stop_success_rate": 0.1,  # Below 0.25 threshold
            "go_rt": 800.0,
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is not None
        assert "stop_success" in result["reason"]

    def test_high_stop_success_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion
        metrics = {
            "stop_success_rate": 0.9,  # Above 0.75 threshold
            "go_rt": 800.0,
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is not None

    def test_high_go_rt_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion
        metrics = {
            "stop_success_rate": 0.5,
            "go_rt": 1100.0,  # Above 1000ms threshold
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is not None
        assert "go_rt" in result["reason"]


class TestCheckGoNogoExclusion:
    def test_valid_gonogo_not_excluded(self):
        from neuro_workflow.events.qc import check_go_nogo_exclusion
        metrics = {"go_acc": 0.9, "nogo_acc": 0.6}
        assert check_go_nogo_exclusion(metrics) is None

    def test_both_rules_triggered(self):
        from neuro_workflow.events.qc import check_go_nogo_exclusion
        # rule1: go <= 0.75 or nogo <= 0.2 -> nogo=0.1 triggers
        # rule2: go <= 0.5 or nogo <= 0.5  -> nogo=0.1 triggers
        metrics = {"go_acc": 0.9, "nogo_acc": 0.1}
        result = check_go_nogo_exclusion(metrics)
        assert result is not None


class TestCheckOtherExclusion:
    def test_valid_not_excluded(self):
        from neuro_workflow.events.qc import check_other_exclusion
        metrics = {"acc": 0.8, "omission_rate": 0.1}
        assert check_other_exclusion(metrics) is None

    def test_low_accuracy_excluded(self):
        from neuro_workflow.events.qc import check_other_exclusion
        metrics = {"acc": 0.4, "omission_rate": 0.1}
        result = check_other_exclusion(metrics)
        assert result is not None
        assert "accuracy" in result["reason"]

    def test_high_omission_excluded(self):
        from neuro_workflow.events.qc import check_other_exclusion
        metrics = {"acc": 0.8, "omission_rate": 0.35}
        result = check_other_exclusion(metrics)
        assert result is not None
        assert "omission" in result["reason"]
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_qc.py -v`
Expected: FAIL

**Step 3: Write the QC module**

This module provides:
- `detect_rt_tail_cutoff()` — ported from `trimmed_behavior_utils.py`
- `compute_metrics()` — computes per-run behavioral metrics from sourcedata CSV
- `check_*_exclusion()` functions — simplified exclusion checks for fMRI data
- `run_qc()` — CLI entry point that walks sourcedata, computes metrics, produces exclusion entries and trim list

```python
# src/neuro_workflow/events/qc.py
"""Behavioral QC: compute metrics, flag exclusions, detect trimming needs."""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from neuro_workflow.events.qc_globals import (
    STOP_SUCCESS_ACC_LOW_THRESHOLD,
    STOP_SUCCESS_ACC_HIGH_THRESHOLD,
    GO_RT_THRESHOLD_FMRI,
    GONOGO_GO_ACC_THRESHOLD_1,
    GONOGO_NOGO_ACC_THRESHOLD_1,
    GONOGO_GO_ACC_THRESHOLD_2,
    GONOGO_NOGO_ACC_THRESHOLD_2,
    NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1,
    NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1,
    NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_2,
    NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2,
    NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_1,
    NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1,
    NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_2,
    NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2,
    ACC_THRESHOLD,
    OMISSION_RATE_THRESHOLD,
    LAST_N_TEST_TRIALS,
)

log = logging.getLogger(__name__)


# --- RT tail cutoff detection ---

def detect_rt_tail_cutoff(df: pd.DataFrame, last_n: int = LAST_N_TEST_TRIALS) -> dict | None:
    """Detect if participant stopped responding at the end of a run.

    Returns dict with cutoff info, or None if no cutoff detected.
    """
    df = df.copy()
    if "trial_id" not in df.columns or "rt" not in df.columns:
        return None

    df["rt"] = pd.to_numeric(df["rt"], errors="coerce").fillna(-1)
    test_trials = df[df["trial_id"] == "test_trial"]

    if len(test_trials) < last_n:
        return None

    # Check if last N test trials are all non-responses
    if not (test_trials["rt"].tail(last_n) == -1).all():
        return None

    # Find last valid response across all rows
    valid_mask = df["rt"] != -1
    if not valid_mask.any():
        return None

    last_valid_idx = valid_mask[valid_mask].index[-1]

    # Verify all rows after last valid are -1
    tail = df.loc[last_valid_idx:].iloc[1:]
    if not (tail["rt"] == -1).all():
        return None

    # Compute cutoff position
    cutoff_iloc = df.index.get_loc(last_valid_idx) + 1
    test_trials_included = test_trials[test_trials.index <= last_valid_idx]
    halfway = len(test_trials) / 2.0
    cutoff_before_halfway = len(test_trials_included) < halfway

    # Get onset time at cutoff for NIfTI trimming
    cutoff_onset = None
    if "time_elapsed" in df.columns:
        cutoff_onset = float(df.iloc[cutoff_iloc - 1]["time_elapsed"])

    proportion_blank = (test_trials["rt"] == -1).sum() / len(test_trials)

    return {
        "cutoff_index": cutoff_iloc,
        "cutoff_before_halfway": cutoff_before_halfway,
        "cutoff_onset_ms": cutoff_onset,
        "proportion_blank": float(proportion_blank),
    }


# --- Per-task exclusion checks ---

def check_stop_signal_exclusion(metrics: dict) -> dict | None:
    """Check stop signal exclusion criteria. Returns reason dict or None."""
    reasons = []
    ss_rate = metrics.get("stop_success_rate")
    if ss_rate is not None:
        if ss_rate < STOP_SUCCESS_ACC_LOW_THRESHOLD:
            reasons.append(f"stop_success_rate ({ss_rate:.2f}) < {STOP_SUCCESS_ACC_LOW_THRESHOLD}")
        if ss_rate > STOP_SUCCESS_ACC_HIGH_THRESHOLD:
            reasons.append(f"stop_success_rate ({ss_rate:.2f}) > {STOP_SUCCESS_ACC_HIGH_THRESHOLD}")
    go_rt = metrics.get("go_rt")
    if go_rt is not None and go_rt > GO_RT_THRESHOLD_FMRI:
        reasons.append(f"go_rt ({go_rt:.0f}ms) > {GO_RT_THRESHOLD_FMRI}ms")
    return {"reason": "; ".join(reasons)} if reasons else None


def check_go_nogo_exclusion(metrics: dict) -> dict | None:
    """Check go/nogo dual-rule exclusion. Returns reason dict or None."""
    go_acc = metrics.get("go_acc")
    nogo_acc = metrics.get("nogo_acc")
    if go_acc is None or nogo_acc is None:
        return None
    rule1 = (go_acc <= GONOGO_GO_ACC_THRESHOLD_1) or (nogo_acc <= GONOGO_NOGO_ACC_THRESHOLD_1)
    rule2 = (go_acc <= GONOGO_GO_ACC_THRESHOLD_2) or (nogo_acc <= GONOGO_NOGO_ACC_THRESHOLD_2)
    if rule1 and rule2:
        return {"reason": f"go_acc={go_acc:.2f}, nogo_acc={nogo_acc:.2f} — both exclusion rules triggered"}
    return None


def check_nback_exclusion(metrics: dict, load: int) -> dict | None:
    """Check n-back exclusion for a specific load. Returns reason dict or None."""
    if load not in (1, 2):
        return None
    match_acc = metrics.get(f"match_{load}back_acc")
    mismatch_acc = metrics.get(f"mismatch_{load}back_acc")
    if match_acc is None or mismatch_acc is None:
        return None
    if load == 1:
        t1_match, t1_mismatch = NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1, NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1
        t2_match, t2_mismatch = NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_2, NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2
    else:
        t1_match, t1_mismatch = NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_1, NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1
        t2_match, t2_mismatch = NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_2, NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2
    rule1 = (match_acc <= t1_match) or (mismatch_acc <= t1_mismatch)
    rule2 = (match_acc <= t2_match) or (mismatch_acc <= t2_mismatch)
    if rule1 and rule2:
        return {"reason": f"{load}-back match={match_acc:.2f}, mismatch={mismatch_acc:.2f} — exclusion rules triggered"}
    return None


def check_other_exclusion(metrics: dict) -> dict | None:
    """Check accuracy/omission exclusion for non-special tasks."""
    reasons = []
    acc = metrics.get("acc")
    if acc is not None and acc < ACC_THRESHOLD:
        reasons.append(f"accuracy ({acc:.2f}) < {ACC_THRESHOLD}")
    omission = metrics.get("omission_rate")
    if omission is not None and omission > OMISSION_RATE_THRESHOLD:
        reasons.append(f"omission_rate ({omission:.2f}) > {OMISSION_RATE_THRESHOLD}")
    return {"reason": "; ".join(reasons)} if reasons else None


# --- Metric computation from sourcedata CSV ---

def compute_metrics_from_csv(csv_path: Path, task_name: str) -> dict:
    """Compute behavioral QC metrics from a sourcedata CSV.

    Args:
        csv_path: Path to the behavioral CSV
        task_name: BIDS task name (e.g., "stopSignal", "goNogo")

    Returns:
        Dict of metric_name -> value
    """
    df = pd.read_csv(csv_path)
    df["rt"] = pd.to_numeric(df.get("rt", pd.Series(dtype=float)), errors="coerce").fillna(-1)

    test_rows = df[df.get("trial_id", pd.Series(dtype=str)) == "test_trial"]
    if len(test_rows) == 0:
        return {}

    metrics = {}

    if "stopSignal" in task_name:
        go_trials = test_rows[test_rows.get("stop_signal_condition", pd.Series()) == "go"]
        stop_trials = test_rows[test_rows.get("stop_signal_condition", pd.Series()) == "stop"]
        if len(go_trials) > 0:
            valid_go = go_trials[go_trials["rt"] != -1]
            metrics["go_rt"] = float(valid_go["rt"].mean()) if len(valid_go) > 0 else None
            metrics["go_acc"] = float((go_trials["key_press"] == go_trials["correct_response"]).mean())
        if len(stop_trials) > 0:
            metrics["stop_success_rate"] = float((stop_trials.get("stop_acc", pd.Series()) == 1).mean())

    elif "goNogo" in task_name:
        go_trials = test_rows[test_rows.get("go_nogo_condition", pd.Series()) == "go"]
        nogo_trials = test_rows[test_rows.get("go_nogo_condition", pd.Series()) == "nogo"]
        if len(go_trials) > 0:
            metrics["go_acc"] = float((go_trials["key_press"] == go_trials["correct_response"]).mean())
        if len(nogo_trials) > 0:
            metrics["nogo_acc"] = float((nogo_trials["rt"] == -1).mean())

    elif "nBack" in task_name:
        for load in [1, 2]:
            load_str = f"{load}.0back"
            load_trials = test_rows[test_rows.get("n_back_condition", pd.Series()).astype(str).str.contains(load_str, na=False)]
            if len(load_trials) == 0:
                continue
            # Match = target present, Mismatch = target absent
            match_trials = load_trials[load_trials.get("n_back_condition", pd.Series()).str.contains("match", na=False) & ~load_trials.get("n_back_condition", pd.Series()).str.contains("mismatch", na=False)]
            mismatch_trials = load_trials[load_trials.get("n_back_condition", pd.Series()).str.contains("mismatch", na=False)]
            if len(match_trials) > 0:
                metrics[f"match_{load}back_acc"] = float((match_trials["key_press"] == match_trials["correct_response"]).mean())
            if len(mismatch_trials) > 0:
                metrics[f"mismatch_{load}back_acc"] = float((mismatch_trials["key_press"] == mismatch_trials["correct_response"]).mean())

    else:
        # Generic task: accuracy and omission rate
        valid_trials = test_rows[test_rows["rt"] != -1]
        if len(valid_trials) > 0:
            metrics["acc"] = float((valid_trials["key_press"] == valid_trials["correct_response"]).mean())
        metrics["omission_rate"] = float((test_rows["rt"] == -1).sum() / len(test_rows))

    return metrics


def determine_exclusion(task_name: str, metrics: dict) -> dict | None:
    """Determine if a run should be excluded based on task-specific criteria."""
    if "stopSignal" in task_name:
        return check_stop_signal_exclusion(metrics)
    elif "goNogo" in task_name:
        return check_go_nogo_exclusion(metrics)
    elif "nBack" in task_name:
        for load in [1, 2]:
            result = check_nback_exclusion(metrics, load)
            if result is not None:
                return result
        return None
    else:
        return check_other_exclusion(metrics)


def run_qc(
    behavioral_dir: Path,
    bids_dir: Path,
    subjects: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Run behavioral QC on sourcedata CSVs.

    Returns:
        (exclusion_entries, trim_entries) — lists of dicts for the exclusions system and trim list
    """
    exclusion_entries = []
    trim_entries = []
    qc_output_dir = bids_dir / "sourcedata" / "behavioral_qc"
    qc_output_dir.mkdir(parents=True, exist_ok=True)

    for sub_dir in sorted(behavioral_dir.glob("sub-*")):
        if subjects and sub_dir.name not in subjects:
            continue
        for ses_dir in sorted(sub_dir.glob("ses-*")):
            beh_dir = ses_dir / "beh"
            if not beh_dir.exists():
                continue
            for csv_file in sorted(beh_dir.glob("*.csv")):
                import re
                m = re.search(r"task-(\w+)", csv_file.name)
                if not m:
                    continue
                task_name = m.group(1)

                # Compute metrics
                metrics = compute_metrics_from_csv(csv_file, task_name)

                # Detect RT tail cutoff
                df = pd.read_csv(csv_file)
                cutoff_info = detect_rt_tail_cutoff(df)

                if cutoff_info is not None:
                    if cutoff_info["cutoff_before_halfway"]:
                        exclusion_entries.append({
                            "subject": sub_dir.name,
                            "session": ses_dir.name,
                            "task": task_name,
                            "run": "run-1",
                            "action": "exclude",
                            "source": "behavioral-qc",
                            "reason": f"RT tail cutoff before halfway (proportion_blank={cutoff_info['proportion_blank']:.2f})",
                        })
                    else:
                        trim_entries.append({
                            "subject": sub_dir.name,
                            "session": ses_dir.name,
                            "task": task_name,
                            "cutoff_onset_ms": cutoff_info["cutoff_onset_ms"],
                            "proportion_blank": cutoff_info["proportion_blank"],
                        })

                # Check exclusion criteria
                excl = determine_exclusion(task_name, metrics)
                if excl is not None:
                    exclusion_entries.append({
                        "subject": sub_dir.name,
                        "session": ses_dir.name,
                        "task": task_name,
                        "run": "run-1",
                        "action": "exclude",
                        "source": "behavioral-qc",
                        "reason": excl["reason"],
                    })

    # Write trim list
    trim_path = qc_output_dir / "trim_list.json"
    with open(trim_path, "w") as f:
        json.dump(trim_entries, f, indent=2)
    log.info("Wrote trim list: %s (%d entries)", trim_path, len(trim_entries))

    return exclusion_entries, trim_entries
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_qc.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/events/qc.py tests/events/test_qc.py
git commit -m "feat(events): add behavioral QC module with exclusion criteria and RT tail detection"
```

---

## Task 6: Behavioral Exclusion Generator — Replace Stub

**Files:**
- Modify: `src/neuro_workflow/exclusions/behavioral.py` (replace stub)
- Test: `tests/events/test_behavioral_exclusion_generator.py`

**Step 1: Write the failing test**

```python
# tests/events/test_behavioral_exclusion_generator.py
import pytest
from pathlib import Path
from unittest.mock import patch


class TestBehavioralGenerator:
    def test_registered_as_behavioral(self):
        from neuro_workflow.exclusions.base import get_generator
        import neuro_workflow.exclusions.behavioral  # trigger registration
        gen = get_generator("behavioral")
        assert gen is not None
        assert gen.name == "behavioral"

    def test_generate_returns_list(self, tmp_path):
        from neuro_workflow.exclusions.base import get_generator
        import neuro_workflow.exclusions.behavioral
        gen = get_generator("behavioral")
        # Create minimal sourcedata structure
        beh_dir = tmp_path / "sourcedata" / "sub-s01" / "ses-01" / "beh"
        beh_dir.mkdir(parents=True)
        # Also need bids_dir with func dir
        func_dir = tmp_path / "sub-s01" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        from argparse import Namespace
        args = Namespace(behavioral_dir=str(tmp_path / "sourcedata"))
        config = {"bids_dir": str(tmp_path)}
        result = gen.generate("test", config, args)
        assert isinstance(result, list)

    def test_exclusion_entry_format(self):
        """Entries must have required fields for the exclusions system."""
        entry = {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "stopSignal",
            "run": "run-1",
            "action": "exclude",
            "source": "behavioral-qc",
            "reason": "test reason",
        }
        required = {"subject", "session", "task", "run", "action", "reason"}
        assert required.issubset(entry.keys())
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_behavioral_exclusion_generator.py -v`
Expected: At least `test_generate_returns_list` should fail (current stub returns empty list without doing QC).

**Step 3: Replace the stub with real implementation**

```python
# src/neuro_workflow/exclusions/behavioral.py
"""Behavioral exclusion generator — runs behavioral QC and produces exclusion entries."""
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.exclusions.base import register_generator


class BehavioralGenerator:
    name = "behavioral"
    description = "Generate exclusions from behavioral QC (accuracy, RT, omission thresholds)"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--behavioral-dir",
            required=False,
            default=None,
            help="Path to sourcedata behavioral directory (default: {bids_dir}/sourcedata)",
        )

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        try:
            from neuro_workflow.events.qc import run_qc
        except ImportError:
            print("Error: pandas required for behavioral generator. Install with: uv pip install -e '.[events]'")
            return []

        bids_dir = Path(dataset_config["bids_dir"])
        behavioral_dir = Path(args.behavioral_dir) if getattr(args, "behavioral_dir", None) else bids_dir / "sourcedata"

        exclusion_entries, trim_entries = run_qc(
            behavioral_dir=behavioral_dir,
            bids_dir=bids_dir,
        )

        # Source field is set by the exclusions system when saving, but include for clarity
        for entry in exclusion_entries:
            entry["source"] = "behavioral-qc"

        print(f"Behavioral QC: {len(exclusion_entries)} exclusions, {len(trim_entries)} trim entries")
        return exclusion_entries


register_generator(BehavioralGenerator())
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_behavioral_exclusion_generator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/exclusions/behavioral.py tests/events/test_behavioral_exclusion_generator.py
git commit -m "feat(exclusions): replace behavioral stub with QC-driven exclusion generator"
```

---

## Task 7: NIfTI Trimming Module

**Files:**
- Create: `src/neuro_workflow/events/trim.py`
- Test: `tests/events/test_trim.py`

**Step 1: Write the failing tests**

```python
# tests/events/test_trim.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np


class TestCalculateVolumeCutoff:
    def test_basic_calculation(self):
        from neuro_workflow.events.trim import calculate_volume_cutoff
        # onset_cutoff=10000ms, TR=2000ms -> 5 volumes
        assert calculate_volume_cutoff(10000.0, 2.0) == 5

    def test_rounds_down(self):
        from neuro_workflow.events.trim import calculate_volume_cutoff
        # onset_cutoff=11000ms, TR=2000ms -> floor(5.5) = 5
        assert calculate_volume_cutoff(11000.0, 2.0) == 5


class TestTrimNifti:
    def test_trims_to_correct_volumes(self, tmp_path):
        from neuro_workflow.events.trim import trim_nifti
        import nibabel as nib

        # Create a fake 4D NIfTI with 10 volumes
        data = np.random.rand(2, 2, 2, 10).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nifti_path = tmp_path / "bold.nii.gz"
        nib.save(img, str(nifti_path))

        # Also create a JSON sidecar
        sidecar = {"RepetitionTime": 2.0, "NumVolumes": 10}
        json_path = tmp_path / "bold.json"
        json_path.write_text(json.dumps(sidecar))

        out_nifti = tmp_path / "out" / "bold_trimmed.nii.gz"
        out_json = tmp_path / "out" / "bold_trimmed.json"
        out_nifti.parent.mkdir(parents=True)

        trim_nifti(nifti_path, out_nifti, n_volumes=7)

        trimmed = nib.load(str(out_nifti))
        assert trimmed.shape[-1] == 7

    def test_patches_json_sidecar(self, tmp_path):
        from neuro_workflow.events.trim import trim_nifti
        import nibabel as nib

        data = np.random.rand(2, 2, 2, 10).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nifti_path = tmp_path / "bold.nii.gz"
        nib.save(img, str(nifti_path))

        sidecar = {"RepetitionTime": 2.0, "NumVolumes": 10}
        json_path = tmp_path / "bold.json"
        json_path.write_text(json.dumps(sidecar))

        out_nifti = tmp_path / "out" / "bold_trimmed.nii.gz"
        out_json = tmp_path / "out" / "bold_trimmed.json"
        out_nifti.parent.mkdir(parents=True)

        trim_nifti(nifti_path, out_nifti, n_volumes=7, json_in=json_path, json_out=out_json)

        patched = json.loads(out_json.read_text())
        assert patched["NumVolumes"] == 7
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_trim.py -v`
Expected: FAIL

**Step 3: Write the trim module**

```python
# src/neuro_workflow/events/trim.py
"""Trim NIfTIs to match behavioral cutoff."""
import json
import logging
import math
import re
from pathlib import Path

log = logging.getLogger(__name__)


def calculate_volume_cutoff(onset_cutoff_ms: float, tr_seconds: float) -> int:
    """Calculate number of volumes to keep based on onset cutoff time."""
    onset_seconds = onset_cutoff_ms / 1000.0
    return math.floor(onset_seconds / tr_seconds)


def trim_nifti(
    nifti_in: Path,
    nifti_out: Path,
    n_volumes: int,
    json_in: Path | None = None,
    json_out: Path | None = None,
) -> None:
    """Truncate a 4D NIfTI to n_volumes and optionally patch JSON sidecar."""
    import nibabel as nib

    img = nib.load(str(nifti_in))
    data = img.get_fdata()
    trimmed_data = data[..., :n_volumes]
    trimmed_img = nib.Nifti1Image(trimmed_data, img.affine, img.header)
    nifti_out.parent.mkdir(parents=True, exist_ok=True)
    nib.save(trimmed_img, str(nifti_out))
    log.info("Trimmed %s -> %s (%d volumes)", nifti_in.name, nifti_out.name, n_volumes)

    if json_in is not None and json_out is not None and json_in.exists():
        sidecar = json.loads(json_in.read_text())
        if "NumVolumes" in sidecar:
            sidecar["NumVolumes"] = n_volumes
        json_out.write_text(json.dumps(sidecar, indent=2))


def run_trim(bids_dir: Path) -> None:
    """Trim NIfTIs based on trim_list.json from behavioral QC.

    Reads: {bids_dir}/sourcedata/behavioral_qc/trim_list.json
    Writes: {bids_dir}/derivatives/trimmed/sub-*/ses-*/func/*_desc-trimmed_bold.nii.gz
    """
    trim_list_path = bids_dir / "sourcedata" / "behavioral_qc" / "trim_list.json"
    if not trim_list_path.exists():
        log.warning("No trim list found at %s", trim_list_path)
        return

    trim_list = json.loads(trim_list_path.read_text())
    if not trim_list:
        log.info("Trim list is empty, nothing to do")
        return

    deriv_dir = bids_dir / "derivatives" / "trimmed"

    for entry in trim_list:
        subject = entry["subject"]
        session = entry["session"]
        task = entry["task"]
        cutoff_ms = entry["cutoff_onset_ms"]

        func_dir = bids_dir / subject / session / "func"
        if not func_dir.exists():
            log.warning("No func dir for %s %s", subject, session)
            continue

        # Find matching NIfTIs
        pattern = f"{subject}_{session}_task-{task}_*_bold.nii.gz"
        niftis = sorted(func_dir.glob(pattern))
        if not niftis:
            # Try without run entity
            pattern = f"{subject}_{session}_task-{task}_bold.nii.gz"
            niftis = sorted(func_dir.glob(pattern))

        for nifti_path in niftis:
            # Get TR from JSON sidecar
            json_path = nifti_path.with_suffix("").with_suffix(".json")
            if not json_path.exists():
                # Try removing .nii.gz and adding .json
                json_path = Path(str(nifti_path).replace(".nii.gz", ".json"))
            if not json_path.exists():
                log.warning("No JSON sidecar for %s, skipping", nifti_path)
                continue

            sidecar = json.loads(json_path.read_text())
            tr = sidecar.get("RepetitionTime")
            if tr is None:
                log.warning("No RepetitionTime in %s, skipping", json_path)
                continue

            n_volumes = calculate_volume_cutoff(cutoff_ms, tr)

            # Build output path with desc-trimmed entity
            out_name = re.sub(r"_bold\.nii\.gz$", "_desc-trimmed_bold.nii.gz", nifti_path.name)
            out_path = deriv_dir / subject / session / "func" / out_name
            out_json = out_path.with_suffix("").with_suffix(".json")

            trim_nifti(nifti_path, out_path, n_volumes, json_in=json_path, json_out=out_json)

    log.info("Trimming complete: processed %d entries", len(trim_list))
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_trim.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/events/trim.py tests/events/test_trim.py
git commit -m "feat(events): add NIfTI trimming module for behavioral cutoff"
```

---

## Task 8: CLI Wiring — events create/qc/trim Commands

**Files:**
- Modify: `src/neuro_workflow/cli.py`
- Test: `tests/events/test_cli.py`

**Step 1: Write the failing tests**

```python
# tests/events/test_cli.py
import pytest
from unittest.mock import patch, MagicMock


class TestEventsSubcommand:
    def test_events_create_parses(self):
        """neuro-run events create <dataset> --behavioral-dir <dir>"""
        import sys
        from neuro_workflow.cli import main
        with patch.object(sys, "argv", [
            "neuro-run", "events", "create", "discovery",
            "--behavioral-dir", "/tmp/sourcedata",
        ]):
            with patch("neuro_workflow.cli.cmd_events_create") as mock_create:
                with patch("neuro_workflow.cli.get_dataset", return_value={"bids_dir": "/tmp/bids"}):
                    main()
                    mock_create.assert_called_once()

    def test_events_qc_parses(self):
        """neuro-run events qc <dataset> --behavioral-dir <dir>"""
        import sys
        from neuro_workflow.cli import main
        with patch.object(sys, "argv", [
            "neuro-run", "events", "qc", "discovery",
            "--behavioral-dir", "/tmp/sourcedata",
        ]):
            with patch("neuro_workflow.cli.cmd_events_qc") as mock_qc:
                with patch("neuro_workflow.cli.get_dataset", return_value={"bids_dir": "/tmp/bids"}):
                    main()
                    mock_qc.assert_called_once()

    def test_events_trim_parses(self):
        """neuro-run events trim <dataset>"""
        import sys
        from neuro_workflow.cli import main
        with patch.object(sys, "argv", [
            "neuro-run", "events", "trim", "discovery",
        ]):
            with patch("neuro_workflow.cli.cmd_events_trim") as mock_trim:
                with patch("neuro_workflow.cli.get_dataset", return_value={"bids_dir": "/tmp/bids"}):
                    main()
                    mock_trim.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/events/test_cli.py -v`
Expected: FAIL — `cmd_events_create` doesn't exist

**Step 3: Add CLI wiring**

Add to `src/neuro_workflow/cli.py`:

1. Three command functions: `cmd_events_create`, `cmd_events_qc`, `cmd_events_trim`
2. An `events` subparser group with `create`, `qc`, `trim` sub-subcommands
3. Each takes `dataset` positional arg and `--behavioral-dir` optional arg

Add these functions after the existing `cmd_bidsify`:

```python
def cmd_events_create(args, remaining):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from neuro_workflow.events.create import run_create_events
    config = get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    behavioral_dir = Path(args.behavioral_dir) if args.behavioral_dir else bids_dir / "sourcedata"
    run_create_events(behavioral_dir=behavioral_dir, bids_dir=bids_dir)


def cmd_events_qc(args, remaining):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from neuro_workflow.events.qc import run_qc
    from neuro_workflow.core.exclusions import save_source_entries
    config = get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    behavioral_dir = Path(args.behavioral_dir) if args.behavioral_dir else bids_dir / "sourcedata"
    exclusion_entries, trim_entries = run_qc(behavioral_dir=behavioral_dir, bids_dir=bids_dir)
    if exclusion_entries:
        save_source_entries(args.dataset, "behavioral-qc", exclusion_entries)
        print(f"Saved {len(exclusion_entries)} behavioral-qc exclusion entries")
    print(f"Found {len(trim_entries)} runs needing trimming")


def cmd_events_trim(args, remaining):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from neuro_workflow.events.trim import run_trim
    config = get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    run_trim(bids_dir=bids_dir)
```

Add the subparser group in `main()` after the `bidsify` parser:

```python
    # events
    events_p = subparsers.add_parser("events", help="Behavioral events pipeline")
    events_sub = events_p.add_subparsers(dest="events_command", required=True)

    # events create
    ev_create = events_sub.add_parser("create", help="Generate BIDS _events.tsv from behavioral CSVs")
    ev_create.add_argument("dataset", help="Dataset name")
    ev_create.add_argument("--behavioral-dir", default=None, help="Path to sourcedata behavioral directory")
    ev_create.set_defaults(func=cmd_events_create)

    # events qc
    ev_qc = events_sub.add_parser("qc", help="Run behavioral QC and generate exclusions")
    ev_qc.add_argument("dataset", help="Dataset name")
    ev_qc.add_argument("--behavioral-dir", default=None, help="Path to sourcedata behavioral directory")
    ev_qc.set_defaults(func=cmd_events_qc)

    # events trim
    ev_trim = events_sub.add_parser("trim", help="Trim NIfTIs to match behavioral cutoff")
    ev_trim.add_argument("dataset", help="Dataset name")
    ev_trim.set_defaults(func=cmd_events_trim)
```

**Step 4: Run test to verify it passes**

Run: `module load uv && uv run pytest tests/events/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/cli.py tests/events/test_cli.py
git commit -m "feat(events): wire events create/qc/trim CLI commands"
```

---

## Task 9: Dependencies and README Update

**Files:**
- Modify: `pyproject.toml` — add `[events]` optional dependency group
- Modify: `README.md` — document events pipeline

**Step 1: Add optional dependency group**

In `pyproject.toml`, add under `[project.optional-dependencies]`:

```toml
events = ["pandas", "numpy", "nibabel"]
```

**Step 2: Update README.md**

Add a section documenting:
- `scripts/rename_behavioral_to_sourcedata.py` usage
- `neuro-run events create <dataset>`
- `neuro-run events qc <dataset>`
- `neuro-run events trim <dataset>`
- Integration with `neuro-run exclusions compile`

**Step 3: Run all tests**

Run: `module load uv && uv run pytest tests/events/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add pyproject.toml README.md
git commit -m "docs: add events pipeline documentation and optional dependency group"
```

---

## Data Flow Summary

```
raw_cleaned/                    (original behavioral CSVs)
    | [scripts/rename_behavioral_to_sourcedata.py]  (one-time)
sourcedata/                     (standardized BIDS layout)
    | [neuro-run events create]
{bids_dir}/.../func/*_events.tsv    (BIDS event files)
    | [neuro-run events qc]
    |-> exclusions system            (behavioral-qc source -> compile -> lev1)
    |-> QC summary CSVs              (per-task metrics)
    |-> trim_list.json               (tasks needing trimming)
        | [neuro-run events trim]
        |-> derivatives/trimmed/     (truncated NIfTIs with desc-trimmed)
```

## Module Structure

```
src/neuro_workflow/events/
├── __init__.py
├── create.py          # event file generation (ported from discovery_wm)
├── utils.py           # shared event processing utilities
├── qc.py              # behavioral QC metrics + exclusion criteria
├── qc_globals.py      # thresholds and task definitions
└── trim.py            # NIfTI trimming

src/neuro_workflow/exclusions/
└── behavioral.py      # exclusion generator (replaces stub)

scripts/
└── rename_behavioral_to_sourcedata.py
```
