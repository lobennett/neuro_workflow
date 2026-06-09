"""Handlers for the ``exclusions`` subcommand group."""

import sys

from neuro_workflow.core.exclusions import (
    save_source_entries,
    compile_exclusions,
    load_compiled_exclusions,
)
from neuro_workflow.exclusions.base import get_generator, list_generators


def cmd_exclusions_generate(args, remaining):
    import neuro_workflow.cli as cli

    generator = get_generator(args.source)
    if generator is None:
        available = ", ".join(list_generators()) or "(none registered)"
        print(f"Error: unknown generator '{args.source}'. Available: {available}", file=sys.stderr)
        sys.exit(1)
    config = cli.get_dataset(args.dataset)
    entries = generator.generate(args.dataset, config, args)
    save_source_entries(args.dataset, generator.name, entries, args=args)
    print(f"Saved {len(entries)} entries to sources/{generator.name}.json")


def cmd_exclusions_compile(args, remaining):
    import neuro_workflow.cli as cli

    config = cli.get_dataset(args.dataset)
    compiled = compile_exclusions(args.dataset, bids_dir=config.get("bids_dir"))
    from collections import Counter
    by_source = Counter(e["source"] for e in compiled)
    by_action = Counter(e["action"] for e in compiled)
    print(f"Compiled {len(compiled)} exclusions for '{args.dataset}':")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"  Actions: {dict(by_action)}")


def cmd_exclusions_show(args, remaining):
    import json
    from collections import Counter
    from neuro_workflow.core.exclusions import _lockfile_path

    compiled = load_compiled_exclusions(args.dataset)

    # Existing per-source count table (only if compiled exists).
    if not compiled:
        print(f"No compiled exclusions for '{args.dataset}'. Run 'neuro-run exclusions compile {args.dataset}' first.")
    else:
        by_source = Counter(e["source"] for e in compiled)
        by_action = Counter(e["action"] for e in compiled)
        print(f"Exclusions for '{args.dataset}':")
        print(f"{'Source':<15} {'Exclude':>8} {'Trim':>8} {'Total':>8}")
        print("-" * 41)
        for source in sorted(by_source):
            src_entries = [e for e in compiled if e["source"] == source]
            n_exc = sum(1 for e in src_entries if e["action"] == "exclude")
            n_trim = sum(1 for e in src_entries if e["action"] == "trim")
            print(f"{source:<15} {n_exc:>8} {n_trim:>8} {len(src_entries):>8}")
        print("-" * 41)
        print(f"{'Total':<15} {by_action.get('exclude', 0):>8} {by_action.get('trim', 0):>8} {len(compiled):>8}")

    # Provenance block from lockfile, if present.
    lock_path = _lockfile_path(args.dataset)
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        print()
        print(f"Provenance ({lock_path}):")
        print(f"  Compiled at: {lock['compiled_at']} (code_sha: {lock.get('compiled_at_code_sha')})")
        print(f"  Total entries: {lock['n_total_entries']}, overrides: {lock['n_overrides']}")
        for s in lock["sources"]:
            ran_at = s.get("ran_at") or "<unknown>"
            sha = s.get("code_sha") or "<unknown>"
            n = s.get("n_entries", 0)
            print(f"  - {s['generator']:<15} ran_at={ran_at} code_sha={sha} n_entries={n}")


def cmd_exclusions_import(args, remaining):
    import json
    with open(args.input_file) as f:
        entries = json.load(f)
    for entry in entries:
        entry["source"] = args.source_name
    save_source_entries(args.dataset, args.source_name, entries, args=args)
    print(f"Imported {len(entries)} entries as source '{args.source_name}'")


def add_exclusions_parser(subparsers):
    import neuro_workflow.cli as cli

    excl_p = subparsers.add_parser("exclusions", help="Manage scan exclusions")
    excl_sub = excl_p.add_subparsers(dest="excl_command", required=True)

    # exclusions generate
    gen_p = excl_sub.add_parser("generate", help="Generate exclusions from a source")
    gen_p.add_argument("source", help="Generator name (e.g. motion, neg-events)")
    gen_p.add_argument("dataset", help="Dataset name")
    for gen in list_generators().values():
        gen.add_cli_args(gen_p)
    gen_p.set_defaults(func=cli.cmd_exclusions_generate)

    # exclusions compile
    comp_p = excl_sub.add_parser("compile", help="Compile all exclusion sources")
    comp_p.add_argument("dataset", help="Dataset name")
    comp_p.set_defaults(func=cli.cmd_exclusions_compile)

    # exclusions show
    show_excl_p = excl_sub.add_parser("show", help="Show exclusion summary")
    show_excl_p.add_argument("dataset", help="Dataset name")
    show_excl_p.set_defaults(func=cli.cmd_exclusions_show)

    # exclusions import
    imp_p = excl_sub.add_parser("import", help="Import external exclusion list")
    imp_p.add_argument("source_name", help="Source name to assign")
    imp_p.add_argument("dataset", help="Dataset name")
    imp_p.add_argument("--input-file", required=True, help="Path to JSON file to import")
    imp_p.set_defaults(func=cli.cmd_exclusions_import)
