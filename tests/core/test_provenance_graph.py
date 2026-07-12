"""Tests for the provenance-graph exporter (core/provenance_graph.py).

Written red-first (Task 6). ``build_provenance_graph(cohort, bids_root)``
assembles the full Flywheel->BIDS->fMRIPrep->exclusions->lev1->lev2 chain into
one machine-readable dict: an ordered ``stages`` list (each stage exposing at
least ``name`` + ``present``) plus an ``edges`` list where consecutive stages
that both expose a ``code_sha`` carry a ``sha_mismatch`` bool.

Tests are hermetic: the module's repo-root anchor is monkeypatched to a tmp
dir so we never touch the committed lockfiles, and the BIDS tree is stubbed.
"""

from __future__ import annotations

import json

import pytest

from neuro_workflow.core import provenance_graph as pg

# The seven pipeline stages, in chain order.
_EXPECTED_STAGES = [
    "flywheel_snapshot",
    "reconciliation",
    "bidsignore",
    "fmriprep",
    "exclusions_lockfile",
    "lev1",
    "lev2",
]


@pytest.fixture
def stub_repo_and_bids(tmp_path, monkeypatch):
    """A tmp repo-root (with a stub lockfile) + a stub BIDS derivatives tree."""
    monkeypatch.setattr(pg, "_REPO_ROOT", tmp_path)

    cohort = "mycohort"

    # Stub exclusions lockfile at <repo>/data/exclusions/<cohort>_lock.json
    excl_dir = tmp_path / "data" / "exclusions"
    excl_dir.mkdir(parents=True)
    (excl_dir / f"{cohort}_lock.json").write_text(
        json.dumps(
            {
                "dataset": cohort,
                "compiled_at": "2026-07-05T21:36:45Z",
                "compiled_at_code_sha": "abc1234",
                "n_total_entries": 42,
                "n_overrides": 3,
                "sources": [
                    {"generator": "behavioral-qc", "code_sha": "abc1234", "n_entries": 8},
                ],
            }
        )
    )
    # Stub committed collection .bidsignore
    (excl_dir / f"{cohort}_collection.bidsignore").write_text("sub-s01/**\n")

    # Stub reconciliation manifest at <repo>/config/manifests/
    man_dir = tmp_path / "config" / "manifests"
    man_dir.mkdir(parents=True)
    (man_dir / f"reconciliation_{cohort}.tsv").write_text("subject\tsession\ns01\t01\n")

    # Stub BIDS derivatives tree
    bids_root = tmp_path / "bids"
    fmriprep = bids_root / "derivatives" / "fmriprep_25.2.4"
    fmriprep.mkdir(parents=True)
    (fmriprep / "dataset_description.json").write_text(
        json.dumps({"GeneratedBy": [{"Name": "fMRIPrep", "Version": "25.2.4"}]})
    )

    lev1_dir = bids_root / "derivatives" / "lev1_surface" / "sub-s01" / "task-foo"
    lev1_dir.mkdir(parents=True)
    (lev1_dir / "run-manifest.json").write_text(
        json.dumps(
            {
                "stage": "lev1",
                "code_sha": "def5678",
                "config_version": "cfg99",
                "exclusions_source": {"path": "/x", "sha256": "deadbeef"},
            }
        )
    )
    # No lev2 tree -> lev2 stage should be present: false.
    return cohort, bids_root


def test_graph_has_all_seven_stages_in_order(stub_repo_and_bids):
    cohort, bids_root = stub_repo_and_bids
    g = pg.build_provenance_graph(cohort, bids_root=bids_root)

    names = [s["name"] for s in g["stages"]]
    assert names == _EXPECTED_STAGES
    # The three chain-tail stages the task explicitly requires.
    assert {"exclusions_lockfile", "lev1", "lev2"} <= set(names)


def test_stage_presence_and_shas(stub_repo_and_bids):
    cohort, bids_root = stub_repo_and_bids
    g = pg.build_provenance_graph(cohort, bids_root=bids_root)
    by_name = {s["name"]: s for s in g["stages"]}

    # Present stubs
    assert by_name["reconciliation"]["present"] is True
    assert by_name["bidsignore"]["present"] is True
    assert by_name["fmriprep"]["present"] is True
    assert by_name["fmriprep"]["version"] == "25.2.4"
    assert by_name["exclusions_lockfile"]["present"] is True
    assert by_name["exclusions_lockfile"]["code_sha"] == "abc1234"
    assert by_name["lev1"]["present"] is True
    assert by_name["lev1"]["code_sha"] == "def5678"

    # Absent (no stub) -> present: false, does not crash
    assert by_name["flywheel_snapshot"]["present"] is False
    assert by_name["lev2"]["present"] is False


def test_edges_flag_sha_mismatch(stub_repo_and_bids):
    cohort, bids_root = stub_repo_and_bids
    g = pg.build_provenance_graph(cohort, bids_root=bids_root)

    # At least one edge must carry a real boolean sha comparison.
    bool_edges = [e for e in g["edges"] if e.get("sha_mismatch") in (True, False)]
    assert bool_edges, "expected at least one edge with a sha_mismatch bool"

    # The lockfile(abc1234) -> lev1(def5678) edge is a mismatch.
    lock_lev1 = [e for e in g["edges"] if e["from"] == "exclusions_lockfile" and e["to"] == "lev1"]
    assert lock_lev1
    assert lock_lev1[0]["sha_mismatch"] is True


def test_missing_bids_root_does_not_crash(stub_repo_and_bids):
    cohort, _ = stub_repo_and_bids
    # No bids_root at all: fmriprep/lev1/lev2 absent, repo-anchored stages present.
    g = pg.build_provenance_graph(cohort, bids_root=None)
    by_name = {s["name"]: s for s in g["stages"]}
    assert by_name["fmriprep"]["present"] is False
    assert by_name["lev1"]["present"] is False
    assert by_name["exclusions_lockfile"]["present"] is True
    assert [s["name"] for s in g["stages"]] == _EXPECTED_STAGES
