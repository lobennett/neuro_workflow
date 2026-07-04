import pytest
from unittest.mock import patch, MagicMock


class TestEventsSubcommand:
    def test_events_create_parses(self):
        """neuro-run events create <dataset> --behavioral-dir <dir>"""
        import sys
        from neuro_workflow.cli import main

        with patch.object(
            sys,
            "argv",
            [
                "neuro-run",
                "events",
                "create",
                "discovery",
                "--behavioral-dir",
                "/tmp/sourcedata",
            ],
        ):
            with patch("neuro_workflow.cli.cmd_events_create") as mock_create:
                with patch(
                    "neuro_workflow.cli.get_dataset", return_value={"bids_dir": "/tmp/bids"}
                ):
                    main()
                    mock_create.assert_called_once()

    def test_events_qc_parses(self):
        """neuro-run events qc <dataset> --behavioral-dir <dir>"""
        import sys
        from neuro_workflow.cli import main

        with patch.object(
            sys,
            "argv",
            [
                "neuro-run",
                "events",
                "qc",
                "discovery",
                "--behavioral-dir",
                "/tmp/sourcedata",
            ],
        ):
            with patch("neuro_workflow.cli.cmd_events_qc") as mock_qc:
                with patch(
                    "neuro_workflow.cli.get_dataset", return_value={"bids_dir": "/tmp/bids"}
                ):
                    main()
                    mock_qc.assert_called_once()

    def test_events_trim_parses(self):
        """neuro-run events trim <dataset>"""
        import sys
        from neuro_workflow.cli import main

        with patch.object(
            sys,
            "argv",
            [
                "neuro-run",
                "events",
                "trim",
                "discovery",
            ],
        ):
            with patch("neuro_workflow.cli.cmd_events_trim") as mock_trim:
                with patch(
                    "neuro_workflow.cli.get_dataset", return_value={"bids_dir": "/tmp/bids"}
                ):
                    main()
                    mock_trim.assert_called_once()
