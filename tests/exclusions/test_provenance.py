"""Tests for exclusion-run audit trail (Project C, slice C0)."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest


def test_make_meta_shape():
    """make_meta returns a dict with all expected keys."""
    from neuro_workflow.exclusions.base import make_meta

    meta = make_meta("foo", Namespace(x=1, y="hello"), n_entries=5)

    assert set(meta.keys()) == {"generator", "ran_at", "code_sha", "args", "n_entries"}
    assert meta["generator"] == "foo"
    assert meta["n_entries"] == 5
    assert meta["args"] == {"x": 1, "y": "hello"}
    # ran_at is an ISO-8601 timestamp ending in Z (UTC)
    assert isinstance(meta["ran_at"], str)
    assert meta["ran_at"].endswith("Z")
    # code_sha is either a string or None
    assert meta["code_sha"] is None or isinstance(meta["code_sha"], str)


def test_make_meta_serializes_path_args():
    """args containing Path instances stringify to make the dict JSON-safe."""
    from neuro_workflow.exclusions.base import make_meta

    meta = make_meta("foo", Namespace(decisions_tsv=Path("/tmp/x.tsv")), n_entries=0)
    assert meta["args"] == {"decisions_tsv": "/tmp/x.tsv"}


def test_make_meta_accepts_dict_args():
    """args can be a plain dict in addition to Namespace."""
    from neuro_workflow.exclusions.base import make_meta

    meta = make_meta("foo", {"x": 1}, n_entries=0)
    assert meta["args"] == {"x": 1}


def test_make_meta_args_none():
    """args=None records null in the meta block."""
    from neuro_workflow.exclusions.base import make_meta

    meta = make_meta("foo", None, n_entries=0)
    assert meta["args"] is None


def test_save_source_entries_wraps_with_meta(tmp_path, monkeypatch):
    """save_source_entries writes {_meta, entries} on disk, not a bare list."""
    import json
    from argparse import Namespace
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

    entries = [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "source": "lev1_outlier", "action": "exclude",
         "reason": "noisy"},
    ]
    args = Namespace(combined_vif=10.0, strict_vif=15.0)

    core_excl.save_source_entries("discovery", "lev1_outlier", entries, args=args)

    on_disk = json.loads(
        (tmp_path / "exclusions" / "discovery" / "sources" / "lev1_outlier.json").read_text()
    )
    assert set(on_disk.keys()) == {"_meta", "entries"}
    assert on_disk["entries"] == entries
    assert on_disk["_meta"]["generator"] == "lev1_outlier"
    assert on_disk["_meta"]["n_entries"] == 1
    assert on_disk["_meta"]["args"] == {"combined_vif": 10.0, "strict_vif": 15.0}


def test_save_source_entries_args_none_records_null(tmp_path, monkeypatch):
    """save_source_entries with args=None still works; _meta.args is null."""
    import json
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

    entries = [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "source": "behavioral-qc", "action": "exclude",
         "reason": "x"},
    ]

    core_excl.save_source_entries("discovery", "behavioral-qc", entries)

    on_disk = json.loads(
        (tmp_path / "exclusions" / "discovery" / "sources" / "behavioral-qc.json").read_text()
    )
    assert on_disk["_meta"]["args"] is None
