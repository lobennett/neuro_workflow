import json
from pathlib import Path
from neuro_workflow.core.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    load_datasets,
    save_dataset,
    get_dataset,
)


def test_config_dir_is_in_home():
    assert str(CONFIG_DIR) == str(Path.home() / ".neuro_workflow")


def test_defaults_has_expected_keys():
    expected_keys = {"partition", "image_dir", "templateflow_dir", "mail_user"}
    assert set(DEFAULTS.keys()) == expected_keys


def test_load_datasets_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", tmp_path / "datasets.json")
    assert load_datasets() == {}


def test_save_and_load_dataset(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/data/bids", "subjects_file": "/data/subs.txt"})

    datasets = load_datasets()
    assert "test_ds" in datasets
    assert datasets["test_ds"]["bids_dir"] == "/data/bids"


def test_get_dataset_merges_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/data/bids", "subjects_file": "/data/subs.txt"})

    ds = get_dataset("test_ds")
    assert ds["partition"] == "russpold"
    assert ds["image_dir"] == "/home/groups/russpold/singularity_images"
    assert ds["bids_dir"] == "/data/bids"


def test_get_dataset_raises_on_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", tmp_path / "datasets.json")
    from neuro_workflow.core.config import DatasetNotFoundError
    try:
        get_dataset("nonexistent")
        assert False, "Should have raised DatasetNotFoundError"
    except DatasetNotFoundError:
        pass


def test_save_dataset_overwrites_existing(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/old", "subjects_file": "/s.txt"})
    save_dataset("test_ds", {"bids_dir": "/new", "subjects_file": "/s.txt"})

    datasets = load_datasets()
    assert datasets["test_ds"]["bids_dir"] == "/new"
