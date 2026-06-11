"""QC thresholds and task definitions — ported from network-behavior-qc/globals.py.

Threshold VALUES now live in config/thresholds.yaml (config-as-code); this module
binds the same public constant names from that config at import, so importers
(events/qc.py, etc.) are unchanged. See neuro_workflow.core.thresholds.
"""
from neuro_workflow.core.thresholds import behavioral_qc as _behavioral_qc

_BQC = _behavioral_qc()

# Stop signal task
STOP_SUCCESS_ACC_LOW_THRESHOLD = _BQC["stop_success_acc_low_threshold"]
STOP_SUCCESS_ACC_HIGH_THRESHOLD = _BQC["stop_success_acc_high_threshold"]
GO_RT_THRESHOLD_FMRI = _BQC["go_rt_threshold_fmri"]
GO_RT_THRESHOLD_FMRI_DUAL_TASK = _BQC["go_rt_threshold_fmri_dual_task"]

# Go/nogo fMRI exclusion thresholds (both conditions must be met)
GONOGO_GO_ACC_THRESHOLD_1 = _BQC["gonogo_go_acc_threshold_1"]
GONOGO_NOGO_ACC_THRESHOLD_1 = _BQC["gonogo_nogo_acc_threshold_1"]
GONOGO_GO_ACC_THRESHOLD_2 = _BQC["gonogo_go_acc_threshold_2"]
GONOGO_NOGO_ACC_THRESHOLD_2 = _BQC["gonogo_nogo_acc_threshold_2"]

# N-back fMRI exclusion thresholds (both conditions must be met)
NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_1 = _BQC["nback_1back_match_acc_combined_threshold_1"]
NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 = _BQC["nback_1back_mismatch_acc_combined_threshold_1"]
NBACK_1BACK_MATCH_ACC_COMBINED_THRESHOLD_2 = _BQC["nback_1back_match_acc_combined_threshold_2"]
NBACK_1BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2 = _BQC["nback_1back_mismatch_acc_combined_threshold_2"]
NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_1 = _BQC["nback_2back_match_acc_combined_threshold_1"]
NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_1 = _BQC["nback_2back_mismatch_acc_combined_threshold_1"]
NBACK_2BACK_MATCH_ACC_COMBINED_THRESHOLD_2 = _BQC["nback_2back_match_acc_combined_threshold_2"]
NBACK_2BACK_MISMATCH_ACC_COMBINED_THRESHOLD_2 = _BQC["nback_2back_mismatch_acc_combined_threshold_2"]

# All other tasks
ACC_THRESHOLD = _BQC["acc_threshold"]
OMISSION_RATE_THRESHOLD = _BQC["omission_rate_threshold"]

# Trimming detection
LAST_N_TEST_TRIALS = _BQC["last_n_test_trials"]
SUMMARY_ROWS = _BQC["summary_rows"]
