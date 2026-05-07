"""Tests for src/neuro_workflow/exclusions/lev1_outlier.py."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_lev1_outlier_generator_importable():
    """The generator module imports and exposes Lev1OutlierGenerator."""
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    assert Lev1OutlierGenerator.name == "lev1_outlier"
