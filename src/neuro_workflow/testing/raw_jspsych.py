"""Raw-jsPsych behavioral-export synthesis — closes the events.create boundary.

Where :mod:`neuro_workflow.testing.cohort` writes the *sourcedata* (QC-shape)
behavioral CSV, this module writes the stage UPSTREAM of it: the raw jsPsych
export that the *production* :func:`neuro_workflow.events.create.create_events_df`
consumes. Threading a synthetic raw CSV through ``create_events_df`` produces a
genuine BIDS ``events.tsv``, closing the one simulation boundary the cohort
stack bypassed.

What ``create_events_df`` reads (traced from ``events/create.py`` +
``events/utils.py``):

  * ``exp_id`` — the full jsPsych experiment id (e.g.
    ``flanker_single_task_network__fmri``). It keys the column-selection
    (``_COLS_LOOKUP``), trial-type construction (``_TRIAL_TYPE_LOOKUP``) and
    cell-rename tables. This is NOT the BIDS task name; the map lives in
    :data:`EXP_ID`.
  * a row with ``trial_id == 'fmri_trigger_initial'`` — ``cal_time_elapsed``
    subtracts this row's ``time_elapsed`` from every row (the scanner-trigger
    zero).
  * ``time_elapsed`` (ms, cumulative/absolute) and ``block_duration`` (ms,
    per-trial) — onset is reconstructed as
    ``(time_elapsed - trigger_time - block_duration)/1000`` and then shifted by
    the dummy-volume offset (``N_DUMMY * TR_SECONDS``). ``get_neg_rt_correction``
    drops rows with NaN ``block_duration`` and (only) rewrites timing when an
    ``rt < -1`` is present — which we never plant, so it is a no-op.
  * ``stim_duration`` (ms) — becomes the events ``duration`` (``/1000``).
  * ``rt`` (ms) — becomes ``response_time`` (``/1000``); ``-1`` marks an
    omission (no response).
  * ``key_press`` / ``correct_response`` — accuracy (``choice_acc``) and the
    lev1 nuisance masks (omission/commission) derive from these.
  * the task condition column(s): ``flanker_condition`` (+ ``center_letter``)
    for flanker; ``stop_signal_condition`` / ``stop_acc`` (+ ``SS_delay`` /
    ``SS_duration`` / ``stim``) for stopSignal.

Because the raw export already carries ``trial_id`` / ``rt`` / ``key_press`` /
``correct_response`` (+ ``stop_signal_condition`` / ``stop_acc`` for
stopSignal), the SAME file the events stage parses is also exactly what
:func:`neuro_workflow.events.qc.compute_metrics_from_csv` reads. So one writer
serves both shapes: a high-omission raw CSV both produces a valid events.tsv
AND trips the behavioral exclusion. (The QC reads ``rt`` in ms and counts
``rt == -1`` over ``test_trial`` rows; the events stage divides ``rt`` by 1000.
Both see the same planted omissions/accuracy/go-RT.)

Onset timing (the one subtle bit). For test-trial ``i`` we set::

    time_elapsed[i] = trigger_time + block_duration + DUMMY_OFFSET_MS
                      + (first_onset + i * iti) * 1000

so that ``create_events_df``'s pipeline
(``-trigger_time`` then ``-block_duration`` then ``/1000`` then
``-DUMMY_OFFSET_S``) recovers the events onset ``first_onset + i * iti``
exactly. Onsets are therefore monotonic and land where requested.

Dependency-light: numpy / pandas only. All randomness is explicitly seeded so
output is deterministic. This is import-only test support; nothing in
production imports from here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from neuro_workflow.core.acquisition import N_DUMMY, TR_SECONDS

__all__ = ["EXP_ID", "make_raw_jspsych_csv"]

# Dummy-volume offset in milliseconds (events.create subtracts N_DUMMY*TR after
# the /1000). Kept in lock-step with events.create.DUMMY_OFFSET_S (which is
# N_DUMMY * TR_SECONDS) via the same single source in core.acquisition.
_DUMMY_OFFSET_MS = N_DUMMY * TR_SECONDS * 1000.0

# Scanner-trigger ``time_elapsed`` (ms) — an arbitrary positive offset; the
# only requirement is that test trials land after it. Real exports sit around
# 60 s of pre-scan instructions, so 60000 ms is representative.
_TRIGGER_TIME_MS = 60000.0

# jsPsych key codes the real flanker export uses for the two responses (H / F).
_KEY_H = 89.0
_KEY_F = 71.0

# BIDS task name -> jsPsych ``exp_id`` for the supported tasks. The exp_id keys
# the production column-selection / trial-type tables in events/utils.py.
EXP_ID: dict[str, str] = {
    "flanker": "flanker_single_task_network__fmri",
    "stopSignal": "stop_signal_single_task_network__fmri",
}

_SUPPORTED = tuple(EXP_ID)


def make_raw_jspsych_csv(
    path: Path,
    task: str,
    *,
    n_trials: int = 40,
    seed: int = 0,
    omission_rate: float = 0.0,
    accuracy: float = 1.0,
    go_rt_ms: float = 500.0,
    first_onset: float = 5.0,
    iti: float = 3.0,
    block_duration_ms: float = 2000.0,
    stim_duration_ms: float = 1000.0,
) -> Path:
    """Write a raw jsPsych export the REAL ``create_events_df`` parses.

    Produces a CSV whose rows carry the jsPsych columns
    ``create_events_df`` reads (``exp_id`` / ``time_elapsed`` /
    ``block_duration`` / ``stim_duration`` / an ``fmri_trigger_initial`` row +
    the task condition columns). Threading it through the production events
    pipeline yields a valid ``events.tsv`` (onsets monotonic and at
    ``first_onset + i*iti``); the SAME file drives the production behavioral QC
    (``compute_metrics_from_csv``), so the QC-controlling knobs below also
    apply.

    Args:
        path: Destination CSV path (parent dirs created).
        task: BIDS task name — one of :data:`EXP_ID` (``flanker`` /
            ``stopSignal``).
        n_trials: Number of ``test_trial`` rows.
        seed: RNG seed (used only to jitter the inert ``center_letter`` /
            ``SS_delay`` columns; all timing/accuracy/condition values are
            deterministic so events + QC outcomes are fully controllable).
        omission_rate: Fraction of test trials with no response (``rt == -1``).
            For flanker these are the FIRST ``round(omission_rate*n_trials)``
            test trials; for stopSignal they are the first such *go* trials
            (stop trials are non-responses by design). Drives the generic
            omission metric (and, for go trials, removes them from the go-RT
            mean).
        accuracy: Fraction of RESPONDED trials scored correct
            (``key_press == correct_response``); flanker accuracy metric, and
            stopSignal go-accuracy.
        go_rt_ms: Reaction time (ms) for every responded go trial. The computed
            mean ``go_rt`` equals this exactly (stopSignal only; flanker uses it
            as the uniform responded-trial RT). ``> 1000`` trips the stopSignal
            go-RT exclusion.
        first_onset: Events onset (seconds) of the first test trial.
        iti: Inter-trial interval (seconds) between successive test-trial onsets.
        block_duration_ms: Per-trial ``block_duration`` (ms). Subtracted in
            ``cal_time_elapsed``; folded into the planted ``time_elapsed`` so
            the recovered onset is exact.
        stim_duration_ms: Per-trial ``stim_duration`` (ms); becomes the events
            ``duration`` after ``/1000``.

    Returns:
        Path to the written CSV.

    Raises:
        ValueError: on an unsupported ``task``, ``n_trials < 1``, or an
            ``omission_rate`` / ``accuracy`` outside [0, 1].
    """
    if task not in EXP_ID:
        raise ValueError(f"unsupported task {task!r}; supported: {list(_SUPPORTED)}")
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if not 0.0 <= omission_rate <= 1.0:
        raise ValueError(f"omission_rate must be in [0, 1], got {omission_rate}")
    if not 0.0 <= accuracy <= 1.0:
        raise ValueError(f"accuracy must be in [0, 1], got {accuracy}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    if task == "flanker":
        df = _flanker_frame(
            n_trials,
            omission_rate,
            accuracy,
            go_rt_ms,
            first_onset,
            iti,
            block_duration_ms,
            stim_duration_ms,
            rng,
        )
    else:  # stopSignal
        df = _stop_signal_frame(
            n_trials,
            omission_rate,
            accuracy,
            go_rt_ms,
            first_onset,
            iti,
            block_duration_ms,
            stim_duration_ms,
            rng,
        )

    df.to_csv(path, index=False)
    return path


def _onset_to_time_elapsed(onset_s: float, block_duration_ms: float) -> float:
    """Plant ``time_elapsed`` so the recovered events onset is ``onset_s``.

    Inverts the production reconstruction
    (``-trigger_time`` then ``-block_duration`` then ``/1000`` then
    ``-DUMMY_OFFSET_S``).
    """
    return _TRIGGER_TIME_MS + block_duration_ms + _DUMMY_OFFSET_MS + onset_s * 1000.0


def _trigger_row(exp_id: str, block_duration_ms: float) -> dict:
    """The ``fmri_trigger_initial`` row ``cal_time_elapsed`` zeroes timing on."""
    return {
        "exp_id": exp_id,
        "trial_id": "fmri_trigger_initial",
        "time_elapsed": _TRIGGER_TIME_MS,
        "block_duration": block_duration_ms,
        "rt": int(block_duration_ms),  # real exports record the wait as rt
        "stim_duration": np.nan,
        "key_press": np.nan,
        "correct_response": np.nan,
        "stimulus": "",
    }


def _flanker_frame(
    n_trials: int,
    omission_rate: float,
    accuracy: float,
    rt_ms: float,
    first_onset: float,
    iti: float,
    block_duration_ms: float,
    stim_duration_ms: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build a raw flanker jsPsych frame (trigger row + n_trials test trials).

    Omissions are the FIRST ``n_omit`` test trials (``rt == -1``); of the
    remaining responded trials, the first ``round(accuracy*n_resp)`` are
    correct. ``flanker_condition`` alternates congruent/incongruent. Placement
    is deterministic so the planted onsets/metrics are exact.
    """
    exp_id = EXP_ID["flanker"]
    n_omit = min(int(round(omission_rate * n_trials)), n_trials)
    n_resp = n_trials - n_omit
    n_correct = int(round(accuracy * n_resp)) if n_resp else 0

    rows = [_trigger_row(exp_id, block_duration_ms)]
    for i in range(n_trials):
        onset_s = first_onset + i * iti
        omit = i < n_omit
        responded_rank = i - n_omit
        correct = 0 <= responded_rank < n_correct
        condition = "congruent" if i % 2 == 0 else "incongruent"
        center = "H" if rng.random() < 0.5 else "F"
        correct_response = _KEY_H if center == "H" else _KEY_F
        if omit:
            key_press = -1.0
            rt = -1
        elif correct:
            key_press = correct_response
            rt = int(rt_ms)
        else:
            # Wrong (commission): press the OTHER key.
            key_press = _KEY_F if correct_response == _KEY_H else _KEY_H
            rt = int(rt_ms)

        rows.append(
            {
                "exp_id": exp_id,
                "trial_id": "test_trial",
                "time_elapsed": _onset_to_time_elapsed(onset_s, block_duration_ms),
                "block_duration": block_duration_ms,
                "rt": rt,
                "stim_duration": stim_duration_ms,
                "key_press": key_press,
                "correct_response": correct_response,
                "flanker_condition": condition,
                "center_letter": center,
                "stimulus": "",
            }
        )
    return pd.DataFrame(rows)


def _stop_signal_frame(
    n_trials: int,
    omission_rate: float,
    accuracy: float,
    go_rt_ms: float,
    first_onset: float,
    iti: float,
    block_duration_ms: float,
    stim_duration_ms: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build a raw stopSignal jsPsych frame (trigger row + n_trials test trials).

    Trials alternate go / stop (even index = go). Go trials respond at exactly
    ``go_rt_ms`` (so the computed mean ``go_rt`` equals it); ``accuracy``
    controls go correctness. Stop trials are non-responses (``rt == -1``) with
    ``stop_acc`` alternating 1/0 (~0.5 success, inside the healthy band, so go
    RT is the sole exclusion driver). ``omission_rate`` plants that fraction of
    GO trials as additional non-responses. The production ``_cleanup_stop_signal``
    maps these to trial_type go / stop_success / stop_failure.
    """
    exp_id = EXP_ID["stopSignal"]
    condition = np.array(["go" if i % 2 == 0 else "stop" for i in range(n_trials)])
    is_go = condition == "go"
    go_positions = np.flatnonzero(is_go)
    stop_positions = np.flatnonzero(~is_go)
    n_go = int(is_go.sum())

    # Omissions among go trials: first n_omit go trials become non-responses.
    n_omit = int(round(omission_rate * n_go))
    omit_go = set(go_positions[:n_omit].tolist())
    # Go correctness over the (responded) go trials.
    n_go_correct = int(round(accuracy * n_go)) if n_go else 0

    # Map go position -> rank for accuracy assignment.
    go_rank = {pos: rank for rank, pos in enumerate(go_positions)}
    stop_rank = {pos: rank for rank, pos in enumerate(stop_positions)}

    rows = [_trigger_row(exp_id, block_duration_ms)]
    for i in range(n_trials):
        onset_s = first_onset + i * iti
        cond = condition[i]
        # stim/correct_response codes mirror the H/F flanker codes (arbitrary
        # but consistent so commission = pressing the wrong key).
        correct_response = _KEY_H if (i % 4 < 2) else _KEY_F
        if cond == "go":
            if i in omit_go:
                key_press, rt = -1.0, -1
            else:
                correct = go_rank[i] < n_go_correct
                key_press = (
                    correct_response
                    if correct
                    else (_KEY_F if correct_response == _KEY_H else _KEY_H)
                )
                rt = int(go_rt_ms)
            stop_acc = 0  # n/a for go; QC only reads stop_acc on stop trials
            ss_delay = np.nan
        else:  # stop trial: no response; stop_acc alternates 1/0
            key_press, rt = -1.0, -1
            stop_acc = 1 if stop_rank[i] % 2 == 0 else 0
            ss_delay = float(rng.integers(200, 500))

        rows.append(
            {
                "exp_id": exp_id,
                "trial_id": "test_trial",
                "time_elapsed": _onset_to_time_elapsed(onset_s, block_duration_ms),
                "block_duration": block_duration_ms,
                "rt": rt,
                "stim_duration": stim_duration_ms,
                "key_press": key_press,
                "correct_response": correct_response,
                "stop_signal_condition": cond,
                "stop_acc": stop_acc,
                "go_acc": 0,
                "SS_delay": ss_delay,
                "SS_duration": 250.0,
                "stim": "stim",
                "stimulus": "",
            }
        )
    return pd.DataFrame(rows)
