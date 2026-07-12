"""Handlers for the ``provenance`` subcommand group.

``neuro-run provenance graph --cohort X [--bids-root PATH] [--out FILE]``
exports the full Flywheel->lev2 provenance chain as machine-readable JSON. Pure
data exporter: prints to stdout (or writes ``--out``); no plotting/HTML.
"""

import json
import sys
from pathlib import Path

from neuro_workflow.core.provenance_graph import build_provenance_graph


def cmd_provenance_graph(args, remaining):
    graph = build_provenance_graph(args.cohort, bids_root=args.bids_root)
    payload = json.dumps(graph, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n")
        print(f"Wrote provenance graph to {args.out}", file=sys.stderr)
    else:
        print(payload)


def add_provenance_parser(subparsers):
    import neuro_workflow.cli as cli

    prov_p = subparsers.add_parser("provenance", help="Export pipeline provenance")
    prov_sub = prov_p.add_subparsers(dest="prov_command", required=True)

    graph_p = prov_sub.add_parser(
        "graph",
        help="Export the Flywheel->lev2 provenance chain as JSON",
    )
    graph_p.add_argument("--cohort", required=True, help="Cohort name (e.g. validation)")
    graph_p.add_argument(
        "--bids-root",
        default=None,
        metavar="PATH",
        help="BIDS dataset root holding derivatives/ (fmriprep, lev1, lev2)",
    )
    graph_p.add_argument(
        "--out",
        default=None,
        metavar="FILE",
        help="Write JSON to FILE instead of stdout",
    )
    graph_p.set_defaults(func=cli.cmd_provenance_graph)
