from argparse import Namespace
from neuro_workflow.exclusions.behavioral import BehavioralGenerator


def test_generator_attributes():
    g = BehavioralGenerator()
    assert g.name == "behavioral"
    assert g.description


def test_generate_returns_empty(tmp_path):
    g = BehavioralGenerator()
    config = {"bids_dir": str(tmp_path)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert entries == []
