import pytest
from neuro_workflow.behavioral_archive.normalize_filenames import (
    normalize_task_name,
    normalize_mturk_filename,
    normalize_out_of_scanner_filename,
    normalize_survey_filename,
)


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
    """survey: prescan_1.json -> prescan-01_survey.json (subject added later)"""
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
