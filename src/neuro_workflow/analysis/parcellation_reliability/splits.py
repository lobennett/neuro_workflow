"""Generate random session splits for split-half MSHBM reliability.

Standard practice in PFM split-half reliability (Kong et al. 2019; Gordon
et al. 2017 Midnight Scan Club; Buckner-lab analyses): partition each
subject's sessions into two halves, retrain individual MSHBM parcellation
on each half, and score the two parcellations against each other.  To
stabilise the estimate, multiple random partitions are used and Dice is
averaged across them.

This module produces the partitions.  The actual MSHBM training and Dice
computation live in sister modules.

Default: 20 random splits with seed 0.  Determinism is critical so that
the partition labels written for one subject match across reruns and
across the prep-mshbm + MSHBM operational pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SubjectSplit:
    """Half-A and half-B session ids for a single subject and seed."""

    subject: str
    iteration: int
    half_a: tuple[str, ...]
    half_b: tuple[str, ...]


def random_split(sessions: list[str], seed: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Single random half-split of a subject's session list.

    Sessions are drawn without replacement: half_a + half_b is a
    permutation of the input.  If the count is odd, half_a gets the
    extra session so that no session is dropped.

    Args:
        sessions: list of session ids (sorted is irrelevant; the rng
            shuffles them).
        seed: deterministic seed for ``np.random.default_rng``.

    Returns:
        ``(half_a, half_b)`` tuples of session ids.
    """
    if len(sessions) < 2:
        raise ValueError(
            f'Cannot split-half: need at least 2 sessions, got {len(sessions)}'
        )
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(sessions).tolist()
    mid = (len(shuffled) + 1) // 2  # half_a gets the extra when odd
    return tuple(shuffled[:mid]), tuple(shuffled[mid:])


def generate_splits(
    sessions_per_subject: dict[str, list[str]],
    n_iterations: int = 20,
    base_seed: int = 0,
) -> list[SubjectSplit]:
    """Generate ``n_iterations`` random splits per subject.

    Each ``(subject, iteration)`` pair gets a unique deterministic seed so
    the partition is reproducible across operational reruns:

        seed = base_seed * 10_000_000 + hash(subject) % 10_000_000 * n_iterations + iteration

    The hash is computed via Python's hash() over the subject id at
    function-call time.  Because Python's per-process hash randomisation
    can perturb hash(str) across processes, we instead use the
    deterministic ``zlib.adler32`` so the seed survives process
    boundaries (e.g. SLURM array jobs across nodes).

    Args:
        sessions_per_subject: mapping ``sub-X`` → list of session ids.
        n_iterations: number of random splits per subject (default 20,
            matching mid-end of the 10–1000 range reported in the
            literature; balance between split-noise stability and
            compute cost).
        base_seed: top-level seed for the deterministic mixer.

    Returns:
        Flat list of ``SubjectSplit`` entries, one per
        ``(subject, iteration)`` cell.
    """
    if n_iterations < 1:
        raise ValueError(f'n_iterations must be >= 1; got {n_iterations}')

    import zlib

    out: list[SubjectSplit] = []
    for subject, sessions in sessions_per_subject.items():
        subj_mix = zlib.adler32(subject.encode('utf-8')) % 10_000_000
        for i in range(n_iterations):
            seed = base_seed * 10_000_000 + subj_mix * n_iterations + i
            half_a, half_b = random_split(sessions, seed=seed)
            out.append(SubjectSplit(
                subject=subject, iteration=i, half_a=half_a, half_b=half_b,
            ))
    return out
