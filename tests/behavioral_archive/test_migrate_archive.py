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
    (archive_mturk / "s528" / "s528_task1.csv").write_text("data")
    (archive_mturk / "s528" / "s528_go_nogo_with_shape_matching.csv").write_text("more")
    (archive_mturk / "s999").mkdir(parents=True)
    (archive_mturk / "s999" / "s999_stroop.csv").write_text("other")

    # Setup destination
    dest_mturk = tmp_path / "mturk"

    # Migrate
    stats = migrate_mturk_data(archive_mturk, dest_mturk, dry_run=False)

    # Verify
    assert stats["migrated"] == 3
    assert (dest_mturk / "sub-s528" / "sub-s528_task-task1_behavior.csv").exists()
    assert (dest_mturk / "sub-s999" / "sub-s999_task-stroop_behavior.csv").exists()


def test_migrate_mturk_data_dry_run(tmp_path):
    """Dry-run mode shows what would happen without copying."""
    archive_mturk = tmp_path / "archive" / "mTurk" / "all_data"
    (archive_mturk / "s528").mkdir(parents=True)
    (archive_mturk / "s528" / "s528_stroop.csv").write_text("data")

    dest_mturk = tmp_path / "mturk"

    stats = migrate_mturk_data(archive_mturk, dest_mturk, dry_run=True)

    # Stats should show action but files should not be copied
    assert stats["migrated"] == 1
    assert not (dest_mturk / "sub-s528" / "sub-s528_task-stroop_behavior.csv").exists()


def test_migrate_out_of_scanner_data(tmp_path):
    """Migrate out_of_scanner data only for subjects in sample."""
    # Setup archive
    archive_out = tmp_path / "archive" / "out_of_scanner"
    (archive_out / "s247").mkdir(parents=True)
    (archive_out / "s247" / "s247_flanker_single_task.csv").write_text("data")
    (archive_out / "s999").mkdir(parents=True)  # Not in sample
    (archive_out / "s999" / "s999_stroop.csv").write_text("data")

    # Setup config with only s247
    config = {"discovery": ["s247"], "validation": []}

    dest_out = tmp_path / "sourcedata" / "out_scanner_behavior"

    stats = migrate_out_of_scanner_data(archive_out, dest_out, config, dry_run=False)

    # Should migrate s247 but skip s999
    assert stats["migrated"] == 1
    assert stats["skipped_not_in_sample"] == 1
    assert (dest_out / "sub-s247" / "sub-s247_task-flanker_behavior.csv").exists()
    assert not (dest_out / "sub-s999").exists()


def test_migrate_survey_data(tmp_path):
    """Migrate survey data only for subjects in sample."""
    import json

    # Setup archive with valid survey JSON
    survey_json = {
        "worker_id": "test",
        "experiment_id": "prescan",
        "battery_name": "Prescan",
        "finishtime": "2024-01-01T00:00:00Z",
        "completed": True,
        "data": {}
    }

    archive_survey = tmp_path / "archive" / "survey_data" / "prescan_surveys" / "raw"
    (archive_survey / "s247").mkdir(parents=True)
    (archive_survey / "s247" / "prescan_1.json").write_text(json.dumps(survey_json))
    (archive_survey / "s247" / "prescan_2.json").write_text(json.dumps(survey_json))
    (archive_survey / "s528").mkdir(parents=True)
    (archive_survey / "s528" / "prescan_1.json").write_text(json.dumps(survey_json))

    config = {"discovery": ["s247"], "validation": ["s528"]}

    dest_survey = tmp_path / "sourcedata" / "survey_data"

    stats = migrate_survey_data(archive_survey, dest_survey, config, dry_run=False)

    # Should migrate all (both in sample)
    assert stats["migrated"] == 3
    assert (dest_survey / "sub-s247" / "sub-s247_prescan-01_survey.csv").exists()
    assert (dest_survey / "sub-s247" / "sub-s247_prescan-02_survey.csv").exists()
    assert (dest_survey / "sub-s528" / "sub-s528_prescan-01_survey.csv").exists()
