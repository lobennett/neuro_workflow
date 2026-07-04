import sys
import pytest
from unittest.mock import patch, MagicMock
from neuro_workflow.cli import main


def test_bidsify_cli_parses_args(monkeypatch):
    """Test that the bidsify subcommand parses correctly."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "neuro-run",
            "bidsify",
            "discovery",
            "--output-dir",
            "/tmp/test_bids",
            "--subjects",
            "s03",
            "s10",
        ],
    )
    with patch("neuro_workflow.cli.cmd_bidsify") as mock_cmd:
        mock_cmd.return_value = None
        main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.sample == "discovery"
        assert args.output_dir == "/tmp/test_bids"
        assert args.subjects == ["s03", "s10"]
