import argparse
import sys
from pathlib import Path

from neuro_workflow.core.config import save_dataset, get_dataset, load_datasets
from neuro_workflow.core.image import ensure_image
from neuro_workflow.core.slurm import render_template, submit_sbatch
from neuro_workflow.core.exclusions import (
    save_source_entries,
    save_overrides,
    load_overrides,
    compile_exclusions,
    load_compiled_exclusions,
)
from neuro_workflow.pipelines.base import get_pipeline, list_pipelines, TEMPLATE_DIR
from neuro_workflow.qa.base import get_qa_command, list_qa_commands
from neuro_workflow.exclusions.base import get_generator, list_generators

# Import pipeline modules to trigger auto-registration
import neuro_workflow.pipelines.fmriprep  # noqa: F401
import neuro_workflow.pipelines.qsiprep  # noqa: F401
import neuro_workflow.pipelines.fsqc  # noqa: F401
import neuro_workflow.pipelines.freesurfer  # noqa: F401
import neuro_workflow.pipelines.happy  # noqa: F401
import neuro_workflow.pipelines.lev1  # noqa: F401
import neuro_workflow.pipelines.lev2  # noqa: F401
import neuro_workflow.pipelines.prep_mshbm  # noqa: F401
import neuro_workflow.pipelines.mshbm  # noqa: F401
import neuro_workflow.pipelines.bidsify  # noqa: F401

# Import QA modules to trigger auto-registration
import neuro_workflow.qa.neg_events  # noqa: F401
import neuro_workflow.qa.breaks  # noqa: F401
import neuro_workflow.qa.global_signal  # noqa: F401
import neuro_workflow.qa.outlier_report  # noqa: F401
import neuro_workflow.qa.reliability  # noqa: F401
import neuro_workflow.qa.fieldmap_check  # noqa: F401

# Import exclusion generators to trigger auto-registration
import neuro_workflow.exclusions.motion  # noqa: F401
import neuro_workflow.exclusions.neg_events  # noqa: F401
import neuro_workflow.exclusions.behavioral  # noqa: F401


def cmd_add_dataset(args):
    dataset_config = {
        "bids_dir": args.bids_dir,
        "subjects_file": args.subjects_file,
    }
    optional = {
        "partition": args.partition,
        "mail_user": args.mail_user,
        "image_dir": args.image_dir,
        "templateflow_dir": args.templateflow_dir,
    }
    for key, value in optional.items():
        if value is not None:
            dataset_config[key] = value

    for path_key in ("bids_dir", "subjects_file"):
        p = Path(dataset_config[path_key])
        if not p.exists():
            print(f"Warning: {path_key} path does not exist: {p}", file=sys.stderr)

    save_dataset(args.name, dataset_config)
    print(f"Dataset '{args.name}' saved.")


def cmd_show(args, remaining):
    if args.list:
        datasets = load_datasets()
        if not datasets:
            print("No datasets registered. Use 'neuro-run add-dataset' to add one.")
            return
        for name, ds in datasets.items():
            print(f"  {name}: {ds.get('bids_dir', '(no bids_dir)')}")
        return

    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}", file=sys.stderr)
        sys.exit(1)

    # Parse pipeline-specific args
    pipeline_parser = argparse.ArgumentParser()
    pipeline.add_cli_args(pipeline_parser)
    pipeline_args = pipeline_parser.parse_args(remaining)
    # Merge into args namespace
    for key, value in vars(pipeline_args).items():
        setattr(args, key, value)

    config = get_dataset(args.dataset)
    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)
    print(script)


def cmd_submit(args, remaining):
    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}", file=sys.stderr)
        sys.exit(1)

    # Parse pipeline-specific args
    pipeline_parser = argparse.ArgumentParser()
    pipeline.add_cli_args(pipeline_parser)
    pipeline_args = pipeline_parser.parse_args(remaining)
    for key, value in vars(pipeline_args).items():
        setattr(args, key, value)

    if getattr(pipeline, "requires_dataset", True):
        config = get_dataset(args.dataset)
        if pipeline.docker_uri:
            ensure_image(config["image_dir"], pipeline.name, args.version, pipeline.docker_uri)
    else:
        config = {}

    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)

    print("--- Generated sbatch script ---")
    print(script)
    print("--- Submitting ---")
    submit_sbatch(script)


def cmd_qa(args, remaining):
    command = get_qa_command(args.qa_command)
    if command is None:
        available = ", ".join(list_qa_commands()) or "(none registered)"
        print(f"Error: unknown QA command '{args.qa_command}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    # Parse QA-command-specific args
    qa_parser = argparse.ArgumentParser()
    command.add_cli_args(qa_parser)
    qa_args = qa_parser.parse_args(remaining)
    for key, value in vars(qa_args).items():
        setattr(args, key, value)

    config = get_dataset(args.dataset)
    command.run(args.dataset, config, args)


def cmd_exclusions_generate(args, remaining):
    generator = get_generator(args.source)
    if generator is None:
        available = ", ".join(list_generators()) or "(none registered)"
        print(f"Error: unknown generator '{args.source}'. Available: {available}", file=sys.stderr)
        sys.exit(1)
    config = get_dataset(args.dataset)
    entries = generator.generate(args.dataset, config, args)
    save_source_entries(args.dataset, generator.name, entries)
    print(f"Saved {len(entries)} entries to sources/{generator.name}.json")


def cmd_exclusions_compile(args, remaining):
    config = get_dataset(args.dataset)
    compiled = compile_exclusions(args.dataset, bids_dir=config.get("bids_dir"))
    from collections import Counter
    by_source = Counter(e["source"] for e in compiled)
    by_action = Counter(e["action"] for e in compiled)
    print(f"Compiled {len(compiled)} exclusions for '{args.dataset}':")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"  Actions: {dict(by_action)}")


def cmd_exclusions_show(args, remaining):
    compiled = load_compiled_exclusions(args.dataset)
    if not compiled:
        print(f"No compiled exclusions for '{args.dataset}'. Run 'neuro-run exclusions compile {args.dataset}' first.")
        return
    from collections import Counter
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


def cmd_exclusions_import(args, remaining):
    import json
    with open(args.input_file) as f:
        entries = json.load(f)
    for entry in entries:
        entry["source"] = args.source_name
    save_source_entries(args.dataset, args.source_name, entries)
    print(f"Imported {len(entries)} entries as source '{args.source_name}'")


def cmd_bidsify(args):
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from neuro_workflow.bidsify.run import run_bidsify
    from neuro_workflow.bidsify.integration import run_bold_analysis_and_update_bidsignore
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

    # Run BOLD analysis (automatic, unless skipped)
    if not getattr(args, "skip_validation", False):
        try:
            run_bold_analysis_and_update_bidsignore(
                bids_dir=output_dir,
                tr_threshold_minutes=args.tr_threshold_minutes,
                merge_bidsignore=True,
                verbose=args.verbose,
            )
        except Exception as e:
            logging.error(f"BOLD analysis failed: {e}")
            if args.validation_fail_hard:
                raise
            # Otherwise, log warning and continue


def cmd_events_create(args, remaining):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from neuro_workflow.events.create import run_create_events
    config = get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    behavioral_dir = Path(args.behavioral_dir) if args.behavioral_dir else bids_dir / "sourcedata"
    run_create_events(behavioral_dir=behavioral_dir, bids_dir=bids_dir)


def cmd_events_qc(args, remaining):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from neuro_workflow.events.qc import run_qc
    config = get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    behavioral_dir = Path(args.behavioral_dir) if args.behavioral_dir else bids_dir / "sourcedata"
    exclusion_entries, trim_entries = run_qc(behavioral_dir=behavioral_dir, bids_dir=bids_dir)
    if exclusion_entries:
        save_source_entries(args.dataset, "behavioral-qc", exclusion_entries)
        print(f"Saved {len(exclusion_entries)} behavioral-qc exclusion entries")
    print(f"Found {len(trim_entries)} runs needing trimming")


def cmd_events_trim(args, remaining):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from neuro_workflow.events.trim import run_trim
    config = get_dataset(args.dataset)
    bids_dir = Path(config["bids_dir"])
    run_trim(bids_dir=bids_dir)


def main():
    parser = argparse.ArgumentParser(prog="neuro-run", description="Submit neuroimaging SLURM array jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-dataset (pipeline-agnostic)
    add_p = subparsers.add_parser("add-dataset", help="Register a dataset")
    add_p.add_argument("name", help="Dataset name (e.g., discovery, validation)")
    add_p.add_argument("--bids-dir", required=True, help="Path to BIDS directory")
    add_p.add_argument("--subjects-file", required=True, help="Path to subjects text file")
    add_p.add_argument("--partition", help="SLURM partition")
    add_p.add_argument("--mail-user", help="Email for SLURM notifications")
    add_p.add_argument("--image-dir", help="Directory for SIF images")
    add_p.add_argument("--templateflow-dir", help="TemplateFlow directory")
    add_p.set_defaults(func=lambda args, remaining: cmd_add_dataset(args))

    # show — pipeline-specific args parsed in second pass
    show_p = subparsers.add_parser("show", help="Preview sbatch script or list datasets")
    show_p.add_argument("--list", action="store_true", help="List all registered datasets")
    show_p.add_argument("pipeline", nargs="?", help="Pipeline name (e.g. fmriprep)")
    show_p.add_argument("dataset", nargs="?", help="Dataset name to preview")
    show_p.set_defaults(func=cmd_show)

    # submit — pipeline-specific args parsed in second pass
    sub_p = subparsers.add_parser("submit", help="Submit a pipeline job to SLURM")
    sub_p.add_argument("pipeline", help="Pipeline name (e.g. fmriprep, qsiprep)")
    sub_p.add_argument("dataset", help="Dataset name to submit")
    sub_p.set_defaults(func=cmd_submit)

    # qa — command-specific args parsed in second pass
    qa_p = subparsers.add_parser("qa", help="Run QA analysis scripts")
    qa_p.add_argument("qa_command", help="QA command name")
    qa_p.add_argument("dataset", help="Dataset name")
    qa_p.set_defaults(func=cmd_qa)

    # exclusions
    excl_p = subparsers.add_parser("exclusions", help="Manage scan exclusions")
    excl_sub = excl_p.add_subparsers(dest="excl_command", required=True)

    # exclusions generate
    gen_p = excl_sub.add_parser("generate", help="Generate exclusions from a source")
    gen_p.add_argument("source", help="Generator name (e.g. motion, neg-events)")
    gen_p.add_argument("dataset", help="Dataset name")
    for gen in list_generators().values():
        gen.add_cli_args(gen_p)
    gen_p.set_defaults(func=cmd_exclusions_generate)

    # exclusions compile
    comp_p = excl_sub.add_parser("compile", help="Compile all exclusion sources")
    comp_p.add_argument("dataset", help="Dataset name")
    comp_p.set_defaults(func=cmd_exclusions_compile)

    # exclusions show
    show_excl_p = excl_sub.add_parser("show", help="Show exclusion summary")
    show_excl_p.add_argument("dataset", help="Dataset name")
    show_excl_p.set_defaults(func=cmd_exclusions_show)

    # exclusions import
    imp_p = excl_sub.add_parser("import", help="Import external exclusion list")
    imp_p.add_argument("source_name", help="Source name to assign")
    imp_p.add_argument("dataset", help="Dataset name")
    imp_p.add_argument("--input-file", required=True, help="Path to JSON file to import")
    imp_p.set_defaults(func=cmd_exclusions_import)

    # bidsify
    bidsify_p = subparsers.add_parser("bidsify", help="Pull and BIDSify data from Flywheel")
    bidsify_p.add_argument("sample", help="Sample name (discovery, validation)")
    bidsify_p.add_argument("--output-dir", required=True, help="BIDS output directory")
    bidsify_p.add_argument("--subjects", nargs="+", help="Subject labels to process (default: all in sample)")
    bidsify_p.add_argument("--flywheel-project", default=None, help="Flywheel project label")
    bidsify_p.add_argument("--overwrite", action="store_true", help="Overwrite existing output")
    bidsify_p.add_argument("--tr-threshold-minutes", type=float, default=3.0, help="TR threshold for short scans in minutes (default: 3.0)")
    bidsify_p.add_argument("--skip-validation", action="store_true", help="Skip BOLD validation analysis (default: always run)")
    bidsify_p.add_argument("--validation-fail-hard", action="store_true", help="Fail if BOLD validation fails (default: warn and continue)")
    bidsify_p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    bidsify_p.set_defaults(func=lambda args, remaining: cmd_bidsify(args))

    # events
    events_p = subparsers.add_parser("events", help="Behavioral events pipeline")
    events_sub = events_p.add_subparsers(dest="events_command", required=True)

    # events create
    ev_create = events_sub.add_parser("create", help="Generate BIDS _events.tsv from behavioral CSVs")
    ev_create.add_argument("dataset", help="Dataset name")
    ev_create.add_argument("--behavioral-dir", default=None, help="Path to sourcedata behavioral directory")
    ev_create.set_defaults(func=cmd_events_create)

    # events qc
    ev_qc = events_sub.add_parser("qc", help="Run behavioral QC and generate exclusions")
    ev_qc.add_argument("dataset", help="Dataset name")
    ev_qc.add_argument("--behavioral-dir", default=None, help="Path to sourcedata behavioral directory")
    ev_qc.set_defaults(func=cmd_events_qc)

    # events trim
    ev_trim = events_sub.add_parser("trim", help="Trim NIfTIs to match behavioral cutoff")
    ev_trim.add_argument("dataset", help="Dataset name")
    ev_trim.set_defaults(func=cmd_events_trim)

    args, remaining = parser.parse_known_args()
    args.func(args, remaining)
