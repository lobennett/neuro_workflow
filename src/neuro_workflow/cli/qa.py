"""Handler for the ``qa`` subcommand."""

import argparse
import sys

from neuro_workflow.qa.base import get_qa_command, list_qa_commands


def cmd_qa(args, remaining):
    import neuro_workflow.cli as cli

    command = get_qa_command(args.qa_command)
    if command is None:
        available = ", ".join(list_qa_commands()) or "(none registered)"
        print(
            f"Error: unknown QA command '{args.qa_command}'. Available: {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse QA-command-specific args
    qa_parser = argparse.ArgumentParser()
    command.add_cli_args(qa_parser)
    qa_args = qa_parser.parse_args(remaining)
    for key, value in vars(qa_args).items():
        setattr(args, key, value)

    config = cli.get_dataset(args.dataset)
    command.run(args.dataset, config, args)


def add_qa_parser(subparsers):
    import neuro_workflow.cli as cli

    qa_p = subparsers.add_parser("qa", help="Run QA analysis scripts")
    qa_p.add_argument("qa_command", help="QA command name")
    qa_p.add_argument("dataset", help="Dataset name")
    qa_p.set_defaults(func=cli.cmd_qa)
