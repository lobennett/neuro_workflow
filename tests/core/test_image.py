from pathlib import Path

from neuro_workflow.core.image import ensure_image, get_image_path


def test_get_image_path():
    path = get_image_path("/images", "fmriprep", "24.1.0rc2")
    assert path == Path("/images/fmriprep_24.1.0rc2.sif")


def test_get_image_path_different_pipeline():
    path = get_image_path("/images", "mriqc", "24.1.0")
    assert path == Path("/images/mriqc_24.1.0.sif")


def test_ensure_image_exists(tmp_path):
    sif = tmp_path / "fmriprep_24.1.0.sif"
    sif.touch()
    result = ensure_image(str(tmp_path), "fmriprep", "24.1.0", "docker://nipreps/fmriprep")
    assert result == sif


def test_ensure_image_pulls_when_missing(tmp_path, monkeypatch):
    calls = []

    def mock_run(cmd, check):
        calls.append(cmd)
        (tmp_path / "mriqc_1.0.0.sif").touch()

    monkeypatch.setattr("subprocess.run", mock_run)
    result = ensure_image(str(tmp_path), "mriqc", "1.0.0", "docker://nipreps/mriqc")
    assert result == tmp_path / "mriqc_1.0.0.sif"
    assert len(calls) == 1
    assert "docker://nipreps/mriqc:1.0.0" in calls[0]


def test_ensure_image_exits_on_pull_failure(tmp_path, monkeypatch):
    import subprocess

    def mock_run(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("subprocess.run", mock_run)
    try:
        ensure_image(str(tmp_path), "fmriprep", "1.0.0", "docker://nipreps/fmriprep")
        raise AssertionError("Should have raised SystemExit")
    except SystemExit:
        pass
