import json
import sys
from pathlib import Path
from neuro_workflow.cli import main


def test_add_dataset_creates_config(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
    ])
    main()

    data = json.loads(config_file.read_text())
    assert "myds" in data
    assert data["myds"]["bids_dir"] == str(bids)
    assert data["myds"]["subjects_file"] == str(subs)
    # Should NOT have fmriprep-specific fields
    assert "fmriprep_version" not in data["myds"]


def test_add_dataset_with_optional_args(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
        "--partition", "normal",
        "--mail-user", "test@stanford.edu",
    ])
    main()

    data = json.loads(config_file.read_text())
    ds = data["myds"]
    assert ds["partition"] == "normal"
    assert ds["mail_user"] == "test@stanford.edu"


def test_show_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", tmp_path / "datasets.json")
    monkeypatch.setattr(sys, "argv", ["neuro-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "No datasets registered" in output


def test_show_list_with_datasets(tmp_path, monkeypatch, capsys):
    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "discovery": {"bids_dir": "/oak/disc", "subjects_file": "/s.txt"},
    }))
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)
    monkeypatch.setattr(sys, "argv", ["neuro-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "discovery" in output
    assert "/oak/disc" in output


def test_show_renders_fmriprep_script(tmp_path, monkeypatch, capsys):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "test_ds": {
            "bids_dir": "/oak/data/bids",
            "subjects_file": str(subs),
        },
    }))
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "show", "fmriprep", "test_ds",
        "--version", "24.1.0",
        "--output-spaces", "MNI152NLin2009cAsym:res-2",
        "--fs-license", "/home/user/license.txt",
    ])
    main()
    output = capsys.readouterr().out
    assert "#SBATCH -J fmriprep_test_ds" in output
    assert "#SBATCH --array=1-2" in output


def test_submit_renders_and_calls_sbatch(tmp_path, monkeypatch, capsys):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    sif = tmp_path / "images" / "fmriprep_24.1.0.sif"
    sif.parent.mkdir()
    sif.touch()

    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "test_ds": {
            "bids_dir": "/oak/data/bids",
            "subjects_file": str(subs),
            "image_dir": str(sif.parent),
        },
    }))
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    # Mock submit_sbatch to avoid actually calling sbatch
    submitted = []
    monkeypatch.setattr("neuro_workflow.cli.submit_sbatch", lambda script: submitted.append(script) or "Submitted batch job 12345")

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "submit", "fmriprep", "test_ds",
        "--version", "24.1.0",
        "--output-spaces", "MNI152NLin2009cAsym:res-2",
        "--fs-license", "/home/user/license.txt",
    ])
    main()
    assert len(submitted) == 1
    assert "#SBATCH -J fmriprep_test_ds" in submitted[0]
