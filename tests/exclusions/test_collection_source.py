"""PR5c: committed collection .bidsignore block + render concatenation.

Validates that:
  - committed data/exclusions/<ds>_collection.bidsignore files exist + are non-empty;
  - render_bidsignore_with_collection() = collection block THEN generated QC lines;
  - SUBSET PROOF: every non-comment line in each committed collection file
    appears VERBATIM in the corresponding real (READ-ONLY) .bidsignore;
  - RESIDUAL SHAPE: the real .bidsignore lines NOT in the collection file are
    all func/ BOLD scan-lines (exactly what render_bidsignore emits for QC).

These tests NEVER write to the real BIDS dirs or docs/EXCLUSIONS.md; the real
.bidsignore files are read READ-ONLY as ground truth.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Real READ-ONLY ground-truth .bidsignore files.
REAL_BIDSIGNORE = {
    "discovery": Path("/scratch/users/logben/discovery_bids/.bidsignore"),
    "validation": Path("/scratch/users/logben/validation_bids/.bidsignore"),
}

# Matches the func BOLD scan-line shape that render_bidsignore emits for QC.
_SCAN_RE = re.compile(r"^sub-[^/]+/ses-[^/]+/func/.*task-.*_bold\..*$")


def _non_comment_globs(text: str) -> list[str]:
    return [l for l in text.splitlines() if l and not l.startswith("#")]


# ---------------------------------------------------------------------------
# Collection files exist + non-empty
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dataset", ["discovery", "validation"])
def test_collection_file_exists_and_nonempty(dataset):
    from neuro_workflow.core.exclusions_render import collection_path
    path = collection_path(dataset)
    assert path.is_file(), f"missing committed collection file: {path}"
    globs = _non_comment_globs(path.read_text())
    assert len(globs) > 0, f"collection file has no glob lines: {path}"


@pytest.mark.parametrize("dataset", ["discovery", "validation"])
def test_collection_file_has_human_curated_header(dataset):
    from neuro_workflow.core.exclusions_render import collection_path
    text = collection_path(dataset).read_text()
    assert "Human-curated" in text


# ---------------------------------------------------------------------------
# SUBSET PROOF — collection ⊆ real .bidsignore (verbatim)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dataset", ["discovery", "validation"])
def test_collection_lines_subset_of_real_bidsignore(dataset):
    from neuro_workflow.core.exclusions_render import collection_path
    real = REAL_BIDSIGNORE[dataset]
    if not real.is_file():
        pytest.skip(f"real ground-truth .bidsignore not present: {real}")
    real_set = set(real.read_text().splitlines())
    coll_globs = _non_comment_globs(collection_path(dataset).read_text())
    missing = [l for l in coll_globs if l not in real_set]
    assert not missing, (
        f"{dataset}: collection lines not found VERBATIM in real .bidsignore: {missing}"
    )


@pytest.mark.parametrize("dataset", ["discovery", "validation"])
def test_residual_real_lines_are_scan_shaped(dataset):
    """Real .bidsignore globs NOT in the collection file must be QC scan-lines."""
    from neuro_workflow.core.exclusions_render import collection_path
    real = REAL_BIDSIGNORE[dataset]
    if not real.is_file():
        pytest.skip(f"real ground-truth .bidsignore not present: {real}")
    coll_set = set(_non_comment_globs(collection_path(dataset).read_text()))
    residual = [l for l in _non_comment_globs(real.read_text()) if l not in coll_set]
    bad = [l for l in residual if not _SCAN_RE.match(l)]
    assert not bad, f"{dataset}: residual real lines not scan-shaped: {bad}"


# ---------------------------------------------------------------------------
# render_bidsignore_with_collection — concatenation order
# ---------------------------------------------------------------------------

_QC_ENTRY = {
    "subject": "sub-s19",
    "session": "ses-09",
    "task": "flanker",
    "run": "run-*",
    "source": "behavioral-qc",
    "action": "exclude",
    "reason": "omission rate 30% > 25% threshold",
}


def test_render_with_collection_starts_with_collection_block():
    """Output begins with the committed collection block (its header first)."""
    from neuro_workflow.core.exclusions_render import (
        render_bidsignore_with_collection,
        collection_path,
    )
    out = render_bidsignore_with_collection("discovery", [_QC_ENTRY])
    collection_block = collection_path("discovery").read_text()
    assert out.startswith(collection_block)
    # Collection header text must appear before the generated stamp.
    assert "Human-curated" in out


def test_render_with_collection_appends_generated_qc_after_collection():
    """Generated QC stamp + scan-line follow the collection block."""
    from neuro_workflow.core.exclusions_render import (
        render_bidsignore_with_collection,
        collection_path,
    )
    out = render_bidsignore_with_collection("discovery", [_QC_ENTRY])
    collection_block = collection_path("discovery").read_text()
    generated_portion = out[len(collection_block):]
    assert "DO NOT EDIT" in generated_portion
    assert "render-bidsignore" in generated_portion
    # The QC scan-line is in the generated portion, not the collection block.
    assert "sub-s19/ses-09/func/" in generated_portion
    assert "sub-s19/ses-09/func/" not in collection_block


def test_render_with_collection_order_human_header_before_do_not_edit():
    from neuro_workflow.core.exclusions_render import render_bidsignore_with_collection
    out = render_bidsignore_with_collection("validation", [])
    assert out.index("Human-curated") < out.index("DO NOT EDIT")


def test_render_with_collection_missing_file_raises(tmp_path, monkeypatch):
    """A missing collection file must raise — never silently drop collection."""
    import neuro_workflow.core.exclusions_render as r
    monkeypatch.setattr(r, "_COLLECTION_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        r.render_bidsignore_with_collection("nonexistent_ds", [])


def test_render_with_collection_includes_all_collection_globs_verbatim():
    """Every collection glob is present verbatim in the concatenated output."""
    from neuro_workflow.core.exclusions_render import (
        render_bidsignore_with_collection,
        collection_path,
    )
    for ds in ("discovery", "validation"):
        out = render_bidsignore_with_collection(ds, [_QC_ENTRY])
        for glob in _non_comment_globs(collection_path(ds).read_text()):
            assert glob in out, f"{ds}: collection glob dropped from render: {glob}"
