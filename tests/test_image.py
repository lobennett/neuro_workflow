from pathlib import Path
from fmriprep_workflow.image import get_image_path, ensure_image


def test_get_image_path():
    path = get_image_path("/images", "24.1.0rc2")
    assert path == Path("/images/fmriprep_24.1.0rc2.sif")


def test_ensure_image_exists(tmp_path):
    sif = tmp_path / "fmriprep_24.1.0.sif"
    sif.touch()
    result = ensure_image(str(tmp_path), "24.1.0")
    assert result == sif


def test_ensure_image_pulls_when_missing(tmp_path, monkeypatch):
    calls = []

    def mock_run(cmd, check):
        calls.append(cmd)
        # Simulate successful pull by creating the file
        (tmp_path / "fmriprep_1.0.0.sif").touch()

    monkeypatch.setattr("subprocess.run", mock_run)
    result = ensure_image(str(tmp_path), "1.0.0")
    assert result == tmp_path / "fmriprep_1.0.0.sif"
    assert len(calls) == 1
    assert "docker://nipreps/fmriprep:1.0.0" in calls[0]


def test_ensure_image_exits_on_pull_failure(tmp_path, monkeypatch):
    import subprocess

    def mock_run(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("subprocess.run", mock_run)
    try:
        ensure_image(str(tmp_path), "1.0.0")
        assert False, "Should have raised SystemExit"
    except SystemExit:
        pass
