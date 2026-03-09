from neuro_workflow.pipelines.base import Pipeline, TEMPLATE_DIR, get_pipeline, list_pipelines


def test_template_dir_exists():
    assert TEMPLATE_DIR.is_dir()


def test_pipeline_protocol_has_required_attributes():
    """Verify the protocol defines the expected interface."""
    import inspect
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
