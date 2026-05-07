"""Inline guard: rank-deficient design matrix + pathological VIF."""
from __future__ import annotations

import pytest

try:
    import nilearn  # noqa: F401
except ImportError:
    pytest.skip(
        "neuroimaging dependencies not installed (install with: uv pip install -e '.[lev1]')",
        allow_module_level=True,
    )

import numpy as np
import pandas as pd

from neuro_workflow.analysis.lev1.processing.glm import (
    PathologicalVIFError,
    RankDeficientDesignError,
    check_design_matrix_health,
)


def test_rank_deficient_design_matrix_raises():
    # Two perfectly correlated columns -> rank deficient
    n = 100
    rng = np.random.default_rng(0)
    a = rng.normal(size=n)
    dm = pd.DataFrame({
        "go": a,
        "go_dup": a,                 # perfect duplicate of "go"
        "constant": np.ones(n),
    })
    with pytest.raises(RankDeficientDesignError, match="rank"):
        check_design_matrix_health(dm)


def test_clean_design_matrix_passes():
    n = 100
    rng = np.random.default_rng(1)
    dm = pd.DataFrame({
        "go": rng.normal(size=n),
        "stop": rng.normal(size=n),
        "constant": np.ones(n),
    })
    # Should not raise
    check_design_matrix_health(dm)


def test_pathological_vif_raises():
    # Construct a near-degenerate pair: x1 ~ x2, but with tiny noise -> VIF >> 100
    n = 1000
    rng = np.random.default_rng(2)
    x1 = rng.normal(size=n)
    x2 = x1 + rng.normal(scale=0.001, size=n)
    dm = pd.DataFrame({"x1": x1, "x2": x2, "constant": np.ones(n)})
    with pytest.raises(PathologicalVIFError, match="VIF"):
        check_design_matrix_health(dm)
