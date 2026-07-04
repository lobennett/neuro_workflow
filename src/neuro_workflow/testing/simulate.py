"""Thin end-to-end pipeline-simulation drivers.

Two drivers live here, both orchestration-only (they reimplement **no**
pipeline logic):

  * :func:`simulate_exclusions` — chains the *real* neuro_workflow exclusion
    stages on a synthetic cohort built by
    :func:`neuro_workflow.testing.cohort.make_synthetic_cohort` (synthetic BIDS
    is the start point) and returns the compiled exclusion list + rendered
    ``.bidsignore``.
  * :func:`simulate_full_pipeline` — the FULL Flywheel -> lev1 chain. It drives
    the REAL stages in order: FakeFlywheel -> ``run_bidsify`` -> BIDS; sourcedata
    raw-jsPsych CSVs -> the REAL ``events.create`` -> events.tsv; the
    fMRIPrep-derivative stub (a planted contrast in a keep scan); the REAL
    behavioral + motion generators -> ``compile_exclusions`` -> ``.bidsignore``
    (delegated to :func:`simulate_exclusions`); and the REAL lev1 components on
    the keep scan. It returns a manifest (BIDS produced, compiled exclusions,
    lev1 recovered contrast).

The shared exclusion glue below is the CAPSTONE simulation core.

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

from neuro_workflow.core import exclusions as _exclusions
from neuro_workflow.core import exclusions_render as _render
from neuro_workflow.core.exclusions import compile_exclusions, save_source_entries
from neuro_workflow.core.exclusions_render import render_bidsignore_with_collection

# Import the generators for their REAL .generate() implementations. Importing
# the modules also registers them in the exclusions registry (side effect of
# `register_generator(...)` at import time), though we call them directly here.
from neuro_workflow.exclusions.behavioral import BehavioralGenerator
from neuro_workflow.exclusions.motion import MotionGenerator

__all__ = [
    "SimulationResult",
    "simulate_exclusions",
    "FullPipelineResult",
    "simulate_full_pipeline",
]


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
        compiled: list[dict],
        bidsignore: str | None,
        behavioral_entries: list[dict],
        motion_entries: list[dict],
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
def _redirect_exclusion_paths(exclusions_dir: Path, lockfile_dir: Path, collection_dir: Path):
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
    manifest: dict,
    *,
    dataset: str = "sim",
    work_dir: Path | None = None,
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
    behavioral_entries = BehavioralGenerator().generate(dataset, dataset_config, behavioral_args)

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


# =========================================================================== #
# Full Flywheel -> lev1 driver.
# =========================================================================== #


class FullPipelineResult:
    """Result of :func:`simulate_full_pipeline` — the whole-chain manifest.

    Attributes:
        manifest: A dict describing the produced dataset. Keys:

            * ``bids_dir`` / ``fmriprep_dir`` (str paths),
            * ``version`` (fMRIPrep version),
            * ``scans``: one dict per produced func scan with ``subject`` /
              ``session`` / ``task`` / ``run`` (BIDS-prefixed forms, e.g.
              ``sub-s01`` / ``ses-01`` / ``flanker`` / ``run-1``), ``outcome``,
              ``plant_contrast``, plus the resolved ``events`` /
              ``beh_csv`` / ``mni_data`` paths.
        exclusions: The :class:`SimulationResult` from the REAL exclusion stage
            (compiled entries + rendered ``.bidsignore`` + hermetic dir).
        recovery_scan: The single keep scan dict (from ``manifest['scans']``)
            into which the known contrast was planted, or ``None`` if the spec
            planted none.
        recovered_contrast: The lev1-recovered mean ``incongruent-congruent``
            effect for ``recovery_scan`` (float), or ``None``.
    """

    def __init__(
        self,
        *,
        manifest: dict,
        exclusions: SimulationResult,
        recovery_scan: dict | None,
        recovered_contrast: float | None,
    ) -> None:
        self.manifest = manifest
        self.exclusions = exclusions
        self.recovery_scan = recovery_scan
        self.recovered_contrast = recovered_contrast


# The planted GLM betas for the lev1 recovery scan (matches the dataset-sim
# capstone): incongruent - congruent == +5.0 on top of a 100.0 baseline.
_PLANTED_BETAS = {"incongruent": 10.0, "congruent": 5.0, "constant": 100.0}
_PLANTED_EFFECT = _PLANTED_BETAS["incongruent"] - _PLANTED_BETAS["congruent"]


def _map_spec_to_bids_scans(spec) -> list[dict]:
    """Compute each func acquisition's produced BIDS (sub, ses, task, run).

    Reproduces ``bidsify/run.py``'s numbering WITHOUT running it: sessions are
    numbered ``ses-01..`` by ascending timestamp; within a session, multiple
    acquisitions of the same task are numbered ``run-1..`` by ascending
    timestamp. (Alias/override semantics are not modeled — the full-chain spec
    uses plain subject labels, exactly as the bidsify-e2e ``_basic_spec``.)

    Returns one record per FUNC acquisition (anat/fmap/dwi/unknown skipped),
    carrying the planted ``outcome`` / ``plant_contrast`` / ``n_trs`` so the
    driver can plant the matching sourcedata + derivatives.
    """
    from neuro_workflow.bidsify.config import map_acquisition

    records: list[dict] = []
    for subj in spec.subjects:
        sub = f"sub-{subj.label}"
        sessions_sorted = sorted(subj.sessions, key=lambda s: (s.timestamp or "", s.label))
        for ses_idx, sess in enumerate(sessions_sorted, start=1):
            ses = f"ses-{ses_idx:02d}"
            # Group this session's func acqs by task, number runs by timestamp.
            func_acqs = []
            for acq in sess.acquisitions:
                mapping = map_acquisition(acq.label)
                if not mapping or mapping["modality"] != "func":
                    continue
                func_acqs.append((acq, mapping["task"]))

            # Per-task run numbering by ascending acq timestamp.
            by_task: dict[str, list] = {}
            for acq, task in func_acqs:
                by_task.setdefault(task, []).append(acq)
            for task, acqs in by_task.items():
                acqs_sorted = sorted(acqs, key=lambda a: (a.timestamp or "", a.label))
                for run_idx, acq in enumerate(acqs_sorted, start=1):
                    records.append(
                        {
                            "subject": sub,
                            "session": ses,
                            "task": task,
                            "run": f"run-{run_idx}",
                            "outcome": getattr(acq, "outcome", "keep"),
                            "plant_contrast": getattr(acq, "plant_contrast", False),
                            "n_trs": getattr(acq, "n_trs", 10),
                        }
                    )
    return records


def simulate_full_pipeline(
    spec,
    root: Path,
    *,
    dataset: str = "sim",
    version: str = "25.2.4",
    seed: int = 0,
    install_flywheel=None,
) -> FullPipelineResult:
    """Drive the WHOLE Flywheel -> lev1 chain on a fake Flywheel project.

    Orchestration only — every load-bearing step is production code:

      1. **FakeFlywheel -> run_bidsify -> BIDS.** Builds a fake client from
         ``spec`` (:func:`neuro_workflow.testing.fake_flywheel.make_fake_flywheel`),
         installs it as ``flywheel.Client`` via ``install_flywheel`` (the test's
         monkeypatch seam), and runs the production ``run_bidsify`` for each
         subject. The produced BIDS tree is the real output of bidsify.
      2. **sourcedata + events.create -> events.tsv.** Writes a raw-jsPsych CSV
         (``testing.raw_jspsych.make_raw_jspsych_csv``) per scan to
         ``<bids>/sourcedata/...`` (clean unless ``exclude:behavioral``), then
         runs the production ``events.create.run_create_events`` to emit BIDS
         events.tsv files.
      3. **fMRIPrep-derivative stub.** Plants a confounds TSV + preproc BOLD per
         scan (``testing.synthetic.make_fmriprep_run``; ``motion='high'`` for
         ``exclude:motion``), and overwrites the planted-contrast keep scan's
         BOLD with a known incongruent-congruent contrast.
      4. **Exclusions.** Delegates to :func:`simulate_exclusions` over the
         produced tree — the REAL behavioral + motion generators ->
         ``compile_exclusions`` -> ``render_bidsignore_with_collection``.
      5. **lev1.** Discovers the planted-contrast keep scan via the REAL
         ``FileFinder``, builds the design via the REAL lev1 events path +
         ``create_design_matrix``, fits via ``fit_run_glm``, and recovers the
         contrast via ``compute_run_contrasts``.

    Args:
        spec: A :class:`neuro_workflow.testing.fake_flywheel.FlywheelCohortSpec`
            whose func acquisitions carry ``outcome`` / ``plant_contrast`` tags.
        root: Root dir for the simulation (created). BIDS is ``<root>/bids``;
            derivatives nest under ``<root>/bids/derivatives``.
        dataset: Logical dataset name for the exclusions store (default
            ``"sim"`` — matches the collection-file stem written here).
        version: fMRIPrep version; derivatives land in
            ``<bids>/derivatives/fmriprep_{version}``.
        seed: Base RNG seed; each scan gets a distinct derived seed.
        install_flywheel: Callable that installs the built fake client as
            ``flywheel.Client`` (the test passes its ``patch_flywheel`` setter).
            Required — there is no global monkeypatch here so the seam stays in
            the test.

    Returns:
        A :class:`FullPipelineResult`.

    Raises:
        ValueError: if ``install_flywheel`` is None, or the spec declares more
            than one ``plant_contrast`` scan.
    """
    if install_flywheel is None:
        raise ValueError(
            "install_flywheel is required (the test's flywheel.Client setter); "
            "the driver never monkeypatches globally so the seam stays explicit"
        )

    # Local imports keep this module cheap to import (heavy deps only on use).
    import nibabel as nib
    import numpy as np
    import pandas as pd

    from neuro_workflow.analysis.io.file_discovery import FileFinder
    from neuro_workflow.analysis.lev1.processing.contrasts import (
        compute_run_contrasts,
    )
    from neuro_workflow.analysis.lev1.processing.design import create_design_matrix
    from neuro_workflow.analysis.lev1.processing.events import (
        add_junk_trials,
        preprocess_events,
    )
    from neuro_workflow.analysis.lev1.processing.glm import fit_run_glm
    from neuro_workflow.analysis.task_config.loader import (
        get_task_contrasts,
        get_task_parameters,
    )
    from neuro_workflow.bidsify.run import run_bidsify
    from neuro_workflow.events.create import run_create_events
    from neuro_workflow.testing.fake_flywheel import make_fake_flywheel
    from neuro_workflow.testing.raw_jspsych import EXP_ID, make_raw_jspsych_csv
    from neuro_workflow.testing.synthetic import (
        as_4d_nifti,
        make_fmriprep_run,
        make_mask,
        plant_bold,
    )

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    bids_dir = root / "bids"
    fmriprep_dir = bids_dir / "derivatives" / f"fmriprep_{version}"
    sourcedata_dir = bids_dir / "sourcedata"

    # --- 1. FakeFlywheel -> run_bidsify -> BIDS ---------------------------
    fake = make_fake_flywheel(spec)
    install_flywheel(fake)
    subject_labels = [s.label for s in spec.subjects]
    run_bidsify("discovery", output_dir=bids_dir, subjects=subject_labels, overwrite=True)

    # Map each spec func acquisition to its produced BIDS (sub, ses, task, run).
    scans = _map_spec_to_bids_scans(spec)
    plant_scans = [s for s in scans if s["plant_contrast"]]
    if len(plant_scans) > 1:
        raise ValueError(f"at most one plant_contrast scan supported; got {len(plant_scans)}")

    # --- 2. sourcedata raw-jsPsych CSVs + REAL events.create --------------
    collection_lines: list[str] = []
    scan_seed = seed
    for scan in scans:
        scan_seed += 1
        sub, ses = scan["subject"], scan["session"]
        task, run = scan["task"], scan["run"]
        run_num = run.split("-", 1)[1]
        prefix = f"{sub}_{ses}_task-{task}_{run}"

        # Behavioral CSV (raw jsPsych shape). For supported tasks, write a raw
        # export; high-omission / slow-go only for exclude:behavioral. For tasks
        # without a raw-jsPsych synth (e.g. goNogo here), no behavioral CSV is
        # written — those scans are excluded by other layers (collection) and
        # the events stage simply finds no CSV for them.
        beh_csv = None
        if task in EXP_ID:
            beh_dir = sourcedata_dir / sub / ses / "beh"
            beh_csv = beh_dir / f"{prefix}_beh.csv"
            if scan["outcome"] == "exclude:behavioral":
                if task == "stopSignal":
                    beh_params = {"go_rt_ms": 1200.0}
                else:
                    beh_params = {"omission_rate": 0.5}
            else:
                beh_params = {}
            make_raw_jspsych_csv(beh_csv, task, n_trials=40, seed=scan_seed, **beh_params)
        scan["beh_csv"] = str(beh_csv) if beh_csv else None

        # fMRIPrep derivative stub (clean unless exclude:motion).
        motion = "high" if scan["outcome"] == "exclude:motion" else "clean"
        written = make_fmriprep_run(
            fmriprep_dir,
            sub.replace("sub-", ""),
            ses.replace("ses-", ""),
            task,
            run_num,
            space="MNI",
            n_trs=scan["n_trs"],
            version=version,
            motion=motion,
            seed=scan_seed,
        )
        scan["mni_data"] = str(written["mni_data"])
        scan["events"] = str(bids_dir / sub / ses / "func" / f"{prefix}_events.tsv")

        # Collection glob for exclude:collection scans (committed-collection
        # .bidsignore style — covers every echo of the run).
        if scan["outcome"] == "exclude:collection":
            collection_lines.append(f"{sub}/{ses}/func/{prefix}_echo-*_bold.*")

    # REAL events generation: walks sourcedata CSVs, discovers BIDS func NIfTIs,
    # writes events.tsv into the produced BIDS func dirs.
    run_create_events(behavioral_dir=sourcedata_dir, bids_dir=bids_dir)

    # --- 3b. Plant the known contrast into the keep scan's preproc BOLD ----
    recovery_scan = plant_scans[0] if plant_scans else None
    recovered_contrast = None
    if recovery_scan is not None:
        task = recovery_scan["task"]
        n_trs = recovery_scan["n_trs"]
        tr = get_task_parameters(task)["tr"]
        events = pd.read_csv(recovery_scan["events"], sep="\t")
        prepped = preprocess_events(events, task, n_scans=n_trs, tr=tr)
        junked, _ = add_junk_trials(prepped, task)
        confounds = pd.DataFrame({"constant": np.ones(n_trs)})
        design, _ = create_design_matrix(junked, confounds, task, n_trs, tr)
        # Noiseless plant: the recovery is then a deterministic property of the
        # real design + GLM (no seed-dependent noise draw). The recovered effect
        # is a stable ~4.92 (the HRF/regressor numerical floor under the planted
        # 5.0), which the e2e checks within abs=1.0. (noise_sd>0 makes the tight
        # check flaky — see the dataset-sim capstone's noise note.)
        ts = plant_bold(design, _PLANTED_BETAS, noise_sd=0.0, seed=scan_seed + 1)
        planted_img = as_4d_nifti(ts)
        nib.save(planted_img, recovery_scan["mni_data"])

    # --- 4. Exclusions: REAL behavioral + motion + compile + render -------
    # Write the synthetic collection block (same stem simulate_exclusions
    # expects: <root>/data/exclusions/<dataset>_collection.bidsignore).
    collection_file = _write_full_collection_block(root, dataset, sorted(set(collection_lines)))
    excl_manifest = {
        "bids_dir": str(bids_dir),
        "fmriprep_dir": str(fmriprep_dir),
        "version": version,
        "collection_file": str(collection_file) if collection_file else None,
    }
    exclusions = simulate_exclusions(root, excl_manifest, dataset=dataset)

    # --- 5. lev1 recovery on the planted keep scan ------------------------
    if recovery_scan is not None:
        finder = FileFinder(str(bids_dir), str(fmriprep_dir))
        files = finder.get_files(
            recovery_scan["subject"],
            recovery_scan["task"],
            required_files=FileFinder.get_required_files_for_space("MNI"),
        )
        session, run = recovery_scan["session"], recovery_scan["run"]
        run_files = files[session][run]
        task = recovery_scan["task"]
        n_trs = recovery_scan["n_trs"]
        tr = get_task_parameters(task)["tr"]

        events = pd.read_csv(run_files["events"], sep="\t")
        prepped = preprocess_events(events, task, n_scans=n_trs, tr=tr)
        junked, _ = add_junk_trials(prepped, task)
        confounds = pd.DataFrame({"constant": np.ones(n_trs)})
        design, _ = create_design_matrix(junked, confounds, task, n_trs, tr)

        reloaded = nib.load(str(run_files["mni_data"]))
        fitted = fit_run_glm(
            reloaded,
            design,
            analysis_type="task",
            tr=tr,
            mask_img=make_mask(reloaded),
        )
        formula = get_task_contrasts(task)["incongruent-congruent"]
        saved = compute_run_contrasts(
            fitted_glm=fitted,
            task_name=task,
            output_dir=root / "lev1_out",
            base_filename=(f"{recovery_scan['subject']}_{session}_task-{task}_{run}"),
            contrasts={"incongruent-congruent": formula},
        )
        effect_path = saved["incongruent-congruent"]["effect_size"]
        recovered_contrast = float(np.mean(nib.load(str(effect_path)).get_fdata()))

    manifest = {
        "bids_dir": str(bids_dir),
        "fmriprep_dir": str(fmriprep_dir),
        "version": version,
        "scans": scans,
        "collection_file": str(collection_file) if collection_file else None,
        "planted_effect": _PLANTED_EFFECT,
    }
    return FullPipelineResult(
        manifest=manifest,
        exclusions=exclusions,
        recovery_scan=recovery_scan,
        recovered_contrast=recovered_contrast,
    )


_FULL_COLLECTION_HEADER = (
    "# Synthetic data-collection / anatomical exclusions (full-chain sim).\n"
    "#\n"
    "# Auto-generated by neuro_workflow.testing.simulate.simulate_full_pipeline.\n"
    "# Each glob below covers a scan tagged 'exclude:collection' in the spec —\n"
    "# the static-collection layer excludes these (they pass behavioral + motion\n"
    "# QC otherwise).\n"
)


def _write_full_collection_block(root: Path, dataset: str, lines: list[str]) -> Path | None:
    """Write the full-chain collection ``.bidsignore`` block, if any lines.

    Mirrors ``cohort._write_collection_block`` but keyed on ``dataset`` so the
    stem matches ``simulate_exclusions``'s ``<dataset>_collection.bidsignore``
    lookup. Returns the written path, or None when there is nothing to exclude.
    """
    if not lines:
        return None
    coll_dir = Path(root) / "data" / "exclusions"
    coll_dir.mkdir(parents=True, exist_ok=True)
    coll_path = coll_dir / f"{dataset}_collection.bidsignore"
    body = _FULL_COLLECTION_HEADER + "\n" + "\n".join(lines) + "\n"
    coll_path.write_text(body)
    return coll_path
