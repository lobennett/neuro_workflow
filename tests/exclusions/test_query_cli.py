"""CLI-level tests for `neuro-run exclusions query` — written RED-first."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

import neuro_workflow.cli as cli_mod
from neuro_workflow.core import exclusions as core_excl

# ---------------------------------------------------------------------------
# Shared fixture: isolated compiled exclusions in tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture()
def compiled_dataset(tmp_path, monkeypatch):
    """
    Write a minimal compiled_exclusions.json into an isolated EXCLUSIONS_DIR
    and return the dataset name.
    """
    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    dataset = "discovery"
    entries = [
        {
            "subject": "sub-s10",
            "session": "ses-05",
            "task": "task-goNogo",
            "run": "run-1",
            "source": "behavioral-qc",
            "action": "exclude",
            "reason": "go_rt (1043ms) > 1000ms",
            "metrics": {"go_rt_ms": 1043},
        },
        {
            "subject": "sub-s10",
            "session": "ses-07",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        },
        {
            "subject": "sub-s19",
            "session": "ses-02",
            "task": "task-goNogo",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        },
    ]
    # Write compiled JSON directly (bypass compile to keep test atomic).
    compiled_path = tmp_path / "exclusions" / dataset / "compiled_exclusions.json"
    compiled_path.parent.mkdir(parents=True)
    compiled_path.write_text(json.dumps(entries))
    return dataset


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cmd_exclusions_query_by_subject(compiled_dataset, capsys):
    """Prints matching entries for a subject; skips non-matching subjects."""
    args = Namespace(dataset=compiled_dataset, subject="sub-s10", session=None, task=None)
    cli_mod.cmd_exclusions_query(args, [])
    out = capsys.readouterr().out
    assert "sub-s10" in out
    assert "sub-s19" not in out
    # Both sessions appear
    assert "ses-05" in out
    assert "ses-07" in out


def test_cmd_exclusions_query_prefix_stripped(compiled_dataset, capsys):
    """subject='s10' (no sub- prefix) also works."""
    args = Namespace(dataset=compiled_dataset, subject="s10", session=None, task=None)
    cli_mod.cmd_exclusions_query(args, [])
    out = capsys.readouterr().out
    assert "ses-05" in out
    assert "ses-07" in out


def test_cmd_exclusions_query_with_task_filter(compiled_dataset, capsys):
    """--task filters to matching entries only."""
    args = Namespace(dataset=compiled_dataset, subject="sub-s10", session=None, task="task-goNogo")
    cli_mod.cmd_exclusions_query(args, [])
    out = capsys.readouterr().out
    assert "task-goNogo" in out
    assert "task-rest" not in out


def test_cmd_exclusions_query_no_matches_prints_message(compiled_dataset, capsys):
    """No matches → clear message containing subject and dataset name."""
    args = Namespace(dataset=compiled_dataset, subject="sub-s99", session=None, task=None)
    cli_mod.cmd_exclusions_query(args, [])
    out = capsys.readouterr().out
    # Should not crash; should print a "no exclusions" message
    assert "sub-s99" in out or "s99" in out
    assert compiled_dataset in out


def test_cmd_exclusions_query_missing_compiled_prints_hint(tmp_path, monkeypatch, capsys):
    """When compiled file is absent, prints reminder to run compile first."""
    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    args = Namespace(dataset="discovery", subject="sub-s10", session=None, task=None)
    cli_mod.cmd_exclusions_query(args, [])
    out = capsys.readouterr().out
    assert "compile" in out.lower()


def test_cmd_exclusions_query_action_and_source_in_output(compiled_dataset, capsys):
    """Each output line contains the action and source."""
    args = Namespace(dataset=compiled_dataset, subject="sub-s10", session=None, task=None)
    cli_mod.cmd_exclusions_query(args, [])
    out = capsys.readouterr().out
    assert "exclude" in out
    assert "behavioral-qc" in out or "motion" in out


def test_cmd_exclusions_query_is_exported_on_cli_namespace():
    """cmd_exclusions_query is re-exported on neuro_workflow.cli (dispatch + monkeypatch)."""
    assert hasattr(cli_mod, "cmd_exclusions_query")
    assert callable(cli_mod.cmd_exclusions_query)


def test_exclusions_query_subparser_registered(tmp_path):
    """'exclusions query --help' exit code 0 (subparser exists)."""
    import subprocess

    result = subprocess.run(
        ["uv", "run", "neuro-run", "exclusions", "query", "--help"],
        capture_output=True,
        text=True,
        cwd="/scratch/users/logben/neuro_workflow_refactor",
        env={**__import__("os").environ, "UV_CACHE_DIR": "/scratch/users/logben/.uv-cache"},
    )
    assert result.returncode == 0, result.stderr
    assert "--subject" in result.stdout
