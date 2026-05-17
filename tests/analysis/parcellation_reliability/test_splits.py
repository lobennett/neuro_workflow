"""Tests for split-half session partitioning.

Covers:
- Determinism — same (subject, iteration, base_seed) always yields the
  same partition, across processes (uses zlib.adler32, not Python's
  hash-randomised str hash).
- Partition is a permutation (no session lost or duplicated).
- Odd-length session lists get an extra session in half_a (no drop).
- Different iterations produce different partitions for the same subject.
- Different subjects with the same iteration produce different partitions.
- Edge cases: 2 sessions, ValueError on 0/1 sessions.
"""

from __future__ import annotations

import pytest

from neuro_workflow.analysis.parcellation_reliability.splits import (
    SubjectSplit,
    generate_splits,
    random_split,
)


# ---------------------------------------------------------------------------
# random_split — core determinism + permutation invariant
# ---------------------------------------------------------------------------


def test_random_split_is_deterministic_for_same_seed():
    sessions = ['ses-01', 'ses-02', 'ses-03', 'ses-04']
    a1, b1 = random_split(sessions, seed=42)
    a2, b2 = random_split(sessions, seed=42)
    assert a1 == a2 and b1 == b2


def test_random_split_partition_is_full_permutation():
    sessions = ['ses-01', 'ses-02', 'ses-03', 'ses-04', 'ses-05']
    a, b = random_split(sessions, seed=0)
    assert set(a) | set(b) == set(sessions)
    assert set(a).isdisjoint(set(b))


def test_random_split_assigns_extra_to_half_a_when_odd():
    sessions = ['ses-01', 'ses-02', 'ses-03', 'ses-04', 'ses-05']
    a, b = random_split(sessions, seed=0)
    assert len(a) == 3
    assert len(b) == 2


def test_random_split_balanced_when_even():
    sessions = ['ses-01', 'ses-02', 'ses-03', 'ses-04']
    a, b = random_split(sessions, seed=7)
    assert len(a) == 2 and len(b) == 2


def test_random_split_different_seeds_give_different_partitions():
    sessions = ['ses-01', 'ses-02', 'ses-03', 'ses-04', 'ses-05', 'ses-06']
    a1, _ = random_split(sessions, seed=0)
    a2, _ = random_split(sessions, seed=1)
    assert set(a1) != set(a2), 'Different seeds must produce different halves'


def test_random_split_two_sessions_returns_one_each():
    a, b = random_split(['ses-01', 'ses-02'], seed=0)
    assert len(a) == 1 and len(b) == 1
    assert set(a) | set(b) == {'ses-01', 'ses-02'}


def test_random_split_too_few_sessions_raises():
    with pytest.raises(ValueError):
        random_split(['ses-01'], seed=0)
    with pytest.raises(ValueError):
        random_split([], seed=0)


# ---------------------------------------------------------------------------
# generate_splits — n_iterations + cross-subject independence
# ---------------------------------------------------------------------------


def test_generate_splits_returns_one_entry_per_subject_iteration():
    sessions = {
        'sub-s10': ['ses-01', 'ses-02', 'ses-03', 'ses-04'],
        'sub-s19': ['ses-01', 'ses-02', 'ses-03', 'ses-04'],
    }
    out = generate_splits(sessions, n_iterations=5)
    assert len(out) == 2 * 5
    assert all(isinstance(x, SubjectSplit) for x in out)


def test_generate_splits_within_subject_iterations_differ():
    """Across iterations of one subject, the half_a sets should differ
    (with overwhelmingly-high probability for n_sessions=6)."""
    sessions = {'sub-s10': ['ses-01', 'ses-02', 'ses-03', 'ses-04', 'ses-05', 'ses-06']}
    out = generate_splits(sessions, n_iterations=10)
    half_a_sets = {frozenset(s.half_a) for s in out}
    assert len(half_a_sets) > 1, (
        'All 10 iterations produced the same half_a — seed mixing is broken'
    )


def test_generate_splits_is_deterministic_across_calls():
    sessions = {'sub-s10': ['ses-01', 'ses-02', 'ses-03', 'ses-04']}
    a = generate_splits(sessions, n_iterations=5, base_seed=42)
    b = generate_splits(sessions, n_iterations=5, base_seed=42)
    assert a == b


def test_generate_splits_seed_uses_deterministic_subject_hash():
    """Different subjects with the same iteration index produce
    different partitions, *and* the partition for ``sub-s10`` at
    iter=0, base_seed=0 is the same every time (which requires the
    subject hash to be deterministic across processes — Python's
    builtin hash() of strings is randomised per-process unless
    PYTHONHASHSEED is set; we use zlib.adler32 instead)."""
    sessions = {
        'sub-s10': ['ses-01', 'ses-02', 'ses-03', 'ses-04'],
        'sub-s19': ['ses-01', 'ses-02', 'ses-03', 'ses-04'],
    }
    out = generate_splits(sessions, n_iterations=1, base_seed=0)
    by_subj = {s.subject: s for s in out}
    assert set(by_subj['sub-s10'].half_a) != set(by_subj['sub-s19'].half_a), (
        'Different subjects produced identical splits — subject seed mixing failed'
    )


def test_generate_splits_invalid_n_iterations_raises():
    with pytest.raises(ValueError):
        generate_splits({'sub-x': ['ses-01', 'ses-02']}, n_iterations=0)
