"""Tests for src/neuro_workflow/analysis/mshbm/run.py."""
from __future__ import annotations

import pytest


def test_get_parser_importable():
    """Smoke test: the analysis script's get_parser is importable."""
    from neuro_workflow.analysis.mshbm.run import get_parser
    parser = get_parser()
    assert parser is not None
