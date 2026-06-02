import numpy as np
from neuro_workflow.analysis.mshbm.compare import (
    vertex_agreement,
    dice_per_network,
    parcel_homogeneity,
    temporal_snr,
)


def test_vertex_agreement_ignores_medial_wall():
    a = np.array([0, 1, 1, 2, 3])
    b = np.array([0, 1, 2, 2, 3])
    assert abs(vertex_agreement(a, b) - 0.75) < 1e-9


def test_dice_per_network():
    a = np.array([1, 1, 2, 2])
    b = np.array([1, 2, 2, 2])
    d = dice_per_network(a, b, n_networks=2)
    assert abs(d[0] - (2 * 1) / (2 + 1)) < 1e-9
    assert abs(d[1] - (2 * 2) / (2 + 3)) < 1e-9


def test_parcel_homogeneity_perfect_when_identical_ts():
    ts = np.zeros((6, 50))
    rng = np.random.default_rng(0)
    a = rng.standard_normal(50)
    b = rng.standard_normal(50)
    ts[:3] = a
    ts[3:] = b
    labels = np.array([1, 1, 1, 2, 2, 2])
    h = parcel_homogeneity(ts, labels)
    assert abs(h - 1.0) < 1e-6


def test_temporal_snr():
    ts = np.ones((4, 100)) * 5.0
    ts[:, ::2] += 1.0
    out = temporal_snr(ts)
    assert out.shape == (4,)
    assert np.allclose(out, 11.0, atol=0.2)
