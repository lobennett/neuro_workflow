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


def test_make_meta_strips_callable_from_args():
    """argparse Namespaces carry a `func` callback (set via subparser
    set_defaults). The audit-trail args dict must drop it so json.dumps
    succeeds on the saved sources file."""
    import json
    from neuro_workflow.exclusions.base import make_meta

    def _stub_callback(args, remaining):
        pass

    meta = make_meta(
        "foo",
        Namespace(dataset="discovery", source="motion", func=_stub_callback),
        n_entries=0,
    )
    # callable stripped out
    assert "func" not in meta["args"]
    # other args preserved
    assert meta["args"]["dataset"] == "discovery"
    assert meta["args"]["source"] == "motion"
    # full meta JSON-serializes without crashing
    json.dumps(meta)


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


def test_load_source_entries_handles_wrapped_format(tmp_path, monkeypatch):
    """load_source_entries returns the entries list when the file is wrapped."""
    import json
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

    sources_dir = tmp_path / "exclusions" / "discovery" / "sources"
    sources_dir.mkdir(parents=True)
    payload = {
        "_meta": {"generator": "x", "ran_at": "2026-05-07T00:00:00Z",
                  "code_sha": "abc", "args": {}, "n_entries": 1},
        "entries": [
            {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
             "run": "run-1", "source": "x", "action": "exclude", "reason": "y"},
        ],
    }
    (sources_dir / "x.json").write_text(json.dumps(payload))

    out = core_excl.load_source_entries("discovery", "x")
    assert len(out) == 1
    assert out[0]["subject"] == "sub-s03"


def test_load_source_entries_handles_bare_list(tmp_path, monkeypatch):
    """Legacy bare-list source files still load (back-compat)."""
    import json
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

    sources_dir = tmp_path / "exclusions" / "discovery" / "sources"
    sources_dir.mkdir(parents=True)
    bare = [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
         "run": "run-1", "source": "x", "action": "exclude", "reason": "y"},
    ]
    (sources_dir / "x.json").write_text(json.dumps(bare))

    out = core_excl.load_source_entries("discovery", "x")
    assert len(out) == 1
    assert out[0]["subject"] == "sub-s03"


def test_compile_handles_mixed_wrapped_and_bare_sources(tmp_path, monkeypatch):
    """compile_exclusions tolerates a mix of wrapped + legacy bare files."""
    import json
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    sources_dir = tmp_path / "exclusions" / "discovery" / "sources"
    sources_dir.mkdir(parents=True)

    wrapped = {
        "_meta": {"generator": "lev1_outlier", "ran_at": "2026-05-07T00:00:00Z",
                  "code_sha": "abc", "args": {}, "n_entries": 1},
        "entries": [
            {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
             "run": "run-1", "source": "lev1_outlier", "action": "exclude", "reason": "y"},
        ],
    }
    (sources_dir / "lev1_outlier.json").write_text(json.dumps(wrapped))

    bare = [
        {"subject": "sub-s10", "session": "ses-02", "task": "task-x",
         "run": "run-1", "source": "motion", "action": "exclude", "reason": "z"},
    ]
    (sources_dir / "motion.json").write_text(json.dumps(bare))

    compiled = core_excl.compile_exclusions("discovery")
    subjects = {e["subject"] for e in compiled}
    assert subjects == {"sub-s03", "sub-s10"}


def test_compile_writes_lockfile(tmp_path, monkeypatch):
    """compile_exclusions writes data/exclusions/<ds>_lock.json with the right schema."""
    import json
    from argparse import Namespace
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "home" / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    args = Namespace(combined_vif=10.0)
    core_excl.save_source_entries("discovery", "lev1_outlier", [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
         "run": "run-1", "source": "lev1_outlier", "action": "exclude", "reason": "y"},
    ], args=args)
    core_excl.save_source_entries("discovery", "motion", [], args=Namespace(fd_threshold=0.2))

    core_excl.compile_exclusions("discovery")

    lock_path = tmp_path / "data" / "exclusions" / "discovery_lock.json"
    assert lock_path.exists()
    lock = json.loads(lock_path.read_text())
    assert lock["dataset"] == "discovery"
    assert lock["n_total_entries"] == 1
    assert lock["n_overrides"] == 0
    assert isinstance(lock["compiled_at"], str)
    assert lock["compiled_at"].endswith("Z")
    assert "compiled_at_code_sha" in lock
    source_names = {s["generator"] for s in lock["sources"]}
    assert source_names == {"lev1_outlier", "motion"}
    lev1_meta = next(s for s in lock["sources"] if s["generator"] == "lev1_outlier")
    assert lev1_meta["n_entries"] == 1
    assert lev1_meta["args"] == {"combined_vif": 10.0}


def test_compile_no_sources_writes_empty_lockfile(tmp_path, monkeypatch):
    """No sources/*.json files -> lockfile with sources: [], n_total_entries: 0."""
    import json
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "home" / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    core_excl.compile_exclusions("discovery")

    lock_path = tmp_path / "data" / "exclusions" / "discovery_lock.json"
    assert lock_path.exists()
    lock = json.loads(lock_path.read_text())
    assert lock["sources"] == []
    assert lock["n_total_entries"] == 0


def test_compile_with_bare_list_sources_records_null_meta(tmp_path, monkeypatch):
    """Legacy bare-list source files appear in the lockfile with null fields."""
    import json
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "home" / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    sources_dir = tmp_path / "home" / "exclusions" / "discovery" / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "old_source.json").write_text(json.dumps([
        {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
         "run": "run-1", "source": "old_source", "action": "exclude", "reason": "y"},
    ]))

    core_excl.compile_exclusions("discovery")

    lock = json.loads((tmp_path / "data" / "exclusions" / "discovery_lock.json").read_text())
    assert len(lock["sources"]) == 1
    s = lock["sources"][0]
    assert s["generator"] == "old_source"
    assert s["ran_at"] is None
    assert s["code_sha"] is None
    assert s["args"] is None
    assert s["n_entries"] == 1


def test_cmd_exclusions_generate_passes_args_through(tmp_path, monkeypatch):
    """cmd_exclusions_generate passes the argparse Namespace to save_source_entries
    so the saved _meta records the CLI args."""
    import json
    from argparse import Namespace
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    # Stub get_dataset to avoid loading real datasets.json.
    import neuro_workflow.cli as cli_mod
    monkeypatch.setattr(cli_mod, "get_dataset", lambda name: {"bids_dir": "/tmp"})

    # Build a fake generator that returns a known entry list.
    captured: dict = {}

    class StubGenerator:
        name = "stub_gen"
        description = "stub"

        def add_cli_args(self, parser): pass

        def generate(self, dataset_name, dataset_config, args):
            captured["args_seen"] = args
            return [
                {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
                 "run": "run-1", "source": "stub_gen", "action": "exclude", "reason": "y"},
            ]

    from neuro_workflow.exclusions import base as base_mod
    base_mod.register_generator(StubGenerator())

    args = Namespace(
        dataset="discovery",
        source="stub_gen",
        threshold_a=42,
    )
    cli_mod.cmd_exclusions_generate(args, [])

    on_disk = json.loads(
        (tmp_path / "exclusions" / "discovery" / "sources" / "stub_gen.json").read_text()
    )
    assert on_disk["_meta"]["args"]["threshold_a"] == 42


def test_cmd_exclusions_show_prints_provenance_when_lockfile_exists(
    tmp_path, monkeypatch, capsys,
):
    """cmd_exclusions_show prints lockfile-based provenance when available."""
    import json
    from argparse import Namespace
    from neuro_workflow.core import exclusions as core_excl
    import neuro_workflow.cli as cli_mod

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "home" / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    # Compile something so a lockfile exists.
    core_excl.save_source_entries(
        "discovery", "lev1_outlier",
        [{"subject": "sub-s03", "session": "ses-02", "task": "task-x",
          "run": "run-1", "source": "lev1_outlier", "action": "exclude", "reason": "y"}],
        args=Namespace(combined_vif=10.0),
    )
    core_excl.compile_exclusions("discovery")

    args = Namespace(dataset="discovery")
    cli_mod.cmd_exclusions_show(args, [])
    captured = capsys.readouterr()

    # Lockfile-derived fields visible in stdout
    assert "lev1_outlier" in captured.out
    assert "compiled_at" in captured.out.lower() or "compiled at" in captured.out.lower()
    assert "1" in captured.out  # n_total_entries
