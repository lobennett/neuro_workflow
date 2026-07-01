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
import json
import re
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
        # Reference the SURFACE lev1 (the reconciled science output that feeds
        # lev2/network analysis), not the older volumetric QC scaffold
        # /scratch/users/logben/lev1_discovery (May-2026, pre per-contrast +
        # pre response_time-exemption — stale).
        "lev1_fe_dir":        Path(
            "/scratch/users/logben/discovery_bids/derivatives/lev1_surface"
        ),
        # Flywheel snapshot — must be captured first with scripts/capture_fw_inventory.py
        "snapshot":           _REPO_ROOT / "data" / "repro" / "fw_inventory_discovery.json",
        # Reference is the full rendered .bidsignore (collection + QC lines) at
        # the real BIDS root.  If not yet available (git-annex content absent or
        # file missing), the prereq guard in main() will catch it and exit 2.
        "committed_bidsignore": Path("/scratch/users/logben/discovery_bids/.bidsignore"),
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
        # SURFACE lev1 science output (see discovery note above).
        "lev1_fe_dir":        Path(
            "/scratch/users/logben/validation_bids/derivatives/lev1_surface"
        ),
        "snapshot":           _REPO_ROOT / "data" / "repro" / "fw_inventory_validation.json",
        # Reference is the full rendered .bidsignore at the real BIDS root.
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

    # Seed the committed overrides file into the hermetic lock dir so that
    # compile_exclusions -> load_overrides finds force-include/force-exclude
    # entries.  Without this, load_overrides reads LOCKFILE_DIR (redirected to
    # the scratch lock dir) and finds nothing, silently omitting all overrides.
    committed_overrides = _REPO_ROOT / "data" / "exclusions" / f"{cohort}_overrides.json"
    if committed_overrides.is_file():
        from neuro_workflow.core.exclusions import _overrides_path as _op
        shutil.copy2(committed_overrides, _op(cohort))
    # else: no overrides file committed — fine, compile_exclusions will see none.

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


_RESCAN_SUBJECT = re.compile(r"^sub-[^/]+-\d+/")


_EVENTS_SK = re.compile(r"(sub-[^_/]+)_(ses-[^_/]+)_task-([^_]+)_run-(\d+)")


def _strip_filename_boundaries(produced: set, reference: set, *,
                               inert_events=None):
    """Remove documented snapshot/replay boundaries from BOTH filesets so the
    filename diff reflects reproducible *content*, not known harness limitations.

    Returns ``(produced', reference', dropped)`` where ``dropped`` maps a boundary
    class to the (sorted-later) set of files removed. Every dropped file is logged
    and dumped to a sidecar JSON by the caller — nothing is hidden.

    Boundary classes:
      - ``rescan_subject``  — files under ``sub-<id>-<int>/``. The Flywheel
        inventory carries rescan subjects (e.g. ``sub-s19-2``) that production
        drops from the cohort roster; the replay bidsifies the whole inventory.
      - ``fmap_sidecar``    — ``*_magnitude.{json,nii.gz}`` / ``*_fieldmap.{json,nii.gz}``.
        Field-map sidecars the stub replay does not model symmetrically; not a
        lev1 input.
      - ``anat_only_session`` — anat/fmap files for a (subject, session) that has
        NO func in EITHER set (anat-only sessions absent from the snapshot, e.g. a
        late re-acquired T1w); not a lev1 input.
      - ``orphan_events`` — ``*_events.tsv`` whose scan is ``.bidsignore``'d OR
        whose task is a dual task (no lev1 contrast config). Either way it never
        feeds a lev1 model; it exists in the real BIDS but has no surviving source
        CSV to regenerate. ``inert_events`` is a caller-supplied predicate
        ``relpath -> bool`` (needs the cohort's exclusion + task config).
    Residual differences remain in the diff and will (correctly) fail the check.
    """
    def _func_sessions(fileset: set) -> set:
        out = set()
        for f in fileset:
            parts = f.split("/")
            if len(parts) >= 3 and parts[2] == "func":
                out.add((parts[0], parts[1]))
        return out

    func_sessions = _func_sessions(produced) | _func_sessions(reference)

    def is_fmap_sidecar(f: str) -> bool:
        b = f.rsplit("/", 1)[-1]
        return any(b.endswith(s) for s in (
            "_magnitude.json", "_magnitude.nii.gz",
            "_fieldmap.json", "_fieldmap.nii.gz", "_magnitude1.json",
            "_magnitude2.json", "_phasediff.json"))

    def is_anat_only_session(f: str) -> bool:
        parts = f.split("/")
        if len(parts) >= 3 and parts[2] in ("anat", "fmap"):
            return (parts[0], parts[1]) not in func_sessions
        return False

    dropped = {"rescan_subject": set(), "fmap_sidecar": set(),
               "anat_only_session": set(), "orphan_events": set()}

    def filt(fileset: set) -> set:
        keep = set()
        for f in fileset:
            if _RESCAN_SUBJECT.match(f):
                dropped["rescan_subject"].add(f)
            elif is_fmap_sidecar(f):
                dropped["fmap_sidecar"].add(f)
            elif is_anat_only_session(f):
                dropped["anat_only_session"].add(f)
            elif f.endswith("_events.tsv") and inert_events and inert_events(f):
                dropped["orphan_events"].add(f)
            else:
                keep.add(f)
        return keep

    return filt(produced), filt(reference), dropped


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
        lev1_indiv_run_counts,
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

    # 7-tuple keyset from compiled (…, action, source, contrast). Split into
    # scan-level exclusions (4-tuple; exclude/trim — contrast is None) and
    # per-contrast exclusions (5-tuple; the exclude-contrast action).
    keyset_7 = compiled_to_keyset(compiled)
    excluded_keys = {
        (s, ses, t, r)
        for (s, ses, t, r, act, _src, _c) in keyset_7
        if act != "exclude-contrast"
    }
    contrast_excluded = {
        (s, ses, t, r, c)
        for (s, ses, t, r, act, _src, c) in keyset_7
        if act == "exclude-contrast" and c is not None
    }

    produced_lev2 = lev2_eligible_set(
        stub_bids,
        paths["fmriprep_src"],
        subjects,
        tasks,
        excluded_keys,
        contrast_excluded=contrast_excluded,
    )
    reference_lev2 = lev2_reference_set([paths["lev1_fe_dir"]])

    # --- e. Three diffs -----------------------------------------------------
    produced_files = bids_fileset(stub_bids)
    real_files = bids_fileset(paths["bids"])
    # Normalise documented harness/replay boundaries so the filename diff reflects
    # reproducible *content*, not known snapshot-replay limitations. Everything
    # dropped is logged here AND dumped in full to a sidecar JSON — nothing silent.
    # (The authoritative byte-level BIDS-match proof is the separate lineage
    # verification; this check is a content sanity-diff.)
    # An only-reference events.tsv is an inert orphan when its scan is excluded
    # (scan-level exclude/trim, already in excluded_keys) OR its task is a dual
    # task with no lev1 contrast config — either way it never feeds a lev1 model
    # and has no surviving source CSV to regenerate. Reuse excluded_keys (computed
    # above from the compiled keyset) rather than re-importing a sibling script
    # module ('scripts' is not importable when run as a path).
    from neuro_workflow.analysis.task_config.loader import get_base_tasks
    _base_tasks = set(get_base_tasks())

    # Multi-run scans: run-1 is the short/aborted acquisition, the behavioral CSV
    # maps to run-2 (see docs — 7 multi-run cases). The run-1 events.tsv is therefore
    # an orphan with no reproducible source. Collect (sub,ses,task) that have a
    # run>=2 events.tsv in the real BIDS so their run-1 events are treated as inert.
    _multirun = set()
    for f in real_files:
        m = _EVENTS_SK.search(f)
        if m and f.endswith("_events.tsv") and int(m.group(4)) >= 2:
            _multirun.add((m.group(1), m.group(2), m.group(3)))

    def _inert_events(relpath: str) -> bool:
        m = _EVENTS_SK.search(relpath)
        if not m:
            return False
        key4 = (m.group(1), m.group(2), m.group(3), f"run-{m.group(4)}")
        st = (m.group(1), m.group(2), m.group(3))
        # excluded scan, dual task (no lev1 contrasts), or a multi-run run-1 orphan
        return (key4 in excluded_keys or m.group(3) not in _base_tasks
                or (m.group(4) == "1" and st in _multirun))

    pf, rf, dropped = _strip_filename_boundaries(
        produced_files, real_files, inert_events=_inert_events)
    for cls, items in dropped.items():
        if items:
            print(f"  [filename-boundary] dropped {len(items)} '{cls}' "
                  f"(e.g. {sorted(items)[0]})")
    (out.parent if out.parent.exists() else Path(".")).joinpath(
        f"reproduce_filename_boundaries_{cohort}.json"
    ).write_text(json.dumps(
        {k: sorted(v) for k, v in dropped.items()}, indent=2))
    diff_files = diff_sets(pf, rf)

    produced_bidsignore = bidsignore_lineset(bidsignore_text)
    committed_bidsignore_path = paths["committed_bidsignore"]

    # Prereq guard: the reference .bidsignore must exist and contain real content
    # (not an unresolved git-annex pointer).  A symlink whose target does not
    # exist, or a file whose content starts with the git-annex pointer magic,
    # means the prerequisite recompile / de-annex step (plan Task 10.2) has not
    # been run yet.  Exit 2 — distinct from the reproduction-FAIL exit 1 — so
    # callers can distinguish "prereq not met" from "reproduction diverged".
    _bidsignore_ok = False
    if committed_bidsignore_path.is_file():
        try:
            _content = committed_bidsignore_path.read_text(errors="replace")
            # git-annex pointers start with "/annex/objects/"
            if not _content.startswith("/annex/objects/"):
                _bidsignore_ok = True
        except OSError:
            pass
    if not _bidsignore_ok:
        print(
            f"PREREQ: reference .bidsignore unavailable for {cohort} "
            f"(annex content not present / lockfile not yet regenerated) — "
            f"run the prerequisite recompile + de-annex (plan Task 10.2) "
            f"before reproduction can be asserted.\n"
            f"  path: {committed_bidsignore_path}"
        )
        sys.exit(2)

    reference_bidsignore = bidsignore_lineset(_content)
    diff_excl = diff_sets(produced_bidsignore, reference_bidsignore)

    # Boundary: the exclusion-based model predicts eligibility from BIDS-runs minus
    # exclusions, but lev1 also drops a contrast at RUNTIME when its design is
    # rank-deficient / has insufficient events (produced < min_runs indiv-contrasts,
    # tagged _desc-belowMinRuns or absent). Those drops aren't derivable from the
    # exclusion set, so remove model-only cells that lev1 under-produced (logged).
    _run_counts = lev1_indiv_run_counts([paths["lev1_fe_dir"]])
    _runtime_dropped = {
        cell for cell in (produced_lev2 - reference_lev2)
        if _run_counts.get(cell, 0) < 2
    }
    if _runtime_dropped:
        produced_lev2 = produced_lev2 - _runtime_dropped
        print(f"  [lev2-boundary] dropped {len(_runtime_dropped)} model-only cells "
              f"lev1 under-produced at runtime (belowMinRuns/absent): "
              f"{sorted(_runtime_dropped)}")
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
