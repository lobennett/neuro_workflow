"""Tests for load-time contrast-formula validation in the task config loader.

These tests verify that contrast formulas referencing undeclared regressor names
raise ContrastFormulaError at config load time, with a clear message naming the
task, contrast, and unknown identifier.

They run in the core suite (no heavy analysis deps).
"""

import textwrap
from pathlib import Path

import pytest
import yaml

from neuro_workflow.analysis.task_config.loader import (
    ContrastFormulaError,
    _load_yaml,
    _TASKS_DIR,
    get_task_contrasts,
    list_available_tasks,
)

# -------------------------------------------------------------------
# Helper: write a minimal task YAML into a tmp dir and monkey-patch the
# loader's _TASKS_DIR so _load_yaml picks it up.
# -------------------------------------------------------------------

BASE_TASKS = [
    "cuedTS",
    "directedForgetting",
    "flanker",
    "goNogo",
    "nBack",
    "shapeMatching",
    "spatialTS",
    "stopSignal",
]


@pytest.fixture()
def tmp_task_yaml(tmp_path, monkeypatch):
    """Return a helper that writes YAML text to a temp tasks dir and patches _TASKS_DIR."""

    def _write(task_name: str, yaml_text: str) -> Path:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir(exist_ok=True)
        # Patch the module-level _TASKS_DIR so _load_yaml resolves against tmp
        import neuro_workflow.analysis.task_config.loader as loader_mod

        monkeypatch.setattr(loader_mod, "_TASKS_DIR", tasks_dir)
        # Also clear the lru_cache so the patched path is used
        loader_mod._get_task_config.cache_clear()
        yaml_path = tasks_dir / f"{task_name}.yaml"
        yaml_path.write_text(yaml_text, encoding="utf-8")
        return yaml_path

    yield _write

    # Clear cache after each test so real tasks load normally afterwards
    import neuro_workflow.analysis.task_config.loader as loader_mod

    loader_mod._get_task_config.cache_clear()


# -------------------------------------------------------------------
# RED tests (must fail before implementation, green after)
# -------------------------------------------------------------------


class TestContrastFormulaErrorClass:
    """ContrastFormulaError must be a ValueError subclass."""

    def test_is_value_error_subclass(self):
        err = ContrastFormulaError("some message")
        assert isinstance(err, ValueError)

    def test_message_preserved(self):
        err = ContrastFormulaError("task 'foo' contrast 'bar': unknown regressor 'stp'")
        assert "stp" in str(err)


class TestContrastFormulaValidationRejectsUnknown:
    """_load_yaml must raise ContrastFormulaError for unknown regressor tokens."""

    def test_single_typo_raises(self, tmp_task_yaml):
        """A contrast referencing 'stp' instead of 'stop' raises ContrastFormulaError."""
        yaml_text = textwrap.dedent("""\
            regressors:
              go:
                amplitude: 1
                duration: 1
                subset: null
              stop:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              bad_contrast: "go - stp"
        """)
        tmp_task_yaml("fake_task", yaml_text)
        with pytest.raises(ContrastFormulaError) as exc_info:
            _load_yaml("fake_task")
        msg = str(exc_info.value)
        assert "fake_task" in msg, f"Task name missing from error: {msg}"
        assert "bad_contrast" in msg, f"Contrast name missing from error: {msg}"
        assert "stp" in msg, f"Unknown identifier missing from error: {msg}"

    def test_error_message_names_declared_regressors(self, tmp_task_yaml):
        """Error message includes the declared regressor names for context."""
        yaml_text = textwrap.dedent("""\
            regressors:
              congruent:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              wrong: "congruent - incongruent"
        """)
        tmp_task_yaml("flanker_bad", yaml_text)
        with pytest.raises(ContrastFormulaError) as exc_info:
            _load_yaml("flanker_bad")
        msg = str(exc_info.value)
        assert "incongruent" in msg

    def test_multiple_bad_tokens_raises(self, tmp_task_yaml):
        """Multiple unknown tokens in one formula still raise ContrastFormulaError."""
        yaml_text = textwrap.dedent("""\
            regressors:
              go:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              totally_wrong: "foo + bar"
        """)
        tmp_task_yaml("multi_bad", yaml_text)
        with pytest.raises(ContrastFormulaError):
            _load_yaml("multi_bad")

    def test_caught_by_except_value_error(self, tmp_task_yaml):
        """ContrastFormulaError is catchable as ValueError (backward compat)."""
        yaml_text = textwrap.dedent("""\
            regressors:
              a:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              bad: "a - b"
        """)
        tmp_task_yaml("compat_task", yaml_text)
        caught = False
        try:
            _load_yaml("compat_task")
        except ValueError:
            caught = True
        assert caught, "ContrastFormulaError was not caught as ValueError"


class TestContrastFormulaValidationAcceptsValid:
    """_load_yaml must NOT raise for valid contrast formulas."""

    def test_simple_difference_loads(self, tmp_task_yaml):
        """A valid contrast formula (declared regressors only) loads fine."""
        yaml_text = textwrap.dedent("""\
            regressors:
              congruent:
                amplitude: 1
                duration: 1
                subset: null
              incongruent:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              incongruent_minus_congruent: "incongruent - congruent"
        """)
        tmp_task_yaml("valid_task", yaml_text)
        config = _load_yaml("valid_task")
        assert "contrasts" in config

    def test_weighted_sum_loads(self, tmp_task_yaml):
        """Formulas with numeric coefficients and parens load fine."""
        yaml_text = textwrap.dedent("""\
            regressors:
              a:
                amplitude: 1
                duration: 1
                subset: null
              b:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              mean: "0.5 * a + 0.5 * b"
        """)
        tmp_task_yaml("weighted_task", yaml_text)
        config = _load_yaml("weighted_task")
        assert config["contrasts"]["mean"] == "0.5 * a + 0.5 * b"

    def test_single_regressor_contrast_loads(self, tmp_task_yaml):
        """A contrast that is just a single regressor name (no operators) loads fine."""
        yaml_text = textwrap.dedent("""\
            regressors:
              go:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              go_only: "go"
        """)
        tmp_task_yaml("single_reg_task", yaml_text)
        config = _load_yaml("single_reg_task")
        assert "go_only" in config["contrasts"]

    def test_fractional_coefficient_loads(self, tmp_task_yaml):
        """Formulas like '1/3 * (a + b)' parse correctly (no false positive on '3')."""
        yaml_text = textwrap.dedent("""\
            regressors:
              a:
                amplitude: 1
                duration: 1
                subset: null
              b:
                amplitude: 1
                duration: 1
                subset: null
            contrasts:
              avg: "1/3 * (a + b)"
        """)
        tmp_task_yaml("frac_task", yaml_text)
        config = _load_yaml("frac_task")
        assert "avg" in config["contrasts"]


class TestPlaceholderYamlSkipsValidation:
    """Placeholder YAMLs (regressors: null) must skip contrast validation."""

    def test_null_regressors_skip_validation(self, tmp_task_yaml):
        """A YAML with regressors: null does NOT raise even if contrasts is null."""
        yaml_text = textwrap.dedent("""\
            regressors: null
            contrasts: null
        """)
        tmp_task_yaml("placeholder_task", yaml_text)
        # Should not raise
        config = _load_yaml("placeholder_task")
        assert config["regressors"] is None


class TestRealTasksAllValidate:
    """Regression: every real task YAML must load cleanly via get_task_contrasts."""

    @pytest.mark.parametrize("task_name", BASE_TASKS)
    def test_real_task_contrasts_load(self, task_name):
        """get_task_contrasts must not raise ContrastFormulaError for real tasks."""
        # This verifies the validator doesn't reject any real contrast formula
        contrasts = get_task_contrasts(task_name)
        assert isinstance(contrasts, dict)
        assert len(contrasts) > 0

    def test_all_available_non_placeholder_tasks_load(self):
        """Every task returned by list_available_tasks that has regressors must validate."""
        import neuro_workflow.analysis.task_config.loader as loader_mod
        from neuro_workflow.analysis.task_config.loader import TaskNotConfiguredError
        import yaml as _yaml

        failed = []
        for task in list_available_tasks():
            yaml_path = _TASKS_DIR / f"{task}.yaml"
            raw = _yaml.safe_load(yaml_path.read_text())
            if raw.get("regressors") is None:
                continue  # placeholder, skip
            try:
                get_task_contrasts(task)
            except ContrastFormulaError as exc:
                failed.append(f"{task}: {exc}")
            except ValueError:
                # e.g. empty contrasts — not our concern here
                pass
        assert not failed, "Real task YAMLs failed contrast validation:\n" + "\n".join(failed)
