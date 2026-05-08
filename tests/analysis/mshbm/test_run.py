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
