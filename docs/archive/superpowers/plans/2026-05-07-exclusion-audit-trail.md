# Exclusion Audit Trail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-source `_meta` provenance to generator outputs and a committed dataset lockfile (`data/exclusions/<ds>_lock.json`) written by `compile_exclusions`, plus enhance `neuro-run exclusions show` to surface the audit info.

**Architecture:** Helpers (`_git_sha`, `_jsonify`, `make_meta`) live in `exclusions/base.py`. `save_source_entries` (in `core/exclusions.py`) wraps each generator's output as `{"_meta": ..., "entries": [...]}`. `compile_exclusions` reads each source's `_meta` (handling both wrapped and legacy bare-list formats), aggregates into a top-level provenance dict, and writes `data/exclusions/<ds>_lock.json` alongside the existing `compiled_exclusions.json`. `cmd_exclusions_show` enhanced to also print provenance from the lockfile when it exists.

**Tech Stack:** Python 3.13, json, subprocess (for git SHA), datetime (for ISO timestamps), pytest.

**Spec:** `docs/superpowers/specs/2026-05-07-exclusion-audit-trail-design.md`

---

## Adjustments to spec wording

The spec's section on `save_source_entries` says the signature becomes `(ds, source, entries, args, generator_name)`. In practice `source_name` IS the generator name (the existing call sites already pass them as the same thing). The simpler signature is `(ds, source_name, entries, args=None)` — `args=None` covers the existing import + events_qc paths cleanly without forcing every call site to invent a Namespace.

Also: `cmd_exclusions_show` already exists at `cli.py:170`. The spec's "new command" is more accurately an *enhancement*: it now reads the lockfile (when present) and prints provenance, falling back to the existing compiled-JSON-based summary if the lockfile doesn't exist yet.

These two adjustments don't change the design's substance.

---

## Task 1: Add `_git_sha`, `_jsonify`, `make_meta` helpers (TDD)

**Files:**
- Create: `tests/exclusions/test_provenance.py`
- Modify: `src/neuro_workflow/exclusions/base.py`

- [ ] **Step 1.1: Create test file with first failing test**

Create `tests/exclusions/test_provenance.py`:

```python
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
```

- [ ] **Step 1.2: Run; expect FAIL on missing imports**

```bash
module load uv
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: FAIL with `ImportError: cannot import name 'make_meta' from 'neuro_workflow.exclusions.base'`.

- [ ] **Step 1.3: Add helpers to `exclusions/base.py`**

Edit `src/neuro_workflow/exclusions/base.py`. Append after the existing `load_dataset_subjects` function:

```python
import json
import subprocess
from datetime import datetime, timezone


def _git_sha() -> str | None:
    """Return the current git HEAD short SHA, with '+dirty' suffix if the working
    tree has uncommitted changes. Returns None if git is unavailable or this is
    not a git repo."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not sha:
        return None
    try:
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return sha
    return f"{sha}+dirty" if dirty else sha


def _jsonify(value):
    """Convert non-JSON-native values (Path, set, etc.) to JSON-safe forms.

    Walks dicts and lists recursively. Path becomes str. Other unknown types
    are returned as-is and may fail json.dumps loudly downstream — that's fine.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def make_meta(
    generator_name: str,
    args: "Namespace | dict | None",
    n_entries: int,
) -> dict:
    """Build the _meta block for a generator's saved sources file.

    args can be argparse.Namespace, a plain dict, or None (for callers that
    don't have an args object — e.g., cmd_exclusions_import / cmd_events_qc).
    """
    if args is None:
        args_dict = None
    elif hasattr(args, "__dict__") and not isinstance(args, dict):
        args_dict = vars(args)
    else:
        args_dict = dict(args)

    return {
        "generator": generator_name,
        "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_sha": _git_sha(),
        "args": _jsonify(args_dict) if args_dict is not None else None,
        "n_entries": n_entries,
    }
```

Add `from argparse import Namespace` to the imports near the top of the file if not already present (it should be, from the existing Protocol). Add `from pathlib import Path` if not already there (already added in QA-DEC Task 1). Add `import json`, `import subprocess`, `from datetime import datetime, timezone` near the other imports.

- [ ] **Step 1.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: 4 passed.

- [ ] **Step 1.5: Commit**

```bash
git add tests/exclusions/test_provenance.py src/neuro_workflow/exclusions/base.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): add _git_sha, _jsonify, make_meta helpers

Building blocks for the audit-trail _meta block. _git_sha returns
the short SHA with +dirty suffix when uncommitted changes exist;
returns None when git is unavailable. _jsonify walks dicts/lists
and stringifies Path. make_meta builds the full dict.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `save_source_entries` wraps with `_meta` (TDD)

**Files:**
- Modify: `src/neuro_workflow/core/exclusions.py`
- Modify: `tests/exclusions/test_provenance.py`

- [ ] **Step 2.1: Append failing test**

Append to `tests/exclusions/test_provenance.py`:

```python
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
```

- [ ] **Step 2.2: Run; expect FAIL on shape mismatch**

```bash
uv run pytest tests/exclusions/test_provenance.py::test_save_source_entries_wraps_with_meta -v
```

Expected: FAIL with `AssertionError: ... set(on_disk.keys())` mismatch (currently the file is a bare list).

- [ ] **Step 2.3: Update `save_source_entries` to wrap**

Edit `src/neuro_workflow/core/exclusions.py`. Replace the existing `save_source_entries` (currently lines 41-46):

```python
def save_source_entries(dataset_name: str, source_name: str, entries: list[dict]) -> None:
    """Write entries for a single source to its JSON file."""
    d = _sources_dir(dataset_name)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{source_name}.json", "w") as f:
        json.dump(entries, f, indent=2)
```

with:

```python
def save_source_entries(
    dataset_name: str,
    source_name: str,
    entries: list[dict],
    args: "Namespace | dict | None" = None,
) -> None:
    """Write entries for a single source as `{"_meta": ..., "entries": [...]}`.

    args is recorded in the _meta block (as JSON-safe dict). If None, args
    field is null — fine for callers that don't have a generator-level
    Namespace (cmd_exclusions_import / cmd_events_qc).
    """
    from neuro_workflow.exclusions.base import make_meta
    d = _sources_dir(dataset_name)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": make_meta(source_name, args, len(entries)),
        "entries": entries,
    }
    with open(d / f"{source_name}.json", "w") as f:
        json.dump(payload, f, indent=2)
```

Add `from argparse import Namespace` to the imports at the top of the file (used only as a type hint; the body uses `make_meta` for dispatch).

- [ ] **Step 2.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: 6 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/neuro_workflow/core/exclusions.py tests/exclusions/test_provenance.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): wrap saved source entries with _meta provenance

save_source_entries now writes {"_meta": {...}, "entries": [...]} per
file. The _meta block records generator, ISO timestamp, git SHA (with
+dirty suffix), CLI args, and n_entries. Bare-list back-compat at the
read path follows in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Read path handles both wrapped + bare-list formats (TDD)

`compile_exclusions` and `load_source_entries` currently treat each sources file as a bare list. Now that we write wrapped, we need to read both — wrapped for new files, bare-list for any legacy file or for tests written before this change.

**Files:**
- Modify: `src/neuro_workflow/core/exclusions.py`
- Modify: `tests/exclusions/test_provenance.py`

- [ ] **Step 3.1: Append failing tests**

Append to `tests/exclusions/test_provenance.py`:

```python
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

    sources_dir = tmp_path / "exclusions" / "discovery" / "sources"
    sources_dir.mkdir(parents=True)

    # Wrapped
    wrapped = {
        "_meta": {"generator": "lev1_outlier", "ran_at": "2026-05-07T00:00:00Z",
                  "code_sha": "abc", "args": {}, "n_entries": 1},
        "entries": [
            {"subject": "sub-s03", "session": "ses-02", "task": "task-x",
             "run": "run-1", "source": "lev1_outlier", "action": "exclude", "reason": "y"},
        ],
    }
    (sources_dir / "lev1_outlier.json").write_text(json.dumps(wrapped))

    # Bare-list
    bare = [
        {"subject": "sub-s10", "session": "ses-02", "task": "task-x",
         "run": "run-1", "source": "motion", "action": "exclude", "reason": "z"},
    ]
    (sources_dir / "motion.json").write_text(json.dumps(bare))

    compiled = core_excl.compile_exclusions("discovery")
    subjects = {e["subject"] for e in compiled}
    assert subjects == {"sub-s03", "sub-s10"}
```

- [ ] **Step 3.2: Run; expect FAILS**

```bash
uv run pytest tests/exclusions/test_provenance.py::test_load_source_entries_handles_wrapped_format -v
uv run pytest tests/exclusions/test_provenance.py::test_compile_handles_mixed_wrapped_and_bare_sources -v
```

Expected: both FAIL — `load_source_entries` returns the dict (not the list); `compile_exclusions` calls `all_entries.extend(json.load(f))` which extends with a dict's keys instead of entries.

- [ ] **Step 3.3: Add a helper + update read paths**

Edit `src/neuro_workflow/core/exclusions.py`. Add a private helper near the top (after the constants, before `_scan_key`):

```python
def _read_source_file(path: Path) -> tuple[list[dict], dict | None]:
    """Read a sources/*.json file. Returns (entries, meta).

    Handles both new wrapped format `{"_meta": ..., "entries": [...]}` and
    legacy bare-list format `[...]`. For bare-list, meta is a synthetic
    null-fields dict with generator inferred from the filename stem.
    """
    with open(path) as f:
        loaded = json.load(f)
    if isinstance(loaded, list):
        # Legacy bare-list format.
        meta = {
            "generator": path.stem,
            "ran_at": None,
            "code_sha": None,
            "args": None,
            "n_entries": len(loaded),
        }
        return loaded, meta
    # Wrapped format.
    return loaded.get("entries", []), loaded.get("_meta")
```

Update `load_source_entries`:

```python
def load_source_entries(dataset_name: str, source_name: str) -> list[dict]:
    """Load entries for a single source. Handles both wrapped and bare formats."""
    path = _sources_dir(dataset_name) / f"{source_name}.json"
    if not path.exists():
        return []
    entries, _meta = _read_source_file(path)
    return entries
```

Update `compile_exclusions`'s sources-reading loop. Replace the block:

```python
    if sources_dir.exists():
        for source_file in sorted(sources_dir.glob("*.json")):
            with open(source_file) as f:
                all_entries.extend(json.load(f))
```

with:

```python
    sources_meta: list[dict] = []
    if sources_dir.exists():
        for source_file in sorted(sources_dir.glob("*.json")):
            entries, meta = _read_source_file(source_file)
            all_entries.extend(entries)
            if meta is not None:
                sources_meta.append(meta)
```

`sources_meta` is collected here for use by Task 4 (lockfile writing). For now it just sits unused.

- [ ] **Step 3.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: 9 passed (existing 6 + 3 new).

- [ ] **Step 3.5: Run full exclusions + analysis suites for regressions**

```bash
uv run pytest tests/exclusions/ tests/analysis/ -q --tb=line 2>&1 | tail -10
```

Expected: all green. The compile-pipeline integration tests in `test_lev1_outlier.py` and `test_qa_decisions.py` must still pass — they call `save_source_entries` (now wraps) then `compile_exclusions` (now unwraps); round-trips correctly.

- [ ] **Step 3.6: Commit**

```bash
git add src/neuro_workflow/core/exclusions.py tests/exclusions/test_provenance.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): read both wrapped + legacy bare-list source files

_read_source_file dispatches on JSON shape: wrapped {_meta, entries}
or legacy bare-list. compile_exclusions and load_source_entries use
the helper. sources_meta collected but unused; lockfile writing
follows in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `compile_exclusions` writes the lockfile (TDD)

**Files:**
- Modify: `src/neuro_workflow/core/exclusions.py`
- Modify: `tests/exclusions/test_provenance.py`

- [ ] **Step 4.1: Append failing tests**

Append to `tests/exclusions/test_provenance.py`:

```python
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
    # Both sources show up in the manifest
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
```

- [ ] **Step 4.2: Run; expect FAIL on missing LOCKFILE_DIR / no lockfile**

```bash
uv run pytest tests/exclusions/test_provenance.py::test_compile_writes_lockfile -v
```

Expected: FAIL with `AttributeError: module ... has no attribute 'LOCKFILE_DIR'` (or assertion that lock_path doesn't exist).

- [ ] **Step 4.3: Add `LOCKFILE_DIR` constant + lockfile writing**

Edit `src/neuro_workflow/core/exclusions.py`.

(a) Near the top, after `EXCLUSIONS_DIR = CONFIG_DIR / "exclusions"`, add:

```python
# Project-relative path for committed lockfiles. Resolved at write time
# from the package's parent directories.
_REPO_ROOT = Path(__file__).resolve().parents[3]
LOCKFILE_DIR = _REPO_ROOT / "data" / "exclusions"
```

(`Path(__file__)` is `.../src/neuro_workflow/core/exclusions.py`. `.parents[3]` is `.../neuro_workflow` — the repo root. The implementer verifies the index matches; if the package layout has changed, adjust.)

(b) Add a helper near `_compiled_path`:

```python
def _lockfile_path(dataset_name: str) -> Path:
    return LOCKFILE_DIR / f"{dataset_name}_lock.json"
```

(c) Update `compile_exclusions`. Just before `return all_entries`, add the lockfile writing block. Replace the end of the function from `# Save compiled` through `return all_entries`:

```python
    # Save compiled
    compiled_path = _compiled_path(dataset_name)
    compiled_path.parent.mkdir(parents=True, exist_ok=True)
    with open(compiled_path, "w") as f:
        json.dump(all_entries, f, indent=2)

    # Copy to derivatives if bids_dir provided
    if bids_dir:
        deriv = Path(bids_dir) / "derivatives" / "exclusions"
        deriv.mkdir(parents=True, exist_ok=True)
        with open(deriv / "compiled_exclusions.json", "w") as f:
            json.dump(all_entries, f, indent=2)

    # Write the committed lockfile.
    from neuro_workflow.exclusions.base import _git_sha
    from datetime import datetime, timezone

    lock_path = _lockfile_path(dataset_name)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = {
        "dataset": dataset_name,
        "compiled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compiled_at_code_sha": _git_sha(),
        "compiled_path": str(compiled_path),
        "n_total_entries": len(all_entries),
        "n_overrides": len(overrides),
        "sources": sources_meta,
    }
    with open(lock_path, "w") as f:
        json.dump(lock, f, indent=2)

    return all_entries
```

The `sources_meta` was collected in Task 3 Step 3.3.

- [ ] **Step 4.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: 12 passed.

- [ ] **Step 4.5: Run full exclusions + analysis suites**

```bash
uv run pytest tests/exclusions/ tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: all green. Compile-integration tests in `test_lev1_outlier.py` and `test_qa_decisions.py` exercise the full save → compile path; they will now also write a lockfile to `LOCKFILE_DIR` (the real `data/exclusions/`) — that's a side effect but not a regression. The implementer may need to monkeypatch `LOCKFILE_DIR` in those tests too if pytest tmp_path isolation matters; check by running.

- [ ] **Step 4.6: Commit**

```bash
git add src/neuro_workflow/core/exclusions.py tests/exclusions/test_provenance.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): compile_exclusions writes data/exclusions/<ds>_lock.json

Lockfile is the canonical audit artifact, committed to git. Schema:
dataset, compiled_at (ISO), compiled_at_code_sha, compiled_path,
n_total_entries, n_overrides, sources (per-source _meta blocks).
Per-source meta is null-filled when the source file is in legacy
bare-list format.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update CLI call sites to pass `args` (TDD)

`save_source_entries` now accepts `args=None`. Three call sites in `cli.py` should pass meaningful args when available.

**Files:**
- Modify: `src/neuro_workflow/cli.py`
- Modify: `tests/exclusions/test_provenance.py`

- [ ] **Step 5.1: Append failing test**

Append to `tests/exclusions/test_provenance.py`:

```python
def test_cmd_exclusions_generate_passes_args_through(tmp_path, monkeypatch):
    """cmd_exclusions_generate passes the argparse Namespace to save_source_entries
    so the saved _meta records the CLI args."""
    import json
    from argparse import Namespace
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

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
    # The args dict in _meta should include 'threshold_a': 42 from the Namespace.
    assert on_disk["_meta"]["args"]["threshold_a"] == 42
```

- [ ] **Step 5.2: Run; expect FAIL**

```bash
uv run pytest tests/exclusions/test_provenance.py::test_cmd_exclusions_generate_passes_args_through -v
```

Expected: FAIL — current call is `save_source_entries(args.dataset, generator.name, entries)` with no args param.

- [ ] **Step 5.3: Update the three call sites in `cli.py`**

In `src/neuro_workflow/cli.py`:

(a) `cmd_exclusions_generate` (around line 154):
```python
    save_source_entries(args.dataset, generator.name, entries)
```
becomes:
```python
    save_source_entries(args.dataset, generator.name, entries, args=args)
```

(b) `cmd_exclusions_import` (around line 196):
```python
    save_source_entries(args.dataset, args.source_name, entries)
```
becomes:
```python
    save_source_entries(args.dataset, args.source_name, entries, args=args)
```

(c) `cmd_events_qc` (around line 240):
```python
        save_source_entries(args.dataset, "behavioral-qc", exclusion_entries)
```
becomes:
```python
        save_source_entries(args.dataset, "behavioral-qc", exclusion_entries, args=args)
```

- [ ] **Step 5.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: 13 passed.

- [ ] **Step 5.5: Run full exclusions + analysis suites**

```bash
uv run pytest tests/exclusions/ tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 5.6: Commit**

```bash
git add src/neuro_workflow/cli.py tests/exclusions/test_provenance.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(cli): thread args into save_source_entries for audit trail

Three call sites updated: cmd_exclusions_generate, cmd_exclusions_import,
cmd_events_qc. The CLI args land in the _meta block so the lockfile
records what the user invoked.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Enhance `cmd_exclusions_show` to surface lockfile (TDD)

`cmd_exclusions_show` currently reads `compiled_exclusions.json` and prints a per-source count table. After C0 we have richer info in the lockfile (timestamps, args, code SHA). Enhance the command to print a provenance block when the lockfile exists.

**Files:**
- Modify: `src/neuro_workflow/cli.py`
- Modify: `tests/exclusions/test_provenance.py`

- [ ] **Step 6.1: Append failing test**

Append to `tests/exclusions/test_provenance.py`:

```python
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
```

- [ ] **Step 6.2: Run; expect FAIL on missing provenance keywords**

```bash
uv run pytest tests/exclusions/test_provenance.py::test_cmd_exclusions_show_prints_provenance_when_lockfile_exists -v
```

Expected: FAIL because the existing show output has `Source` / `Exclude` / `Trim` / `Total` headers but no `compiled_at` or `compiled at`.

- [ ] **Step 6.3: Enhance `cmd_exclusions_show`**

Edit `src/neuro_workflow/cli.py`. Replace the existing function:

```python
def cmd_exclusions_show(args, remaining):
    compiled = load_compiled_exclusions(args.dataset)
    if not compiled:
        print(f"No compiled exclusions for '{args.dataset}'. Run 'neuro-run exclusions compile {args.dataset}' first.")
        return
    from collections import Counter
    by_source = Counter(e["source"] for e in compiled)
    by_action = Counter(e["action"] for e in compiled)
    print(f"Exclusions for '{args.dataset}':")
    print(f"{'Source':<15} {'Exclude':>8} {'Trim':>8} {'Total':>8}")
    print("-" * 41)
    for source in sorted(by_source):
        src_entries = [e for e in compiled if e["source"] == source]
        n_exc = sum(1 for e in src_entries if e["action"] == "exclude")
        n_trim = sum(1 for e in src_entries if e["action"] == "trim")
        print(f"{source:<15} {n_exc:>8} {n_trim:>8} {len(src_entries):>8}")
    print("-" * 41)
    print(f"{'Total':<15} {by_action.get('exclude', 0):>8} {by_action.get('trim', 0):>8} {len(compiled):>8}")
```

with:

```python
def cmd_exclusions_show(args, remaining):
    import json
    from collections import Counter
    from neuro_workflow.core.exclusions import _lockfile_path

    compiled = load_compiled_exclusions(args.dataset)

    # Existing per-source count table (always shown if compiled exists).
    if not compiled:
        print(f"No compiled exclusions for '{args.dataset}'. Run 'neuro-run exclusions compile {args.dataset}' first.")
    else:
        by_source = Counter(e["source"] for e in compiled)
        by_action = Counter(e["action"] for e in compiled)
        print(f"Exclusions for '{args.dataset}':")
        print(f"{'Source':<15} {'Exclude':>8} {'Trim':>8} {'Total':>8}")
        print("-" * 41)
        for source in sorted(by_source):
            src_entries = [e for e in compiled if e["source"] == source]
            n_exc = sum(1 for e in src_entries if e["action"] == "exclude")
            n_trim = sum(1 for e in src_entries if e["action"] == "trim")
            print(f"{source:<15} {n_exc:>8} {n_trim:>8} {len(src_entries):>8}")
        print("-" * 41)
        print(f"{'Total':<15} {by_action.get('exclude', 0):>8} {by_action.get('trim', 0):>8} {len(compiled):>8}")

    # Provenance block from lockfile, if present.
    lock_path = _lockfile_path(args.dataset)
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        print()
        print(f"Provenance ({lock_path}):")
        print(f"  Compiled at: {lock['compiled_at']} (code_sha: {lock.get('compiled_at_code_sha')})")
        print(f"  Total entries: {lock['n_total_entries']}, overrides: {lock['n_overrides']}")
        for s in lock["sources"]:
            ran_at = s.get("ran_at") or "<unknown>"
            sha = s.get("code_sha") or "<unknown>"
            n = s.get("n_entries", 0)
            print(f"  - {s['generator']:<15} ran_at={ran_at} code_sha={sha} n_entries={n}")
```

- [ ] **Step 6.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_provenance.py -v
```

Expected: 14 passed.

- [ ] **Step 6.5: Smoke-test the CLI**

```bash
uv run python -c "
from argparse import Namespace
from neuro_workflow.cli import cmd_exclusions_show
cmd_exclusions_show(Namespace(dataset='discovery'), [])
" 2>&1 | head -25
```

Expected: prints the per-source table followed by a `Provenance (...)` block. Note: this hits the real `data/exclusions/discovery_lock.json` if one exists locally; if not, only the table prints.

- [ ] **Step 6.6: Commit**

```bash
git add src/neuro_workflow/cli.py tests/exclusions/test_provenance.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(cli): cmd_exclusions_show prints lockfile provenance block

Reads data/exclusions/<ds>_lock.json (if present) and prints
compiled_at, code_sha, per-source ran_at + code_sha + n_entries.
Falls back gracefully when the lockfile doesn't exist yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `.gitignore` allow-list + final smoke

**Files:**
- Modify (maybe): `.gitignore`

- [ ] **Step 7.1: Inspect `.gitignore` for `data/exclusions/` patterns**

```bash
grep -n 'data/exclusions\|\*_lock\.json' /home/users/logben/neuro_workflow/.gitignore || echo '(no matches)'
```

If the output is `(no matches)`, the lockfile is not gitignored. Skip Step 7.2 and proceed to Step 7.3.

If a wholesale `data/exclusions/` ignore exists (it shouldn't given the existing `<ds>_overrides.json` files already live there and are committed — verify with `git ls-files data/exclusions/`), add an allow-list:

```
!data/exclusions/*_lock.json
```

- [ ] **Step 7.2: Commit `.gitignore` change (only if it was modified)**

```bash
git add .gitignore
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
chore(gitignore): allow data/exclusions/*_lock.json through

Audit-trail lockfiles need to be tracked even though the surrounding
sources/ tree is local-only.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7.3: Generate a real lockfile for discovery + commit it**

Sanity-test the full flow on a real dataset:

```bash
module load uv
uv run neuro-run exclusions compile discovery 2>&1 | tail -5
ls -la /home/users/logben/neuro_workflow/data/exclusions/discovery_lock.json
cat /home/users/logben/neuro_workflow/data/exclusions/discovery_lock.json | head -40
```

Expected: lockfile exists; contains `dataset: "discovery"`, `compiled_at`, `compiled_at_code_sha`, sources for whatever generators have been run (lev1_outlier in particular). The sources may be in legacy bare-list format (their _meta is null until they're re-run); that's expected.

Same for validation if it has any compiled exclusions:

```bash
uv run neuro-run exclusions compile validation 2>&1 | tail -5
ls -la /home/users/logben/neuro_workflow/data/exclusions/validation_lock.json 2>&1 || echo '(no validation lockfile)'
```

- [ ] **Step 7.4: Commit the freshly-generated lockfiles**

```bash
git add data/exclusions/discovery_lock.json data/exclusions/validation_lock.json 2>/dev/null
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
chore(exclusions): commit initial lockfiles for discovery + validation

Snapshot of what generators have been run for each dataset as of
this branch's HEAD. The bare-list sources files (motion, behavioral,
lev1_outlier from before C0) record null fields in the lockfile;
re-running each generator will fill in ran_at/code_sha/args.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)" 2>&1 | tail -3
```

If only one lockfile exists (e.g., validation hasn't been compiled), only that file is added. The `2>/dev/null` swallows the missing-file warning. If the commit fails because nothing was added, that's fine — skip and continue.

- [ ] **Step 7.5: Full broader test suite**

```bash
uv run pytest tests/ -q --tb=line --ignore=tests/analysis 2>&1 | tail -5
uv run pytest tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: both green.

- [ ] **Step 7.6: No additional commit unless verification surfaced a fix.**

---

# Self-Review

**Spec coverage:**
- Goal 1 (per-source `_meta` block) → Tasks 1, 2.
- Goal 2 (`compile_exclusions` writes lockfile + reads `_meta`) → Tasks 3, 4.
- Goal 3 (`neuro-run exclusions show <ds>` enhanced) → Task 6.
- Goal 4 (back-compat for legacy bare-list) → Task 3, plus Task 4's `test_compile_with_bare_list_sources_records_null_meta`.
- Goal 5 (generator code unchanged; wrapping at save layer) → Task 2.
- Helpers (`_git_sha`, `_jsonify`, `make_meta`) → Task 1.
- `.gitignore` allow-list → Task 7 Step 7.1-7.2.
- CLI call sites threaded → Task 5.
- Operational verification → Task 7 Step 7.3-7.4.

**Type consistency:**
- `save_source_entries(ds, source_name, entries, args=None)` — same signature used in tests + production call sites.
- `_lockfile_path(dataset_name)` returns `LOCKFILE_DIR / f"{dataset_name}_lock.json"` — used in lockfile writing AND in `cmd_exclusions_show`.
- `_read_source_file(path)` returns `(entries, meta)` tuple — same shape used by both `load_source_entries` and `compile_exclusions`.
- `make_meta(generator_name, args, n_entries)` signature consistent across helpers + save call.

**Placeholder scan:** no TBD / "implement later" / vague guidance. Each step lists exact text to add or replace. The `Path(__file__).parents[3]` index in Task 4 Step 4.3 has an explicit verification note (the implementer reads the actual layout).

**Risk notes:**
- Task 4 introduces `LOCKFILE_DIR` as a module-level constant resolved from `Path(__file__).resolve().parents[3]`. If the package layout changes in the future (e.g., `src/neuro_workflow/` becomes `neuro_workflow/`), the index needs adjustment.
- Task 5's stub-generator test in Step 5.1 mutates the registry at module level. If pytest collection sees this as a side effect, it could leak between tests. Acceptable risk for a single dedicated test.
- Task 7 Step 7.4 commits real lockfiles. If the implementer's local discovery dataset has no existing compiled exclusions (unlikely given the day's work), the lockfile may have empty `sources: []` — still useful to commit.
