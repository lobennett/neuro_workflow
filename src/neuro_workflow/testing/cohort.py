"""Synthetic-cohort generator with planted per-mechanism exclusions.

The input layer for an end-to-end pipeline simulation. Where B1's
:mod:`neuro_workflow.testing.synthetic` manufactures ONE fMRIPrep derivative
run for the file-discovery / motion-exclusion code, this module assembles a
whole *cohort* — synthetic BIDS + ``sourcedata`` behavioral CSVs + fMRIPrep
derivatives + a collection ``.bidsignore`` block — with each scan deliberately
planted to be excluded by a specific REAL mechanism (or kept).

The point is to drive the production events + exclusions generators on data
whose ground truth is known: a ``exclude:behavioral`` scan's CSV genuinely
trips ``events.qc.compute_metrics_from_csv`` / ``determine_exclusion``; a
``exclude:motion`` scan's confounds genuinely trip
``exclusions.motion.MotionGenerator``; a ``exclude:collection`` scan is covered
by a glob line for the static collection layer; and a ``keep`` scan is
discoverable by ``analysis.io.file_discovery.FileFinder`` and passes every
generator.

Behavioral CSVs are written in the SOURCEDATA shape that
``events.qc.compute_metrics_from_csv`` reads — ``trial_id`` == ``"test_trial"``
rows with ``rt`` / ``key_press`` / ``correct_response`` and the per-task
condition columns (``stop_signal_condition`` / ``stop_acc`` for stopSignal). It
is intentionally NOT the full jsPsych raw export that
``events.create.create_events_df`` consumes (that needs ``exp_id`` /
``block_duration`` / ``fmri_trigger_initial`` / ``time_elapsed`` and the
task-specific column families); generating those is out of scope for the QC /
exclusion gate this module targets.

Dependency-light: numpy / pandas / nibabel only (nibabel via the reused B1
writers). All randomness is explicitly seeded so output is deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from neuro_workflow.core.acquisition import TR_SECONDS
from neuro_workflow.testing.synthetic import make_events, make_fmriprep_run

__all__ = [
    "make_behavioral_csv",
    "ScanSpec",
    "SessionSpec",
    "SubjectSpec",
    "CohortSpec",
    "make_synthetic_cohort",
]

# Planted-outcome vocabulary. A scan is tagged with exactly one of these.
VALID_OUTCOMES = ("keep", "exclude:behavioral", "exclude:motion", "exclude:collection")


# --------------------------------------------------------------------------- #
# Behavioral CSV writer (sourcedata shape that events.qc reads).
# --------------------------------------------------------------------------- #
def make_behavioral_csv(
    path: Path,
    task: str,
    *,
    n_trials: int = 40,
    omission_rate: float = 0.0,
    accuracy: float = 1.0,
    go_rt_ms: float = 500.0,
    seed: int = 0,
) -> Path:
    """Write a sourcedata behavioral CSV the REAL ``compute_metrics_from_csv`` reads.

    The columns reproduce EXACTLY what ``events.qc.compute_metrics_from_csv``
    consumes for the task family:

    * **generic** (e.g. ``flanker``, ``directedForgetting``, any task without a
      ``stopSignal`` / ``goNogo`` / ``nBack`` substring): ``trial_id``, ``rt``,
      ``key_press``, ``correct_response``. The QC code computes
      ``omission_rate = (rt == -1).mean()`` over ``test_trial`` rows and
      ``acc = (key_press == correct_response).mean()`` over the RESPONDED rows.
      ``omission_rate`` plants ``round(omission_rate * n_trials)`` non-response
      rows (``rt == -1``); ``accuracy`` makes that fraction of the RESPONDED
      rows correct (``key_press == correct_response``) and the rest wrong.
    * **stopSignal**: adds ``stop_signal_condition`` (``go`` / ``stop``) and
      ``stop_acc``. Half the trials are go, half stop. Go trials all respond
      with ``rt == go_rt_ms`` (so the mean go RT is exactly ``go_rt_ms``);
      ``accuracy`` controls go correctness. Stop trials get ``stop_acc`` ~0.5
      success so ``stop_success_rate`` lands inside the healthy [0.25, 0.75]
      band and only ``go_rt`` drives the exclusion when ``go_rt_ms > 1000``.

    To trip the REAL thresholds (from ``config/thresholds.yaml``):

    * generic omission: ``omission_rate > 0.25`` (strict). ``n_trials=40`` gives
      a 1/40 = 0.025 grid, so 0.25 (10/40) is exactly AT threshold (not
      flagged) and 0.275 (11/40) is over (flagged).
    * generic accuracy: ``acc < 0.55`` (strict). ``accuracy=0.4`` trips it.
    * stopSignal go RT: ``go_rt > 1000`` ms (strict). ``go_rt_ms=1200`` trips it.

    Args:
        path: Destination CSV path (parent dirs created).
        task: BIDS task name. Substring ``stopSignal`` selects the stopSignal
            layout; anything else uses the generic layout.
        n_trials: Number of ``test_trial`` rows.
        omission_rate: Fraction of test trials with no response (``rt == -1``).
            Rounded to the nearest whole trial.
        accuracy: Fraction of RESPONDED trials scored correct
            (``key_press == correct_response``). Rounded over responded rows.
        go_rt_ms: Go-trial reaction time in milliseconds (stopSignal only; the
            mean go RT equals this exactly since all go RTs are identical).
        seed: RNG seed (used only to jitter inert extra columns; the
            threshold-driving values are deterministic so the QC decision is
            fully controllable).

    Returns:
        Path to the written CSV.

    Raises:
        ValueError: if ``n_trials < 1`` or ``omission_rate`` / ``accuracy`` lie
            outside [0, 1].
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if not 0.0 <= omission_rate <= 1.0:
        raise ValueError(f"omission_rate must be in [0, 1], got {omission_rate}")
    if not 0.0 <= accuracy <= 1.0:
        raise ValueError(f"accuracy must be in [0, 1], got {accuracy}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    if "stopSignal" in task:
        df = _stop_signal_frame(n_trials, omission_rate, accuracy, go_rt_ms, rng)
    else:
        df = _generic_frame(n_trials, omission_rate, accuracy, go_rt_ms, rng)

    df.to_csv(path, index=False)
    return path


def _generic_frame(
    n_trials: int,
    omission_rate: float,
    accuracy: float,
    rt_ms: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build a generic-task ``test_trial`` frame for compute_metrics_from_csv.

    Omissions are the FIRST ``n_omit`` rows (``rt == -1``); of the remaining
    responded rows, the first ``round(accuracy * n_resp)`` are correct.
    Placement is deterministic so the planted metrics are exact regardless of
    seed.
    """
    n_omit = int(round(omission_rate * n_trials))
    n_omit = min(n_omit, n_trials)
    n_resp = n_trials - n_omit
    n_correct = int(round(accuracy * n_resp)) if n_resp else 0

    rt = np.full(n_trials, float(rt_ms))
    rt[:n_omit] = -1.0

    correct_response = np.ones(n_trials, dtype=int)  # canonical correct key
    key_press = np.ones(n_trials, dtype=int)
    # Responded rows occupy indices [n_omit, n_trials). Make the first
    # n_correct of them correct (key_press == 1) and the rest wrong (== 2).
    if n_resp:
        wrong_start = n_omit + n_correct
        key_press[wrong_start:] = 2
    # Omitted rows: key_press is irrelevant to acc (they're not "responded"),
    # but give them a non-matching sentinel so a naive reader can't mistake an
    # omission for a correct response.
    key_press[:n_omit] = -1

    return pd.DataFrame(
        {
            "trial_id": ["test_trial"] * n_trials,
            "rt": rt,
            "key_press": key_press,
            "correct_response": correct_response,
            # Inert realistic extras (compute_metrics_from_csv ignores these).
            "trial_index": np.arange(n_trials),
            "block": rng.integers(0, 2, size=n_trials),
        }
    )


def _stop_signal_frame(
    n_trials: int,
    omission_rate: float,
    accuracy: float,
    go_rt_ms: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build a stopSignal ``test_trial`` frame for compute_metrics_from_csv.

    Trials alternate go/stop. Go trials respond at exactly ``go_rt_ms`` (so the
    computed mean ``go_rt`` equals it); ``accuracy`` controls go correctness.
    Stop trials get ``stop_acc`` alternating 1/0 so ``stop_success_rate`` ~0.5,
    inside the healthy band — keeping go RT the sole exclusion driver.
    ``omission_rate`` plants that fraction of GO trials as non-responses, which
    is how the real generator would see in-scanner omissions.
    """
    # Alternate conditions: even index = go, odd = stop.
    condition = np.array(["go" if i % 2 == 0 else "stop" for i in range(n_trials)])
    is_go = condition == "go"
    n_go = int(is_go.sum())

    rt = np.full(n_trials, -1.0)
    rt[is_go] = float(go_rt_ms)  # all go trials respond at go_rt_ms

    # Plant omissions among go trials (deterministic: first n_omit go trials).
    n_omit = int(round(omission_rate * n_go))
    if n_omit:
        go_idx = np.flatnonzero(is_go)[:n_omit]
        rt[go_idx] = -1.0

    correct_response = np.ones(n_trials, dtype=int)
    key_press = np.ones(n_trials, dtype=int)
    # Go correctness: of the go trials, make `accuracy` fraction correct.
    go_positions = np.flatnonzero(is_go)
    n_go_correct = int(round(accuracy * n_go)) if n_go else 0
    for rank, pos in enumerate(go_positions):
        key_press[pos] = 1 if rank < n_go_correct else 2
    # Stop trials: key_press is irrelevant to the stopSignal metrics (which use
    # stop_acc), set a sentinel.
    key_press[~is_go] = -1

    # stop_acc alternates 1/0 over stop trials -> ~0.5 stop-success rate.
    stop_acc = np.zeros(n_trials, dtype=int)
    stop_positions = np.flatnonzero(~is_go)
    for rank, pos in enumerate(stop_positions):
        stop_acc[pos] = 1 if rank % 2 == 0 else 0

    return pd.DataFrame(
        {
            "trial_id": ["test_trial"] * n_trials,
            "rt": rt,
            "key_press": key_press,
            "correct_response": correct_response,
            "stop_signal_condition": condition,
            "stop_acc": stop_acc,
            # Inert realistic extras.
            "SS_delay": np.where(is_go, np.nan, rng.integers(200, 500, size=n_trials)),
            "trial_index": np.arange(n_trials),
        }
    )


# --------------------------------------------------------------------------- #
# Cohort spec dataclasses.
# --------------------------------------------------------------------------- #
@dataclass
class ScanSpec:
    """One planted scan: a (task, run) tagged with an intended exclusion outcome.

    Args:
        task: BIDS task name (e.g. ``"flanker"``, ``"stopSignal"``, ``"goNogo"``).
        run: Run label without the ``run-`` prefix (e.g. ``"1"``).
        outcome: One of :data:`VALID_OUTCOMES` — ``keep`` |
            ``exclude:behavioral`` | ``exclude:motion`` | ``exclude:collection``.
        space: fMRIPrep analysis space for the derivative (default ``"MNI"``;
            see :func:`neuro_workflow.testing.synthetic.write_fmriprep_bold`).
        n_trials: Number of behavioral ``test_trial`` rows.
        n_trs: Number of fMRIPrep BOLD / confounds timepoints.
    """

    task: str
    run: str = "1"
    outcome: str = "keep"
    space: str = "MNI"
    n_trials: int = 40
    n_trs: int = 100

    def __post_init__(self) -> None:
        if self.outcome not in VALID_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {VALID_OUTCOMES}, got {self.outcome!r}"
            )


@dataclass
class SessionSpec:
    """One session containing scans."""

    session: str
    scans: List[ScanSpec] = field(default_factory=list)


@dataclass
class SubjectSpec:
    """One subject containing sessions."""

    subject: str
    sessions: List[SessionSpec] = field(default_factory=list)


@dataclass
class CohortSpec:
    """A whole synthetic cohort: subjects -> sessions -> scans."""

    subjects: List[SubjectSpec] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Cohort assembly.
# --------------------------------------------------------------------------- #
_BOLD_JSON = {
    "RepetitionTime": TR_SECONDS,
    "TaskName": None,  # filled per scan
    "NumberOfVolumesDiscardedByUser": 7,
}


def make_synthetic_cohort(
    root: Path,
    spec: CohortSpec,
    *,
    version: str = "25.2.4",
    seed: int = 0,
) -> Dict:
    """Assemble a synthetic BIDS + sourcedata + fMRIPrep cohort with planted exclusions.

    Builds, under ``root``:

    * **BIDS** — ``root/sub-X/ses-Y/func/`` with ``*_bold.nii.gz`` + ``.json``
      and a real ``*_events.tsv`` (via :func:`synthetic.make_events`) for every
      scan, so :class:`~neuro_workflow.analysis.io.file_discovery.FileFinder`
      discovers complete runs.
    * **sourcedata** — ``root/sourcedata/sub-X/ses-Y/beh/*_beh.csv`` behavioral
      CSVs (via :func:`make_behavioral_csv`): CLEAN for every outcome EXCEPT
      ``exclude:behavioral`` (high omission so the real behavioral QC flags it).
    * **fMRIPrep derivatives** — ``root/derivatives/fmriprep_{version}/`` via
      :func:`synthetic.make_fmriprep_run`: ``motion="clean"`` for every outcome
      EXCEPT ``exclude:motion`` (``motion="high"`` so the real MotionGenerator
      flags it).
    * **collection block** — for each ``exclude:collection`` scan, a glob line
      in the committed-collection ``.bidsignore`` style, written to
      ``root/data/exclusions/sim_collection.bidsignore`` and returned in the
      manifest so the static-collection layer can exclude it.

    The behavioral and motion failures are planted ONLY on their own scans:
    a ``keep`` / ``exclude:motion`` / ``exclude:collection`` scan's CSV is clean
    and a ``keep`` / ``exclude:behavioral`` / ``exclude:collection`` scan's
    confounds are clean. So each generator sees exactly its planted target.

    Args:
        root: Cohort root directory (created if absent). The BIDS dataset IS
            ``root``; derivatives nest under ``root/derivatives``.
        spec: The :class:`CohortSpec` describing subjects/sessions/scans.
        version: fMRIPrep version; derivatives land in
            ``root/derivatives/fmriprep_{version}`` (the path MotionGenerator
            reconstructs from ``--fmriprep-version``).
        seed: Base RNG seed; each scan gets a distinct derived seed so files
            differ but stay deterministic.

    Returns:
        A manifest dict with keys:

        * ``root`` / ``bids_dir`` / ``fmriprep_dir`` (str paths),
        * ``version``,
        * ``scans``: list of per-scan dicts (``subject``, ``session``, ``task``,
          ``run``, ``outcome``, ``motion``, ``behavioral`` planted params,
          ``files`` written, ``events`` path, ``beh_csv`` path),
        * ``collection_lines``: the collection ``.bidsignore`` glob lines (empty
          if no ``exclude:collection`` scans),
        * ``collection_file``: path to the written collection file (or ``None``).
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    bids_dir = root
    fmriprep_dir = root / "derivatives" / f"fmriprep_{version}"
    sourcedata_dir = root / "sourcedata"

    scans_manifest: List[Dict] = []
    collection_lines: List[str] = []
    scan_seed = seed

    for subj in spec.subjects:
        for sess in subj.sessions:
            for scan in sess.scans:
                scan_seed += 1
                record = _build_scan(
                    bids_dir=bids_dir,
                    fmriprep_dir=fmriprep_dir,
                    sourcedata_dir=sourcedata_dir,
                    subject=subj.subject,
                    session=sess.session,
                    scan=scan,
                    version=version,
                    seed=scan_seed,
                )
                scans_manifest.append(record)
                if scan.outcome == "exclude:collection":
                    collection_lines.append(record["collection_glob"])

    collection_file = _write_collection_block(root, collection_lines)

    return {
        "root": str(root),
        "bids_dir": str(bids_dir),
        "fmriprep_dir": str(fmriprep_dir),
        "version": version,
        "scans": scans_manifest,
        "collection_lines": collection_lines,
        "collection_file": str(collection_file) if collection_file else None,
    }


def _build_scan(
    *,
    bids_dir: Path,
    fmriprep_dir: Path,
    sourcedata_dir: Path,
    subject: str,
    session: str,
    scan: ScanSpec,
    version: str,
    seed: int,
) -> Dict:
    """Write all files for one planted scan and return its manifest record."""
    sub = f"sub-{subject}"
    ses = f"ses-{session}"
    prefix = f"{sub}_{ses}_task-{scan.task}_run-{scan.run}"

    # --- BIDS func: bold.nii.gz + json + events.tsv -----------------------
    func_dir = bids_dir / sub / ses / "func"
    func_dir.mkdir(parents=True, exist_ok=True)

    bold_path = func_dir / f"{prefix}_bold.nii.gz"
    _write_bold_nifti(bold_path, n_trs=scan.n_trs, seed=seed)

    json_path = func_dir / f"{prefix}_bold.json"
    sidecar = dict(_BOLD_JSON)
    sidecar["TaskName"] = scan.task
    json_path.write_text(json.dumps(sidecar, indent=2))

    events_path = func_dir / f"{prefix}_events.tsv"
    events_df = make_events(scan.task, n_trials=max(2, scan.n_trials // 4))
    events_df.to_csv(events_path, sep="\t", index=False)

    # --- sourcedata behavioral CSV (clean unless exclude:behavioral) ------
    beh_dir = sourcedata_dir / sub / ses / "beh"
    beh_dir.mkdir(parents=True, exist_ok=True)
    beh_csv = beh_dir / f"{prefix}_beh.csv"

    if scan.outcome == "exclude:behavioral":
        # Plant a clear behavioral failure. For stopSignal use a slow go RT;
        # for everything else use high omission so the generic rule trips.
        if "stopSignal" in scan.task:
            beh_params = {"omission_rate": 0.0, "accuracy": 1.0, "go_rt_ms": 1200.0}
        else:
            beh_params = {"omission_rate": 0.5, "accuracy": 1.0, "go_rt_ms": 500.0}
    else:
        beh_params = {"omission_rate": 0.0, "accuracy": 1.0, "go_rt_ms": 500.0}

    make_behavioral_csv(
        beh_csv,
        scan.task,
        n_trials=scan.n_trials,
        seed=seed,
        **beh_params,
    )

    # --- fMRIPrep derivatives (clean unless exclude:motion) ----------------
    motion = "high" if scan.outcome == "exclude:motion" else "clean"
    written = make_fmriprep_run(
        fmriprep_dir,
        subject,
        session,
        scan.task,
        scan.run,
        space=scan.space,
        n_trs=scan.n_trs,
        version=version,
        motion=motion,
        seed=seed,
    )

    # --- collection glob line (committed-collection .bidsignore style) -----
    collection_glob = (
        f"{sub}/{ses}/func/{prefix}_echo-*_bold.*"
    )

    return {
        "subject": sub,
        "session": ses,
        "task": scan.task,
        "run": f"run-{scan.run}",
        "outcome": scan.outcome,
        "space": scan.space,
        "motion": motion,
        "behavioral": beh_params,
        "bold": str(bold_path),
        "bold_json": str(json_path),
        "events": str(events_path),
        "beh_csv": str(beh_csv),
        "fmriprep_files": {k: str(v) for k, v in written.items()},
        "collection_glob": collection_glob,
    }


def _write_bold_nifti(path: Path, *, n_trs: int, n_voxels: int = 4, seed: int = 0) -> Path:
    """Write a tiny loadable raw-BIDS 4D BOLD NIfTI.

    Reuses the same 4D layout as the B1 derivative writers (a small block of
    voxels over time) so the file is a real, loadable ``.nii.gz`` that a NIfTI
    reader and the events-stage ``discover_nifti_tasks`` glob both accept. It is
    the RAW (pre-fMRIPrep) BOLD; trimming/onset adjustment are handled upstream
    by the pipeline and intentionally NOT applied here.
    """
    import nibabel as nib  # local import keeps module import cheap

    from neuro_workflow.testing.synthetic import as_4d_nifti

    rng = np.random.default_rng(seed)
    ts = rng.normal(0.0, 1.0, size=max(n_trs, 1))
    img = as_4d_nifti(ts, n_voxels=n_voxels)
    nib.save(img, str(path))
    return path


# Header for the synthetic collection .bidsignore (mirrors the committed
# data/exclusions/<ds>_collection.bidsignore preamble style).
_COLLECTION_HEADER = (
    "# Synthetic data-collection / anatomical exclusions (simulation cohort).\n"
    "#\n"
    "# Auto-generated by neuro_workflow.testing.cohort.make_synthetic_cohort for\n"
    "# end-to-end pipeline simulation. Each glob below covers a scan tagged\n"
    "# 'exclude:collection' in the CohortSpec — the static-collection layer\n"
    "# excludes these (they pass behavioral + motion QC otherwise).\n"
)


def _write_collection_block(root: Path, lines: List[str]) -> Optional[Path]:
    """Write the synthetic collection ``.bidsignore`` block, if any lines.

    Returns the written path, or ``None`` when there are no
    ``exclude:collection`` scans (nothing to write).
    """
    if not lines:
        return None
    coll_dir = root / "data" / "exclusions"
    coll_dir.mkdir(parents=True, exist_ok=True)
    coll_path = coll_dir / "sim_collection.bidsignore"
    body = _COLLECTION_HEADER + "\n" + "\n".join(sorted(set(lines))) + "\n"
    coll_path.write_text(body)
    return coll_path
