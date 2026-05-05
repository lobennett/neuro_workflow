"""Tests for src/neuro_workflow/qa/reliability_movies.py.

Mocks subprocess.run so tests run without the brm CLI installed.
"""
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from neuro_workflow.qa.reliability_movies import MovieResult, render_reliability_movies


def _ok_proc() -> CompletedProcess:
    return CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def test_render_reliability_movies_success(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    def fake_run(cmd, **kwargs):
        # Simulate brm writing the expected output
        out.mkdir(parents=True, exist_ok=True)
        (out / "sub-s03.mp4").write_bytes(b"\x00")
        return _ok_proc()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-s03"])

    assert "sub-s03" in result
    assert result["sub-s03"].path == out / "sub-s03.mp4"
    assert result["sub-s03"].error is None


def test_render_reliability_movies_filters_subjects(tmp_path):
    """Each subject is rendered with its own brm invocation + sub= filter."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        out.mkdir(parents=True, exist_ok=True)
        # write the expected file based on the --filter sub= argument
        i = cmd.index("--filter")
        sub_id = cmd[i + 1].split("=", 1)[1]
        (out / f"sub-{sub_id}.mp4").write_bytes(b"\x00")
        return _ok_proc()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-A", "sub-B"])

    assert {"sub-A", "sub-B"} == set(result)
    assert len(captured_cmds) == 2
    # filter values strip the sub- prefix
    filters = sorted(c[c.index("--filter") + 1] for c in captured_cmds)
    assert filters == ["sub=A", "sub=B"]


def test_render_reliability_movies_handles_per_subject_failure(tmp_path):
    """Non-zero exit → MovieResult with error, no exception bubbles up."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    fail_proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="ffmpeg crashed")

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", return_value=fail_proc):
        result = render_reliability_movies(deriv, out, ["sub-bad"])

    assert "sub-bad" in result
    assert result["sub-bad"].path is None
    assert "ffmpeg crashed" in result["sub-bad"].error


def test_render_reliability_movies_handles_brm_not_found(tmp_path):
    """If brm is not on PATH, FileNotFoundError → MovieResult with error."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run",
               side_effect=FileNotFoundError):
        result = render_reliability_movies(deriv, out, ["sub-A"])

    assert result["sub-A"].path is None
    assert "not found" in result["sub-A"].error.lower()


def test_render_reliability_movies_silent_no_output(tmp_path):
    """brm exit 0 but no output file → flagged as error, not silent success."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    # subprocess.run returns 0 but doesn't create any file
    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", return_value=_ok_proc()):
        result = render_reliability_movies(deriv, out, ["sub-A"])

    assert result["sub-A"].path is None
    assert "no output" in result["sub-A"].error.lower()
