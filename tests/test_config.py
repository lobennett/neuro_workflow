import json
import os
from pathlib import Path
from fmriprep_workflow.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    load_datasets,
    save_dataset,
    get_dataset,
)


def test_config_dir_is_in_home():
    assert str(CONFIG_DIR) == str(Path.home() / ".fmriprep_workflow")


def test_defaults_has_required_keys():
    expected_keys = {
        "partition", "nthreads", "mem_per_cpu_gb", "time",
        "image_dir", "templateflow_dir", "fs_license",
        "bids_filter_file", "mail_user",
    }
    assert set(DEFAULTS.keys()) == expected_keys


def test_load_datasets_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", tmp_path / "datasets.json")
    assert load_datasets() == {}


def test_save_and_load_dataset(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {
        "bids_dir": "/data/bids",
        "subjects_file": "/data/subs.txt",
        "fmriprep_version": "24.1.0",
    })

    datasets = load_datasets()
    assert "test_ds" in datasets
    assert datasets["test_ds"]["bids_dir"] == "/data/bids"


def test_get_dataset_merges_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {
        "bids_dir": "/data/bids",
        "subjects_file": "/data/subs.txt",
        "fmriprep_version": "24.1.0",
    })

    ds = get_dataset("test_ds")
    # Should have defaults merged in
    assert ds["partition"] == "russpold"
    assert ds["nthreads"] == 8
    # Should have user values
    assert ds["bids_dir"] == "/data/bids"


def test_get_dataset_raises_on_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", tmp_path / "datasets.json")
    try:
        get_dataset("nonexistent")
        assert False, "Should have raised SystemExit"
    except SystemExit:
        pass


def test_save_dataset_overwrites_existing(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/old", "subjects_file": "/s.txt", "fmriprep_version": "1.0"})
    save_dataset("test_ds", {"bids_dir": "/new", "subjects_file": "/s.txt", "fmriprep_version": "2.0"})

    datasets = load_datasets()
    assert datasets["test_ds"]["bids_dir"] == "/new"
