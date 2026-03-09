from argparse import ArgumentParser, Namespace
from pathlib import Path
from io import StringIO

from neuro_workflow.qa.neg_events import NegEventsQa, find_monotonic_point


def test_find_monotonic_point_monotonic():
    import pandas as pd
    s = pd.Series([1.0, 2.0, 3.0])
    assert find_monotonic_point(s) == 0


def test_find_monotonic_point_non_monotonic():
    import pandas as pd
    s = pd.Series([5.0, 1.0, 2.0, 3.0])
    assert find_monotonic_point(s) == 1


def test_find_monotonic_point_never_monotonic():
    import pandas as pd
    s = pd.Series([3.0, 1.0, 3.0, 1.0])
    assert find_monotonic_point(s) is None


def test_qa_attributes():
    qa = NegEventsQa()
    assert qa.name == "neg-events"
    assert qa.description


def test_run_reports_non_monotonic(tmp_path, capsys):
    """Create event files and verify run() reports non-monotonic ones."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)

    # Monotonic file
    (func / "sub-s01_ses-01_task-rest_events.tsv").write_text(
        "onset\tduration\n1.0\t1.0\n2.0\t1.0\n3.0\t1.0\n"
    )

    # Non-monotonic file
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text(
        "onset\tduration\n5.0\t1.0\n1.0\t1.0\n2.0\t1.0\n"
    )

    config = {"bids_dir": str(bids)}
    args = Namespace()
    qa = NegEventsQa()
    qa.run("discovery", config, args)

    captured = capsys.readouterr()
    assert "flanker" in captured.out
    assert "1" in captured.out  # trim index
