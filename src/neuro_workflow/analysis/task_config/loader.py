"""Load and validate task configurations from YAML files.

Each task has a YAML file in task_config/tasks/ defining its regressors,
contrasts, and parameters. This module provides the same API as the old
tasks.py so callers do not need to change.

YAML regressor format:
    amplitude: 1              -> constant amplitude of 1
    amplitude: omission       -> use the 'omission' column from events
    duration: 1               -> constant duration of 1 second
    duration: response_time   -> use the 'response_time' column from events
    subset: null              -> use all rows (no filter)
    subset: "trial_type == 'go'"  -> pandas query string
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

# Default analysis parameters (can be overridden per task in YAML)
DEFAULT_TR = 1.49
DEFAULT_DUMMY_SCANS = 7
DEFAULT_MIN_RT = 0.2

# Directory containing per-task YAML files
_TASKS_DIR = Path(__file__).parent / 'tasks'

# Required fields in each YAML file
_REQUIRED_FIELDS = {'regressors', 'contrasts'}
_REQUIRED_REGRESSOR_FIELDS = {'amplitude', 'duration', 'subset'}


def _load_yaml(task_name: str) -> Dict[str, Any]:
    """Load a single task YAML file.

    Args:
        task_name: Name of the task (matches filename without extension).

    Returns:
        Parsed YAML content as a dictionary.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If required fields are missing.
    """
    yaml_path = _TASKS_DIR / f'{task_name}.yaml'
    if not yaml_path.exists():
        available = list_available_tasks()
        raise FileNotFoundError(
            f"No config file for task '{task_name}'. "
            f'Available tasks: {available}'
        )

    with open(yaml_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Validate top-level fields
    missing = _REQUIRED_FIELDS - set(config.keys())
    if missing:
        raise ValueError(
            f"Task config '{task_name}' is missing required fields: {missing}"
        )

    # Validate each regressor has required fields
    for reg_name, reg_config in config.get('regressors', {}).items():
        if not isinstance(reg_config, dict):
            raise ValueError(
                f"Regressor '{reg_name}' in task '{task_name}' must be a dict, "
                f'got {type(reg_config).__name__}'
            )
        missing_reg = _REQUIRED_REGRESSOR_FIELDS - set(reg_config.keys())
        if missing_reg:
            raise ValueError(
                f"Regressor '{reg_name}' in task '{task_name}' is missing "
                f'required fields: {missing_reg}'
            )

    return config


@lru_cache(maxsize=32)
def _get_task_config(task_name: str) -> Dict[str, Any]:
    """Cached wrapper around _load_yaml."""
    return _load_yaml(task_name)


def _convert_regressor_config(yaml_regressors: Dict) -> Dict[str, Dict[str, str]]:
    """Convert YAML regressor format to the internal format used by design.py.

    YAML format:
        amplitude: 1 | column_name
        duration: 1 | column_name
        subset: null | query_string

    Internal format (used by create_regressor):
        amplitude_column: 'constant_1_column' | column_name
        duration_column: 'constant_1_column' | column_name
        subset: None | query_string
    """
    converted = {}
    for name, cfg in yaml_regressors.items():
        amp = cfg['amplitude']
        dur = cfg['duration']

        # Convert integer/float 1 to 'constant_1_column' sentinel
        amp_col = 'constant_1_column' if isinstance(amp, (int, float)) else str(amp)
        dur_col = 'constant_1_column' if isinstance(dur, (int, float)) else str(dur)

        # subset: null in YAML becomes None in Python
        subset = cfg.get('subset')

        converted[name] = {
            'amplitude_column': amp_col,
            'duration_column': dur_col,
            'subset': subset,
        }

    return converted


def list_available_tasks() -> List[str]:
    """List all tasks with YAML config files.

    Returns:
        Sorted list of task names.
    """
    if not _TASKS_DIR.exists():
        return []
    return sorted(p.stem for p in _TASKS_DIR.glob('*.yaml'))


def get_regressor_config(task_name: str) -> Dict[str, Dict[str, str]]:
    """Get regressor configuration for a task.

    Args:
        task_name: Name of the task.

    Returns:
        Dictionary mapping regressor names to their configuration.

    Raises:
        FileNotFoundError: If no YAML file exists for the task.
        ValueError: If the regressor config is empty.
    """
    config = _get_task_config(task_name)
    regressors = config.get('regressors', {})
    if not regressors:
        raise ValueError(
            f"Regressor config is empty for task '{task_name}'. "
            'Define regressors in the YAML file before running.'
        )
    return _convert_regressor_config(regressors)


def get_task_contrasts(task_name: str) -> Dict[str, str]:
    """Get contrast definitions for a task.

    Args:
        task_name: Name of the task.

    Returns:
        Dictionary mapping contrast names to formula strings.

    Raises:
        FileNotFoundError: If no YAML file exists for the task.
        ValueError: If the contrast config is empty.
    """
    config = _get_task_config(task_name)
    contrasts = config.get('contrasts', {})
    if not contrasts:
        raise ValueError(
            f"Contrast config is empty for task '{task_name}'. "
            'Define contrasts in the YAML file before running.'
        )
    return dict(contrasts)


def get_task_parameters(task_name: str) -> Dict[str, Any]:
    """Get general parameters for a task.

    Args:
        task_name: Name of the task.

    Returns:
        Dictionary with keys: tr, dummy_scans, min_rt, expected_sessions.
    """
    config = _get_task_config(task_name)
    return {
        'tr': config.get('tr', DEFAULT_TR),
        'dummy_scans': config.get('dummy_scans', DEFAULT_DUMMY_SCANS),
        'min_rt': config.get('min_rt', DEFAULT_MIN_RT),
        'expected_sessions': config.get('expected_sessions', 5),
    }


def get_raw_yaml_config(task_name: str) -> Dict[str, Any]:
    """Get the raw YAML config for inspection/debugging.

    Args:
        task_name: Name of the task.

    Returns:
        The full parsed YAML dictionary.
    """
    return _get_task_config(task_name)


# Backward-compatible constants (used by events.py, confounds.py, etc.)
TR = DEFAULT_TR
DUMMY_SCANS = DEFAULT_DUMMY_SCANS
MIN_RT = DEFAULT_MIN_RT
