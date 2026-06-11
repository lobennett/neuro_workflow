"""Tests for the reusable provenance primitive (core/provenance.py).

Written red-first (PR4a). Covers git_sha, git_is_dirty, uv_lock_hash,
tool_versions, file_manifest, write_run_manifest, write_dataset_description,
and require_clean_tree. Tests must not depend on the real working tree being
clean (we monkeypatch git_is_dirty / repo-root paths where needed).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from neuro_workflow.core import provenance as prov


# --------------------------------------------------------------------------- #
# git_sha / git_is_dirty
# --------------------------------------------------------------------------- #
def test_git_sha_returns_str():
    """git_sha returns a string (real short SHA, possibly +dirty, or 'unknown')."""
    sha = prov.git_sha()
    assert isinstance(sha, str)
    assert sha  # non-empty


def test_git_sha_unknown_when_not_a_repo(tmp_path, monkeypatch):
    """When the repo root isn't a git repo, git_sha returns 'unknown'."""
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    assert prov.git_sha() == "unknown"


def test_git_is_dirty_returns_bool():
    assert isinstance(prov.git_is_dirty(), bool)


def test_git_is_dirty_false_when_not_a_repo(tmp_path, monkeypatch):
    """A non-repo can't be 'dirty' — returns False rather than raising."""
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    assert prov.git_is_dirty() is False


# --------------------------------------------------------------------------- #
# _git_sha back-compat re-export (behavior-preservation)
# --------------------------------------------------------------------------- #
def test_exclusions_base_reexports_git_sha():
    """exclusions.base._git_sha must remain importable and identical to the
    canonical provenance.git_sha (DRY move must be behavior-preserving)."""
    from neuro_workflow.exclusions import base as excl_base

    assert excl_base._git_sha is prov.git_sha


# --------------------------------------------------------------------------- #
# uv_lock_hash
# --------------------------------------------------------------------------- #
def test_uv_lock_hash_deterministic(tmp_path, monkeypatch):
    """uv_lock_hash returns a stable short sha256 of uv.lock at the repo root."""
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"some lock contents\n")
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)

    expected = hashlib.sha256(b"some lock contents\n").hexdigest()[:12]
    h1 = prov.uv_lock_hash()
    h2 = prov.uv_lock_hash()
    assert h1 == h2 == expected
    assert isinstance(h1, str)


def test_uv_lock_hash_unknown_when_absent(tmp_path, monkeypatch):
    """No uv.lock at the repo root -> 'unknown'."""
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    assert prov.uv_lock_hash() == "unknown"


def test_uv_lock_hash_real_repo_is_str():
    """The real repo has a uv.lock, so this should be a 12-char hex string."""
    h = prov.uv_lock_hash()
    assert isinstance(h, str)
    assert h != "unknown"
    assert len(h) == 12


# --------------------------------------------------------------------------- #
# tool_versions
# --------------------------------------------------------------------------- #
def test_tool_versions_known_and_missing():
    versions = prov.tool_versions(["numpy", "definitely-not-a-real-package-xyz"])
    assert set(versions.keys()) == {"numpy", "definitely-not-a-real-package-xyz"}
    assert isinstance(versions["numpy"], str)
    assert versions["numpy"] != "not installed"
    assert versions["definitely-not-a-real-package-xyz"] == "not installed"


def test_tool_versions_empty_list():
    assert prov.tool_versions([]) == {}


# --------------------------------------------------------------------------- #
# file_manifest
# --------------------------------------------------------------------------- #
def test_file_manifest_sha256_and_size(tmp_path):
    content = b"hello provenance\n"
    f = tmp_path / "input.txt"
    f.write_bytes(content)

    manifest = prov.file_manifest([f])
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["path"] == str(f)
    assert entry["size_bytes"] == len(content)
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()


def test_file_manifest_empty_list():
    assert prov.file_manifest([]) == []


def test_file_manifest_raises_on_missing(tmp_path):
    """file_manifest fails loud on a missing input file."""
    missing = tmp_path / "nope.nii.gz"
    with pytest.raises(FileNotFoundError):
        prov.file_manifest([missing])


# --------------------------------------------------------------------------- #
# write_run_manifest
# --------------------------------------------------------------------------- #
def test_write_run_manifest_all_keys_and_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)  # no uv.lock here -> 'unknown'
    monkeypatch.setattr(prov, "git_is_dirty", lambda: False)

    inp = tmp_path / "in.txt"
    inp.write_bytes(b"abc")
    excl = tmp_path / "compiled.json"
    excl.write_bytes(b'[{"x":1}]')

    out_dir = tmp_path / "out"
    path = prov.write_run_manifest(
        out_dir,
        stage="lev1",
        args={"subject": "sub-s10", "bids_dir": Path("/tmp/bids")},
        inputs=[inp],
        exclusions_source=excl,
        tools=["numpy"],
        allow_dirty=True,
    )

    assert path == out_dir / "run-manifest.json"
    assert path.exists()

    m = json.loads(path.read_text())
    expected_keys = {
        "stage", "code_sha", "code_dirty", "uv_lock_hash", "config_version",
        "tool_versions", "exclusions_source", "args", "created_at", "host",
        "slurm_job_id", "inputs",
    }
    assert expected_keys.issubset(set(m.keys()))

    assert m["stage"] == "lev1"
    assert isinstance(m["code_sha"], str)
    assert m["code_dirty"] is False
    assert m["uv_lock_hash"] == "unknown"
    assert isinstance(m["config_version"], str)
    assert "numpy" in m["tool_versions"]
    # args JSON-safe: Path stringified
    assert m["args"]["subject"] == "sub-s10"
    assert m["args"]["bids_dir"] == "/tmp/bids"
    # created_at is UTC ISO ending in Z, matching the lockfile format
    assert isinstance(m["created_at"], str)
    assert m["created_at"].endswith("Z")
    # exclusions_source carries path + sha256
    assert m["exclusions_source"]["path"] == str(excl)
    assert m["exclusions_source"]["sha256"] == hashlib.sha256(b'[{"x":1}]').hexdigest()
    # inputs is a file manifest
    assert len(m["inputs"]) == 1
    assert m["inputs"][0]["path"] == str(inp)
    assert m["inputs"][0]["sha256"] == hashlib.sha256(b"abc").hexdigest()


def test_write_run_manifest_minimal(tmp_path, monkeypatch):
    """No inputs / exclusions_source / tools -> sensible defaults, still valid."""
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(prov, "git_is_dirty", lambda: False)

    out_dir = tmp_path / "out"
    path = prov.write_run_manifest(out_dir, stage="lev2", args={})
    m = json.loads(path.read_text())

    assert m["stage"] == "lev2"
    assert m["inputs"] == []
    assert m["exclusions_source"] is None
    # default tool set is non-empty
    assert isinstance(m["tool_versions"], dict)
    assert len(m["tool_versions"]) > 0


def test_write_run_manifest_records_slurm_job_id(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(prov, "git_is_dirty", lambda: False)
    monkeypatch.setenv("SLURM_JOB_ID", "23477309")

    path = prov.write_run_manifest(tmp_path / "out", stage="lev1", args={})
    m = json.loads(path.read_text())
    assert m["slurm_job_id"] == "23477309"


def test_write_run_manifest_slurm_job_id_null_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(prov, "git_is_dirty", lambda: False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)

    path = prov.write_run_manifest(tmp_path / "out", stage="lev1", args={})
    m = json.loads(path.read_text())
    assert m["slurm_job_id"] is None


def test_write_run_manifest_raises_when_dirty_and_not_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(prov, "git_is_dirty", lambda: True)

    with pytest.raises(RuntimeError):
        prov.write_run_manifest(tmp_path / "out", stage="lev1", args={}, allow_dirty=False)


# --------------------------------------------------------------------------- #
# write_dataset_description
# --------------------------------------------------------------------------- #
def test_write_dataset_description_valid_bids(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "git_is_dirty", lambda: False)

    out_dir = tmp_path / "deriv"
    path = prov.write_dataset_description(
        out_dir,
        name="neuro-workflow lev1",
        pipeline_version="0.2.0",
        source_datasets=[{"URL": "/tmp/bids"}],
    )
    assert path == out_dir / "dataset_description.json"
    d = json.loads(path.read_text())

    # Minimal valid BIDS derivative
    assert "BIDSVersion" in d
    assert d["DatasetType"] == "derivative"
    assert d["Name"] == "neuro-workflow lev1"
    assert isinstance(d["GeneratedBy"], list) and d["GeneratedBy"]
    gb = d["GeneratedBy"][0]
    assert "Name" in gb
    assert gb["Version"] == "0.2.0"
    # GeneratedBy carries the code SHA somewhere
    flat = json.dumps(gb)
    assert prov.git_sha() in flat
    assert d["SourceDatasets"] == [{"URL": "/tmp/bids"}]


def test_write_dataset_description_defaults(tmp_path):
    out_dir = tmp_path / "deriv"
    path = prov.write_dataset_description(out_dir, name="x")
    d = json.loads(path.read_text())
    assert d["DatasetType"] == "derivative"
    assert d["SourceDatasets"] == []
    assert isinstance(d["GeneratedBy"], list)


# --------------------------------------------------------------------------- #
# require_clean_tree
# --------------------------------------------------------------------------- #
def test_require_clean_tree_raises_when_dirty(monkeypatch):
    monkeypatch.setattr(prov, "git_is_dirty", lambda: True)
    with pytest.raises(RuntimeError):
        prov.require_clean_tree(allow_dirty=False)


def test_require_clean_tree_passes_when_allowed(monkeypatch):
    monkeypatch.setattr(prov, "git_is_dirty", lambda: True)
    # allow_dirty=True -> no raise
    prov.require_clean_tree(allow_dirty=True)


def test_require_clean_tree_passes_when_clean(monkeypatch):
    monkeypatch.setattr(prov, "git_is_dirty", lambda: False)
    prov.require_clean_tree(allow_dirty=False)
