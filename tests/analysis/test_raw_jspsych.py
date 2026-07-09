"""Raw-jsPsych CSV synthesis — the last bypassed simulation boundary.

The cohort/simulate stack feeds the behavioral QC the *sourcedata* (QC-shape)
CSV, but the REAL ``events.create.create_events_df`` consumes the full raw
jsPsych export (``exp_id`` / ``time_elapsed`` / ``block_duration`` /
``stim_duration`` / an ``fmri_trigger_initial`` row + the task condition
columns). This module proves the new
:func:`neuro_workflow.testing.raw_jspsych.make_raw_jspsych_csv` writes a raw CSV
that:

  1. the REAL ``create_events_df`` parses into a valid BIDS events.tsv (onsets
     monotonic and where planted; ``trial_type`` carrying the task conditions);
  2. that events.tsv, pushed through the REAL lev1 events path
     (``preprocess_events`` -> ``add_junk_trials``) + ``create_design_matrix``,
     yields a design whose regressors satisfy the task YAML — congruent /
     incongruent for flanker (cross-checked against
     ``get_regressor_config('flanker')`` and the contrast formula); and
  3. the SAME raw CSV drives the REAL behavioral QC
     (``compute_metrics_from_csv`` / ``determine_exclusion``): a clean CSV is
     not flagged and a high-omission CSV is — unifying the two CSV shapes (the
     raw export is a superset of the QC-shape, so one writer serves both).

Everything load-bearing is production code (``events.create``,
``events.qc``, ``lev1.processing.*``, ``task_config.loader``); the ONLY new
thing is the additive ``testing.raw_jspsych`` helper.
"""

from __future__ import annotations

import pytest

# The synth writer + the real events/QC/design code all need pandas; the
# design leg additionally needs nilearn. Skip cleanly if absent.
pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from neuro_workflow.analysis.lev1.processing.design import (  # noqa: E402
    create_design_matrix,
)
from neuro_workflow.analysis.lev1.processing.events import (  # noqa: E402
    add_junk_trials,
    preprocess_events,
)
from neuro_workflow.analysis.task_config.loader import (  # noqa: E402
    get_regressor_config,
    get_task_contrasts,
)
from neuro_workflow.events.create import create_events_df  # noqa: E402
from neuro_workflow.events.qc import (  # noqa: E402
    compute_metrics_from_csv,
    determine_exclusion,
)
from neuro_workflow.testing.raw_jspsych import make_raw_jspsych_csv  # noqa: E402


# --------------------------------------------------------------------------- #
# Helper: run the produced events.tsv through the REAL lev1 events path +
# design build (the genuine path the runner takes between events.tsv and GLM).
# --------------------------------------------------------------------------- #
def _build_design(events_tsv, task, n_scans=120, tr=1.49):
    events = pd.read_csv(events_tsv, sep="\t")
    prepped = preprocess_events(events, task, n_scans=n_scans, tr=tr)
    junked, _ = add_junk_trials(prepped, task)
    confounds = pd.DataFrame({"constant": np.ones(n_scans)})
    design, _ = create_design_matrix(junked, confounds, task, n_scans, tr)
    return design


# --------------------------------------------------------------------------- #
# Part 1a: events.create parses the raw CSV into a valid events.tsv.
# --------------------------------------------------------------------------- #
class TestFlankerRawToEvents:
    def test_create_events_df_produces_valid_events_tsv(self, tmp_path):
        """REAL create_events_df turns the raw flanker CSV into an events.tsv
        with monotonic onsets and congruent/incongruent trial_types."""
        raw = make_raw_jspsych_csv(tmp_path / "raw_flanker.csv", "flanker", n_trials=24, seed=0)
        events = create_events_df(raw, "flanker")

        # Onsets present, numeric, strictly increasing.
        assert "onset" in events.columns
        onsets = pd.to_numeric(events["onset"])
        assert onsets.is_monotonic_increasing
        assert (onsets >= 0).all()

        # trial_type carries the flanker conditions the YAML subsets reference.
        ttypes = set(events["trial_type"].unique())
        assert {"congruent", "incongruent"} <= ttypes

        # The columns the flanker design references at the events level.
        for col in (
            "onset",
            "duration",
            "response_time",
            "trial_id",
            "trial_type",
            "key_press",
            "correct_response",
        ):
            assert col in events.columns, f"events.tsv missing {col}"

    def test_planted_onsets_land_where_requested(self, tmp_path):
        """First onset / ITI are honored exactly through the real pipeline."""
        raw = make_raw_jspsych_csv(
            tmp_path / "raw.csv",
            "flanker",
            n_trials=10,
            seed=1,
            first_onset=5.0,
            iti=3.0,
        )
        events = create_events_df(raw, "flanker")
        onsets = pd.to_numeric(events["onset"]).tolist()
        # n=10 test trials at 5, 8, 11, ... (3s spacing) after dummy adjust.
        assert onsets[0] == pytest.approx(5.0, abs=1e-6)
        assert onsets[1] == pytest.approx(8.0, abs=1e-6)
        assert len(onsets) == 10


# --------------------------------------------------------------------------- #
# Part 1b: the events.tsv satisfies the flanker task YAML (lev1-valid).
# --------------------------------------------------------------------------- #
class TestFlankerEventsSatisfyYaml:
    def test_design_has_yaml_event_regressors_nonzero(self, tmp_path):
        """The design built from the synthetic events.tsv has the flanker YAML's
        event-driven regressors (congruent / incongruent / response_time) and
        they are non-degenerate (non-zero)."""
        raw = make_raw_jspsych_csv(tmp_path / "raw.csv", "flanker", n_trials=40, seed=2)
        events_tsv = tmp_path / "flanker_events.tsv"
        create_events_df(raw, "flanker").to_csv(events_tsv, sep="\t", index=False, na_rep="n/a")
        design = _build_design(events_tsv, "flanker")

        for reg in ("congruent", "incongruent", "response_time"):
            assert reg in design.columns, f"design missing regressor {reg}"
            assert (
                np.abs(design[reg].to_numpy()).sum() > 0
            ), f"regressor {reg} is all-zero (degenerate)"

    def test_contrast_formula_regressors_present(self, tmp_path):
        """Every regressor named in the flanker contrast formulas is a design
        column (cross-checked against get_task_contrasts / regressor config)."""
        raw = make_raw_jspsych_csv(tmp_path / "raw.csv", "flanker", n_trials=40, seed=3)
        events_tsv = tmp_path / "ev.tsv"
        create_events_df(raw, "flanker").to_csv(events_tsv, sep="\t", index=False, na_rep="n/a")
        design = _build_design(events_tsv, "flanker")

        # The headline contrast must be computable: its tokens are design cols.
        formula = get_task_contrasts("flanker")["incongruent-congruent"]
        assert formula == "incongruent - congruent"
        for token in ("incongruent", "congruent"):
            assert token in design.columns

        # Every declared regressor in the YAML is realized as a design column.
        declared = set(get_regressor_config("flanker").keys())
        assert declared <= set(
            design.columns
        ), f"YAML regressors missing from design: {declared - set(design.columns)}"


# --------------------------------------------------------------------------- #
# Part 1c: the SAME raw CSV drives behavioral QC (unified shape).
# --------------------------------------------------------------------------- #
class TestRawCsvDrivesBehavioralQC:
    def test_clean_raw_csv_not_flagged(self, tmp_path):
        raw = make_raw_jspsych_csv(
            tmp_path / "clean.csv",
            "flanker",
            n_trials=40,
            seed=4,
            omission_rate=0.0,
            accuracy=1.0,
        )
        metrics = compute_metrics_from_csv(raw, "flanker")
        assert metrics.get("omission_rate") == pytest.approx(0.0)
        assert metrics.get("acc") == pytest.approx(1.0)
        assert determine_exclusion("flanker", metrics) is None

    def test_high_omission_raw_csv_is_flagged(self, tmp_path):
        """A high-omission raw flanker CSV both parses to events AND trips the
        REAL behavioral omission exclusion (>0.25)."""
        raw = make_raw_jspsych_csv(
            tmp_path / "bad.csv",
            "flanker",
            n_trials=40,
            seed=5,
            omission_rate=0.5,
        )
        # It still produces a (valid) events.tsv ...
        events = create_events_df(raw, "flanker")
        assert pd.to_numeric(events["onset"]).is_monotonic_increasing
        # ... AND it is flagged by behavioral QC.
        metrics = compute_metrics_from_csv(raw, "flanker")
        assert metrics["omission_rate"] == pytest.approx(0.5)
        excl = determine_exclusion("flanker", metrics)
        assert excl is not None
        assert "omission" in excl["reason"]

    def test_omission_boundary_is_strict(self, tmp_path):
        """At exactly the 0.25 threshold (strict >) the scan is NOT flagged;
        just over it is — pins the boundary the way the cohort tests do."""
        at = make_raw_jspsych_csv(
            tmp_path / "at.csv",
            "flanker",
            n_trials=40,
            seed=6,
            omission_rate=0.25,  # 10/40 — AT threshold
        )
        over = make_raw_jspsych_csv(
            tmp_path / "over.csv",
            "flanker",
            n_trials=40,
            seed=7,
            omission_rate=0.275,  # 11/40 — over threshold
        )
        assert determine_exclusion("flanker", compute_metrics_from_csv(at, "flanker")) is None
        assert determine_exclusion("flanker", compute_metrics_from_csv(over, "flanker")) is not None


# --------------------------------------------------------------------------- #
# stopSignal (the cheap second task): events + QC both work.
# --------------------------------------------------------------------------- #
class TestStopSignalRaw:
    def test_stop_signal_events_have_go_and_stop_trial_types(self, tmp_path):
        """REAL create_events_df on a raw stopSignal CSV yields go /
        stop_success / stop_failure trial_types (the stopSignal YAML's)."""
        raw = make_raw_jspsych_csv(tmp_path / "ss.csv", "stopSignal", n_trials=40, seed=8)
        events = create_events_df(raw, "stopSignal")
        onsets = pd.to_numeric(events["onset"])
        assert onsets.is_monotonic_increasing
        ttypes = set(events["trial_type"].unique())
        # go is always present; at least one stop_* class present.
        assert "go" in ttypes
        assert ttypes & {"stop_success", "stop_failure"}

    def test_stop_signal_slow_go_rt_is_flagged(self, tmp_path):
        """A slow-go-RT stopSignal raw CSV trips the REAL go_rt > 1000ms rule."""
        raw = make_raw_jspsych_csv(
            tmp_path / "slow.csv",
            "stopSignal",
            n_trials=40,
            seed=9,
            go_rt_ms=1200.0,
        )
        metrics = compute_metrics_from_csv(raw, "stopSignal")
        assert metrics.get("go_rt") == pytest.approx(1200.0)
        excl = determine_exclusion("stopSignal", metrics)
        assert excl is not None
        assert "go_rt" in excl["reason"]

    def test_stop_signal_clean_not_flagged(self, tmp_path):
        raw = make_raw_jspsych_csv(
            tmp_path / "ok.csv",
            "stopSignal",
            n_trials=40,
            seed=10,
            go_rt_ms=500.0,
        )
        metrics = compute_metrics_from_csv(raw, "stopSignal")
        assert determine_exclusion("stopSignal", metrics) is None


# --------------------------------------------------------------------------- #
# Dual-task raw-frame builders (minimal jsPsych exports mirroring the REAL
# raw_cleaned structure for the two tasks whose events.create transform is
# under test). These synthesize the exact columns/row-ordering the production
# `create_events_df` reads, so the fixes are exercised end-to-end rather than
# via a stub of the transform.
# --------------------------------------------------------------------------- #
from neuro_workflow.core.acquisition import N_DUMMY, TR_SECONDS  # noqa: E402

_TRIGGER_MS = 60000.0
_DUMMY_MS = N_DUMMY * TR_SECONDS * 1000.0
_BLOCK_MS = 2000.0


def _te(onset_s: float) -> float:
    """Plant time_elapsed so create_events_df recovers events onset ``onset_s``."""
    return _TRIGGER_MS + _BLOCK_MS + _DUMMY_MS + onset_s * 1000.0


def _write_cued_ts_flanker_csv(path, cue_switch_pairs, flankers):
    """Raw flanker_with_cued_task_switching export.

    The cued-task-switch factor (cue_condition / task_condition) lives ONLY on
    the ``test_cue`` row; ``flanker_condition`` is on both the cue and the
    following ``test_trial`` row. Rows are ordered cue-then-trial per trial, as
    in the real export.
    """
    exp_id = "flanker_with_cued_task_switching"
    trig = {
        "exp_id": exp_id,
        "trial_id": "fmri_trigger_initial",
        "time_elapsed": _TRIGGER_MS,
        "block_duration": _BLOCK_MS,
        "rt": int(_BLOCK_MS),
        "stim_duration": np.nan,
        "key_press": np.nan,
        "correct_response": np.nan,
        "flanker_condition": np.nan,
        "cue": np.nan,
        "task_condition": np.nan,
        "cue_condition": np.nan,
        "flanking_number": np.nan,
        "stimulus": "",
    }
    rows = [trig]
    onset = 5.0
    for (cue_cond, task_cond), flk in zip(cue_switch_pairs, flankers):
        rows.append(
            {
                "exp_id": exp_id,
                "trial_id": "test_cue",
                "time_elapsed": _te(onset),
                "block_duration": _BLOCK_MS,
                "rt": -1,
                "stim_duration": 500.0,
                "key_press": -1,
                "correct_response": np.nan,
                "flanker_condition": flk,
                "cue": "Parity",
                "task_condition": task_cond,
                "cue_condition": cue_cond,
                "flanking_number": np.nan,
                "stimulus": "",
            }
        )
        onset += 1.5
        rows.append(
            {
                "exp_id": exp_id,
                "trial_id": "test_trial",
                "time_elapsed": _te(onset),
                "block_duration": _BLOCK_MS,
                "rt": 700,
                "stim_duration": 1000.0,
                "key_press": 71.0,
                "correct_response": 71.0,
                "flanker_condition": flk,
                "cue": "Parity",
                "task_condition": np.nan,  # switch factor absent on trial row
                "cue_condition": np.nan,
                "flanking_number": 5.0,
                "stimulus": "",
            }
        )
        onset += 1.5
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# --------------------------------------------------------------------------- #
# Defect A — cuedTSWFlanker: the cued-task-switch trial_type must be carried
# onto the modeled test_trial row (it lives only on the preceding test_cue).
# --------------------------------------------------------------------------- #
class TestCuedTSWFlankerSwitchFactorOnTestTrial:
    def test_switch_factor_propagated_to_following_test_trial(self, tmp_path):
        raw = _write_cued_ts_flanker_csv(
            tmp_path / "raw_cuedtsflanker.csv",
            cue_switch_pairs=[
                ("switch", "stay"),  # -> switch_stay
                ("stay", "stay"),  # -> stay_stay
                ("switch", "switch"),  # -> switch_switch
                ("na", "na"),  # -> n/a_n/a
            ],
            flankers=["incongruent", "congruent", "incongruent", "congruent"],
        )
        events = create_events_df(raw, "flankerWCuedTS").reset_index(drop=True)

        onsets = pd.to_numeric(events["onset"])
        assert onsets.is_monotonic_increasing

        # Every test_trial carries the switch trial_type of its preceding cue
        # (no n/a left over), and flanker_condition stays on the trial row.
        last_cue_tt = None
        seen_switch_stay = False
        for _, row in events.iterrows():
            if row["trial_id"] == "test_cue":
                last_cue_tt = row["trial_type"]
            elif row["trial_id"] == "test_trial":
                assert row["trial_type"] == last_cue_tt, (
                    f"test_trial trial_type {row['trial_type']!r} != preceding cue "
                    f"{last_cue_tt!r}"
                )
                assert row["trial_type"] != "n/a"
                assert row["flanker_condition"] in {"congruent", "incongruent"}
                if last_cue_tt == "switch_stay":
                    seen_switch_stay = True
        assert seen_switch_stay, "expected a test_trial following a switch_stay cue"
