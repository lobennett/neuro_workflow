import pandas as pd


def _make_stop_signal_events():
    """Minimal stop signal events TSV as DataFrame."""
    return pd.DataFrame(
        {
            "trial_id": ["test_trial"] * 10,
            "trial_type": ["go"] * 5 + ["stop_success"] * 3 + ["stop_failure"] * 2,
            "onset": [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 15.0, 17.0, 19.0],
            "response_time": [0.4, 0.5, 0.45, 0.42, 0.48, "n/a", "n/a", "n/a", 0.6, 0.55],
            "acc": [1, 1, 1, 0, 1, 1, 1, 1, 0, 0],
        }
    )


class TestRtTailCutoff:
    def test_no_cutoff_when_all_respond(self):
        from neuro_workflow.events.qc import detect_rt_tail_cutoff

        df = pd.DataFrame(
            {
                "trial_id": ["test_trial"] * 5,
                "rt": [400, 500, 450, 420, 480],
            }
        )
        result = detect_rt_tail_cutoff(df)
        assert result is None

    def test_detects_tail_cutoff(self):
        from neuro_workflow.events.qc import detect_rt_tail_cutoff

        # 5 good responses, then 10 non-responses
        rts = [400, 500, 450, 420, 480] + [-1] * 10
        df = pd.DataFrame(
            {
                "trial_id": ["test_trial"] * 15,
                "rt": rts,
                "time_elapsed": list(range(1000, 16000, 1000)),
            }
        )
        result = detect_rt_tail_cutoff(df)
        assert result is not None
        assert "cutoff_index" in result
        assert "cutoff_before_halfway" in result

    def test_cutoff_before_halfway_flags_exclude(self):
        from neuro_workflow.events.qc import detect_rt_tail_cutoff

        # 2 good, 10 bad -> cutoff is before halfway
        rts = [400, 500] + [-1] * 10
        df = pd.DataFrame(
            {
                "trial_id": ["test_trial"] * 12,
                "rt": rts,
                "time_elapsed": list(range(1000, 13000, 1000)),
            }
        )
        result = detect_rt_tail_cutoff(df)
        assert result is not None
        assert result["cutoff_before_halfway"] is True


class TestCheckStopSignalExclusion:
    def test_valid_stop_signal_not_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion

        # 50% stop success, go_rt < 1000ms -> valid
        metrics = {
            "stop_success_rate": 0.5,
            "go_rt": 800.0,
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is None

    def test_low_stop_success_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion

        metrics = {
            "stop_success_rate": 0.1,  # Below 0.25 threshold
            "go_rt": 800.0,
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is not None
        assert "stop_success" in result["reason"]

    def test_high_stop_success_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion

        metrics = {
            "stop_success_rate": 0.9,  # Above 0.75 threshold
            "go_rt": 800.0,
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is not None

    def test_high_go_rt_excluded(self):
        from neuro_workflow.events.qc import check_stop_signal_exclusion

        metrics = {
            "stop_success_rate": 0.5,
            "go_rt": 1100.0,  # Above 1000ms threshold
        }
        result = check_stop_signal_exclusion(metrics)
        assert result is not None
        assert "go_rt" in result["reason"]


class TestCheckGoNogoExclusion:
    def test_valid_gonogo_not_excluded(self):
        from neuro_workflow.events.qc import check_go_nogo_exclusion

        metrics = {"go_acc": 0.9, "nogo_acc": 0.6}
        assert check_go_nogo_exclusion(metrics) is None

    def test_both_rules_triggered(self):
        from neuro_workflow.events.qc import check_go_nogo_exclusion

        # rule1: go <= 0.75 or nogo <= 0.2 -> nogo=0.1 triggers
        # rule2: go <= 0.5 or nogo <= 0.5  -> nogo=0.1 triggers
        metrics = {"go_acc": 0.9, "nogo_acc": 0.1}
        result = check_go_nogo_exclusion(metrics)
        assert result is not None


class TestCheckOtherExclusion:
    def test_valid_not_excluded(self):
        from neuro_workflow.events.qc import check_other_exclusion

        metrics = {"acc": 0.8, "omission_rate": 0.1}
        assert check_other_exclusion(metrics) is None

    def test_low_accuracy_excluded(self):
        from neuro_workflow.events.qc import check_other_exclusion

        metrics = {"acc": 0.4, "omission_rate": 0.1}
        result = check_other_exclusion(metrics)
        assert result is not None
        assert "accuracy" in result["reason"]

    def test_high_omission_excluded(self):
        from neuro_workflow.events.qc import check_other_exclusion

        metrics = {"acc": 0.8, "omission_rate": 0.35}
        result = check_other_exclusion(metrics)
        assert result is not None
        assert "omission" in result["reason"]


class TestRunQcRunLabel:
    """B1 regression: a behavioral-QC failure on run-2 must key to run-2,
    not the previously-hardcoded run-1 (which never matched the lev1 run key)."""

    def test_determine_exclusion_entry_uses_parsed_run_label(self, tmp_path):
        from neuro_workflow.events.qc import run_qc

        beh = tmp_path / "sourcedata" / "sub-s99" / "ses-02" / "beh"
        beh.mkdir(parents=True)
        # Generic task (flanker), run-2: 5/12 omissions (0.42 > 0.25 threshold),
        # interleaved so it is NOT an end-of-run tail cutoff -> only the
        # determine_exclusion (omission) branch fires.
        rt = [500, -1, 480, -1, 520, -1, 510, -1, 505, -1, 495, 530]
        df = pd.DataFrame(
            {
                "trial_id": ["test_trial"] * 12,
                "rt": rt,
                "key_press": [1] * 12,
                "correct_response": [1] * 12,
            }
        )
        df.to_csv(beh / "sub-s99_ses-02_task-flanker_run-2_events.csv", index=False)

        exclusion_entries, _trim = run_qc(
            behavioral_dir=tmp_path / "sourcedata",
            bids_dir=tmp_path,
        )
        excl = [e for e in exclusion_entries if e["task"] == "task-flanker"]
        assert len(excl) == 1, exclusion_entries
        # The bug stored "run-1" here; the parsed label is "run-2".
        assert excl[0]["run"] == "run-2", excl[0]
        assert excl[0]["subject"] == "sub-s99"
        assert excl[0]["session"] == "ses-02"
        assert "omission" in excl[0]["reason"]
