"""Per-network and aggregate Dice for split-half MSHBM parcellation reliability.

Field-standard primary metric (Kong et al. 2019; Gordon et al. 2017;
Buckner-lab PFM papers): compute Dice coefficient per network between
the two split-half parcellations, then report the mean across networks
as the subject's reliability summary.  Optional secondary metric is the
per-vertex label-agreement rate ("fraction of vertices that received the
same network label in both halves").

For two label vectors `a` and `b` over the same vertex set, with K
networks, per-network Dice is

    Dice_k = 2 * |a == k ∧ b == k| / (|a == k| + |b == k|)

Range: 0 (no overlap) to 1 (perfect overlap).  Undefined when both
|a==k| and |b==k| are zero; we return NaN in that case so the caller can
distinguish "the network has no vertices in this subject's parcellation"
from "the network overlaps poorly".

Inputs are 1-D integer arrays per hemisphere.  The MSHBM dlabel
convention assigns label 0 to medial wall / unassigned vertices; by
default we exclude label 0 from the Dice computation so the report
matches what Buckner-lab tables show (Dice over the K cortical networks).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DiceSummary:
    """Per-network Dice plus aggregate summaries for one subject and split.

    Attributes:
        per_network: 1-D array of length K with Dice for each network
            (NaN if either half had zero vertices in that network).
        mean_dice: mean Dice across all networks present in BOTH halves.
        vertex_agreement: fraction of vertices with identical labels
            (excluding the medial wall / label 0 if requested).
        k_networks: number of networks present in the union of both
            halves (informational).
    """

    per_network: np.ndarray
    mean_dice: float
    vertex_agreement: float
    k_networks: int


def dice_per_network(
    labels_a: np.ndarray,
    labels_b: np.ndarray,
    n_networks: int | None = None,
    ignore_label: int = 0,
) -> np.ndarray:
    """Compute per-network Dice between two label vectors.

    Args:
        labels_a: 1-D int array of vertex labels (split-half A).
        labels_b: same length as ``labels_a``; split-half B.
        n_networks: if provided, force the output length to ``n_networks``
            (networks not in the data get NaN).  When None, returned
            length is ``max(labels_a, labels_b)`` excluding ignore_label.
        ignore_label: network label to skip (default 0 → medial wall).

    Returns:
        1-D array of Dice coefficients per non-ignored network in
        ascending label order.  NaN where the network is absent from
        both halves.
    """
    if labels_a.shape != labels_b.shape or labels_a.ndim != 1:
        raise ValueError(
            f'labels_a and labels_b must be 1-D and the same length; '
            f'got shapes {labels_a.shape} and {labels_b.shape}'
        )

    if n_networks is None:
        max_label = int(max(labels_a.max(), labels_b.max(), 0))
        labels = [k for k in range(1, max_label + 1) if k != ignore_label]
    else:
        labels = [k for k in range(1, n_networks + 1) if k != ignore_label]

    out = np.full(len(labels), np.nan, dtype=np.float64)
    for idx, k in enumerate(labels):
        a_k = labels_a == k
        b_k = labels_b == k
        size_sum = int(a_k.sum() + b_k.sum())
        if size_sum == 0:
            out[idx] = np.nan
        else:
            inter = int((a_k & b_k).sum())
            out[idx] = 2.0 * inter / size_sum
    return out


def vertex_label_agreement(
    labels_a: np.ndarray,
    labels_b: np.ndarray,
    ignore_label: int = 0,
) -> float:
    """Fraction of vertices with identical labels across split-halves.

    Vertices that have ``ignore_label`` in EITHER half are excluded from
    both the numerator and the denominator — they don't contribute to
    or detract from the agreement score.
    """
    if labels_a.shape != labels_b.shape:
        raise ValueError('labels_a and labels_b must have identical shape')
    keep = (labels_a != ignore_label) & (labels_b != ignore_label)
    if not keep.any():
        return float('nan')
    return float((labels_a[keep] == labels_b[keep]).mean())


def summarise_dice(
    labels_a: np.ndarray,
    labels_b: np.ndarray,
    n_networks: int | None = None,
    ignore_label: int = 0,
) -> DiceSummary:
    """Compute per-network Dice + mean + vertex agreement in one pass."""
    per_net = dice_per_network(
        labels_a, labels_b, n_networks=n_networks, ignore_label=ignore_label,
    )
    valid = per_net[~np.isnan(per_net)]
    mean = float(valid.mean()) if valid.size > 0 else float('nan')
    agree = vertex_label_agreement(labels_a, labels_b, ignore_label=ignore_label)
    k_present = int(
        len(set(labels_a.tolist()) | set(labels_b.tolist()))
        - (1 if (ignore_label in labels_a or ignore_label in labels_b) else 0)
    )
    return DiceSummary(
        per_network=per_net,
        mean_dice=mean,
        vertex_agreement=agree,
        k_networks=max(k_present, 0),
    )
