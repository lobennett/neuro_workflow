# fMRIPrep 25.2.4 Rerun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably preprocess all 46 subjects (5 discovery + 41 validation) with fmriprep 25.2.4 producing 1mm MNI volumetric + CIFTI 91k + surface outputs, deployed via SLURM on the russpold partition.

**Architecture:** Single-phase fmriprep per subject, 7-day wall, 8 CPUs × 22-24 GB. A pre-flight script translates `.bidsignore` into a symlink BIDS view at `<bids_dir>/derivatives/fmriprep_25.2.4_input/` (since pybids does not honor `.bidsignore`). One `neuro-run` extension (`--bids-dir-override`) points fmriprep at the view while keeping derivatives output at the original BIDS dir.

**Tech Stack:** Python 3.13, pytest, fmriprep 25.2.4 (Apptainer), SLURM (russpold partition), uv for env management.

**Spec:** `docs/superpowers/specs/2026-04-28-fmriprep-rerun-design.md`

---

## File Structure

**Files to create:**
- `scripts/fmriprep_preflight.py` — Pre-flight CLI: parse `.bidsignore`, build symlink view, sanity-check
- `tests/scripts/test_fmriprep_preflight.py` — TDD tests for the pre-flight script
- `docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md` — Filled in after Phase 1

**Files to modify:**
- `src/neuro_workflow/pipelines/fmriprep.py` — Add `--bids-dir-override` flag (≈15 lines)
- `tests/pipelines/test_fmriprep.py` — Add tests for the override flag (≈80 lines)

**Files NOT modified:**
- `src/neuro_workflow/templates/fmriprep.sbatch` — Already binds `{bids_dir}` to `/data`. We swap which path that variable holds, no template change.

---

## Task 1: Pre-flight helper — parse `.bidsignore`

**Files:**
- Create: `scripts/fmriprep_preflight.py`
- Create: `tests/scripts/test_fmriprep_preflight.py`

- [ ] **Step 1.1: Write failing test for `parse_bidsignore`**

Create `tests/scripts/test_fmriprep_preflight.py`:

```python
import sys
from pathlib import Path

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from fmriprep_preflight import parse_bidsignore


def test_parse_bidsignore_strips_comments_and_blanks(tmp_path):
    bidsignore = tmp_path / ".bidsignore"
    bidsignore.write_text(
        "# comment line\n"
        "\n"
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*\n"
        "  \n"  # whitespace-only line
        "# another comment\n"
        "sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-*_bold.*\n"
    )
    patterns = parse_bidsignore(bidsignore)
    assert patterns == [
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*",
        "sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-*_bold.*",
    ]


def test_parse_bidsignore_missing_file_returns_empty(tmp_path):
    patterns = parse_bidsignore(tmp_path / "nonexistent")
    assert patterns == []
```

- [ ] **Step 1.2: Run test, verify failure**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/scripts/test_fmriprep_preflight.py::test_parse_bidsignore_strips_comments_and_blanks -v
```
Expected: ImportError on `fmriprep_preflight` (file doesn't exist yet).

- [ ] **Step 1.3: Create `scripts/fmriprep_preflight.py` with parse function**

```python
#!/usr/bin/env python3
"""Pre-flight: build symlink BIDS view that physically excludes .bidsignore'd files.

pybids does not honor .bidsignore, so fmriprep would otherwise process every file
in the BIDS tree. This script creates a parallel symlink directory under
<bids_dir>/derivatives/fmriprep_<version>_input/ where excluded files are simply
not linked, then sanity-checks that every subject still has a usable T1w.

Usage:
    uv run python scripts/fmriprep_preflight.py discovery
    uv run python scripts/fmriprep_preflight.py validation
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_bidsignore(path: Path) -> list[str]:
    """Return non-comment, non-blank lines from a .bidsignore file."""
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns
```

- [ ] **Step 1.4: Run tests, verify pass**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 2 passing.

- [ ] **Step 1.5: Commit**

```bash
git add scripts/fmriprep_preflight.py tests/scripts/test_fmriprep_preflight.py
git commit -m "feat: add fmriprep_preflight skeleton with .bidsignore parser"
```

---

## Task 2: Pre-flight helper — pattern matching

**Files:**
- Modify: `scripts/fmriprep_preflight.py`
- Modify: `tests/scripts/test_fmriprep_preflight.py`

`.bidsignore` patterns are gitignore-style: `*` does not match `/`. Implement segment-by-segment fnmatch.

- [ ] **Step 2.1: Write failing tests for `path_matches_any`**

Append to `tests/scripts/test_fmriprep_preflight.py`:

```python
from scripts.fmriprep_preflight import path_matches_any


def test_path_matches_simple_pattern():
    patterns = ["sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*"]
    assert path_matches_any("sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz", patterns)
    assert path_matches_any("sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.json", patterns)


def test_path_matches_subject_specific():
    patterns = ["sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-*_bold.*"]
    assert path_matches_any("sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-1_bold.nii.gz", patterns)
    assert path_matches_any("sub-s43/ses-08/func/sub-s43_ses-08_task-directedForgetting_run-1_echo-2_bold.nii.gz", patterns)
    # Different subject — no match
    assert not path_matches_any("sub-s10/ses-08/func/sub-s10_ses-08_task-directedForgetting_run-1_echo-1_bold.nii.gz", patterns)


def test_path_matches_star_does_not_cross_slash():
    """Critical gitignore semantics — `*` does not span path separators."""
    patterns = ["sub-*/anat/*T1w.nii.gz"]
    # Same depth — should match
    assert path_matches_any("sub-s03/anat/sub-s03_T1w.nii.gz", patterns)
    # Different depth — should NOT match
    assert not path_matches_any("sub-s03/ses-01/anat/sub-s03_T1w.nii.gz", patterns)


def test_path_matches_no_patterns():
    assert not path_matches_any("sub-s03/ses-01/anat/sub-s03_T1w.nii.gz", [])


def test_path_matches_run_specific_excludes_only_that_run():
    """s10 ses-01 task-goNogo run-1 is .bidsignore'd, but run-2 must remain."""
    patterns = ["sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-1_echo-*_bold.*"]
    assert path_matches_any("sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-1_echo-1_bold.nii.gz", patterns)
    assert not path_matches_any("sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-2_echo-1_bold.nii.gz", patterns)
```

- [ ] **Step 2.2: Run tests, verify failure**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 5 new tests fail with ImportError on `path_matches_any`.

- [ ] **Step 2.3: Add `path_matches_any` to `scripts/fmriprep_preflight.py`**

Append to `scripts/fmriprep_preflight.py` after `parse_bidsignore`:

```python
import fnmatch


def path_matches_any(rel_path: str, patterns: list[str]) -> bool:
    """Return True if `rel_path` matches any gitignore-style pattern.

    Implements gitignore semantics where `*` does not span `/` separators by
    splitting both path and pattern on `/` and matching segment-by-segment.
    """
    path_parts = rel_path.split("/")
    for pattern in patterns:
        pattern_parts = pattern.split("/")
        if len(path_parts) != len(pattern_parts):
            continue
        if all(fnmatch.fnmatchcase(p, pat) for p, pat in zip(path_parts, pattern_parts)):
            return True
    return False
```

- [ ] **Step 2.4: Run tests, verify pass**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 7 passing.

- [ ] **Step 2.5: Commit**

```bash
git add scripts/fmriprep_preflight.py tests/scripts/test_fmriprep_preflight.py
git commit -m "feat: add gitignore-style pattern matcher to fmriprep_preflight"
```

---

## Task 3: Pre-flight — view builder

**Files:**
- Modify: `scripts/fmriprep_preflight.py`
- Modify: `tests/scripts/test_fmriprep_preflight.py`

- [ ] **Step 3.1: Write failing tests for `build_view`**

Append to `tests/scripts/test_fmriprep_preflight.py`:

```python
from scripts.fmriprep_preflight import build_view


def _make_fake_bids(tmp_path: Path) -> Path:
    """Create a tiny BIDS-like tree for testing."""
    bids = tmp_path / "fake_bids"
    (bids / "sub-s03" / "ses-01" / "anat").mkdir(parents=True)
    (bids / "sub-s03" / "ses-01" / "func").mkdir(parents=True)
    (bids / "sub-s03" / "ses-05" / "anat").mkdir(parents=True)
    (bids / "sub-s03" / "ses-01" / "anat" / "sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").touch()
    (bids / "sub-s03" / "ses-01" / "anat" / "sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.json").touch()
    (bids / "sub-s03" / "ses-05" / "anat" / "sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz").touch()
    (bids / "sub-s03" / "ses-05" / "anat" / "sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.json").touch()
    (bids / "sub-s03" / "ses-01" / "func" / "sub-s03_ses-01_task-flanker_run-1_echo-1_bold.nii.gz").touch()
    (bids / "sub-s03" / "ses-01" / "func" / "sub-s03_ses-01_task-nBack_run-1_echo-1_bold.nii.gz").touch()
    (bids / "dataset_description.json").write_text('{"Name": "fake"}')
    (bids / "README").write_text("fake")
    (bids / ".bidsignore").write_text(
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*\n"
        "sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-1_echo-*_bold.*\n"
    )
    # Should be ignored entirely (not walked):
    (bids / "derivatives" / "junk").mkdir(parents=True)
    (bids / "derivatives" / "junk" / "should_not_appear.nii.gz").touch()
    return bids


def test_build_view_excludes_bidsignored_files(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"

    summary = build_view(bids, view)

    # MPRAGEPromo files NOT in view
    assert not (view / "sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").exists()
    assert not (view / "sub-s03/ses-01/anat/sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.json").exists()
    # SagMPRAGE files ARE in view
    assert (view / "sub-s03/ses-05/anat/sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz").is_symlink()
    # nBack BOLD excluded
    assert not (view / "sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-1_echo-1_bold.nii.gz").exists()
    # flanker BOLD retained
    assert (view / "sub-s03/ses-01/func/sub-s03_ses-01_task-flanker_run-1_echo-1_bold.nii.gz").is_symlink()


def test_build_view_includes_top_level_metadata(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    assert (view / "dataset_description.json").is_symlink()
    assert (view / "README").is_symlink()
    assert (view / ".bidsignore").is_symlink()


def test_build_view_skips_derivatives_subtree(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    # The derivatives/junk/ subtree must not appear in view
    assert not (view / "derivatives").exists()


def test_build_view_idempotent(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    s1 = build_view(bids, view)
    s2 = build_view(bids, view)
    assert s1["files_linked"] == s2["files_linked"]
    assert s1["files_excluded"] == s2["files_excluded"]


def test_build_view_summary_counts(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    summary = build_view(bids, view)
    # Expected: 3 top-level files (dataset_description, README, .bidsignore)
    # + 2 SagMPRAGE files (nii.gz + json) + 1 flanker BOLD = 6 linked
    # Excluded: 2 MPRAGEPromo + 1 nBack = 3
    assert summary["files_linked"] == 6
    assert summary["files_excluded"] == 3
```

- [ ] **Step 3.2: Run tests, verify failure**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 5 new tests fail with ImportError on `build_view`.

- [ ] **Step 3.3: Implement `build_view`**

Append to `scripts/fmriprep_preflight.py`:

```python
TOP_LEVEL_METADATA = {
    "dataset_description.json",
    "README",
    "README.md",
    "README.txt",
    "participants.tsv",
    "participants.json",
    ".bidsignore",
    "CHANGES",
    "CITATION.cff",
}

SKIP_TOP_LEVEL_DIRS = {"derivatives", "sourcedata", "code"}


def build_view(bids_dir: Path, view_dir: Path) -> dict:
    """Build a symlink view of `bids_dir` at `view_dir` excluding .bidsignore patterns.

    Returns a summary dict with files_linked, files_excluded.
    Idempotent: existing identical symlinks are left in place; missing ones are created;
    extras from a previous run are removed.
    """
    bids_dir = bids_dir.resolve()
    view_dir = Path(view_dir)
    patterns = parse_bidsignore(bids_dir / ".bidsignore")

    desired_links: dict[Path, Path] = {}  # view_path -> target

    # Top-level metadata files
    for child in bids_dir.iterdir():
        if child.is_file() and child.name in TOP_LEVEL_METADATA:
            desired_links[view_dir / child.name] = child

    # Subject directories
    for sub_dir in sorted(bids_dir.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        for fpath in sorted(sub_dir.rglob("*")):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(bids_dir).as_posix()
            if path_matches_any(rel, patterns):
                continue
            desired_links[view_dir / rel] = fpath

    # Apply: ensure view_dir exists, create symlinks, remove stale
    view_dir.mkdir(parents=True, exist_ok=True)
    _sync_symlinks(view_dir, desired_links)

    excluded_count = _count_excluded_files(bids_dir, patterns)
    return {
        "files_linked": len(desired_links),
        "files_excluded": excluded_count,
        "patterns": patterns,
    }


def _sync_symlinks(view_dir: Path, desired: dict[Path, Path]) -> None:
    """Create missing symlinks; replace mismatched ones; leave correct ones alone."""
    for view_path, target in desired.items():
        view_path.parent.mkdir(parents=True, exist_ok=True)
        if view_path.is_symlink():
            if Path(view_path.readlink()).resolve() == target.resolve():
                continue
            view_path.unlink()
        elif view_path.exists():
            view_path.unlink()
        view_path.symlink_to(target.resolve())

    # Sweep for stale symlinks under view_dir not in desired set
    desired_paths = set(desired.keys())
    for fpath in view_dir.rglob("*"):
        if fpath.is_symlink() and fpath not in desired_paths:
            fpath.unlink()


def _count_excluded_files(bids_dir: Path, patterns: list[str]) -> int:
    n = 0
    for sub_dir in bids_dir.glob("sub-*"):
        if not sub_dir.is_dir():
            continue
        for fpath in sub_dir.rglob("*"):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(bids_dir).as_posix()
            if path_matches_any(rel, patterns):
                n += 1
    return n
```

- [ ] **Step 3.4: Run tests, verify pass**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 12 passing total (2 + 5 + 5).

- [ ] **Step 3.5: Commit**

```bash
git add scripts/fmriprep_preflight.py tests/scripts/test_fmriprep_preflight.py
git commit -m "feat: add idempotent symlink view builder"
```

---

## Task 4: Pre-flight — view sanity checks

**Files:**
- Modify: `scripts/fmriprep_preflight.py`
- Modify: `tests/scripts/test_fmriprep_preflight.py`

The pre-flight must verify every subject has ≥1 T1w in the view and that intentional multi-anat subjects retain expected counts (per `docs/EXCLUSIONS.md`).

- [ ] **Step 4.1: Write failing tests for `verify_view`**

Append to `tests/scripts/test_fmriprep_preflight.py`:

```python
from scripts.fmriprep_preflight import verify_view


def test_verify_view_passes_when_every_subject_has_t1w(tmp_path):
    bids = _make_fake_bids(tmp_path)
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    # Default: no expected multi-anat for this fake dataset
    errors = verify_view(view, expected_multi_anat={})
    assert errors == []


def test_verify_view_fails_when_subject_has_no_t1w(tmp_path):
    bids = tmp_path / "fake_bids"
    (bids / "sub-s03" / "ses-01" / "anat").mkdir(parents=True)
    # Only an MPRAGEPromo, which is .bidsignore'd
    (bids / "sub-s03" / "ses-01" / "anat" / "sub-s03_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").touch()
    (bids / "dataset_description.json").write_text("{}")
    (bids / ".bidsignore").write_text("sub-*/ses-*/anat/*MPRAGEPromo*\n")
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)
    errors = verify_view(view, expected_multi_anat={})
    assert any("sub-s03" in e and "no T1w" in e for e in errors)


def test_verify_view_checks_expected_multi_anat(tmp_path):
    bids = tmp_path / "fake_bids"
    (bids / "sub-s1351" / "ses-01" / "anat").mkdir(parents=True)
    (bids / "sub-s1351" / "ses-08" / "anat").mkdir(parents=True)
    (bids / "sub-s1351" / "ses-01" / "anat" / "sub-s1351_ses-01_acq-SagMPRAGE_run-1_T1w.nii.gz").touch()
    (bids / "sub-s1351" / "ses-08" / "anat" / "sub-s1351_ses-08_acq-SagMPRAGE_run-1_T1w.nii.gz").touch()
    (bids / "dataset_description.json").write_text("{}")
    (bids / ".bidsignore").write_text("")
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    build_view(bids, view)

    # Expected 2 T1w — passes
    errors = verify_view(view, expected_multi_anat={"s1351": {"T1w": 2}})
    assert errors == []

    # Expected 3 T1w — fails (only 2 in view)
    errors = verify_view(view, expected_multi_anat={"s1351": {"T1w": 3}})
    assert any("s1351" in e for e in errors)
```

- [ ] **Step 4.2: Run tests, verify failure**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 3 new tests fail with ImportError on `verify_view`.

- [ ] **Step 4.3: Implement `verify_view`**

Append to `scripts/fmriprep_preflight.py`:

```python
def verify_view(view_dir: Path, expected_multi_anat: dict[str, dict[str, int]]) -> list[str]:
    """Return a list of error strings; empty list means view is valid.

    Checks:
    1. Every subject directory in the view has ≥ 1 T1w file
    2. For each subject in `expected_multi_anat`, the view contains exactly the
       expected number of T1w / T2w files. The dict shape is:
         {"s1351": {"T1w": 2}, "s1399": {"T2w": 2}}
    """
    errors: list[str] = []
    for sub_dir in sorted(view_dir.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        sub = sub_dir.name.removeprefix("sub-")
        t1w_files = list(sub_dir.glob("ses-*/anat/*T1w.nii.gz"))
        t2w_files = list(sub_dir.glob("ses-*/anat/*T2w.nii.gz"))
        if not t1w_files:
            errors.append(f"sub-{sub}: no T1w in view")
            continue
        if sub in expected_multi_anat:
            for suffix, expected_count in expected_multi_anat[sub].items():
                actual = len(t1w_files) if suffix == "T1w" else len(t2w_files)
                if actual != expected_count:
                    errors.append(
                        f"sub-{sub}: expected {expected_count} {suffix} per EXCLUSIONS.md, "
                        f"view has {actual}"
                    )
    return errors
```

- [ ] **Step 4.4: Run tests, verify pass**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 15 passing.

- [ ] **Step 4.5: Commit**

```bash
git add scripts/fmriprep_preflight.py tests/scripts/test_fmriprep_preflight.py
git commit -m "feat: add view sanity check (T1w presence + multi-anat counts)"
```

---

## Task 5: Pre-flight CLI

**Files:**
- Modify: `scripts/fmriprep_preflight.py`
- Modify: `tests/scripts/test_fmriprep_preflight.py`

Wire the helpers into a CLI that resolves the BIDS dir from `~/.neuro_workflow/datasets.json`, chooses the view location at `<bids_dir>/derivatives/fmriprep_<version>_input/`, and reports a summary table.

- [ ] **Step 5.1: Write failing test for the CLI entrypoint**

Append to `tests/scripts/test_fmriprep_preflight.py`:

```python
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_cli_smoke(tmp_path):
    """End-to-end: build a fake BIDS, run the CLI against it, check view exists."""
    bids = _make_fake_bids(tmp_path)

    # Fake datasets.json
    datasets_json = tmp_path / "datasets.json"
    datasets_json.write_text(json.dumps({
        "fake_ds": {"bids_dir": str(bids), "subjects_file": "ignored"}
    }))

    result = subprocess.run(
        [
            "uv", "run", "python",
            str(PROJECT_ROOT / "scripts" / "fmriprep_preflight.py"),
            "fake_ds",
            "--version", "25.2.4",
            "--datasets-json", str(datasets_json),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    view = bids / "derivatives" / "fmriprep_25.2.4_input"
    assert view.exists()
    assert (view / "sub-s03" / "ses-05" / "anat" / "sub-s03_ses-05_acq-SagMPRAGE_run-1_T1w.nii.gz").is_symlink()
```

- [ ] **Step 5.2: Run test, verify failure**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py::test_cli_smoke -v
```
Expected: FAIL — CLI not yet wired up.

- [ ] **Step 5.3: Add `main` and CLI plumbing**

Append to `scripts/fmriprep_preflight.py`:

```python
EXPECTED_MULTI_ANAT = {
    "discovery": {},  # no multi-anat subjects in discovery
    "validation": {
        "s1351": {"T1w": 2},  # ses-01 + ses-08 SagMPRAGE
        "s1399": {"T2w": 2},  # ses-01 + ses-02 CubePromo
    },
}


def _load_datasets(datasets_json: Path) -> dict:
    return json.loads(datasets_json.read_text())


def _print_summary(view_dir: Path, summary: dict) -> None:
    print(f"View: {view_dir}")
    print(f"  Files linked:   {summary['files_linked']}")
    print(f"  Files excluded: {summary['files_excluded']}")
    print(f"  Patterns:       {len(summary['patterns'])}")
    print()
    print(f"  {'Subject':<10} {'T1w':>4} {'T2w':>4} {'BOLD':>5}")
    for sub_dir in sorted(view_dir.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        sub = sub_dir.name.removeprefix("sub-")
        t1 = len(list(sub_dir.glob("ses-*/anat/*T1w.nii.gz")))
        t2 = len(list(sub_dir.glob("ses-*/anat/*T2w.nii.gz")))
        bold = len(list(sub_dir.glob("ses-*/func/*_bold.nii.gz")))
        print(f"  {sub:<10} {t1:>4} {t2:>4} {bold:>5}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dataset", help="dataset name registered with neuro-run")
    parser.add_argument("--version", required=True, help="fmriprep version (e.g., 25.2.4)")
    parser.add_argument(
        "--datasets-json",
        default=str(Path.home() / ".neuro_workflow" / "datasets.json"),
        help="path to datasets.json (default: ~/.neuro_workflow/datasets.json)",
    )
    args = parser.parse_args(argv)

    datasets = _load_datasets(Path(args.datasets_json))
    if args.dataset not in datasets:
        print(f"ERROR: dataset '{args.dataset}' not found in {args.datasets_json}", file=sys.stderr)
        return 2

    bids_dir = Path(datasets[args.dataset]["bids_dir"])
    view_dir = bids_dir / "derivatives" / f"fmriprep_{args.version}_input"

    summary = build_view(bids_dir, view_dir)

    expected = EXPECTED_MULTI_ANAT.get(args.dataset, {})
    errors = verify_view(view_dir, expected)
    if errors:
        print("VIEW VERIFICATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 3

    _print_summary(view_dir, summary)
    print(f"\nView ready: {view_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5.4: Run all tests, verify pass**

```bash
uv run pytest tests/scripts/test_fmriprep_preflight.py -v
```
Expected: 16 passing.

- [ ] **Step 5.5: Commit**

```bash
git add scripts/fmriprep_preflight.py tests/scripts/test_fmriprep_preflight.py
git commit -m "feat: wire up fmriprep_preflight CLI"
```

---

## Task 6: neuro-run extension — `--bids-dir-override`

**Files:**
- Modify: `src/neuro_workflow/pipelines/fmriprep.py`
- Modify: `tests/pipelines/test_fmriprep.py`

When `--bids-dir-override` is set, the sbatch binds the override path as `/data` (input) and binds the registered BIDS dir's `derivatives/` as `/out` (output). This avoids the recursive nesting that would happen if outputs were written under the view at `view/derivatives/`.

- [ ] **Step 6.1: Write failing test for override flag**

Append to `tests/pipelines/test_fmriprep.py`:

```python
def test_fmriprep_bids_dir_override(tmp_path):
    """When --bids-dir-override is set, /data binds the override path and
    derivatives output redirects to the original BIDS dir's derivatives/."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input",
    )

    ctx = p.build_context("discovery", dataset_config, args)

    # /data should bind the override path
    assert ctx["bids_dir"] == "/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input"
    # Output should bind the registered BIDS dir's derivatives/ as /out
    assert "-B /scratch/users/logben/discovery_bids/derivatives:/out" in ctx["output_bind_line"]
    assert ctx["output_container"] == "/out"
    # Logs should still go to the registered BIDS dir
    assert ctx["log_dir"] == "/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/logs"


def test_fmriprep_bids_dir_override_in_rendered_template(tmp_path):
    """Full render confirms /data and /out paths are correct in the sbatch."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/scratch/users/logben/discovery_bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-1",
        fmriprep_args="--no-submm-recon --skip-bids-validation --cifti-output 91k",
        fs_license="/home/user/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input",
    )

    ctx = p.build_context("discovery", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    # /data binds the view, not the original BIDS dir
    assert "-B /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input:/data" in script
    # /out binds the original BIDS dir's derivatives/
    assert "-B /scratch/users/logben/discovery_bids/derivatives:/out" in script
    # fmriprep CLI uses /data input, /out/fmriprep_25.2.4 output
    assert "/data /out/fmriprep_25.2.4 participant" in script
    # No /data/derivatives anywhere (would mean output is going under the view)
    assert "/data/derivatives" not in script
    # bash syntax
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert r.returncode == 0, f"bash syntax error: {r.stderr}"


def test_fmriprep_bids_dir_override_default_none(tmp_path):
    """Without --bids-dir-override, behavior is unchanged."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="25.2.4",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
        bids_dir_override=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["bids_dir"] == "/oak/data/bids"
    assert ctx["output_bind_line"] == ""
    assert ctx["output_container"] == "/data/derivatives"
```

- [ ] **Step 6.2: Run tests, verify failure**

```bash
uv run pytest tests/pipelines/test_fmriprep.py -v
```
Expected: 3 new tests fail (`AttributeError` on `args.bids_dir_override` or path mismatches).

- [ ] **Step 6.3: Modify `src/neuro_workflow/pipelines/fmriprep.py`**

Open the file and make two changes:

**Change A** — add the CLI flag in `add_cli_args`. Below the existing `--output-dir` argument, add:

```python
        parser.add_argument(
            "--bids-dir-override",
            default=None,
            help="Path to bind as /data instead of the registered bids_dir. Use to "
                 "point fmriprep at a symlink BIDS view. Output derivatives still go "
                 "to <registered bids_dir>/derivatives/fmriprep_<version>/.",
        )
```

**Change B** — in `build_context`, after the existing `output_dir`/`bids_filter_file` blocks and before `mail_line = build_mail_line(...)`, replace the existing logic that decides `bids_dir` / `output_bind_line` / `output_container` / `log_dir`. The full replacement region:

Find this block:
```python
        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{args.version}"

        output_dir = getattr(args, "output_dir", None)
        if output_dir:
            output_bind_line = f"  -B {output_dir}:/out \\\n"
            output_container = "/out"
            log_dir = f"{output_dir}/fmriprep_{args.version}/logs"
        else:
            output_bind_line = ""
            output_container = "/data/derivatives"
            log_dir = f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.version}/logs"
```

Replace with:
```python
        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{args.version}"

        bids_dir_override = getattr(args, "bids_dir_override", None)
        output_dir = getattr(args, "output_dir", None)

        if bids_dir_override and output_dir:
            print(
                "Error: --bids-dir-override and --output-dir are mutually exclusive",
                file=sys.stderr,
            )
            sys.exit(1)

        if bids_dir_override:
            # Input is the view; output is forced to the registered BIDS dir's derivatives/
            bids_dir_for_bind = bids_dir_override
            registered_derivs = f"{dataset_config['bids_dir']}/derivatives"
            output_bind_line = f"  -B {registered_derivs}:/out \\\n"
            output_container = "/out"
            log_dir = f"{registered_derivs}/fmriprep_{args.version}/logs"
        elif output_dir:
            bids_dir_for_bind = dataset_config["bids_dir"]
            output_bind_line = f"  -B {output_dir}:/out \\\n"
            output_container = "/out"
            log_dir = f"{output_dir}/fmriprep_{args.version}/logs"
        else:
            bids_dir_for_bind = dataset_config["bids_dir"]
            output_bind_line = ""
            output_container = "/data/derivatives"
            log_dir = f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.version}/logs"
```

Then in the `return {...}` dict, change:
```python
            "bids_dir": dataset_config["bids_dir"],
```
to:
```python
            "bids_dir": bids_dir_for_bind,
```

- [ ] **Step 6.4: Run tests, verify pass**

```bash
uv run pytest tests/pipelines/test_fmriprep.py -v
```
Expected: All tests pass (existing + 3 new).

- [ ] **Step 6.5: Commit**

```bash
git add src/neuro_workflow/pipelines/fmriprep.py tests/pipelines/test_fmriprep.py
git commit -m "feat(fmriprep): add --bids-dir-override for symlink BIDS view input"
```

---

## Task 7: Pre-flight smoke test on the real scratch BIDS

**Files:** none (operational task)

Verify the pre-flight script produces a valid view for both real datasets.

- [ ] **Step 7.1: Run pre-flight on discovery**

```bash
cd /home/users/logben/neuro_workflow
uv run python scripts/fmriprep_preflight.py discovery --version 25.2.4
```
Expected:
- Exit code 0
- Summary table prints with 5 subjects (s03, s10, s19, s29, s43)
- Each subject shows ≥1 T1w
- Final line: "View ready: /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input"

- [ ] **Step 7.2: Spot-check the discovery view**

```bash
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input/sub-s03/ses-05/anat/
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input/sub-s03/ses-01/anat/ 2>/dev/null
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input/sub-s10/ses-01/func/ | head -5
```
Expected:
- ses-05 anat: SagMPRAGE T1w + JSON symlinks
- ses-01 anat: empty or doesn't exist (MPRAGEPromo excluded)
- ses-01 func: NOT contains `task-goNogo_run-1` files (s10 ses-01 goNogo run-1 is .bidsignored), DOES contain `task-goNogo_run-2` files

- [ ] **Step 7.3: Run pre-flight on validation**

```bash
uv run python scripts/fmriprep_preflight.py validation --version 25.2.4
```
Expected:
- Exit code 0
- 41 subjects in summary
- s1351 shows 2 T1w (multi-anat verified)
- s1399 shows 2 T2w (multi-anat verified)

- [ ] **Step 7.4: Verify excluded scans absent**

```bash
ls /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4_input/sub-s1127/ses-01/anat/ 2>/dev/null
ls /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4_input/sub-s1127/ses-09/anat/
```
Expected:
- ses-01 anat: empty (s1127 ses-01 T1w is .bidsignored)
- ses-09 anat: contains SagMPRAGE T1w symlink

- [ ] **Step 7.5: Verify idempotency**

```bash
uv run python scripts/fmriprep_preflight.py discovery --version 25.2.4
uv run python scripts/fmriprep_preflight.py discovery --version 25.2.4
```
Expected: Both runs succeed; second run prints same summary (no errors about pre-existing symlinks).

---

## Task 8: Wipe stale work dirs and failed FS dirs

**Files:** none (operational task)

The prior failed runs left polluted state. Clean before submitting fresh jobs.

- [ ] **Step 8.1: Inspect what exists**

```bash
ls -la /scratch/users/logben/work/ 2>/dev/null | grep fmriprep
ls -la /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/ 2>/dev/null
ls -la /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4/ 2>/dev/null
```
Expected: see fmriprep work dirs and partial derivatives.

- [ ] **Step 8.2: Confirm no fmriprep jobs are still running**

```bash
sqlb 2>/dev/null | grep fmriprep
```
Expected: (empty or only `CG` cleaning-up entries that will exit shortly).

If any RUNNING/PENDING fmriprep jobs exist, do NOT wipe — wait for them to finish or cancel them explicitly. **Stop and triage** before continuing.

- [ ] **Step 8.3: Wipe fmriprep 25.2.4 work dirs and partial derivatives**

```bash
rm -rf /scratch/users/logben/work/fmriprep_discovery_25.2.4
rm -rf /scratch/users/logben/work/fmriprep_validation_25.2.4
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4
rm -rf /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4
```

**Important:** Do NOT remove `derivatives/fmriprep_25.2.4_input/` (the views). Those are needed.

- [ ] **Step 8.4: Verify clean state**

```bash
ls /scratch/users/logben/work/ 2>/dev/null | grep fmriprep
ls /scratch/users/logben/discovery_bids/derivatives/ 2>/dev/null
ls /scratch/users/logben/validation_bids/derivatives/ 2>/dev/null
```
Expected:
- Work: no `fmriprep_*_25.2.4` dirs.
- discovery_bids/derivatives/: contains `fmriprep_25.2.4_input/` only.
- validation_bids/derivatives/: contains `fmriprep_25.2.4_input/` only.

---

## Task 9: Submit Phase 1 — s03 profile

**Files:** none (operational task)

Submit a single fmriprep job for s03 to validate the view, the resource envelope, and the full pipeline shape before launching production.

- [ ] **Step 9.1: Confirm subjects file exists**

```bash
cat /home/users/logben/neuro_workflow/subjects_discovery.txt
```
Expected: 5 subjects (s03, s10, s19, s29, s43).

- [ ] **Step 9.2: Create a single-subject file for s03**

```bash
echo "s03" > /home/users/logben/neuro_workflow/subjects_phase1_s03.txt
```

- [ ] **Step 9.3: Preview the rendered sbatch (do not submit yet)**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run show fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 7-00:00:00 \
  --array-throttle 1 \
  --subjects-file subjects_phase1_s03.txt
```
Expected:
- Print sbatch script.
- Verify: `--array=1-1%1`, `--cpus-per-task=8`, `--mem-per-cpu=24G`, `--time=7-00:00:00`, `-B .../fmriprep_25.2.4_input:/data`, `-B .../discovery_bids/derivatives:/out`.

If the rendered script looks wrong, **stop**, fix, retry.

- [ ] **Step 9.4: Submit Phase 1**

Replace `show` with `submit`:

```bash
uv run neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 7-00:00:00 \
  --array-throttle 1 \
  --subjects-file subjects_phase1_s03.txt
```
Expected: `Submitted batch job <PHASE1_JID>`. Record `PHASE1_JID`.

- [ ] **Step 9.5: Confirm queue state**

```bash
sqlb | grep fmriprep
sleep 30
sqlb | grep fmriprep
```
Expected: 1 task in PD (pending) or R (running).

---

## Task 10: Validate Phase 1 outputs and write profile report

**Files:**
- Create: `docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md`

Wait for Phase 1 to complete (3-7 days). Validate gates per spec, capture metrics.

- [ ] **Step 10.1: Wait for Phase 1 completion**

```bash
# Replace <PHASE1_JID> with the actual job ID
sacct -j <PHASE1_JID> --format=JobID,State,Elapsed,MaxRSS,ExitCode --noheader | grep -v "extern\|batch"
```
Expected: `_1 COMPLETED 0:0` with elapsed time recorded.

If state is FAILED/TIMEOUT/OOM: triage per the failure decision tree in the spec, fix, resubmit, return to Step 10.1.

- [ ] **Step 10.2: Validate the success gates**

```bash
DERIVS=/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4
LOGS=$DERIVS/logs

# 1. No Talairach failure
grep -l "Talairach failed" $LOGS/*-1.out $LOGS/*-1.err 2>/dev/null \
  && echo "FAIL: Talairach failure detected" || echo "OK: no Talairach failure"

# 2. recon-all finished
ls $DERIVS/sourcedata/freesurfer/sub-s03_*/scripts/recon-all-status.log 2>/dev/null \
  && tail -1 $DERIVS/sourcedata/freesurfer/sub-s03_*/scripts/recon-all-status.log

# 3. Anat MNI output
ls $DERIVS/sub-s03/anat/*MNI152NLin2009cAsym*desc-preproc_T1w.nii.gz 2>/dev/null \
  && echo "OK: anat MNI output" || echo "FAIL: missing anat MNI"

# 4. Per-BOLD outputs (one example)
ls $DERIVS/sub-s03/ses-02/func/*desc-preproc_bold.nii.gz 2>/dev/null \
  && echo "OK: BOLD outputs present" || echo "FAIL: missing BOLD outputs"

# 5. CIFTI present
ls $DERIVS/sub-s03/ses-02/func/*den-91k_bold.dtseries.nii 2>/dev/null \
  && echo "OK: CIFTI generated" || echo "FAIL: missing CIFTI"

# 6. Confounds tables
ls $DERIVS/sub-s03/ses-02/func/*confounds_timeseries.tsv 2>/dev/null \
  && echo "OK: confounds present" || echo "FAIL: missing confounds"

# 7. HTML report
ls $DERIVS/sub-s03.html 2>/dev/null \
  && echo "OK: HTML report exists" || echo "FAIL: missing HTML report"

# 8. No CRITICAL lines
grep -c "CRITICAL" $LOGS/*-1.out 2>/dev/null
```
Expected: All gates marked OK; CRITICAL count is 0.

If any gate fails: stop, triage, fix, return to Phase 1.

- [ ] **Step 10.3: Capture sacct profile metrics**

```bash
sacct -j <PHASE1_JID> --format=JobID,State,Elapsed,MaxRSS,MaxVMSize,AveCPU,ReqMem --noheader \
  | grep -v "extern\|batch"
```
Record: Elapsed time, MaxRSS (peak resident memory).

- [ ] **Step 10.4: Write profile report**

Create `docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md`:

```markdown
# fMRIPrep 25.2.4 s03 profile report

**Date:** <fill in>
**SLURM job:** <PHASE1_JID>

## Resource envelope

- Requested: 8 CPU × 24 GB = 192 GB, 7-day wall
- Actual peak RSS: <fill from sacct>
- Actual elapsed time: <fill from sacct>

## Stage breakdown

(extracted from $DERIVS/logs/*-1.out workflow timestamps)

| Stage | Duration |
|-------|----------|
| FreeSurfer (recon-all) | <fill> |
| ANTs templates / normalization | <fill> |
| BOLD preprocessing (all sessions) | <fill> |
| CIFTI generation | <fill> |

## Verification of outputs

- ✅ recon-all finished without error
- ✅ No Talairach failure
- ✅ Anat MNI output present
- ✅ BOLD preproc outputs for all non-.bidsignored BOLDs
- ✅ CIFTI files generated
- ✅ Confounds tables present
- ✅ HTML report renders cleanly

## Production calibration

Based on actual peak RSS:

- Production memory: 8 CPU × <calibrated> GB
  - Rationale: peak RSS + ~20% headroom, capped at 22 GB/CPU to fit all 16 russpold nodes
- Production wall: 7 days (russpold maximum)
- Production throttle: 12 (validation), 4 (discovery)

## Calibration decision

Production envelope: **8 CPU × <X> GB = <X*8> GB total memory**, 7-day wall, throttle 12.
```

Fill in the `<X>` values from the actual sacct output. Conservative rule: round MaxRSS up to next multiple of 16 (e.g., MaxRSS 142 GB → 144 GB → mem-per-cpu-gb=18).

- [ ] **Step 10.5: Commit the profile report**

```bash
git add docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md
git commit -m "docs: add Phase 1 fmriprep s03 profile report"
```

---

## Task 11: Submit Phase 2 — discovery production (4 subjects)

**Files:** none (operational task)

- [ ] **Step 11.1: Build subjects file for Phase 2 discovery (excludes s03)**

```bash
cd /home/users/logben/neuro_workflow
grep -v '^s03$' subjects_discovery.txt > subjects_phase2_discovery.txt
wc -l subjects_phase2_discovery.txt
```
Expected: 4 subjects.

- [ ] **Step 11.2: Preview the sbatch**

```bash
# Replace <X> with calibrated mem-per-cpu-gb from profile report (default to 22 if Phase 1 RSS was < 176 GB)
uv run neuro-run show fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb <X> --time 7-00:00:00 \
  --array-throttle 4 \
  --subjects-file subjects_phase2_discovery.txt
```
Expected: `--array=1-4%4`, correct binds, calibrated memory.

- [ ] **Step 11.3: Submit Phase 2 discovery**

Replace `show` with `submit` and rerun. Record `DISCOVERY_JID`.

- [ ] **Step 11.4: Confirm submission**

```bash
sqlb | grep fmriprep
```
Expected: 4 array tasks PD/R.

---

## Task 12: Submit Phase 2 — validation production (41 subjects)

**Files:** none (operational task)

- [ ] **Step 12.1: Confirm validation subjects file**

```bash
wc -l /home/users/logben/neuro_workflow/subjects_validation.txt
```
Expected: 41 subjects.

- [ ] **Step 12.2: Submit validation with `afterany` dependency on discovery**

```bash
# Replace <X> with calibrated mem-per-cpu-gb, <DISCOVERY_JID> with discovery job ID
uv run neuro-run submit fmriprep validation \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb <X> --time 7-00:00:00 \
  --array-throttle 12 \
  --dependency afterany:<DISCOVERY_JID> \
  --subjects-file subjects_validation.txt
```

**Note:** This requires `neuro-run` to forward `--dependency` to sbatch. If `--dependency` is not yet a recognized flag for neuro-run, fall back to: render the sbatch via `show`, save it to a file, then `sbatch --dependency=afterany:<DISCOVERY_JID> <file>`.

Expected: `Submitted batch job <VALIDATION_JID>`. Record `VALIDATION_JID`.

- [ ] **Step 12.3: Confirm submission state**

```bash
sqlb | grep fmriprep
scontrol show job <VALIDATION_JID> | grep -E "Dependency|JobState"
```
Expected: Validation array shows `Dependency=afterany:<DISCOVERY_JID>` and `JobState=PENDING Reason=Dependency`.

---

## Task 13: Daily monitoring + triage

**Files:** none (operational task, run daily during production)

- [ ] **Step 13.1: Daily snapshot**

```bash
date
echo "=== Active fmriprep jobs ==="
sqlb 2>/dev/null | grep fmriprep
echo ""
echo "=== Completions/failures in last 24h ==="
sacct -u logben --starttime=$(date -d '24 hours ago' +%FT%T) \
  --format=JobID,State,Elapsed,MaxRSS,ExitCode --noheader 2>/dev/null \
  | grep -v "extern\|batch" | grep fmriprep | sort
```

- [ ] **Step 13.2: First-wave resource check**

After the first 5-10 production subjects complete, compare actual peak RSS against allocation:

```bash
sacct -j <DISCOVERY_JID> -j <VALIDATION_JID> \
  --format=JobID,State,Elapsed,MaxRSS,ReqMem --noheader 2>/dev/null \
  | grep -v "extern\|batch" | grep -v PENDING
```

If actual peak RSS / allocation > 90%: bump `--mem-per-cpu-gb` for remaining subjects.
If actual peak RSS / allocation < 50%: leaving as-is is fine; over-provisioning is harmless here (only memory budget per node).

- [ ] **Step 13.3: Per-failure triage (decision tree from spec)**

For each FAILED, TIMEOUT, or OOM task, look up the subject and follow the decision tree:

```bash
# Identify the subject behind a failed array task
SUBJECT=$(sed "${TASKID}q;d" subjects_validation.txt)  # or subjects_phase2_discovery.txt
echo "Failed: sub-$SUBJECT (job ${JID}_${TASKID})"

# Read sacct
sacct -j ${JID}_${TASKID} --format=State,Elapsed,MaxRSS,ExitCode

# Read tail of the err/out log
LOGS=/scratch/users/logben/{discovery,validation}_bids/derivatives/fmriprep_25.2.4/logs
tail -50 $LOGS/*-${JID}-${TASKID}.err
```

Failure → Action:

| Pattern | Action |
|---------|--------|
| `State=OUT_OF_MEMORY` or `MaxRSS` near `ReqMem` | Bump `--mem-per-cpu-gb` by ~25%, resubmit just that subject (single-task array of 1, same flags otherwise). Do NOT wipe work dir; fmriprep resumes. |
| `State=TIMEOUT` with reasonable MaxRSS | Resubmit same flags; same work dir → fmriprep resumes. If second timeout, bump memory. |
| Early `FileNotFoundError` on `*.pklz` (nipype hash race) | Wipe `/scratch/users/logben/work/fmriprep_<dataset>_25.2.4/sub-<SUBJECT>/`, resubmit. |
| `Talairach failed` in workflow log | Should not occur. If it does: investigate which T1w fmriprep used (workflow log says `Building fMRIPrep's workflow: ... Participants and sessions`), check view's anat dir. |
| Other CRITICAL workflow error | Read crashfile path from log, inspect. Fix or escalate. |

For single-subject resubmit:

```bash
uv run neuro-run submit fmriprep validation \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb <bumped X> --time 7-00:00:00 \
  --array-throttle 1 \
  --subjects-file <(echo <SUBJECT>)
```

- [ ] **Step 13.4: Track triage outcomes**

After each triage action, append a row to `docs/superpowers/specs/2026-04-28-fmriprep-rerun-profile-report.md` under a new section:

```markdown
## Production triage log

| Date | Subject | Original failure | Action | Resubmit JID | Outcome |
|------|---------|------------------|--------|--------------|---------|
| 2026-MM-DD | s1057 | TIMEOUT 7d | resubmit (resume) | <jid> | COMPLETED in <Xd> |
```

---

## Task 14: Final validation

**Files:** none (operational task)

After all 46 subjects have COMPLETED state, validate the deliverables.

- [ ] **Step 14.1: Confirm all subjects have outputs**

```bash
for ds in discovery validation; do
  bids=/scratch/users/logben/${ds}_bids
  derivs=$bids/derivatives/fmriprep_25.2.4
  echo "=== $ds ==="
  for sub_dir in $bids/sub-*; do
    sub=$(basename $sub_dir)
    html=$derivs/$sub.html
    anat=$(ls $derivs/$sub/anat/*MNI152NLin2009cAsym*desc-preproc_T1w.nii.gz 2>/dev/null | head -1)
    if [ -n "$html" ] && [ -n "$anat" ]; then
      echo "  $sub: OK"
    else
      echo "  $sub: INCOMPLETE (html=$html anat=$anat)"
    fi
  done
done
```
Expected: All 46 subjects show OK.

- [ ] **Step 14.2: Confirm CIFTI outputs**

```bash
for ds in discovery validation; do
  count=$(find /scratch/users/logben/${ds}_bids/derivatives/fmriprep_25.2.4 \
              -name "*den-91k_bold.dtseries.nii" 2>/dev/null | wc -l)
  echo "$ds: $count CIFTI files"
done
```
Expected: count > 0 for both datasets, roughly matching number of non-.bidsignored BOLDs.

- [ ] **Step 14.3: Visually inspect HTML reports**

For each of the 46 subjects, open `derivatives/fmriprep_25.2.4/sub-XX.html` in a browser:
- T1w → MNI registration looks reasonable
- BOLD → T1w coregistration looks reasonable
- Carpet plots aren't pathological

Note any subjects with concerning visualizations for downstream review.

- [ ] **Step 14.4: Update MEMORY.md**

Add a note to `~/.claude/projects/-home-users-logben-neuro-workflow/memory/MEMORY.md` index pointing at the spec and profile report so future sessions have continuity.

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by task |
|--------------|-----------------|
| Phase 0 pre-flight script | Tasks 1-5 (build), Task 7 (run) |
| Phase 0 wipe stale dirs | Task 8 |
| neuro-run --bids-dir-override | Task 6 |
| Phase 1 s03 profile | Task 9 |
| Phase 1 success gates + profile report | Task 10 |
| Phase 2 discovery production | Task 11 |
| Phase 2 validation production | Task 12 |
| Daily monitoring + failure triage | Task 13 |
| Final validation | Task 14 |
| Multi-anat handling (s1351, s1399) | Task 4 (verify_view), Task 7 (smoke check) |
| .bidsignore translation | Tasks 1-5 (algorithm), Task 7 (real data) |
| Cancellation of prior jobs | Already done before plan execution |

All spec sections have task coverage.

**Placeholder scan:** The plan uses `<PHASE1_JID>`, `<DISCOVERY_JID>`, `<VALIDATION_JID>`, `<X>`, `<SUBJECT>`, `<bumped X>` — these are intentional runtime fill-ins (job IDs assigned by SLURM, calibration values from sacct). They are documented in their respective steps and have explicit replacement instructions. No spec gaps.

**Type consistency:** Functions defined in earlier tasks (`parse_bidsignore`, `path_matches_any`, `build_view`, `verify_view`) are referenced consistently throughout. The `expected_multi_anat` dict shape is consistent between Tasks 4 (definition) and 5 (CLI usage). Test helper `_make_fake_bids` is reused across Tasks 3, 4, and 5.

---

## Execution Notes

- Tasks 1-6 are pure code (TDD), can run back-to-back.
- Task 7 is a smoke test on real data; must come before Task 8.
- Task 8 is destructive (wipes prior runs); confirm before running.
- Tasks 9-14 are operational and span weeks. Submit, wait, triage, repeat.
- `module load uv` is required on Sherlock before any `uv run` command (per CLAUDE.md global instructions).
