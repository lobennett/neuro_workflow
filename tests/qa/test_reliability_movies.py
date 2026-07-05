"""Tests for src/neuro_workflow/qa/reliability_movies.py.

Mocks subprocess.run so tests run without the brm CLI installed.
The wrapper discovers space variants and runs `brm list` once per space.
"""

import csv
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from neuro_workflow.qa.reliability_movies import (
    render_reliability_movies,
)


def _ok_proc() -> CompletedProcess:
    return CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _make_fixture(deriv: Path, subject: str = "sub-s03") -> None:
    """fmriprep tree with native, T1w, and 2 MNI variants."""
    for ses in ("ses-01", "ses-02"):
        func = deriv / subject / ses / "func"
        func.mkdir(parents=True, exist_ok=True)
        base = f"{subject}_{ses}_task-rest_run-1"
        (func / f"{base}_desc-preproc_bold.nii.gz").touch()
        (func / f"{base}_space-T1w_desc-preproc_bold.nii.gz").touch()
        (func / f"{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz").touch()
        (func / f"{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz").touch()


def _fake_run_factory(out: Path):
    """subprocess.run side-effect: write the expected mp4 from manifest group."""
    captured: list[dict] = []

    def fake_run(cmd, **kwargs):
        manifest_path = Path(cmd[2])
        with manifest_path.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        captured.append({"cmd": cmd, "rows": rows})
        out.mkdir(parents=True, exist_ok=True)
        # brm names output as <group>.mp4; group is in row[0]['group']
        (out / f"{rows[0]['group']}.mp4").write_bytes(b"\x00")
        return _ok_proc()

    return fake_run, captured


def test_renders_one_movie_per_space(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv)

    fake_run, captured = _fake_run_factory(out)
    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-s03"])

    # Default: skip native — so 3 spaces (T1w + 2 MNI variants)
    assert "sub-s03" in result
    movies = result["sub-s03"]
    assert len(movies) == 3
    labels = sorted(m.space_label for m in movies)
    assert labels == [
        "MNI152NLin2009cAsym (res-1)",
        "MNI152NLin6Asym (res-2)",
        "T1w",
    ]
    for m in movies:
        assert m.path is not None and m.path.is_file()
        assert m.error is None


def test_include_native_option(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv)

    fake_run, _ = _fake_run_factory(out)
    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-s03"], include_native=True)

    movies = result["sub-s03"]
    assert len(movies) == 4
    assert any(m.space_label == "native" for m in movies)


def test_each_manifest_contains_only_its_space(tmp_path):
    """A T1w manifest must not contain MNI paths and vice versa."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv)

    fake_run, captured = _fake_run_factory(out)
    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        render_reliability_movies(deriv, out, ["sub-s03"])

    for call in captured:
        group = call["rows"][0]["group"]
        # All rows in a single brm call must share the same group
        assert all(r["group"] == group for r in call["rows"])
        # Path token must match the space the group claims
        if "space-T1w" in group:
            for r in call["rows"]:
                assert "_space-T1w_" in r["path"]
                assert "_space-MNI" not in r["path"]
        elif "space-MNI152NLin2009cAsym" in group:
            for r in call["rows"]:
                assert "_space-MNI152NLin2009cAsym_" in r["path"]
        elif "space-MNI152NLin6Asym" in group:
            for r in call["rows"]:
                assert "_space-MNI152NLin6Asym_" in r["path"]


def test_brm_failure_is_per_space(tmp_path):
    """If brm fails for one space, others still attempt and other subjects unaffected."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv)

    def fake_run(cmd, **kwargs):
        manifest = Path(cmd[2])
        with manifest.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        group = rows[0]["group"]
        if "MNI152NLin6Asym" in group:
            return CompletedProcess(args=cmd, returncode=1, stdout="", stderr="ffmpeg crashed")
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{group}.mp4").write_bytes(b"\x00")
        return _ok_proc()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-s03"])

    movies = result["sub-s03"]
    by_label = {m.space_label: m for m in movies}
    assert by_label["T1w"].path is not None
    assert by_label["MNI152NLin2009cAsym (res-1)"].path is not None
    assert by_label["MNI152NLin6Asym (res-2)"].path is None
    assert "ffmpeg crashed" in by_label["MNI152NLin6Asym (res-2)"].error


def test_subject_with_no_preproc_returns_error_marker(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    (deriv / "sub-X").mkdir(parents=True)  # empty subject dir

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run") as mock_run:
        result = render_reliability_movies(deriv, out, ["sub-X"])

    assert len(result["sub-X"]) == 1
    assert result["sub-X"][0].path is None
    assert "no preproc" in result["sub-X"][0].error.lower()
    mock_run.assert_not_called()


def test_brm_not_found(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv, "sub-A")

    with patch(
        "neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=FileNotFoundError
    ):
        result = render_reliability_movies(deriv, out, ["sub-A"])

    movies = result["sub-A"]
    assert all(m.path is None for m in movies)
    assert all("not found" in m.error.lower() for m in movies)


def test_silent_no_output(tmp_path):
    """brm exit 0 but no mp4 written → flagged as error."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv, "sub-A")

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", return_value=_ok_proc()):
        result = render_reliability_movies(deriv, out, ["sub-A"])

    movies = result["sub-A"]
    assert all(m.path is None for m in movies)
    assert all("no output" in m.error.lower() for m in movies)
