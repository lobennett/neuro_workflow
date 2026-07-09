"""TDD tests for task battery accessors in loader.py.

These tests verify that get_base_tasks(), get_dual_tasks(), get_all_tasks()
return the EXACT same lists (members AND order) as the original hardcoded
constants in lev1.py.
"""

from neuro_workflow.analysis.task_config.loader import (
    get_all_tasks,
    get_base_tasks,
    get_dual_tasks,
)

_EXPECTED_BASE = [
    "cuedTS",
    "directedForgetting",
    "flanker",
    "goNogo",
    "nBack",
    "shapeMatching",
    "spatialTS",
    "stopSignal",
]

_EXPECTED_DUAL = [
    "directedForgettingWCuedTS",
    "directedForgettingWFlanker",
    "stopSignalWDirectedForgetting",
    "stopSignalWFlanker",
    "spatialTSWCuedTS",
    "flankerWShapeMatching",
    "cuedTSWFlanker",
    "spatialTSWShapeMatching",
    "nBackWShapeMatching",
    "nBackWSpatialTS",
    "shapeMatchingWCuedTS",
]


def test_get_base_tasks_exact():
    """get_base_tasks() must return exact list (members AND order)."""
    assert get_base_tasks() == _EXPECTED_BASE


def test_get_dual_tasks_exact():
    """get_dual_tasks() must return exact list (members AND order)."""
    assert get_dual_tasks() == _EXPECTED_DUAL


def test_get_all_tasks_exact():
    """get_all_tasks() must equal base + dual (same order)."""
    assert get_all_tasks() == _EXPECTED_BASE + _EXPECTED_DUAL


def test_get_all_tasks_is_base_plus_dual():
    """get_all_tasks() == get_base_tasks() + get_dual_tasks()."""
    assert get_all_tasks() == get_base_tasks() + get_dual_tasks()


def test_base_has_8_tasks():
    assert len(get_base_tasks()) == 8


def test_dual_has_11_tasks():
    assert len(get_dual_tasks()) == 11


def test_all_has_19_tasks():
    assert len(get_all_tasks()) == 19


def test_all_eleven_dual_tasks_registered():
    from neuro_workflow.analysis.task_config.loader import get_dual_tasks

    dual = get_dual_tasks()
    assert "shapeMatchingWCuedTS" in dual
    assert len(dual) == 11
