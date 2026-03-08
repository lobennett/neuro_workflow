import json
import sys
from pathlib import Path
from fmriprep_workflow.cli import main


def test_add_dataset_creates_config(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "fmriprep-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
        "--fmriprep-version", "24.1.0",
    ])
    main()

    data = json.loads(config_file.read_text())
    assert "myds" in data
    assert data["myds"]["fmriprep_version"] == "24.1.0"


def test_add_dataset_with_optional_args(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "fmriprep-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
        "--fmriprep-version", "24.1.0",
        "--output-spaces", "MNI152NLin2009cAsym:res-2 fsnative",
        "--fmriprep-args", "--no-submm-recon --cifti-output 91k",
        "--partition", "normal",
        "--nthreads", "4",
        "--mail-user", "test@stanford.edu",
    ])
    main()

    data = json.loads(config_file.read_text())
    ds = data["myds"]
    assert ds["output_spaces"] == "MNI152NLin2009cAsym:res-2 fsnative"
    assert ds["fmriprep_args"] == "--no-submm-recon --cifti-output 91k"
    assert ds["partition"] == "normal"
    assert ds["nthreads"] == 4
    assert ds["mail_user"] == "test@stanford.edu"


def test_show_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", tmp_path / "datasets.json")
    monkeypatch.setattr(sys, "argv", ["fmriprep-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "No datasets registered" in output


def test_show_list_with_datasets(tmp_path, monkeypatch, capsys):
    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "discovery": {"bids_dir": "/oak/disc", "subjects_file": "/s.txt", "fmriprep_version": "24.1.0"},
    }))
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)
    monkeypatch.setattr(sys, "argv", ["fmriprep-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "discovery" in output
    assert "/oak/disc" in output
