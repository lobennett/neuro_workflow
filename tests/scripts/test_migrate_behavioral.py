"""Tests for scripts/migrate_behavioral.py"""


def _write_manifest(tmp_path, rows):
    """Write a TSV manifest file."""
    manifest = tmp_path / "manifest.tsv"
    header = "subject\tsession\ttask\tstatus\taction\tdest_session\tdest_run\traw_path\tbold_path\tsame_task_other_sessions\tnotes"
    lines = [header]
    for r in rows:
        lines.append("\t".join(str(r.get(c, "")) for c in header.split("\t")))
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def test_migrate_copies_matched_files(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    raw_csv = tmp_path / "raw" / "s03" / "ses-01" / "go-nogo.csv"
    raw_csv.parent.mkdir(parents=True)
    raw_csv.write_text("trial,rt\n1,500\n")

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s03",
                "session": "ses-01",
                "task": "goNogo",
                "status": "matched",
                "action": "copy",
                "dest_session": "ses-01",
                "raw_path": str(raw_csv),
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    report = migrate_from_manifest(manifest, output_dir)

    expected = (
        output_dir
        / "in_scanner_behavior"
        / "sub-s03"
        / "ses-01"
        / "beh"
        / "sub-s03_ses-01_task-goNogo_beh.csv"
    )
    assert expected.exists()
    assert expected.read_text() == "trial,rt\n1,500\n"
    assert report["copied"] == 1


def test_migrate_skips_pending(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s29",
                "session": "ses-01",
                "task": "cuedTS",
                "status": "bold_without_behavioral",
                "action": "pending",
                "dest_session": "ses-01",
                "raw_path": "",
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    report = migrate_from_manifest(manifest, output_dir)

    assert report["copied"] == 0
    assert report["skipped_pending"] == 1


def test_migrate_fails_on_unresolved_pending(tmp_path):
    import pytest

    from scripts.migrate_behavioral import migrate_from_manifest

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s29",
                "session": "ses-01",
                "task": "cuedTS",
                "status": "bold_without_behavioral",
                "action": "pending",
                "dest_session": "ses-01",
                "raw_path": "",
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    with pytest.raises(SystemExit):
        migrate_from_manifest(manifest, output_dir, strict=True)


def test_migrate_respects_dest_session_override(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    raw_csv = tmp_path / "raw" / "s03" / "ses-02" / "nback.csv"
    raw_csv.parent.mkdir(parents=True)
    raw_csv.write_text("trial,rt\n1,600\n")

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s03",
                "session": "ses-02",
                "task": "nBack",
                "status": "matched",
                "action": "copy",
                "dest_session": "ses-01",
                "raw_path": str(raw_csv),
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    migrate_from_manifest(manifest, output_dir)

    expected = (
        output_dir
        / "in_scanner_behavior"
        / "sub-s03"
        / "ses-01"
        / "beh"
        / "sub-s03_ses-01_task-nBack_beh.csv"
    )
    assert expected.exists()


def test_migrate_skips_irreconcilable(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s29",
                "session": "ses-01",
                "task": "cuedTS",
                "status": "bold_without_behavioral",
                "action": "irreconcilable",
                "dest_session": "",
                "raw_path": "",
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    report = migrate_from_manifest(manifest, output_dir)

    assert report["copied"] == 0
    assert report["skipped_irreconcilable"] == 1


def test_migrate_skips_skip_action(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s29",
                "session": "ses-01",
                "task": "cuedTS",
                "status": "behavioral_without_bold",
                "action": "skip",
                "dest_session": "",
                "raw_path": "/some/path.csv",
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    report = migrate_from_manifest(manifest, output_dir)

    assert report["copied"] == 0
    assert report["skipped_skip"] == 1


def test_migrate_uses_dest_run(tmp_path):
    from scripts.migrate_behavioral import migrate_from_manifest

    raw_csv = tmp_path / "raw" / "s29" / "ses-03" / "spatialTS.csv"
    raw_csv.parent.mkdir(parents=True)
    raw_csv.write_text("trial,rt\n1,500\n")

    output_dir = tmp_path / "sourcedata"

    manifest = _write_manifest(
        tmp_path,
        [
            {
                "subject": "s29",
                "session": "ses-03",
                "task": "spatialTS",
                "status": "matched",
                "action": "copy",
                "dest_session": "ses-03",
                "dest_run": "2",
                "raw_path": str(raw_csv),
                "bold_path": "",
                "same_task_other_sessions": "",
                "notes": "",
            }
        ],
    )

    migrate_from_manifest(manifest, output_dir)

    expected = (
        output_dir
        / "in_scanner_behavior"
        / "sub-s29"
        / "ses-03"
        / "beh"
        / "sub-s29_ses-03_task-spatialTS_run-2_beh.csv"
    )
    assert expected.exists()
