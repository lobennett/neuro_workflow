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
