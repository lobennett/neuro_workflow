"""Sherlock-gated end-to-end test for scripts/reproduce_cohort.py.

This test is AUTO-SKIPPED when the real Flywheel snapshot and BIDS dataset
are absent — which is always the case outside Sherlock (CI, dev laptops, the
synthetic-cohort suite).  It runs the full CLI as a subprocess and asserts
that the report's first line contains "PASS" and the exit code is 0.

Skip conditions (OR'd):
    - ``data/repro/fw_inventory_discovery.json`` does not exist (snapshot not
      yet captured from Flywheel).
    - ``/scratch/users/logben/discovery_bids`` does not exist (real BIDS not
      present on this node).

Both conditions are checked at collection time via ``pytest.mark.skipif``, so
the test shows up as "s" (skipped) rather than "E" (error) in any environment
where the inputs are absent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Worktree root (absolute) — resolve relative to this file's parent chain.
# This file lives at tests/analysis/e2e/test_reproduce_cohort.py; the
# worktree root is four levels up.
_WT = Path(__file__).resolve().parents[3]

# Inputs that must exist for the real cohort run to be attempted.
_SNAP = _WT / "data" / "repro" / "fw_inventory_discovery.json"
_REAL_BIDS = Path("/scratch/users/logben/discovery_bids")

pytestmark = pytest.mark.skipif(
    not (_SNAP.exists() and _REAL_BIDS.exists()),
    reason=(
        "real cohort inputs / Flywheel snapshot absent (Sherlock-only): "
        f"snapshot={_SNAP}, bids={_REAL_BIDS}"
    ),
)


def test_discovery_reproduces(tmp_path):
    """Run reproduce_cohort.py discovery and assert PASS in the first line."""
    report_path = tmp_path / "rep.md"
    result = subprocess.run(
        [
            sys.executable,
            str(_WT / "scripts" / "reproduce_cohort.py"),
            "discovery",
            "--out",
            str(report_path),
        ],
        capture_output=True,
        text=True,
    )
    # Print stdout/stderr so the sbatch output file captures generator summaries.
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    assert report_path.exists(), (
        f"reproduce_cohort.py did not write a report to {report_path}. "
        f"stdout: {result.stdout[:2000]}\nstderr: {result.stderr[:2000]}"
    )
    report = report_path.read_text()
    first_line = report.splitlines()[0] if report else ""
    assert "PASS" in first_line, (
        f"Expected 'PASS' in first line of report, got: {first_line!r}\n" f"Full report:\n{report}"
    )
    assert result.returncode == 0, (
        f"reproduce_cohort.py exited with code {result.returncode}.\n"
        f"stdout: {result.stdout[:2000]}\nstderr: {result.stderr[:2000]}"
    )
