"""End-to-end integration test for behavioral data migration."""

import json
import pytest
from pathlib import Path
import subprocess
import sys


def test_migration_end_to_end(tmp_path):
    """Full migration test with realistic archive structure."""
    # Create realistic archive structure
    archive_root = tmp_path / "archive"

    # mTurk data
    mturk_data = archive_root / "behavioral_data" / "mTurk" / "all_data"
    (mturk_data / "s528").mkdir(parents=True)
    (mturk_data / "s528" / "s528_go_nogo_with_shape_matching.csv").write_text("s528,data")
    (mturk_data / "s999").mkdir(parents=True)
    (mturk_data / "s999" / "s999_flanker_single_task_network.csv").write_text("s999,data")

    # out_of_scanner data
    out_data = archive_root / "behavioral_data" / "out_of_scanner"
    (out_data / "s247").mkdir(parents=True)
    (out_data / "s247" / "s247_flanker.csv").write_text("s247,data")
    (out_data / "s528").mkdir(parents=True)
    (out_data / "s528" / "s528_stop_signal_single_task.csv").write_text("s528,data")

    # survey data (with valid JSON structure for conversion)
    survey_json = json.dumps({
        "worker_id": "test",
        "experiment_id": "prescan",
        "battery_name": "Prescan",
        "finishtime": "2024-01-01T00:00:00Z",
        "completed": True,
        "data": {}
    })
    survey_data = archive_root / "behavioral_data" / "survey_data" / "prescan_surveys" / "raw"
    (survey_data / "s247").mkdir(parents=True)
    (survey_data / "s247" / "prescan_1.json").write_text(survey_json)
    (survey_data / "s247" / "prescan_2.json").write_text(survey_json)

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
        sys.executable, "scripts/migrate_archive_behavioral_data.py",
        "--archive-dir", str(archive_root / "behavioral_data"),
        "--sourcedata-dir", str(sourcedata),
        "--mturk-dir", str(mturk_out),
        "--config", str(config),
    ]

    # Get the project root (3 levels up from tests/behavioral_archive)
    project_root = Path(__file__).parent.parent.parent
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    assert result.returncode == 0, f"Migration failed with return code {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"

    # Verify mTurk output
    assert (mturk_out / "sub-s528" / "sub-s528_task-goNogoWShapeMatching_behavior.csv").exists(), \
        f"mTurk file not found at {mturk_out / 'sub-s528'}"
    assert (mturk_out / "sub-s999" / "sub-s999_task-flanker_behavior.csv").exists()

    # Verify out_of_scanner output
    assert (sourcedata / "out_scanner_behavior" / "sub-s247" / "sub-s247_task-flanker_behavior.csv").exists()
    assert (sourcedata / "out_scanner_behavior" / "sub-s528" / "sub-s528_task-stopSignal_behavior.csv").exists()

    # Verify survey output (now CSV format)
    assert (sourcedata / "survey_data" / "sub-s247" / "sub-s247_prescan-01_survey.csv").exists()
    assert (sourcedata / "survey_data" / "sub-s247" / "sub-s247_prescan-02_survey.csv").exists()

    # Verify report
    report_path = sourcedata / "behavioral_migration_report.json"
    assert report_path.exists(), "Migration report not generated"

    report = json.loads(report_path.read_text())
    assert report["dry_run"] is False
    assert report["mturk"]["migrated"] == 2
    assert report["out_of_scanner"]["migrated"] == 2
    assert report["survey"]["migrated"] == 2
    assert report["total_migrated"] == 6
    assert "timestamp" in report
