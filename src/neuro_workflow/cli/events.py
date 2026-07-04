"""Handlers for the ``events`` subcommand group."""

from pathlib import Path

from neuro_workflow.core.exclusions import save_source_entries


def cmd_events_create(args, remaining):
    import neuro_workflow.cli as cli
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from neuro_workflow.events.create import run_create_events

    config = cli.get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    behavioral_dir = Path(args.behavioral_dir) if args.behavioral_dir else bids_dir / "sourcedata"
    run_create_events(behavioral_dir=behavioral_dir, bids_dir=bids_dir)


def cmd_events_qc(args, remaining):
    import neuro_workflow.cli as cli
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from neuro_workflow.events.qc import run_qc

    config = cli.get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    behavioral_dir = Path(args.behavioral_dir) if args.behavioral_dir else bids_dir / "sourcedata"
    exclusion_entries, trim_entries = run_qc(behavioral_dir=behavioral_dir, bids_dir=bids_dir)
    if exclusion_entries:
        save_source_entries(args.dataset, "behavioral-qc", exclusion_entries, args=args)
        print(f"Saved {len(exclusion_entries)} behavioral-qc exclusion entries")
    print(f"Found {len(trim_entries)} runs needing trimming")


def cmd_events_trim(args, remaining):
    import neuro_workflow.cli as cli
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from neuro_workflow.events.trim import run_trim

    config = cli.get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    run_trim(bids_dir=bids_dir)


def add_events_parser(subparsers):
    import neuro_workflow.cli as cli

    events_p = subparsers.add_parser("events", help="Behavioral events pipeline")
    events_sub = events_p.add_subparsers(dest="events_command", required=True)

    # events create
    ev_create = events_sub.add_parser(
        "create", help="Generate BIDS _events.tsv from behavioral CSVs"
    )
    ev_create.add_argument("dataset", help="Dataset name")
    ev_create.add_argument(
        "--behavioral-dir", default=None, help="Path to sourcedata behavioral directory"
    )
    ev_create.set_defaults(func=cli.cmd_events_create)

    # events qc
    ev_qc = events_sub.add_parser("qc", help="Run behavioral QC and generate exclusions")
    ev_qc.add_argument("dataset", help="Dataset name")
    ev_qc.add_argument(
        "--behavioral-dir", default=None, help="Path to sourcedata behavioral directory"
    )
    ev_qc.set_defaults(func=cli.cmd_events_qc)

    # events trim
    ev_trim = events_sub.add_parser("trim", help="Trim NIfTIs to match behavioral cutoff")
    ev_trim.add_argument("dataset", help="Dataset name")
    ev_trim.set_defaults(func=cli.cmd_events_trim)
