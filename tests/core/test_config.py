from pathlib import Path

import pytest

from neuro_workflow.core.config import (
    CONFIG_DIR,
    DEFAULTS,
    get_dataset,
    load_datasets,
    resolve_dataset_subjects,
    save_dataset,
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
        raise AssertionError("Should have raised DatasetNotFoundError")
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


# ---------------------------------------------------------------------------
# resolve_dataset_subjects: canonical subject resolution from
# config/pipeline_config.json `samples` (replaces the removed subjects_*.txt).
# ---------------------------------------------------------------------------


def test_resolve_discovery_subjects():
    """Discovery returns its 5 canonical subject IDs, in config order, bare."""
    subjects = resolve_dataset_subjects("discovery")
    assert subjects == ["s03", "s10", "s19", "s29", "s43"]


def test_resolve_validation_subjects_count():
    """Validation returns all 41 canonical subjects as bare IDs."""
    subjects = resolve_dataset_subjects("validation")
    assert len(subjects) == 41
    assert "s76" in subjects
    assert all(not s.startswith("sub-") for s in subjects)


def test_resolve_excluded_subjects_from_dict():
    """The `excluded` sample is a dict; resolution returns its keys (subject IDs)."""
    subjects = resolve_dataset_subjects("excluded")
    assert len(subjects) == 11
    assert "s214" in subjects
    assert "s297" in subjects


def test_resolve_unknown_dataset_fails_loud():
    """An unknown sample name raises a clear ValueError (NO silent None/empty)."""
    with pytest.raises(ValueError, match="bogus_dataset"):
        resolve_dataset_subjects("bogus_dataset")


def test_resolve_returns_a_list_not_none():
    """resolve_dataset_subjects never returns None — it either returns a list or raises."""
    result = resolve_dataset_subjects("discovery")
    assert isinstance(result, list)
