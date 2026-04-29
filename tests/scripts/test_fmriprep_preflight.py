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
