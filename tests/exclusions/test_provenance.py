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
