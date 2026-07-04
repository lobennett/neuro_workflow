"""Handler for the ``bidsify`` subcommand."""


def cmd_bidsify(args, remaining):
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from neuro_workflow.bidsify.run import run_bidsify
    from pathlib import Path

    subjects = args.subjects if args.subjects else None
    output_dir = Path(args.output_dir)

    run_bidsify(
        sample_name=args.sample,
        output_dir=output_dir,
        subjects=subjects,
        flywheel_project=args.flywheel_project,
        overwrite=args.overwrite,
    )


def add_bidsify_parser(subparsers):
    import neuro_workflow.cli as cli

    bidsify_p = subparsers.add_parser("bidsify", help="Pull and BIDSify data from Flywheel")
    bidsify_p.add_argument("sample", help="Sample name (discovery, validation)")
    bidsify_p.add_argument("--output-dir", required=True, help="BIDS output directory")
    bidsify_p.add_argument(
        "--subjects", nargs="+", help="Subject labels to process (default: all in sample)"
    )
    bidsify_p.add_argument("--flywheel-project", default=None, help="Flywheel project label")
    bidsify_p.add_argument("--overwrite", action="store_true", help="Overwrite existing output")
    bidsify_p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    bidsify_p.set_defaults(func=cli.cmd_bidsify)
