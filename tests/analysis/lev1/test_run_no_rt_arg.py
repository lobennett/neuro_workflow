from neuro_workflow.analysis.lev1.run import get_parser


def test_no_rt_flag_parses():
    a = get_parser().parse_args(
        [
            "--subj-id",
            "sub-s10",
            "--task-name",
            "cuedTS",
            "--bids-dir",
            "/b",
            "--fmriprep-dir",
            "/f",
            "--results-dir",
            "/r",
            "--exclusions-file",
            "/e",
            "--no-rt",
        ]
    )
    assert a.no_rt is True
    assert (
        get_parser()
        .parse_args(
            [
                "--subj-id",
                "x",
                "--task-name",
                "cuedTS",
                "--bids-dir",
                "/b",
                "--fmriprep-dir",
                "/f",
                "--results-dir",
                "/r",
                "--exclusions-file",
                "/e",
            ]
        )
        .no_rt
        is False
    )
