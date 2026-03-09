from argparse import Namespace
from pathlib import Path

from neuro_workflow.exclusions.neg_events import NegEventsGenerator


def test_generator_attributes():
    g = NegEventsGenerator()
    assert g.name == "neg-events"
    assert g.description


def test_generate_detects_trim(tmp_path):
    """Non-monotonic onset with >50% salvageable -> trim action."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    # 10 rows: first onset is out of order, rest monotonic (90% salvageable)
    lines = ["onset\tduration"]
    lines.append("5.0\t1.0")  # bad
    for i in range(1, 10):
        lines.append(f"{float(i)}\t1.0")
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text("\n".join(lines))

    g = NegEventsGenerator()
    config = {"bids_dir": str(bids)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert len(entries) == 1
    assert entries[0]["action"] == "trim"
    assert entries[0]["metrics"]["onset_trim_index"] == 1
    assert entries[0]["metrics"]["rows_to_keep"] == 9


def test_generate_detects_exclude(tmp_path):
    """Non-monotonic onset with <50% salvageable -> exclude action."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    # Mostly non-monotonic: only last 2 of 10 rows are monotonic (20%)
    lines = ["onset\tduration"]
    for i in range(8):
        lines.append(f"{float(8 - i)}\t1.0")  # descending
    lines.append("9.0\t1.0")
    lines.append("10.0\t1.0")
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text("\n".join(lines))

    g = NegEventsGenerator()
    config = {"bids_dir": str(bids)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert len(entries) == 1
    assert entries[0]["action"] == "exclude"


def test_generate_skips_monotonic(tmp_path):
    """Monotonic onsets -> no entries."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    lines = ["onset\tduration"]
    for i in range(10):
        lines.append(f"{float(i)}\t1.0")
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text("\n".join(lines))

    g = NegEventsGenerator()
    config = {"bids_dir": str(bids)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert len(entries) == 0
