import json
import subprocess
from pathlib import Path

from scripts.fmriprep_preflight import parse_bidsignore


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


from scripts.fmriprep_preflight import build_view


def _make_fake_bids(tmp_path: Path) -> Path:
    """Create a tiny BIDS-like tree for testing."""
    bids = tmp_path / "fake_bids"
    (bids / "sub-s03" / "ses-01" / "anat").mkdir(parents=True)
    (bids / "sub-s03" / "ses-01" / "func").mkdir(parents=True)
    (bids / "sub-s03" / "ses-05" / "anat").mkdir(parents=True)
    (bids / "sub-s03" / "ses-01" / "anat" / "sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").touch()
    (bids / "sub-s03" / "ses-01" / "anat" / "sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.json").touch()
    (bids / "sub-s03" / "ses-05" / "anat" / "sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz").touch()
    (bids / "sub-s03" / "ses-05" / "anat" / "sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.json").touch()
    (bids / "sub-s03" / "ses-01" / "func" / "sub-s03_ses-01_task-flanker_run-1_echo-1_bold.nii.gz").touch()
    (bids / "sub-s03" / "ses-01" / "func" / "sub-s03_ses-01_task-nBack_run-1_echo-1_bold.nii.gz").touch()
    (bids / "dataset_description.json").write_text('{"Name": "fake"}')
    (bids / "README").write_text("fake")
    (bids / ".bidsignore").write_text(
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*\n"
        "sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-1_echo-*_bold.*\n"
    )
    # Should be ignored entirely (not walked):
    (bids / "derivatives" / "junk").mkdir(parents=True)
    (bids / "derivatives" / "junk" / "should_not_appear.nii.gz").touch()
    return bids


def test_build_view_excludes_bidsignored_files(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"

    summary = build_view(bids, view)

    # MPRAGEPromo files NOT in view
    assert not (view / "sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").exists()
    assert not (view / "sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.json").exists()
    # SagMPRAGE files ARE in view
    assert (view / "sub-s03/ses-05/anat/sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz").is_symlink()
    # nBack BOLD excluded
    assert not (view / "sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-1_echo-1_bold.nii.gz").exists()
    # flanker BOLD retained
    assert (view / "sub-s03/ses-01/func/sub-s03_ses-01_task-flanker_run-1_echo-1_bold.nii.gz").is_symlink()


def test_build_view_includes_top_level_metadata(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    assert (view / "dataset_description.json").is_symlink()
    assert (view / "README").is_symlink()
    assert (view / ".bidsignore").is_symlink()


def test_build_view_skips_derivatives_subtree(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    # The derivatives/junk/ subtree must not appear in view
    assert not (view / "derivatives").exists()


def test_build_view_idempotent(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    s1 = build_view(bids, view)
    # Capture symlink lstat (so we read the symlink's metadata, not the target's).
    # If a second run perturbed the symlinks, lstat ctime/mtime would change.
    snapshot_1 = {
        p: p.lstat().st_ctime_ns
        for p in view.rglob("*") if p.is_symlink()
    }
    assert snapshot_1, "fixture should produce some symlinks"

    s2 = build_view(bids, view)
    snapshot_2 = {
        p: p.lstat().st_ctime_ns
        for p in view.rglob("*") if p.is_symlink()
    }

    assert s1["files_linked"] == s2["files_linked"]
    assert s1["files_excluded"] == s2["files_excluded"]
    # The strong idempotency property: no symlinks were touched on the second run.
    assert snapshot_1 == snapshot_2, "second run perturbed existing symlinks"


def test_build_view_summary_counts(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    summary = build_view(bids, view)
    # Expected: 3 top-level files (dataset_description, README, .bidsignore)
    # + 2 SagMPRAGE files (nii.gz + json) + 1 flanker BOLD = 6 linked
    # Excluded: 2 MPRAGEPromo + 1 nBack = 3
    assert summary["files_linked"] == 6
    assert summary["files_excluded"] == 3


def test_build_view_replaces_stale_directory_with_symlink(tmp_path):
    """A pre-existing directory at a desired symlink path must be replaced cleanly."""
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    # First run produces the view normally
    build_view(bids, view)
    # Simulate a prior partial run that left a directory where a symlink should be
    target = view / "sub-s03/ses-05/anat/sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz"
    target.unlink()  # remove the symlink
    target.mkdir()  # replace with a directory
    (target / "stale_inner_file").touch()
    # Second run must clean it up and replace with a symlink, no exception
    build_view(bids, view)
    assert target.is_symlink()
    assert not target.is_dir() or target.resolve().is_file()  # symlink resolves to file


def test_build_view_prunes_empty_subject_dir_after_bidsignore_change(tmp_path):
    """If a subject's BOLDs all become .bidsignore'd between runs, the empty
    subject skeleton should not remain in the view."""
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"

    # First run: s03 has files in the view
    build_view(bids, view)
    assert (view / "sub-s03").is_dir()

    # Now expand .bidsignore to exclude EVERY remaining s03 file
    bidsignore = bids / ".bidsignore"
    bidsignore.write_text(
        "sub-s03/ses-*/anat/*.*\n"
        "sub-s03/ses-*/func/*.*\n"
    )

    build_view(bids, view)
    # sub-s03 dir should be entirely gone (no ghost skeleton)
    assert not (view / "sub-s03").exists()


from scripts.fmriprep_preflight import verify_view


def test_verify_view_passes_when_every_subject_has_t1w(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    # Default: no expected multi-anat for this fake dataset
    errors = verify_view(view, expected_multi_anat={})
    assert errors == []


def test_verify_view_fails_when_subject_has_no_t1w(tmp_path):
    bids = tmp_path / "fake_bids"
    (bids / "sub-s03" / "ses-01" / "anat").mkdir(parents=True)
    # Only an MPRAGEPromo, which is .bidsignore'd
    (bids / "sub-s03" / "ses-01" / "anat" / "sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").touch()
    (bids / "dataset_description.json").write_text("{}")
    (bids / ".bidsignore").write_text("sub-*/ses-*/anat/*MPRAGEPromo*\n")
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    errors = verify_view(view, expected_multi_anat={})
    assert any("sub-s03" in e and "no T1w" in e for e in errors)


def test_verify_view_checks_expected_multi_anat(tmp_path):
    bids = tmp_path / "fake_bids"
    (bids / "sub-s1351" / "ses-01" / "anat").mkdir(parents=True)
    (bids / "sub-s1351" / "ses-08" / "anat").mkdir(parents=True)
    (bids / "sub-s1351" / "ses-01" / "anat" / "sub-s1351_ses-01_acq-SagMPRAGE_run-1_T1w.nii.gz").touch()
    (bids / "sub-s1351" / "ses-08" / "anat" / "sub-s1351_ses-08_acq-SagMPRAGE_run-1_T1w.nii.gz").touch()
    (bids / "dataset_description.json").write_text("{}")
    (bids / ".bidsignore").write_text("")
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)

    # Expected 2 T1w — passes
    errors = verify_view(view, expected_multi_anat={"s1351": {"T1w": 2}})
    assert errors == []

    # Expected 3 T1w — fails (only 2 in view)
    errors = verify_view(view, expected_multi_anat={"s1351": {"T1w": 3}})
    assert any("s1351" in e for e in errors)


def test_verify_view_fails_when_view_dir_missing(tmp_path):
    """Calling verify_view on a non-existent view should not silently pass."""
    nonexistent = tmp_path / "no_such_view"
    errors = verify_view(nonexistent, expected_multi_anat={})
    assert any("does not exist" in e for e in errors)


def test_cli_smoke(tmp_path):
    """End-to-end: build a fake BIDS, run the CLI against it, check view exists."""
    bids = _make_fake_bids(tmp_path)

    # Fake datasets.json
    datasets_json = tmp_path / "datasets.json"
    datasets_json.write_text(json.dumps({
        "fake_ds": {"bids_dir": str(bids), "subjects_file": "ignored"}
    }))

    result = subprocess.run(
        [
            "uv", "run", "python",
            str(PROJECT_ROOT / "scripts" / "fmriprep_preflight.py"),
            "fake_ds",
            "--version", "25.2.4",
            "--datasets-json", str(datasets_json),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    assert view.exists()
    assert (view / "sub-s03" / "ses-05" / "anat" / "sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz").is_symlink()
