from scripts.fmriprep_preflight import parse_bidsignore


def test_parse_bidsignore_strips_comments_and_blanks(tmp_path):
    bidsignore = tmp_path / ".bidsignore"
    bidsignore.write_text(
        "# comment line\n"
        "\n"
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*\n"
        "  \n"  # whitespace-only line
        "# another comment\n"
        "sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-*_bold.*\n"
    )
    patterns = parse_bidsignore(bidsignore)
    assert patterns == [
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*",
        "sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-*_bold.*",
    ]


def test_parse_bidsignore_missing_file_returns_empty(tmp_path):
    patterns = parse_bidsignore(tmp_path / "nonexistent")
    assert patterns == []


from scripts.fmriprep_preflight import path_matches_any


def test_path_matches_simple_pattern():
    patterns = ["sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*"]
    assert path_matches_any("sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz", patterns)
    assert path_matches_any("sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.json", patterns)


def test_path_matches_subject_specific():
    patterns = ["sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-*_bold.*"]
    assert path_matches_any("sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-1_bold.nii.gz", patterns)
    assert path_matches_any("sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-2_bold.nii.gz", patterns)
    # Different subject — no match
    assert not path_matches_any("sub-s10/ses-08/func/sub-s10_ses-08_task-directedForgetting_run-1_echo-1_bold.nii.gz", patterns)


def test_path_matches_star_does_not_cross_slash():
    """Critical gitignore semantics — `*` does not span path separators."""
    patterns = ["sub-*/anat/*T1w.nii.gz"]
    # Same depth — should match
    assert path_matches_any("sub-s03/anat/sub-s03_T1w.nii.gz", patterns)
    # Different depth — should NOT match
    assert not path_matches_any("sub-s03/ses-01/anat/sub-s03_T1w.nii.gz", patterns)


def test_path_matches_no_patterns():
    assert not path_matches_any("sub-s03/ses-01/anat/sub-s03_T1w.nii.gz", [])


def test_path_matches_run_specific_excludes_only_that_run():
    """s10 ses-01 task-goNogo run-1 is .bidsignore'd, but run-2 must remain."""
    patterns = ["sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-1_echo-*_bold.*"]
    assert path_matches_any("sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-1_echo-1_bold.nii.gz", patterns)
    assert not path_matches_any("sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-2_echo-1_bold.nii.gz", patterns)
