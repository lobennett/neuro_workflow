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
