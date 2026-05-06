"""Tests for src/neuro_workflow/qa/reliability_movies.py.

Mocks subprocess.run so tests run without the brm CLI installed.
The wrapper pre-filters to native-space preproc and invokes `brm list`.
"""
import csv
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from neuro_workflow.qa.reliability_movies import MovieResult, render_reliability_movies


def _ok_proc() -> CompletedProcess:
    return CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _make_fixture(deriv: Path, subject: str = "sub-s03") -> None:
    """Create a fmriprep-shaped tree with native + space-MNI preproc BOLDs."""
    for ses in ("ses-01", "ses-02"):
        func = deriv / subject / ses / "func"
        func.mkdir(parents=True, exist_ok=True)
        base = f"{subject}_{ses}_task-rest_run-1"
        # native preproc — should be picked
        (func / f"{base}_desc-preproc_bold.nii.gz").touch()
        # MNI space variants — must NOT be picked (would break shape check)
        (func / f"{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz").touch()
        (func / f"{base}_space-T1w_desc-preproc_bold.nii.gz").touch()


def test_render_reliability_movies_success(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv)

    def fake_run(cmd, **kwargs):
        out.mkdir(parents=True, exist_ok=True)
        (out / "sub-s03.mp4").write_bytes(b"\x00")
        return _ok_proc()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-s03"])

    assert result["sub-s03"].path == out / "sub-s03.mp4"
    assert result["sub-s03"].error is None


def test_render_reliability_movies_writes_native_only_manifest(tmp_path):
    """Manifest must contain only native-space (no _space-) BOLDs."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv)

    captured_manifests: list[list[dict]] = []

    def fake_run(cmd, **kwargs):
        # cmd: ["brm", "list", <manifest_path>, "--out", ...]
        manifest_path = Path(cmd[2])
        with manifest_path.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        captured_manifests.append(rows)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sub-s03.mp4").write_bytes(b"\x00")
        return _ok_proc()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        render_reliability_movies(deriv, out, ["sub-s03"])

    assert len(captured_manifests) == 1
    rows = captured_manifests[0]
    # 2 sessions × 1 native preproc each = 2 rows; no space-* paths
    assert len(rows) == 2
    for row in rows:
        assert "_space-" not in row["path"]
        assert row["group"] == "sub-s03"


def test_render_reliability_movies_filters_subjects(tmp_path):
    """Each subject gets its own brm invocation with its own manifest."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv, "sub-A")
    _make_fixture(deriv, "sub-B")

    captured_subjects: list[str] = []

    def fake_run(cmd, **kwargs):
        with Path(cmd[2]).open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        # All rows in a manifest belong to the same group (subject)
        captured_subjects.append(rows[0]["group"])
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{rows[0]['group']}.mp4").write_bytes(b"\x00")
        return _ok_proc()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", side_effect=fake_run):
        result = render_reliability_movies(deriv, out, ["sub-A", "sub-B"])

    assert sorted(captured_subjects) == ["sub-A", "sub-B"]
    assert result["sub-A"].path is not None
    assert result["sub-B"].path is not None


def test_render_reliability_movies_handles_per_subject_failure(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv, "sub-bad")

    fail_proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="ffmpeg crashed")

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", return_value=fail_proc):
        result = render_reliability_movies(deriv, out, ["sub-bad"])

    assert result["sub-bad"].path is None
    assert "ffmpeg crashed" in result["sub-bad"].error


def test_render_reliability_movies_handles_brm_not_found(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv, "sub-A")

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run",
               side_effect=FileNotFoundError):
        result = render_reliability_movies(deriv, out, ["sub-A"])

    assert result["sub-A"].path is None
    assert "not found" in result["sub-A"].error.lower()


def test_render_reliability_movies_silent_no_output(tmp_path):
    """brm exit 0 but no output file → flagged as error."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    _make_fixture(deriv, "sub-A")

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run", return_value=_ok_proc()):
        result = render_reliability_movies(deriv, out, ["sub-A"])

    assert result["sub-A"].path is None
    assert "no output" in result["sub-A"].error.lower()


def test_render_reliability_movies_no_native_preproc(tmp_path):
    """If a subject has no native preproc BOLDs, return error without invoking brm."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    # subject dir exists but has only space-* variants
    func = deriv / "sub-X" / "ses-01" / "func"
    func.mkdir(parents=True)
    (func / "sub-X_ses-01_task-rest_run-1_space-T1w_desc-preproc_bold.nii.gz").touch()

    with patch("neuro_workflow.qa.reliability_movies.subprocess.run") as mock_run:
        result = render_reliability_movies(deriv, out, ["sub-X"])

    assert result["sub-X"].path is None
    assert "no native" in result["sub-X"].error.lower()
    mock_run.assert_not_called()
