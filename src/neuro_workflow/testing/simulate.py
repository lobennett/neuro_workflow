"""Thin end-to-end pipeline-simulation driver over a synthetic cohort.

This module is the glue for the CAPSTONE simulation: it chains the *real*
neuro_workflow exclusion stages on a synthetic cohort built by
:func:`neuro_workflow.testing.cohort.make_synthetic_cohort` and returns the
compiled exclusion list plus the rendered ``.bidsignore``.

It deliberately reimplements **no** pipeline logic. Everything load-bearing is
the production code:

  * behavioral exclusions  — :class:`neuro_workflow.exclusions.behavioral.BehavioralGenerator`
    (which runs the real :func:`neuro_workflow.events.qc.run_qc`),
  * motion exclusions      — :class:`neuro_workflow.exclusions.motion.MotionGenerator`
    (which reads the real fmriprep confounds and applies the real thresholds),
  * persistence + merge    — :func:`neuro_workflow.core.exclusions.save_source_entries`
    and :func:`neuro_workflow.core.exclusions.compile_exclusions`,
  * the planted collection block is folded in by the real
    :func:`neuro_workflow.core.exclusions_render.render_bidsignore_with_collection`.

Hermeticity: ``compile_exclusions`` and ``save_source_entries`` write to
package-level ``EXCLUSIONS_DIR`` / ``LOCKFILE_DIR``, and the collection
renderer reads from ``exclusions_render._COLLECTION_DIR``. So a real run would
touch the version-controlled tree. :func:`simulate_exclusions` redirects all
three at module level (restoring them on exit) into tmp / the cohort root, so a
simulation never writes into ``config/exclusions`` or ``data/exclusions``. The
generators and ``compile_exclusions`` themselves run completely unmodified.

This is import-only test support; nothing in production imports from here.
"""

from __future__ import annotations

import contextlib
from argparse import Namespace
from pathlib import Path
from typing import Dict, List, Optional

from neuro_workflow.core import exclusions as _exclusions
from neuro_workflow.core import exclusions_render as _render
from neuro_workflow.core.exclusions import compile_exclusions, save_source_entries
from neuro_workflow.core.exclusions_render import render_bidsignore_with_collection

# Import the generators for their REAL .generate() implementations. Importing
# the modules also registers them in the exclusions registry (side effect of
# `register_generator(...)` at import time), though we call them directly here.
from neuro_workflow.exclusions.behavioral import BehavioralGenerator
from neuro_workflow.exclusions.motion import MotionGenerator

__all__ = ["SimulationResult", "simulate_exclusions"]


class SimulationResult:
    """Container for the output of :func:`simulate_exclusions`.

    Attributes:
        compiled: The compiled exclusion entries (the real
            :func:`compile_exclusions` return value) — a list of dicts each
            carrying ``subject`` / ``session`` / ``task`` / ``run`` / ``source``
            / ``action`` / ``reason``.
        bidsignore: The rendered ``.bidsignore`` text (collection block folded
            in ahead of the generated QC glob lines), or ``None`` when no
            collection block was planted (no ``exclude:collection`` scans).
        behavioral_entries: The raw entries the behavioral generator produced.
        motion_entries: The raw entries the motion generator produced.
        exclusions_dir: The (tmp) directory ``compile_exclusions`` wrote its
            sources/compiled artifacts under, for callers wanting to inspect.
    """

    def __init__(
        self,
        *,
        compiled: List[dict],
        bidsignore: Optional[str],
        behavioral_entries: List[dict],
        motion_entries: List[dict],
        exclusions_dir: Path,
    ) -> None:
        self.compiled = compiled
        self.bidsignore = bidsignore
        self.behavioral_entries = behavioral_entries
        self.motion_entries = motion_entries
        self.exclusions_dir = exclusions_dir

    def excluded_keys(self) -> set:
        """Return the set of ``(subject, session, task, run)`` excluded keys.

        Uses the same field tuple :func:`neuro_workflow.core.exclusions.is_excluded`
        keys on, restricted to entries whose ``action`` is ``exclude`` / ``trim``.
        """
        return {
            (e["subject"], e["session"], e["task"], e["run"])
            for e in self.compiled
            if e.get("action") in ("exclude", "trim")
        }

    def excluded_keys_with_source(self) -> set:
        """Return ``(subject, session, task, run, source)`` for excluded entries."""
        return {
            (e["subject"], e["session"], e["task"], e["run"], e.get("source"))
            for e in self.compiled
            if e.get("action") in ("exclude", "trim")
        }


@contextlib.contextmanager
def _redirect_exclusion_paths(
    exclusions_dir: Path, lockfile_dir: Path, collection_dir: Path
):
    """Temporarily point the exclusions/render module paths at tmp dirs.

    ``compile_exclusions`` / ``save_source_entries`` resolve ``EXCLUSIONS_DIR``
    and ``LOCKFILE_DIR`` at call time from the ``core.exclusions`` module, and
    ``render_bidsignore_with_collection`` resolves the committed collection
    block from ``exclusions_render._COLLECTION_DIR``. We swap all three for the
    duration of the simulation and restore them afterwards so a simulation run
    is hermetic and never writes into the version-controlled tree.
    """
    saved = (
        _exclusions.EXCLUSIONS_DIR,
        _exclusions.LOCKFILE_DIR,
        _render._COLLECTION_DIR,
    )
    _exclusions.EXCLUSIONS_DIR = Path(exclusions_dir)
    _exclusions.LOCKFILE_DIR = Path(lockfile_dir)
    _render._COLLECTION_DIR = Path(collection_dir)
    try:
        yield
    finally:
        (
            _exclusions.EXCLUSIONS_DIR,
            _exclusions.LOCKFILE_DIR,
            _render._COLLECTION_DIR,
        ) = saved


def simulate_exclusions(
    cohort_root: Path,
    manifest: Dict,
    *,
    dataset: str = "sim",
    work_dir: Optional[Path] = None,
) -> SimulationResult:
    """Run the REAL exclusion pipeline over a synthetic cohort.

    Chains, on the cohort built under ``cohort_root`` (whose layout is described
    by ``manifest``, the return value of
    :func:`neuro_workflow.testing.cohort.make_synthetic_cohort`):

      1. the REAL behavioral generator (``events.qc.run_qc`` under the hood),
      2. the REAL motion generator (reads the synthetic fmriprep confounds),
      3. saves each generator's entries via the REAL ``save_source_entries``,
      4. compiles via the REAL ``compile_exclusions``,
      5. folds in the planted collection block via the REAL
         ``render_bidsignore_with_collection``.

    No pipeline logic is reimplemented: this function only wires the dataset
    config and source names the production CLI would supply.

    Args:
        cohort_root: The cohort root passed to ``make_synthetic_cohort`` (the
            BIDS dataset root; derivatives nest under ``<root>/derivatives``).
        manifest: The manifest dict returned by ``make_synthetic_cohort`` (used
            for the fMRIPrep version and the planted collection file path).
        dataset: Logical dataset name for the exclusions store. Must match the
            collection-file stem the cohort wrote (``make_synthetic_cohort``
            writes ``sim_collection.bidsignore``), so the default ``"sim"``
            lines up with ``render_bidsignore_with_collection``'s lookup of
            ``<dataset>_collection.bidsignore``.
        work_dir: Directory for the (hermetic) exclusions store + lockfile. If
            None, a ``_sim_exclusions`` dir is created under ``cohort_root``.

    Returns:
        A :class:`SimulationResult`.
    """
    cohort_root = Path(cohort_root)
    bids_dir = Path(manifest["bids_dir"])
    version = manifest.get("version", "25.2.4")

    if work_dir is None:
        work_dir = cohort_root / "_sim_exclusions"
    work_dir = Path(work_dir)
    exclusions_dir = work_dir / "config_exclusions"
    lockfile_dir = work_dir / "lock"
    exclusions_dir.mkdir(parents=True, exist_ok=True)
    lockfile_dir.mkdir(parents=True, exist_ok=True)

    # The cohort writes its planted collection block to
    # <root>/data/exclusions/<dataset>_collection.bidsignore; point the renderer
    # there. (make_synthetic_cohort hardcodes the "sim_collection" stem.)
    collection_dir = cohort_root / "data" / "exclusions"

    # Minimal dataset_config: exactly the keys the two generators read.
    dataset_config = {"bids_dir": str(bids_dir)}

    # --- run the REAL generators ------------------------------------------
    behavioral_args = Namespace(behavioral_dir=None)
    behavioral_entries = BehavioralGenerator().generate(
        dataset, dataset_config, behavioral_args
    )

    # MotionGenerator reconstructs <bids_dir>/derivatives/fmriprep_{version}
    # from --fmriprep-version; supply the matching version + the real default
    # thresholds (mirrors the CLI defaults via add_cli_args).
    from neuro_workflow.core.thresholds import motion as _motion_thresholds

    t = _motion_thresholds()
    motion_args = Namespace(
        fmriprep_version=version,
        fd_threshold=t["fd_threshold"],
        proportion_fd_threshold=t["proportion_fd_threshold"],
        proportion_dvars_threshold=t["proportion_dvars_threshold"],
    )
    motion_entries = MotionGenerator().generate(dataset, dataset_config, motion_args)

    # --- persist + compile + render, all hermetic -------------------------
    with _redirect_exclusion_paths(exclusions_dir, lockfile_dir, collection_dir):
        # Save each source. save_source_entries validates entries (fail loud)
        # and stamps the per-source _meta block, exactly as the CLI does.
        save_source_entries(dataset, "behavioral-qc", behavioral_entries)
        save_source_entries(dataset, "motion", motion_entries)

        compiled = compile_exclusions(dataset)

        # Fold the planted collection block ahead of the generated QC lines via
        # the real renderer. If no collection block was planted there is no
        # <dataset>_collection.bidsignore, and the renderer would (correctly)
        # raise; only render when the collection file exists.
        collection_file = manifest.get("collection_file")
        if collection_file and Path(collection_file).is_file():
            bidsignore = render_bidsignore_with_collection(dataset, compiled)
        else:
            bidsignore = None

    return SimulationResult(
        compiled=compiled,
        bidsignore=bidsignore,
        behavioral_entries=behavioral_entries,
        motion_entries=motion_entries,
        exclusions_dir=exclusions_dir,
    )
