import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.qa.breaks import (
    BreaksQa,
    extract_task_name_from_filename,
    analyze_stimulus_for_performance_feedback,
)


def test_extract_task_name():
    assert extract_task_name_from_filename("stop_signal__fmri_rest.csv") == "stopSignal"
    assert extract_task_name_from_filename("flanker__fmri.csv") == "flanker"


def test_analyze_stimulus_feedback():
    indicators, has_feedback = analyze_stimulus_for_performance_feedback(
        "Your accuracy was 85%"
    )
    assert has_feedback is True
    assert "accuracy" in indicators


def test_analyze_stimulus_no_feedback():
    indicators, has_feedback = analyze_stimulus_for_performance_feedback(
        "Press any key to continue"
    )
    assert has_feedback is False
    assert indicators == []


def test_analyze_stimulus_nan():
    import math
    indicators, has_feedback = analyze_stimulus_for_performance_feedback(float("nan"))
    assert has_feedback is False


def test_qa_attributes():
    qa = BreaksQa()
    assert qa.name == "breaks"
    assert qa.description


def test_run_produces_json(tmp_path):
    """Create a minimal behavioral file and verify JSON output."""
    beh_dir = tmp_path / "behavioral"
    sub_dir = beh_dir / "s01" / "ses-01"
    sub_dir.mkdir(parents=True)
    csv_file = sub_dir / "stop_signal__fmri.csv"
    csv_file.write_text(
        "trial_id,stimulus\n"
        "test_trial,fixation\n"
        "test_feedback,Your accuracy was 85%\n"
    )

    output_dir = tmp_path / "output"
    config = {"bids_dir": str(tmp_path / "bids")}
    args = Namespace(behavioral_dir=str(beh_dir), output_dir=str(output_dir))
    qa = BreaksQa()
    qa.run("discovery", config, args)

    master = output_dir / "break_analysis_master.json"
    assert master.exists()
    data = json.loads(master.read_text())
    assert "break_feedback_analysis" in data
    assert len(data["break_feedback_analysis"]) >= 1
