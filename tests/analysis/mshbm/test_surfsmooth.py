"""Tests for src/neuro_workflow/analysis/mshbm/surfsmooth.py."""
from __future__ import annotations

import numpy as np

from neuro_workflow.analysis.mshbm.surfsmooth import (
    array_to_func_gii,
    func_gii_to_array,
)


def test_func_gii_roundtrip(tmp_path):
    arr = np.random.default_rng(0).standard_normal((40962, 7)).astype(np.float32)
    p = tmp_path / "x.func.gii"
    array_to_func_gii(arr, p)
    back = func_gii_to_array(p)
    assert back.shape == (40962, 7)
    np.testing.assert_allclose(back, arr, rtol=1e-5)
