"""Tests for src/neuro_workflow/analysis/mshbm/run.py."""
from __future__ import annotations

import pytest


def test_get_parser_importable():
    """Smoke test: the analysis script's get_parser is importable."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    assert parser is not None


def test_parser_accepts_rest_only_flag():
    """`--rest-only` flag is registered and parses to True when present."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        "--subj-id", "s03",
        "--fmriprep-dir", "/tmp",
        "--rest-only",
    ])
    assert args.rest_only is True
    assert args.glm_dir is None


def test_parser_glm_dir_now_optional():
    """`--glm-dir` is no longer required at argparse level."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        "--subj-id", "s03",
        "--fmriprep-dir", "/tmp",
        "--rest-only",
    ])
    assert args.glm_dir is None


def test_parser_glm_dir_still_accepted():
    """Backwards-compat: `--glm-dir` still parses when supplied."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    args = parser.parse_args([
        "--subj-id", "s03",
        "--glm-dir", "/oak/lev1",
        "--fmriprep-dir", "/tmp",
    ])
    assert args.glm_dir == "/oak/lev1"
    assert args.rest_only is False


def test_main_errors_when_neither_rest_only_nor_glm_dir(monkeypatch, capsys):
    """`main()` exits with a clear error when neither --rest-only nor --glm-dir is set."""
    from neuro_workflow.analysis.mshbm import run as mshbm_run

    monkeypatch.setattr(
        "sys.argv",
        ["mshbm.run", "--subj-id", "s03", "--fmriprep-dir", "/tmp"],
    )
    with pytest.raises(SystemExit) as exc_info:
        mshbm_run.main()
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "rest-only" in (captured.err + captured.out).lower()


def test_main_errors_when_both_rest_only_and_glm_dir(monkeypatch, capsys):
    """`main()` exits with a clear error when both --rest-only and --glm-dir are set."""
    from neuro_workflow.analysis.mshbm import run as mshbm_run

    monkeypatch.setattr(
        "sys.argv",
        [
            "mshbm.run", "--subj-id", "s03",
            "--fmriprep-dir", "/tmp",
            "--glm-dir", "/oak/lev1",
            "--rest-only",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        mshbm_run.main()
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "rest-only" in (captured.err + captured.out).lower()
    assert "glm-dir" in (captured.err + captured.out).lower()


def test_process_subject_rest_only_skips_task_residual_discovery(
    tmp_path, monkeypatch,
):
    """When rest_only=True, task-residual discovery + processing are skipped.

    Mock the four task-residual functions to track calls; assert they're not
    invoked. Mock the rest-discovery + ensure_fsaverage6 paths to no-op so
    process_subject runs cleanly.
    """
    from neuro_workflow.analysis.mshbm import run as mshbm_run

    # FreeSurfer subjects dir must exist for process_subject to proceed
    fmriprep_dir = tmp_path / "fmriprep"
    (fmriprep_dir / "sourcedata" / "freesurfer").mkdir(parents=True)
    output_dir = tmp_path / "out"

    task_residual_calls: list[str] = []
    monkeypatch.setattr(
        mshbm_run, "discover_task_residuals_volume",
        lambda *a, **k: task_residual_calls.append("vol") or [],
    )
    monkeypatch.setattr(
        mshbm_run, "discover_task_residuals_surface",
        lambda *a, **k: task_residual_calls.append("surf") or [],
    )
    monkeypatch.setattr(
        mshbm_run, "process_volume_residuals",
        lambda *a, **k: task_residual_calls.append("proc_vol") or 0,
    )
    monkeypatch.setattr(
        mshbm_run, "process_surface_residuals",
        lambda *a, **k: task_residual_calls.append("proc_surf") or 0,
    )

    # Stub rest paths to no-op so the function returns cleanly.
    monkeypatch.setattr(mshbm_run, "ensure_fsaverage6", lambda *a, **k: None)
    monkeypatch.setattr(mshbm_run, "resolve_fs_subject", lambda d, s: s)
    monkeypatch.setattr(mshbm_run, "discover_rest_bold_fsaverage6", lambda *a, **k: [])
    monkeypatch.setattr(mshbm_run, "discover_rest_bold_surface", lambda *a, **k: [])
    monkeypatch.setattr(mshbm_run, "discover_rest_bold_volume", lambda *a, **k: [])

    errors = mshbm_run.process_subject(
        subject="sub-s03",
        glm_dir=None,
        fmriprep_dir=fmriprep_dir,
        output_dir=output_dir,
        residuals_space="surface",
        rest_fmriprep_dir=None,
        sessions=None,
        rest_only=True,
    )

    assert errors == 0
    assert task_residual_calls == [], (
        f"task-residual functions called when rest_only=True: {task_residual_calls}"
    )


def test_resolve_fs_subject_handles_session_suffixed_dirs(tmp_path):
    from neuro_workflow.analysis.mshbm.run import resolve_fs_subject
    subjects_dir = tmp_path
    # fmriprep longitudinal naming: actual dir is sub-s03_ses-13
    fs_dir = subjects_dir / "sub-s03_ses-13"
    (fs_dir / "surf").mkdir(parents=True)
    (fs_dir / "surf" / "lh.sphere.reg.gii").touch()
    (fs_dir / "surf" / "rh.sphere.reg.gii").touch()

    result = resolve_fs_subject(subjects_dir, "sub-s03")
    assert result == "sub-s03_ses-13"


def test_resolve_fs_subject_handles_bare_subject_dir(tmp_path):
    from neuro_workflow.analysis.mshbm.run import resolve_fs_subject
    subjects_dir = tmp_path
    # cross-session: actual dir is sub-s03
    fs_dir = subjects_dir / "sub-s03"
    (fs_dir / "surf").mkdir(parents=True)
    (fs_dir / "surf" / "lh.sphere.reg.gii").touch()

    result = resolve_fs_subject(subjects_dir, "sub-s03")
    assert result == "sub-s03"


def test_resolve_fs_subject_raises_when_missing(tmp_path):
    from neuro_workflow.analysis.mshbm.run import resolve_fs_subject
    with __import__("pytest").raises(FileNotFoundError):
        resolve_fs_subject(tmp_path, "sub-s03")
