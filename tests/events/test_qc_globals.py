def test_thresholds_exist():
    from neuro_workflow.events.qc_globals import (
        ACC_THRESHOLD,
        GO_RT_THRESHOLD_FMRI,
        LAST_N_TEST_TRIALS,
        OMISSION_RATE_THRESHOLD,
        STOP_SUCCESS_ACC_HIGH_THRESHOLD,
        STOP_SUCCESS_ACC_LOW_THRESHOLD,
    )

    assert STOP_SUCCESS_ACC_LOW_THRESHOLD == 0.25
    assert STOP_SUCCESS_ACC_HIGH_THRESHOLD == 0.75
    assert GO_RT_THRESHOLD_FMRI == 1000
    assert ACC_THRESHOLD == 0.55
    assert OMISSION_RATE_THRESHOLD == 0.25
    assert LAST_N_TEST_TRIALS == 10


def test_nback_thresholds():
    from neuro_workflow.events.qc_globals import (
        NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1,
        NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1,
    )

    assert NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1 == 0.2
    assert NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 == 0.75
