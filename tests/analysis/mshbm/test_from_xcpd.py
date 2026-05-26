"""Tests for the XCP-D → MSHBM prep helpers."""
from __future__ import annotations


def test_module_imports():
    """Smoke import — verifies the package layout is sane."""
    from neuro_workflow.analysis.mshbm import from_xcpd  # noqa: F401
