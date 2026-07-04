"""Non-monotonic onset truncation + >half exclusion.

A raw jsPsych ``time_elapsed`` clock glitch (a backward jump) produces an
``events.tsv`` whose onsets step backward once. The trials after the jump have
unreliable absolute timing, so:

  * ``create_events_df`` TRUNCATES the events at the first non-monotonic onset
    (keeps the clean monotonic prefix).
  * ``run_qc`` EXCLUDES the scan when truncation would drop > half the test
    trials (otherwise the silent truncation above is enough).
"""

import pandas as pd
import pytest


# --- pure cut-finder -------------------------------------------------------


class TestFindNonmonotonicCut:
    def test_monotonic_returns_none(self):
        from neuro_workflow.events.utils import find_nonmonotonic_cut

        assert find_nonmonotonic_cut([1.0, 2.0, 3.0, 4.0]) is None

    def test_equal_onsets_allowed(self):
        from neuro_workflow.events.utils import find_nonmonotonic_cut

        assert find_nonmonotonic_cut([1.0, 1.0, 2.0, 2.0]) is None

    def test_first_backward_step_index(self):
        from neuro_workflow.events.utils import find_nonmonotonic_cut

        # 3.0 -> 2.5 at position 3 is the first decrease
        assert find_nonmonotonic_cut([1.0, 2.0, 3.0, 2.5, 3.5]) == 3

    def test_empty_and_single(self):
        from neuro_workflow.events.utils import find_nonmonotonic_cut

        assert find_nonmonotonic_cut([]) is None
        assert find_nonmonotonic_cut([5.0]) is None


# --- truncation stats on a built df ---------------------------------------


class TestNonmonotonicTruncation:
    def test_drops_backward_tail_counts_test_trials(self):
        from neuro_workflow.events.create import _nonmonotonic_truncation

        df = pd.DataFrame(
            {
                "onset": [1.0, 2.0, 3.0, 2.5, 3.5],
                "trial_id": [
                    "test_trial",
                    "test_fixation",
                    "test_trial",
                    "test_trial",
                    "test_trial",
                ],
            }
        )
        cut, n_total, n_dropped = _nonmonotonic_truncation(df)
        assert cut == 3
        assert n_total == 4  # four test_trial rows total
        assert n_dropped == 2  # rows 3,4 are test_trial

    def test_monotonic_no_cut(self):
        from neuro_workflow.events.create import _nonmonotonic_truncation

        df = pd.DataFrame(
            {
                "onset": [1.0, 2.0, 3.0],
                "trial_id": ["test_trial"] * 3,
            }
        )
        cut, n_total, n_dropped = _nonmonotonic_truncation(df)
        assert cut is None and n_total == 3 and n_dropped == 0


# --- end-to-end through the real events pipeline --------------------------


def _make_backward_jump_csv(path, *, n_trials, jump_after_test_trial, offset_ms=12000.0):
    """Synth a flanker CSV, then shift ``time_elapsed`` of the tail backward.

    The shift starts at the (``jump_after_test_trial``+1)-th test trial, so the
    recovered onsets step backward exactly once there.
    """
    from neuro_workflow.testing.raw_jspsych import make_raw_jspsych_csv

    make_raw_jspsych_csv(path, "flanker", n_trials=n_trials, iti=3.0)
    df = pd.read_csv(path)
    test_pos = df.index[df["trial_id"] == "test_trial"].tolist()
    cut_raw_idx = test_pos[jump_after_test_trial]
    df.loc[df.index >= cut_raw_idx, "time_elapsed"] = (
        df.loc[df.index >= cut_raw_idx, "time_elapsed"] - offset_ms
    )
    df.to_csv(path, index=False)
    return path


class TestCreateEventsTruncates:
    def test_backward_jump_yields_monotonic_truncated_events(self, tmp_path):
        from neuro_workflow.events.create import create_events_df

        csv = _make_backward_jump_csv(
            tmp_path / "sub-s01_ses-01_task-flanker_beh.csv",
            n_trials=40,
            jump_after_test_trial=34,  # ~15% of trials past the jump
        )
        ev = create_events_df(csv, "flanker")
        assert ev["onset"].is_monotonic_increasing
        # tail (post-jump) trials were dropped, so fewer test trials remain
        assert (ev["trial_id"] == "test_trial").sum() < 40


class TestRunQCExcludesMajorityNonmonotonic:
    def test_excludes_when_majority_dropped(self, tmp_path):
        from neuro_workflow.events.qc import run_qc

        beh = tmp_path / "sourcedata" / "sub-s01" / "ses-01" / "beh"
        beh.mkdir(parents=True)
        # jump after only 12 of 40 test trials -> 28/40 = 70% dropped (> half)
        _make_backward_jump_csv(
            beh / "sub-s01_ses-01_task-flanker_beh.csv",
            n_trials=40,
            jump_after_test_trial=12,
        )
        excl, _trim = run_qc(behavioral_dir=tmp_path / "sourcedata", bids_dir=tmp_path)
        nonmono = [e for e in excl if "non-monotonic" in e["reason"].lower()]
        assert len(nonmono) == 1
        e = nonmono[0]
        assert e["subject"] == "sub-s01" and e["session"] == "ses-01"
        assert e["task"] == "task-flanker" and e["action"] == "exclude"
        assert e["source"] == "behavioral-qc"

    def test_no_exclusion_when_minority_dropped(self, tmp_path):
        from neuro_workflow.events.qc import run_qc

        beh = tmp_path / "sourcedata" / "sub-s02" / "ses-01" / "beh"
        beh.mkdir(parents=True)
        # jump after 36 of 40 -> only 10% dropped (truncate, do NOT exclude)
        _make_backward_jump_csv(
            beh / "sub-s02_ses-01_task-flanker_beh.csv",
            n_trials=40,
            jump_after_test_trial=36,
        )
        excl, _trim = run_qc(behavioral_dir=tmp_path / "sourcedata", bids_dir=tmp_path)
        nonmono = [e for e in excl if "non-monotonic" in e["reason"].lower()]
        assert nonmono == []
