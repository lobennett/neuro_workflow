"""Tests for render_md + render_bidsignore renderers — written RED-first (PR5b).

All fixtures are synthetic; this file NEVER touches:
  - docs/EXCLUSIONS.md (the real committed hand-authored file)
  - /scratch/users/logben/{discovery,validation}_bids/.bidsignore (the real BIDS dirs)
"""

from __future__ import annotations

import subprocess
import os
from argparse import Namespace

import pytest

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_ENTRIES = [
    {
        "subject": "sub-s10",
        "session": "ses-05",
        "task": "goNogo",
        "run": "run-1",
        "source": "behavioral-qc",
        "action": "exclude",
        "reason": "go_rt (1043ms) > 1000ms",
        "metrics": {"go_rt_ms": 1043},
    },
    {
        "subject": "sub-s19",
        "session": "ses-02",
        "task": "goNogo",
        "run": "run-1",
        "source": "motion",
        "action": "exclude",
        "reason": "High FD",
    },
    {
        "subject": "sub-s10",
        "session": "ses-01",
        "task": "cuedTS",
        "run": "run-1",
        "source": "tr-count",
        "action": "trim",
        "reason": "15 of 489 TRs (3%)",
    },
]

# Entry with run == "run-*" (wildcard, like real .bidsignore full-run excludes)
ENTRIES_WITH_WILDCARD_RUN = [
    {
        "subject": "sub-s03",
        "session": "ses-01",
        "task": "nBack",
        "run": "run-*",
        "source": "behavioral-qc",
        "action": "exclude",
        "reason": "missing behavioral",
    },
]


# ---------------------------------------------------------------------------
# render_md — pure function tests
# ---------------------------------------------------------------------------


def test_render_md_returns_string():
    from neuro_workflow.core.exclusions_render import render_md

    out = render_md(SAMPLE_ENTRIES)
    assert isinstance(out, str)


def test_render_md_do_not_edit_stamp():
    """Output must contain the DO-NOT-EDIT stamp."""
    from neuro_workflow.core.exclusions_render import render_md

    out = render_md(SAMPLE_ENTRIES)
    assert "DO NOT EDIT" in out
    assert "render-md" in out


def test_render_md_deterministic():
    """Same input → identical output on repeated calls."""
    from neuro_workflow.core.exclusions_render import render_md

    out1 = render_md(SAMPLE_ENTRIES)
    out2 = render_md(SAMPLE_ENTRIES)
    assert out1 == out2


def test_render_md_groups_by_source():
    """Each source name appears as a section header."""
    from neuro_workflow.core.exclusions_render import render_md

    out = render_md(SAMPLE_ENTRIES)
    assert "behavioral-qc" in out
    assert "motion" in out
    assert "tr-count" in out


def test_render_md_contains_subjects():
    """Subject IDs appear in the output."""
    from neuro_workflow.core.exclusions_render import render_md

    out = render_md(SAMPLE_ENTRIES)
    assert "sub-s10" in out or "s10" in out
    assert "sub-s19" in out or "s19" in out


def test_render_md_contains_reasons():
    """Reason strings are included in the output."""
    from neuro_workflow.core.exclusions_render import render_md

    out = render_md(SAMPLE_ENTRIES)
    assert "1043ms" in out
    assert "High FD" in out


def test_render_md_empty_entries():
    """render_md with empty list returns a valid string with stamp."""
    from neuro_workflow.core.exclusions_render import render_md

    out = render_md([])
    assert isinstance(out, str)
    assert "DO NOT EDIT" in out


# ---------------------------------------------------------------------------
# render_bidsignore — pure function tests
# ---------------------------------------------------------------------------


def test_render_bidsignore_returns_string():
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore(SAMPLE_ENTRIES)
    assert isinstance(out, str)


def test_render_bidsignore_do_not_edit_stamp():
    """First line is a comment with the DO-NOT-EDIT stamp."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore(SAMPLE_ENTRIES)
    assert "DO NOT EDIT" in out
    assert "render-bidsignore" in out


def test_render_bidsignore_deterministic():
    """Same input → identical output (sorted order)."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out1 = render_bidsignore(SAMPLE_ENTRIES)
    out2 = render_bidsignore(SAMPLE_ENTRIES)
    assert out1 == out2


def test_render_bidsignore_glob_form_func():
    """Functional BOLD lines use the echo-wildcard glob.

    Expected pattern:
      sub-{subject}/ses-{session}/func/sub-{subject}_ses-{session}_task-{task}_run-{run}_echo-*_bold.*
    """
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore(SAMPLE_ENTRIES)
    # Check at least one func glob line is present and has the right structure.
    func_lines = [l for l in out.splitlines() if "/func/" in l and not l.startswith("#")]
    assert len(func_lines) > 0, "No func/ glob lines found"
    for line in func_lines:
        # Must have: sub-X/ses-Y/func/sub-X_ses-Y_task-T_run-R_echo-*_bold.*
        assert "_echo-*_bold.*" in line, f"Unexpected glob form: {line}"
        assert "sub-" in line
        assert "/func/" in line


def test_render_bidsignore_wildcard_run_preserved():
    """run='run-*' entries produce a run-* glob (full-session exclude)."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore(ENTRIES_WITH_WILDCARD_RUN)
    func_lines = [l for l in out.splitlines() if "/func/" in l and not l.startswith("#")]
    assert any("run-*" in l for l in func_lines), f"run-* not found in lines: {func_lines}"


def test_render_bidsignore_include_trim_and_exclude():
    """Both 'exclude' and 'trim' actions appear in the output."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore(SAMPLE_ENTRIES)
    # s10/ses-05 (exclude) and s10/ses-01 (trim) should both be present.
    assert "ses-05" in out
    assert "ses-01" in out


def test_render_bidsignore_force_include_skipped():
    """force-include entries must NOT appear in .bidsignore output."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    entries = [
        {
            "subject": "sub-s99",
            "session": "ses-01",
            "task": "rest",
            "run": "run-1",
            "source": "override",
            "action": "force-include",
            "reason": "Keep despite motion",
        }
    ]
    out = render_bidsignore(entries)
    assert "sub-s99" not in out


def test_render_bidsignore_sorted_lines():
    """Non-comment lines are in sorted order."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore(SAMPLE_ENTRIES)
    glob_lines = [l for l in out.splitlines() if l and not l.startswith("#")]
    assert glob_lines == sorted(glob_lines)


def test_render_bidsignore_empty_entries():
    """render_bidsignore with empty list returns a valid string with stamp."""
    from neuro_workflow.core.exclusions_render import render_bidsignore

    out = render_bidsignore([])
    assert isinstance(out, str)
    assert "DO NOT EDIT" in out


# ---------------------------------------------------------------------------
# CLI handler tests — cmd_exclusions_render_md
# ---------------------------------------------------------------------------

import json


@pytest.fixture()
def compiled_dataset(tmp_path, monkeypatch):
    """Isolated compiled_exclusions.json in tmp_path."""
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")
    monkeypatch.setattr(core_excl, "LOCKFILE_DIR", tmp_path / "data" / "exclusions")

    dataset = "discovery"
    compiled_path = tmp_path / "exclusions" / dataset / "compiled_exclusions.json"
    compiled_path.parent.mkdir(parents=True)
    compiled_path.write_text(json.dumps(SAMPLE_ENTRIES))
    return dataset, tmp_path


def test_cmd_exclusions_render_md_stdout(compiled_dataset, capsys):
    """Without --output, render-md prints to stdout."""
    import neuro_workflow.cli as cli_mod

    dataset, tmp_path = compiled_dataset
    args = Namespace(dataset=dataset, output=None)
    cli_mod.cmd_exclusions_render_md(args, [])
    out = capsys.readouterr().out
    assert "DO NOT EDIT" in out
    assert "behavioral-qc" in out


def test_cmd_exclusions_render_md_to_file(compiled_dataset, tmp_path):
    """With --output PATH, render-md writes to the given file."""
    import neuro_workflow.cli as cli_mod

    dataset, _ = compiled_dataset
    output_path = tmp_path / "out_EXCLUSIONS.md"
    args = Namespace(dataset=dataset, output=str(output_path))
    cli_mod.cmd_exclusions_render_md(args, [])
    assert output_path.exists()
    content = output_path.read_text()
    assert "DO NOT EDIT" in content


def test_cmd_exclusions_render_md_is_exported():
    """cmd_exclusions_render_md re-exported on neuro_workflow.cli."""
    import neuro_workflow.cli as cli_mod

    assert hasattr(cli_mod, "cmd_exclusions_render_md")
    assert callable(cli_mod.cmd_exclusions_render_md)


# ---------------------------------------------------------------------------
# CLI handler tests — cmd_exclusions_render_bidsignore
# ---------------------------------------------------------------------------


def test_cmd_exclusions_render_bidsignore_stdout(compiled_dataset, capsys):
    """Without --output, render-bidsignore prints to stdout."""
    import neuro_workflow.cli as cli_mod

    dataset, tmp_path = compiled_dataset
    args = Namespace(dataset=dataset, output=None)
    cli_mod.cmd_exclusions_render_bidsignore(args, [])
    out = capsys.readouterr().out
    assert "DO NOT EDIT" in out
    assert "/func/" in out or out.count("\n") >= 1  # either func lines or at least the header


def test_cmd_exclusions_render_bidsignore_to_file(compiled_dataset, tmp_path):
    """With --output PATH, render-bidsignore writes to the given file."""
    import neuro_workflow.cli as cli_mod

    dataset, _ = compiled_dataset
    output_path = tmp_path / "out_.bidsignore"
    args = Namespace(dataset=dataset, output=str(output_path))
    cli_mod.cmd_exclusions_render_bidsignore(args, [])
    assert output_path.exists()
    content = output_path.read_text()
    assert "DO NOT EDIT" in content


def test_cmd_exclusions_render_bidsignore_is_exported():
    """cmd_exclusions_render_bidsignore re-exported on neuro_workflow.cli."""
    import neuro_workflow.cli as cli_mod

    assert hasattr(cli_mod, "cmd_exclusions_render_bidsignore")
    assert callable(cli_mod.cmd_exclusions_render_bidsignore)


# ---------------------------------------------------------------------------
# Subparser help integration tests
# ---------------------------------------------------------------------------


def _run_help(*args):
    return subprocess.run(
        ["uv", "run", "neuro-run", *args],
        capture_output=True,
        text=True,
        cwd="/scratch/users/logben/neuro_workflow_refactor",
        env={**os.environ, "UV_CACHE_DIR": "/scratch/users/logben/.uv-cache"},
    )


def test_render_md_help():
    """'neuro-run exclusions render-md --help' exits 0."""
    result = _run_help("exclusions", "render-md", "--help")
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


def test_render_bidsignore_help():
    """'neuro-run exclusions render-bidsignore --help' exits 0."""
    result = _run_help("exclusions", "render-bidsignore", "--help")
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


def test_exclusions_help_lists_both_render_commands():
    """'neuro-run exclusions --help' lists both render-md and render-bidsignore."""
    result = _run_help("exclusions", "--help")
    assert result.returncode == 0, result.stderr
    assert "render-md" in result.stdout
    assert "render-bidsignore" in result.stdout


# ---------------------------------------------------------------------------
# Drift detection (fail-loud consistency) tests
# ---------------------------------------------------------------------------


def test_drift_detection_no_drift_passes(compiled_dataset):
    """When 'committed' artifact matches rendered output, check detects no drift."""
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.core.exclusions_render import render_md, check_md_drift

    dataset, tmp_path = compiled_dataset
    monkeypatched_entries = core_excl.load_compiled_exclusions(dataset)
    rendered = render_md(monkeypatched_entries)

    # Write the exact rendered output as the "committed" artifact.
    committed_path = tmp_path / "EXCLUSIONS_committed.md"
    committed_path.write_text(rendered)

    drifted, details = check_md_drift(committed_path.read_text(), rendered)
    assert drifted is False
    assert details == ""


def test_drift_detection_hand_edit_fails_loud(compiled_dataset):
    """When 'committed' artifact has been hand-edited, check_md_drift returns True with details."""
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.core.exclusions_render import render_md, check_md_drift

    dataset, tmp_path = compiled_dataset
    entries = core_excl.load_compiled_exclusions(dataset)
    rendered = render_md(entries)

    # Simulate hand-edit: append a stray line to the committed artifact.
    hand_edited = rendered + "\n<!-- hand-added note that breaks drift check -->\n"

    drifted, details = check_md_drift(hand_edited, rendered)
    assert drifted is True
    assert len(details) > 0


def test_drift_detection_bidsignore_no_drift(compiled_dataset):
    """check_bidsignore_drift: identical content → no drift."""
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.core.exclusions_render import render_bidsignore, check_bidsignore_drift

    dataset, tmp_path = compiled_dataset
    entries = core_excl.load_compiled_exclusions(dataset)
    rendered = render_bidsignore(entries)

    drifted, details = check_bidsignore_drift(rendered, rendered)
    assert drifted is False
    assert details == ""


def test_drift_detection_bidsignore_hand_edit_fails_loud(compiled_dataset):
    """check_bidsignore_drift: hand-edited content → drifted=True with details."""
    from neuro_workflow.core import exclusions as core_excl
    from neuro_workflow.core.exclusions_render import render_bidsignore, check_bidsignore_drift

    dataset, tmp_path = compiled_dataset
    entries = core_excl.load_compiled_exclusions(dataset)
    rendered = render_bidsignore(entries)

    # Simulate adding a stray hand-crafted glob that wasn't generated.
    hand_edited = rendered + "\nsub-s99/ses-01/func/*_bold.*\n"

    drifted, details = check_bidsignore_drift(hand_edited, rendered)
    assert drifted is True
    assert len(details) > 0
