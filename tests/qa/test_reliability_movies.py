"""Tests for src/neuro_workflow/qa/reliability_movies.py.

Mocks the bold_reliability_movies API so tests run without ffmpeg.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from neuro_workflow.qa.reliability_movies import MovieResult, render_reliability_movies


def test_render_reliability_movies_success(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    # Mock FmriprepFrameSource and make_videos
    fake_group = MagicMock()
    fake_group.name = "sub-s03"
    fake_summary = MagicMock()
    fake_summary.path = out / "sub-s03.mp4"
    fake_summary.error = None

    with patch("neuro_workflow.qa.reliability_movies.FmriprepFrameSource") as FS, \
         patch("neuro_workflow.qa.reliability_movies.make_videos") as MV, \
         patch("neuro_workflow.qa.reliability_movies.get_renderer") as GR:
        FS.return_value.discover.return_value = [fake_group]
        MV.return_value = [fake_summary]
        GR.return_value = MagicMock()

        result = render_reliability_movies(deriv, out, ["sub-s03"])

    assert "sub-s03" in result
    assert result["sub-s03"].path == out / "sub-s03.mp4"
    assert result["sub-s03"].error is None


def test_render_reliability_movies_filters_subjects(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    fake_a = MagicMock(); fake_a.name = "sub-A"
    fake_b = MagicMock(); fake_b.name = "sub-B"

    with patch("neuro_workflow.qa.reliability_movies.FmriprepFrameSource") as FS, \
         patch("neuro_workflow.qa.reliability_movies.make_videos") as MV, \
         patch("neuro_workflow.qa.reliability_movies.get_renderer") as GR:
        FS.return_value.discover.return_value = [fake_a, fake_b]
        MV.return_value = []
        GR.return_value = MagicMock()

        render_reliability_movies(deriv, out, ["sub-A"])

        # make_videos should be called with only the requested subject
        groups_passed = MV.call_args.kwargs["groups"]
        assert len(groups_passed) == 1
        assert groups_passed[0].name == "sub-A"


def test_render_reliability_movies_handles_per_subject_failure(tmp_path):
    """If make_videos raises for a subject, return error result instead of bubbling up."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    fake_group = MagicMock(); fake_group.name = "sub-bad"

    with patch("neuro_workflow.qa.reliability_movies.FmriprepFrameSource") as FS, \
         patch("neuro_workflow.qa.reliability_movies.make_videos") as MV, \
         patch("neuro_workflow.qa.reliability_movies.get_renderer") as GR:
        FS.return_value.discover.return_value = [fake_group]
        MV.side_effect = RuntimeError("ffmpeg crashed")
        GR.return_value = MagicMock()

        result = render_reliability_movies(deriv, out, ["sub-bad"])

    assert "sub-bad" in result
    assert result["sub-bad"].path is None
    assert "ffmpeg crashed" in result["sub-bad"].error
