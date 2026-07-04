from neuro_workflow.pipelines.base import (
    TEMPLATE_DIR,
    Pipeline,
    build_mail_line,
    get_pipeline,
    list_pipelines,
    resolve_resources,
)


def test_template_dir_exists():
    assert TEMPLATE_DIR.is_dir()


def test_pipeline_protocol_has_required_attributes():
    """Verify the protocol defines the expected interface."""

    annotations = Pipeline.__protocol_attrs__
    assert "name" in annotations
    assert "docker_uri" in annotations
    assert "template_name" in annotations
    assert "default_resources" in annotations
    assert "add_cli_args" in annotations
    assert "build_context" in annotations


def test_get_pipeline_returns_none_for_unknown():
    result = get_pipeline("nonexistent_pipeline_xyz")
    assert result is None


def test_list_pipelines_returns_dict():
    result = list_pipelines()
    assert isinstance(result, dict)


def test_build_mail_line_with_user():
    result = build_mail_line({"mail_user": "user@stanford.edu"})
    assert "#SBATCH --mail-user=user@stanford.edu" in result
    assert "#SBATCH --mail-type=ALL" in result


def test_build_mail_line_without_user():
    assert build_mail_line({"mail_user": None}) == ""
    assert build_mail_line({}) == ""


def test_resolve_resources_defaults():
    from argparse import Namespace

    defaults = {"nthreads": 8, "mem_gb": 64, "time": "2-00:00:00"}
    args = Namespace(nthreads=None, mem_gb=None, time=None)
    result = resolve_resources(args, defaults)
    assert result == {"nthreads": 8, "mem_gb": 64, "time": "2-00:00:00"}


def test_resolve_resources_overrides():
    from argparse import Namespace

    defaults = {"nthreads": 8, "mem_gb": 64, "time": "2-00:00:00"}
    args = Namespace(nthreads=4, mem_gb=32, time="1-00:00:00")
    result = resolve_resources(args, defaults)
    assert result == {"nthreads": 4, "mem_gb": 32, "time": "1-00:00:00"}


def test_resolve_resources_partial_override():
    from argparse import Namespace

    defaults = {"nthreads": 8, "mem_per_cpu_gb": 8, "time": "5-00:00:00"}
    args = Namespace(nthreads=4, mem_per_cpu_gb=None, time=None)
    result = resolve_resources(args, defaults)
    assert result == {"nthreads": 4, "mem_per_cpu_gb": 8, "time": "5-00:00:00"}
