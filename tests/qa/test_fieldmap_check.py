import json
from argparse import Namespace

from neuro_workflow.qa.fieldmap_check import (
    FieldmapCheckQa,
    collect_fieldmap_identifiers,
    collect_func_b0_sources,
)


def _make_session(tmp_path, subject="sub-s01", session="ses-01"):
    """Create a minimal BIDS session with func/ and fmap/ dirs."""
    base = tmp_path / subject / session
    (base / "func").mkdir(parents=True)
    (base / "fmap").mkdir(parents=True)
    return base


def _write_json(path, data):
    path.write_text(json.dumps(data))


def test_collect_fieldmap_identifiers_single(tmp_path):
    base = _make_session(tmp_path)
    _write_json(
        base / "fmap" / "sub-s01_ses-01_dir-PA_epi.json",
        {"B0FieldIdentifier": "pepolar_0"},
    )
    result = collect_fieldmap_identifiers(base / "fmap")
    assert result == {"pepolar_0"}


def test_collect_fieldmap_identifiers_multiple(tmp_path):
    base = _make_session(tmp_path)
    _write_json(
        base / "fmap" / "sub-s01_ses-01_dir-PA_epi.json",
        {"B0FieldIdentifier": "pepolar_0"},
    )
    _write_json(
        base / "fmap" / "sub-s01_ses-01_dir-AP_epi.json",
        {"B0FieldIdentifier": "pepolar_1"},
    )
    result = collect_fieldmap_identifiers(base / "fmap")
    assert result == {"pepolar_0", "pepolar_1"}


def test_collect_fieldmap_identifiers_no_fmap_dir(tmp_path):
    result = collect_fieldmap_identifiers(tmp_path / "nonexistent")
    assert result == set()


def test_collect_func_b0_sources_string(tmp_path):
    base = _make_session(tmp_path)
    _write_json(
        base / "func" / "sub-s01_ses-01_task-rest_run-1_bold.json",
        {"B0FieldSource": "pepolar_0", "RepetitionTime": 1.0},
    )
    result = collect_func_b0_sources(base / "func")
    assert result == [("sub-s01_ses-01_task-rest_run-1_bold.json", {"pepolar_0"})]


def test_collect_func_b0_sources_list(tmp_path):
    base = _make_session(tmp_path)
    _write_json(
        base / "func" / "sub-s01_ses-01_task-rest_run-1_bold.json",
        {"B0FieldSource": ["pepolar_0", "pepolar_1"]},
    )
    result = collect_func_b0_sources(base / "func")
    assert result == [("sub-s01_ses-01_task-rest_run-1_bold.json", {"pepolar_0", "pepolar_1"})]


def test_collect_func_b0_sources_no_field(tmp_path):
    base = _make_session(tmp_path)
    _write_json(
        base / "func" / "sub-s01_ses-01_task-rest_run-1_bold.json",
        {"RepetitionTime": 1.0},
    )
    result = collect_func_b0_sources(base / "func")
    assert result == []


def test_qa_attributes():
    qa = FieldmapCheckQa()
    assert qa.name == "fieldmap-check"
    assert qa.description


def test_run_reports_missing_fieldmap(tmp_path, capsys):
    bids = tmp_path / "bids"
    base = _make_session(bids)

    # Functional scan references pepolar_0, but no fieldmap has that identifier
    _write_json(
        base / "func" / "sub-s01_ses-01_task-rest_run-1_bold.json",
        {"B0FieldSource": "pepolar_0"},
    )
    _write_json(
        base / "fmap" / "sub-s01_ses-01_dir-PA_epi.json",
        {"B0FieldIdentifier": "pepolar_1"},  # wrong identifier
    )

    qa = FieldmapCheckQa()
    qa.run("discovery", {"bids_dir": str(bids)}, Namespace())

    captured = capsys.readouterr()
    assert "pepolar_0" in captured.out
    assert "MISSING" in captured.out


def test_run_passes_when_all_matched(tmp_path, capsys):
    bids = tmp_path / "bids"
    base = _make_session(bids)

    _write_json(
        base / "func" / "sub-s01_ses-01_task-rest_run-1_bold.json",
        {"B0FieldSource": "pepolar_0"},
    )
    _write_json(
        base / "fmap" / "sub-s01_ses-01_dir-PA_epi.json",
        {"B0FieldIdentifier": "pepolar_0"},
    )

    qa = FieldmapCheckQa()
    qa.run("discovery", {"bids_dir": str(bids)}, Namespace())

    captured = capsys.readouterr()
    assert "MISSING" not in captured.out
    assert "0 scans" in captured.out
