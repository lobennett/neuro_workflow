"""Tests for scripts/reconcile_audit.py."""


def test_view_membership_diff_flags_now_excluded_and_newly_included():
    from scripts.reconcile_audit import view_membership_diff
    view_scans = {"sub-s10_ses-02_task-shapeMatching_run-1",
                  "sub-s10_ses-01_task-cuedTS_run-1"}        # old view
    keep_scans = {"sub-s10_ses-02_task-shapeMatching_run-1",
                  "sub-s10_ses-05_task-goNogo_run-1"}        # new keep-set
    now_excluded, newly_included = view_membership_diff(view_scans, keep_scans)
    assert now_excluded == {"sub-s10_ses-01_task-cuedTS_run-1"}
    assert newly_included == {"sub-s10_ses-05_task-goNogo_run-1"}


def test_view_membership_diff_identical_is_empty():
    from scripts.reconcile_audit import view_membership_diff
    s = {"sub-s10_ses-02_task-shapeMatching_run-1"}
    now_excluded, newly_included = view_membership_diff(s, set(s))
    assert now_excluded == set() and newly_included == set()


def test_scankey_from_name_parses_bold_and_confounds():
    from scripts.reconcile_audit import scankey_from_name
    assert (scankey_from_name("sub-s10_ses-02_task-shapeMatching_run-1_echo-2_bold.nii.gz")
            == "sub-s10_ses-02_task-shapeMatching_run-1")
    assert (scankey_from_name("sub-s10_ses-02_task-shapeMatching_run-1_desc-confounds_timeseries.tsv")
            == "sub-s10_ses-02_task-shapeMatching_run-1")
    assert scankey_from_name("dataset_description.json") is None
