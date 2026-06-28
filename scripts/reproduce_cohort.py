"""reproduce_cohort.py — End-to-end cohort reproduction CLI.

Wires the testing.reproduce units into a full Flywheel-snapshot → BIDS →
exclusions → lev2-eligible diff pipeline for a real cohort (discovery or
validation).  Running this CLI is a LIVE operation: it reads the real fMRIPrep
derivatives, behavioral data, and lev1 outputs and compares them against the
committed exclusion lockfile and lev1 fixed-effects maps.

Usage::

    uv run python scripts/reproduce_cohort.py discovery --out /tmp/rep.md
    uv run python scripts/reproduce_cohort.py validation --out /tmp/rep.md

Exit code 0 when the first line of the report contains "PASS"; 1 otherwise.

Real inputs required (Sherlock):
- The Flywheel snapshot JSON (``data/repro/fw_inventory_{cohort}.json``).
- The real fMRIPrep derivatives directory.
- The real behavioral sourcedata directory (OAK).
- The real lev1 fixed-effects outputs (for the lev2-eligible reference set).

This script NEVER writes to the committed data/exclusions or config/exclusions
trees — the hermetic _redirect_exclusion_paths seam is applied so all
generator I/O goes to a scratch work dir.
"""

from __future__ import annotations

import argparse
import sys
import types
from argparse import Namespace
from pathlib import Path

# ---------------------------------------------------------------------------
# Per-cohort canonical paths on Sherlock
# ---------------------------------------------------------------------------

# Repository root: two levels up from this script (scripts/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_FMRIPREP_VERSION = "25.2.4"
_OAK_BEHAVIORAL = Path(
    "/oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior"
)

_COHORT_PATHS: dict[str, dict] = {
    "discovery": {
        "bids":               Path("/scratch/users/logben/discovery_bids"),
        "fmriprep_version":   _FMRIPREP_VERSION,
        "fmriprep_src":       Path(
            "/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4"
        ),
        "behavioral":         _OAK_BEHAVIORAL,
        "lev1_outliers_csv":  Path(
            "/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv"
        ),
        "decisions_tsv":      _REPO_ROOT / "config" / "manifests" / "qc_decisions.tsv",
        "lev1_fe_dir":        Path("/scratch/users/logben/lev1_discovery"),
        # Flywheel snapshot — must be captured first with scripts/capture_fw_inventory.py
        "snapshot":           _REPO_ROOT / "data" / "repro" / "fw_inventory_discovery.json",
        # TODO: replace with the regenerated real .bidsignore after the
        # prerequisite validation-cohort lockfile recompile is done.  Until
        # then we read the committed discovery_collection.bidsignore as the
        # reference for the collection block (the render with QC lines will
        # come from the hermetic compile run here).
        "committed_bidsignore": _REPO_ROOT / "data" / "exclusions" / "discovery_collection.bidsignore",
    },
    "validation": {
        "bids":               Path("/scratch/users/logben/validation_bids"),
        "fmriprep_version":   _FMRIPREP_VERSION,
        "fmriprep_src":       Path(
            "/scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4"
        ),
        "behavioral":         _OAK_BEHAVIORAL,
        "lev1_outliers_csv":  Path(
            "/scratch/users/logben/qa_lev1_validation/lev1_outliers.csv"
        ),
        "decisions_tsv":      _REPO_ROOT / "config" / "manifests" / "qc_decisions.tsv",
        "lev1_fe_dir":        Path("/scratch/users/logben/lev1_validation"),
        "snapshot":           _REPO_ROOT / "data" / "repro" / "fw_inventory_validation.json",
        "committed_bidsignore": Path("/scratch/users/logben/validation_bids/.bidsignore"),
    },
}


# ---------------------------------------------------------------------------
# Hermetic seam (mirrors testing.simulate._redirect_exclusion_paths)
# ---------------------------------------------------------------------------

import contextlib

from neuro_workflow.core import exclusions as _excl_mod
from neuro_workflow.core import exclusions_render as _render_mod


@contextlib.contextmanager
def _hermetic_exclusion_paths(work_dir: Path):
    """Redirect all generator I/O to ``work_dir`` for the duration of a ``with`` block.

    Saves and restores the three module-level path globals that
    ``save_source_entries``, ``compile_exclusions``, and
    ``render_bidsignore_with_collection`` resolve at call time, so the CLI
    never touches the committed config/exclusions or data/exclusions trees.
    """
    excl_dir = work_dir / "config_exclusions"
    lock_dir = work_dir / "lock"
    coll_dir = work_dir / "collection"
    excl_dir.mkdir(parents=True, exist_ok=True)
    lock_dir.mkdir(parents=True, exist_ok=True)
    coll_dir.mkdir(parents=True, exist_ok=True)

    saved = (
        _excl_mod.EXCLUSIONS_DIR,
        _excl_mod.LOCKFILE_DIR,
        _render_mod._COLLECTION_DIR,
    )
    _excl_mod.EXCLUSIONS_DIR = excl_dir
    _excl_mod.LOCKFILE_DIR = lock_dir
    _render_mod._COLLECTION_DIR = coll_dir
    try:
        yield coll_dir
    finally:
        (
            _excl_mod.EXCLUSIONS_DIR,
            _excl_mod.LOCKFILE_DIR,
            _render_mod._COLLECTION_DIR,
        ) = saved


# ---------------------------------------------------------------------------
# Flywheel install seam (matches tests/bidsify/test_fake_flywheel_e2e.py)
# ---------------------------------------------------------------------------

def _make_install_flywheel():
    """Return an install_flywheel callable that stubs ``flywheel.Client``.

    Uses ``sys.modules`` injection (same pattern as the bidsify e2e tests),
    so the real flywheel SDK is NOT required on the SLURM node.
    """
    def _install(fake_client):
        stub = types.ModuleType("flywheel")
        stub.Client = lambda *a, **k: fake_client  # type: ignore[attr-defined]
        sys.modules["flywheel"] = stub

    return _install


# ---------------------------------------------------------------------------
# All-5-generators exclusion run
# ---------------------------------------------------------------------------

def _run_all_generators(
    cohort: str,
    bids_dir: Path,
    paths: dict,
    coll_dir: Path,
) -> tuple[list[dict], str]:
    """Run all 5 exclusion generators under the hermetic seam already active.

    ``coll_dir`` is the redirected ``_COLLECTION_DIR`` — we copy the committed
    collection .bidsignore there so ``render_bidsignore_with_collection`` finds
    ``<cohort>_collection.bidsignore`` in the scratch tree instead of the real one.

    Returns (compiled entries, rendered bidsignore text).
    """
    import shutil

    from neuro_workflow.core.exclusions import compile_exclusions, save_source_entries
    from neuro_workflow.core.exclusions_render import render_bidsignore_with_collection
    from neuro_workflow.core.thresholds import lev1_outlier as _lev1_thresh
    from neuro_workflow.core.thresholds import motion as _motion_thresh
    from neuro_workflow.exclusions.behavioral import BehavioralGenerator
    from neuro_workflow.exclusions.collection import CollectionGenerator
    from neuro_workflow.exclusions.lev1_outlier import Lev1OutlierGenerator
    from neuro_workflow.exclusions.motion import MotionGenerator
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator

    dataset_config = {"bids_dir": str(bids_dir)}

    # Copy the committed collection .bidsignore into the scratch collection dir
    # so the renderer finds ``{cohort}_collection.bidsignore`` there.
    committed_coll = _REPO_ROOT / "data" / "exclusions" / f"{cohort}_collection.bidsignore"
    if committed_coll.is_file():
        shutil.copy2(committed_coll, coll_dir / f"{cohort}_collection.bidsignore")
    else:
        print(
            f"WARNING: committed collection file not found: {committed_coll}. "
            "The collection generator and renderer will find nothing."
        )

    # 1. Behavioral
    behavioral_args = Namespace(
        behavioral_dir=str(paths["behavioral"]) if paths["behavioral"].is_dir() else None,
    )
    behavioral_entries = BehavioralGenerator().generate(cohort, dataset_config, behavioral_args)
    save_source_entries(cohort, "behavioral-qc", behavioral_entries)

    # 2. Motion
    mt = _motion_thresh()
    motion_args = Namespace(
        fmriprep_version=paths["fmriprep_version"],
        fd_threshold=mt["fd_threshold"],
        proportion_fd_threshold=mt["proportion_fd_threshold"],
        proportion_dvars_threshold=mt["proportion_dvars_threshold"],
    )
    motion_entries = MotionGenerator().generate(cohort, dataset_config, motion_args)
    save_source_entries(cohort, "motion", motion_entries)

    # 3. QA decisions
    decisions_tsv = paths["decisions_tsv"]
    if decisions_tsv.is_file():
        qa_args = Namespace(decisions_tsv=decisions_tsv)
        qa_entries = QADecisionsGenerator().generate(cohort, dataset_config, qa_args)
        save_source_entries(cohort, "qa_decisions", qa_entries)
    else:
        print(f"qa_decisions: TSV absent ({decisions_tsv}); skipping (0 entries)")

    # 4. Lev1 outlier
    lev1_csv = paths["lev1_outliers_csv"]
    if lev1_csv.is_file():
        lt = _lev1_thresh()
        lev1_args = Namespace(
            lev1_outliers_csv=lev1_csv,
            combined_vif=lt["combined_vif"],
            combined_outlier_pct=lt["combined_outlier_pct"],
            strict_vif=lt["strict_vif"],
            strict_outlier_pct=lt["strict_outlier_pct"],
        )
        lev1_entries = Lev1OutlierGenerator().generate(cohort, dataset_config, lev1_args)
        save_source_entries(cohort, "lev1_outlier", lev1_entries)
    else:
        print(f"lev1_outlier: CSV absent ({lev1_csv}); skipping (0 entries)")

    # 5. Collection (reads the scratch copy of the collection .bidsignore)
    coll_args = Namespace()
    coll_entries = CollectionGenerator().generate(cohort, dataset_config, coll_args)
    save_source_entries(cohort, "collection", coll_entries)

    # Compile (write to scratch)
    compiled = compile_exclusions(cohort, bids_dir=str(bids_dir))

    # Render full .bidsignore (collection block + QC lines)
    try:
        bidsignore_text = render_bidsignore_with_collection(cohort, compiled)
    except FileNotFoundError as exc:
        print(f"WARNING: {exc}; bidsignore diff will be empty")
        bidsignore_text = ""

    return compiled, bidsignore_text


# ---------------------------------------------------------------------------
# Main reproduction logic
# ---------------------------------------------------------------------------

def _subjects_from_spec(spec) -> list[str]:
    """Return ``sub-{label}`` subject strings from a FlywheelCohortSpec."""
    return [f"sub-{s.label}" for s in spec.subjects]


def _tasks_from_bids(bids_dir: Path) -> list[str]:
    """Discover task names from BOLD filenames in a BIDS directory.

    Scans ``sub-*/ses-*/func/*_task-*_*_bold.nii.gz`` and extracts unique task
    names, then intersects with the canonical battery (base + dual) to filter
    noise.  Falls back to the full base battery if no BOLD files are found.
    """
    from neuro_workflow.analysis.task_config.loader import get_base_tasks, get_dual_tasks

    all_tasks = set(get_base_tasks()) | set(get_dual_tasks())
    found: set[str] = set()
    for bold in bids_dir.glob("sub-*/ses-*/func/*_bold.nii.gz"):
        for part in bold.name.split("_"):
            if part.startswith("task-"):
                task = part[5:]  # strip "task-"
                if task in all_tasks:
                    found.add(task)
    if not found:
        print("WARNING: no BOLD task files found in BIDS dir; using base battery as task list")
        return get_base_tasks()
    return sorted(found)


def main(cohort: str, out: Path) -> None:
    """Reproduce the given cohort and write a diff report to ``out``.

    Orchestration only — every load-bearing step calls production code.

    Steps:
        a. Replay FW snapshot → stub BIDS (via make_fake_flywheel + replay_to_bids).
        b. Stage real fMRIPrep metrics into the stub tree.
        c. Run all 5 generators under the hermetic seam; compile; render .bidsignore.
        d. Compute lev2-eligible set from produced vs reference.
        e. Three diffs (filenames / exclusions / lev2); build report; write.
    """
    import tempfile

    from neuro_workflow.testing.reproduce.canonical import (
        bids_fileset,
        bidsignore_lineset,
        compiled_to_keyset,
    )
    from neuro_workflow.testing.reproduce.lev2_select import (
        lev2_eligible_set,
        lev2_reference_set,
    )
    from neuro_workflow.testing.reproduce.replay import replay_to_bids
    from neuro_workflow.testing.reproduce.report import build_report, diff_sets
    from neuro_workflow.testing.reproduce.snapshot import load_inventory
    from neuro_workflow.testing.reproduce.stage_metrics import stage_metrics

    paths = _COHORT_PATHS[cohort]

    # --- a. Replay FW snapshot -> stub BIDS ---------------------------------
    print(f"[reproduce_cohort] loading inventory: {paths['snapshot']}")
    spec = load_inventory(paths["snapshot"])
    subjects = _subjects_from_spec(spec)
    print(f"  {len(subjects)} subjects: {subjects}")

    scratch_root = Path(tempfile.mkdtemp(prefix=f"repro_{cohort}_"))
    print(f"  scratch root: {scratch_root}")

    install_flywheel = _make_install_flywheel()
    stub_bids = replay_to_bids(
        spec,
        scratch_root,
        sample_name=cohort,
        behavioral_dir=paths["behavioral"],
        install_flywheel=install_flywheel,
    )
    print(f"  stub BIDS produced: {stub_bids}")

    # --- b. Stage real fMRIPrep metrics into the stub tree ------------------
    print("[reproduce_cohort] staging real fMRIPrep derivatives…")
    staged = stage_metrics(
        stub_bids,
        fmriprep_src=paths["fmriprep_src"],
        version=paths["fmriprep_version"],
    )
    print(f"  staged: {staged}")

    # --- c. All 5 generators under the hermetic seam ------------------------
    print("[reproduce_cohort] running all 5 exclusion generators (hermetic)…")
    work_dir = scratch_root / "_excl_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    with _hermetic_exclusion_paths(work_dir) as coll_dir:
        compiled, bidsignore_text = _run_all_generators(
            cohort, stub_bids, paths, coll_dir,
        )

    print(f"  compiled: {len(compiled)} entries")

    # --- d. Lev2-eligible set -----------------------------------------------
    tasks = _tasks_from_bids(stub_bids)
    print(f"  tasks discovered: {tasks}")

    # 6-tuple keyset from compiled; derive bare 4-tuple excluded_keys
    keyset_6 = compiled_to_keyset(compiled)
    excluded_keys = {(s, ses, t, r) for (s, ses, t, r, _act, _src) in keyset_6}

    produced_lev2 = lev2_eligible_set(
        stub_bids,
        paths["fmriprep_src"],
        subjects,
        tasks,
        excluded_keys,
    )
    reference_lev2 = lev2_reference_set([paths["lev1_fe_dir"]])

    # --- e. Three diffs -----------------------------------------------------
    produced_files = bids_fileset(stub_bids)
    real_files = bids_fileset(paths["bids"])
    diff_files = diff_sets(produced_files, real_files)

    produced_bidsignore = bidsignore_lineset(bidsignore_text)
    committed_bidsignore_path = paths["committed_bidsignore"]
    if committed_bidsignore_path.is_file():
        reference_bidsignore = bidsignore_lineset(committed_bidsignore_path.read_text())
    else:
        print(f"WARNING: committed .bidsignore not found: {committed_bidsignore_path}")
        reference_bidsignore = set()
    diff_excl = diff_sets(produced_bidsignore, reference_bidsignore)

    diff_lev2 = diff_sets(produced_lev2, reference_lev2)

    # --- f. Report ----------------------------------------------------------
    from neuro_workflow.core.thresholds import config_version

    provenance = {
        "cohort": cohort,
        "snapshot": str(paths["snapshot"]),
        "fmriprep_version": paths["fmriprep_version"],
        "scratch_root": str(scratch_root),
        "config_version": config_version(),
        "n_subjects": len(subjects),
        "n_compiled_entries": len(compiled),
        "n_tasks": len(tasks),
    }
    report = build_report(cohort, diff_files, diff_excl, diff_lev2, provenance=provenance)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(f"[reproduce_cohort] report written to {out}")
    print(f"  result: {report.splitlines()[0]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce a cohort from a Flywheel snapshot and diff the "
            "produced BIDS/exclusions/lev2-eligible set against the real data."
        )
    )
    parser.add_argument(
        "cohort",
        choices=list(_COHORT_PATHS.keys()),
        help="Which cohort to reproduce (discovery or validation).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reproduce_report.md"),
        help="Path to write the Markdown reproduction report (default: reproduce_report.md).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    main(args.cohort, args.out)
    # Read the first line to determine exit code.
    report_text = args.out.read_text()
    sys.exit(0 if "PASS" in report_text.splitlines()[0] else 1)
