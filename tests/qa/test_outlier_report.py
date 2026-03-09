from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.qa.outlier_report import OutlierReportQa


def test_qa_attributes():
    qa = OutlierReportQa()
    assert qa.name == "outlier-report"
    assert qa.description


def test_add_cli_args():
    qa = OutlierReportQa()
    parser = ArgumentParser()
    qa.add_cli_args(parser)
    args = parser.parse_args([
        "--lev1-dirs", "/path/a", "/path/b",
        "--exclusions-file", "/path/excl.json",
        "--output-dir", "/output",
    ])
    assert args.lev1_dirs == ["/path/a", "/path/b"]
    assert args.exclusions_file == "/path/excl.json"
    assert args.output_dir == "/output"
