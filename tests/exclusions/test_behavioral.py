from argparse import Namespace

import pytest

from neuro_workflow.exclusions.behavioral import BehavioralGenerator


def test_generator_attributes():
    g = BehavioralGenerator()
    assert g.name == "behavioral"
    assert g.description


def test_generate_returns_empty(tmp_path):
    """Empty sourcedata -> no entries (real dataset name so the roster resolves)."""
    g = BehavioralGenerator()
    config = {"bids_dir": str(tmp_path)}
    entries = g.generate("discovery", config, Namespace())
    assert entries == []


def test_generate_scopes_to_dataset_roster(tmp_path, monkeypatch):
    """The generator passes the dataset's roster to run_qc, so a shared behavioral
    tree (all cohorts) cannot cross-contaminate. Regression for the 2026-06-29
    cross-cohort behavioral bug."""
    import neuro_workflow.events.qc as qc
    from neuro_workflow.exclusions.base import load_dataset_subjects

    captured = {}

    def fake_run_qc(behavioral_dir, bids_dir, subjects=None):
        captured["subjects"] = subjects
        return [], []

    monkeypatch.setattr(qc, "run_qc", fake_run_qc)
    BehavioralGenerator().generate("discovery", {"bids_dir": str(tmp_path)}, Namespace())

    assert captured["subjects"] is not None
    assert set(captured["subjects"]) == load_dataset_subjects("discovery")
    # discovery roster is the 5 prefixed IDs; no validation subjects leak in
    assert all(s.startswith("sub-") for s in captured["subjects"])


def test_generate_unknown_dataset_fails_loud(tmp_path):
    """An unknown dataset name fails loud (no silent no-filter path)."""
    with pytest.raises(ValueError):
        BehavioralGenerator().generate("not_a_dataset", {"bids_dir": str(tmp_path)}, Namespace())
