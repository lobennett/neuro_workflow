"""Loader raises TaskNotConfiguredError on placeholder dual-task YAMLs."""
import pytest

from neuro_workflow.analysis.task_config.loader import (
    TaskNotConfiguredError,
    get_task_parameters,
    get_task_regressors,
)


def test_dual_task_placeholder_raises_on_regressors():
    with pytest.raises(TaskNotConfiguredError, match="regressors"):
        get_task_regressors("cuedTSWFlanker")


def test_dual_task_placeholder_parameters_still_load():
    # Parameters (tr, dummy_scans, ...) are intentionally still readable so callers
    # can introspect a placeholder before deciding whether to skip.
    params = get_task_parameters("cuedTSWFlanker")
    assert params["tr"] == 1.49


def test_base_task_loads_normally():
    params = get_task_parameters("stopSignal")
    assert params["tr"] == 1.49
