from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

from neuro_workflow.qa.global_signal import GlobalSignalQa, parse_bids_meta


def test_parse_bids_meta(tmp_path):
    p = tmp_path / "sub-s03_ses-01_task-rest_echo-2_bold.nii.gz"
    p.touch()
    meta = parse_bids_meta(p)
    assert meta["sub_val"] == 3
    assert meta["sub_str"] == "sub-s03"
    assert meta["ses_val"] == 1
    assert meta["task"] == "rest"


def test_qa_attributes():
    qa = GlobalSignalQa()
    assert qa.name == "global-signal"
    assert qa.description


def test_add_cli_args():
    from argparse import ArgumentParser

    qa = GlobalSignalQa()
    parser = ArgumentParser()
    qa.add_cli_args(parser)
    args = parser.parse_args(["--output-dir", "/tmp/out"])
    assert args.output_dir == "/tmp/out"
