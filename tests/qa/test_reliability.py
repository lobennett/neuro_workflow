import re
from argparse import ArgumentParser, Namespace

from neuro_workflow.qa.reliability import ReliabilityQa, parse_bids_filename


def test_parse_bids_filename():
    result = parse_bids_filename("sub-s03_ses-01_task-rest_run-01_space-T1w_desc-preproc_bold.nii.gz")
    assert result["subject"] == "s03"
    assert result["session"] == "01"
    assert result["task"] == "rest"
    assert result["run"] == 1


def test_parse_bids_filename_no_match():
    assert parse_bids_filename("random_file.nii.gz") is None


def test_qa_attributes():
    qa = ReliabilityQa()
    assert qa.name == "reliability"
    assert qa.description


def test_add_cli_args():
    qa = ReliabilityQa()
    parser = ArgumentParser()
    qa.add_cli_args(parser)
    args = parser.parse_args(["--fmriprep-version", "24.1.0", "--output-dir", "/out"])
    assert args.fmriprep_version == "24.1.0"
    assert args.output_dir == "/out"
