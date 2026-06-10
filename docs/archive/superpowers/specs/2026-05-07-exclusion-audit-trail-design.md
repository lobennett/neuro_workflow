# Exclusion Audit Trail — design

**Date:** 2026-05-07
**Status:** Draft, ready for review
**Scope:** Project C, slice C0 — record what generators ran for each dataset, when, with what args, under what code SHA. Out of scope: end-to-end exclusion-flow doc.

---

## Context

Generator outputs at `~/.neuro_workflow/exclusions/<ds>/sources/*.json` are flat JSON arrays of exclusion entries. They live outside the git repo and carry no provenance: there's no record of *what* generator wrote them, *when*, or *what args* it ran with. `compiled_exclusions.json` aggregates them but inherits the same opacity — the only audit trail today is the SLURM `.err` files and the user's memory.

This spec adds a two-layer audit:

1. **Per-source `_meta` block** wrapped around each `sources/<gen>.json` body — out-of-repo, latest-run only.
2. **Committed dataset lockfile** at `data/exclusions/<ds>_lock.json` (matches the existing `<ds>_overrides.json` naming convention) — written by `compile_exclusions`, in-repo, summarizes what was last compiled.

A new `neuro-run exclusions show <ds>` command prints the lockfile contents as a human-readable summary.

---

## Goals

1. Each generator's saved sources file becomes `{"_meta": {...}, "entries": [...]}`. `_meta` records `generator`, `ran_at` (ISO 8601), `code_sha` (with `+dirty` suffix if the working tree is dirty), `args` (full `vars(argparse_namespace)`, with `Path` instances stringified), and `n_entries`.
2. `compile_exclusions(<ds>)` reads each source's `_meta`, aggregates into a top-level provenance dict, and writes both:
    - `~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json` (now has a `_provenance` field)
    - `data/exclusions/<ds>_lock.json` (NEW; committed to git)
3. New `neuro-run exclusions show <ds>` reads the lockfile and prints a formatted summary.
4. Backwards-compatible read path: a sources file in legacy bare-list format (no `_meta` wrapper) is treated as `{"_meta": {"generator": <filename-stem>, "ran_at": null, "code_sha": null, "args": null, "n_entries": len(entries)}, "entries": entries}`. No error, no migration script needed.
5. Generator code itself does not change. The `_meta` wrapping happens at the save-layer (`core.exclusions.save_source_entries`). Generators still return `list[dict]` from `generate(...)`.

## Non-goals

- Append-only history of generator runs (latest-only is enough; git log on the lockfile gives history for free).
- A rendered CLI command string per source (cloners can reconstruct from `args` + generator name).
- Committing the sources files themselves to git (large; YAGNI given the lockfile already enables reproducibility).
- Concurrency safety on lockfile writes (last-writer-wins is acceptable for a fast, rare command).

---

## Architecture

```
src/neuro_workflow/exclusions/base.py        ← add make_meta() + _git_sha() + _jsonify()
src/neuro_workflow/core/exclusions.py        ← save_source_entries wraps _meta;
                                              compile_exclusions writes lockfile;
                                              load step handles bare-list back-compat
src/neuro_workflow/cli.py                    ← new cmd_exclusions_show + subparser
tests/exclusions/test_provenance.py          ← new (9 tests)
.gitignore (verify)                          ← ensure *_lock.json is not gitignored
```

Generator files (`motion.py`, `behavioral.py`, `lev1_outlier.py`, `qa_decisions.py`) are not modified — the `_meta` wrapping is concentrated in `core.exclusions.save_source_entries(...)`. The save call site (currently in `cli.py`'s `cmd_exclusions_generate`) gets the additional `args` and `generator_name` parameters threaded through so the meta can be built.

---

## Data flow

```
neuro-run exclusions generate <gen> <ds> [args]
                        ↓
generator.generate(...) -> list[dict]                                  (unchanged contract)
                        ↓
core.exclusions.save_source_entries(ds, "lev1_outlier", entries, args, generator_name)
   wraps {"_meta": make_meta(...), "entries": entries}
   writes ~/.neuro_workflow/exclusions/<ds>/sources/<gen>.json
                        ↓
neuro-run exclusions compile <ds>
                        ↓
core.exclusions.compile_exclusions(ds)
   - reads each sources/*.json (handles bare-list + wrapped formats)
   - merges entries + applies overrides as before
   - aggregates each source's _meta into provenance dict
   - writes:
       ~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json   (now has _provenance)
       data/exclusions/<ds>_lock.json                                (NEW; committed)
                        ↓
neuro-run exclusions show <ds>
                        ↓
reads data/exclusions/<ds>_lock.json, prints formatted summary
```

---

## Schemas

### `_meta` block (per source)

```json
{
    "generator": "lev1_outlier",
    "ran_at": "2026-05-07T17:30:00Z",
    "code_sha": "20b5738",
    "args": {
        "lev1_outliers_csv": "/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv",
        "combined_vif": 10.0,
        "combined_outlier_pct": 10.0,
        "strict_vif": 15.0,
        "strict_outlier_pct": 15.0
    },
    "n_entries": 131
}
```

### Source file (wrapped)

```json
{
    "_meta": { ... as above ... },
    "entries": [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS", "run": "run-1", "source": "lev1_outlier", "action": "exclude", "reason": "...", "metrics": {...}},
        ...
    ]
}
```

### Lockfile (`data/exclusions/<ds>_lock.json`)

```json
{
    "dataset": "discovery",
    "compiled_at": "2026-05-08T01:30:00Z",
    "compiled_at_code_sha": "20b5738",
    "compiled_path": "~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json",
    "n_total_entries": 141,
    "n_overrides": 0,
    "sources": [
        {
            "generator": "lev1_outlier",
            "ran_at": "2026-05-07T17:30:00Z",
            "code_sha": "20b5738",
            "args": {"lev1_outliers_csv": "/scratch/.../lev1_outliers.csv", "combined_vif": 10.0, "...": "..."},
            "n_entries": 131
        },
        {
            "generator": "motion",
            "ran_at": "2026-05-07T18:00:00Z",
            "code_sha": "20b5738",
            "args": {"fmriprep_version": "25.2.4", "fd_threshold": 0.2, "...": "..."},
            "n_entries": 0
        }
    ]
}
```

### Compiled JSON shape (unchanged)

`~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json` stays a bare list of merged entries. Lev1's `--exclusions-file` reader and any other consumers see the same shape they always have. The lockfile is the canonical audit artifact; duplicating provenance into the compiled JSON would be redundant.

---

## Helper functions in `exclusions/base.py`

```python
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from argparse import Namespace


def _git_sha() -> str | None:
    """Return the current git HEAD SHA (short) plus '+dirty' if working tree is dirty.
    Returns None if git is unavailable or this is not a git repo."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
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
    """Convert Path objects (and other non-JSON natives) to JSON-safe forms."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def make_meta(generator_name: str, args: Namespace | dict, n_entries: int) -> dict:
    """Build the _meta block for a generator's sources file."""
    args_dict = vars(args) if isinstance(args, Namespace) else dict(args)
    return {
        "generator": generator_name,
        "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_sha": _git_sha(),
        "args": _jsonify(args_dict),
        "n_entries": n_entries,
    }
```

---

## Error handling + edge cases

- **Backwards compat for existing sources files**: bare-list format wraps as `{"_meta": {"generator": <filename-stem>, "ran_at": null, "code_sha": null, "args": null, "n_entries": len(entries)}, "entries": entries}` at read time. Compile + lockfile work; nulls flag the unknown fields. Once a generator is re-run, the metadata fills in.
- **Git not available** (Docker without `.git`, or `git` not on PATH): `_git_sha()` returns `None`. Lockfile/_meta records `code_sha: null`. Operation succeeds.
- **Dirty working tree**: SHA suffixed with `+dirty`. Surfaces non-reproducibility without blocking.
- **Path serialization**: `_jsonify` walks dicts/lists/Path. Other non-JSON types (e.g., `Namespace` nested) are not expected; if they appear, `json.dumps` raises and the user sees a clear error.
- **Overrides file missing**: existing behavior — `load_overrides` returns `[]`. Lockfile records `n_overrides: 0`.
- **Lockfile path collision with overrides**: existing convention is `<ds>_overrides.json`. New file is `<ds>_lock.json`. Different stems, no conflict.
- **`.gitignore` pattern**: at implementation time, grep `.gitignore` for any `data/exclusions/` patterns. If `data/exclusions/` is wholesale ignored, add an allow-list `!data/exclusions/*_lock.json` (and `!data/exclusions/*_overrides.json` if the overrides files are currently committed despite a wholesale ignore).
- **Compile run with no sources files**: lockfile written with `sources: []`, `n_total_entries: 0`. No error.
- **Concurrent compile**: last writer wins. Acceptable for this workflow.

---

## Tests

`tests/exclusions/test_provenance.py` (new file):

1. **`test_make_meta_shape`** — `make_meta("foo", Namespace(x=1), n_entries=5)` returns a dict with all expected keys (`generator, ran_at, code_sha, args, n_entries`); `args` has `{"x": 1}`.
2. **`test_make_meta_serializes_path_args`** — args containing `Path("/tmp/x")` serialize to `{"x": "/tmp/x"}` (string).
3. **`test_save_source_entries_wraps_with_meta`** — call save; read back the JSON; assert top-level keys are exactly `{"_meta", "entries"}`; `entries` matches input list.
4. **`test_save_then_compile_round_trips_entries`** — entries written via the wrapper round-trip through `compile_exclusions` unchanged. Consumer back-compat.
5. **`test_compile_writes_lockfile`** — redirect `EXCLUSIONS_DIR` and the project-relative `data/exclusions/`; save two sources; run compile; assert `<ds>_lock.json` exists with expected top-level keys and `len(sources) == 2`.
6. **`test_compile_with_bare_list_sources_file`** — write a sources file as `[{...}, {...}]` (no wrapper); compile succeeds; lockfile records `code_sha: null` and `args: null` for that source.
7. **`test_compile_dirty_tree_appends_dirty_suffix`** — monkeypatch `_git_sha` to return `"abc123+dirty"`; compile; assert lockfile has the suffix.
8. **`test_show_command_prints_summary_lines`** — write a fixture lockfile; invoke `cmd_exclusions_show`; assert stdout contains dataset name, each source's name, total entry count, compiled_at timestamp.
9. **`test_compile_no_sources_writes_empty_lockfile`** — no sources files; compile; lockfile has `sources: []`, `n_total_entries: 0`.

Existing generator tests should not need changes (they assert on the bare entries list returned by `generate()`, which is unchanged). The compile-integration tests in `test_lev1_outlier.py` and `test_qa_decisions.py` (`test_generator_output_flows_through_compile`) may need a small adjustment if they assert on the on-disk file shape; the implementer reads them and adjusts.

---

## Code-style guardrails

- Single new test file (`test_provenance.py`); ≤200 lines.
- All helper functions in `exclusions/base.py` (no separate `provenance.py` — keeping the dependency surface small).
- `_meta` is the canonical key for the metadata block. No `meta`, `metadata`, `provenance` — pick one and stick with it.
- The save call signature change (`save_source_entries(ds, source, entries, args, generator_name)`) updates ALL call sites in one pass (currently just `cli.py:cmd_exclusions_generate`). No backwards-compat shim for the old signature.
- Lockfile path is `data/exclusions/<ds>_lock.json` everywhere. Hard-coded relative path; not configurable.

---

## Open questions / decisions deferred to implementation

1. **Exact place to thread `args` + `generator_name` into `save_source_entries`** — current `cmd_exclusions_generate` in `cli.py` already has both available. Implementer threads them through. If the function is called elsewhere in `core/exclusions.py` (e.g., from a test fixture), the new required args propagate there too.
2. **`.gitignore` allow-list pattern** — implementer greps the file, adds `!data/exclusions/*_lock.json` only if a wholesale ignore would otherwise catch it.
