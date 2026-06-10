"""Scan exclusion management: schema, persistence, compilation, and query API."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Optional

from neuro_workflow.core.config import CONFIG_DIR

EXCLUSIONS_DIR = CONFIG_DIR / "exclusions"

# Project-relative path for committed lockfiles. Resolved at write time
# from the package's parent directories.
_REPO_ROOT = Path(__file__).resolve().parents[3]
LOCKFILE_DIR = _REPO_ROOT / "data" / "exclusions"

REQUIRED_FIELDS = {"subject", "session", "task", "run", "action", "reason"}
VALID_ACTIONS = {"exclude", "trim", "force-include", "force-exclude"}


def _scan_key(entry: dict) -> tuple:
    return (entry["subject"], entry["session"], entry["task"], entry["run"])


def validate_entry(entry: dict) -> bool:
    """Check that an entry has all required fields and a valid action."""
    if not REQUIRED_FIELDS.issubset(entry.keys()):
        return False
    if entry["action"] not in VALID_ACTIONS:
        return False
    return True


def _sources_dir(dataset_name: str) -> Path:
    return EXCLUSIONS_DIR / dataset_name / "sources"


def _overrides_path(dataset_name: str) -> Path:
    return EXCLUSIONS_DIR / dataset_name / "overrides.json"


def _compiled_path(dataset_name: str) -> Path:
    return EXCLUSIONS_DIR / dataset_name / "compiled_exclusions.json"


def _lockfile_path(dataset_name: str) -> Path:
    return LOCKFILE_DIR / f"{dataset_name}_lock.json"


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

    # Fail loud (GE-4): reject malformed entries before they reach disk, rather
    # than silently persisting entries that compile/query will later mishandle.
    invalid = [e for e in entries if not validate_entry(e)]
    if invalid:
        missing = [sorted(REQUIRED_FIELDS - set(e.keys())) for e in invalid]
        raise ValueError(
            f"{len(invalid)} invalid entr{'y' if len(invalid) == 1 else 'ies'} for "
            f"source '{source_name}' (dataset '{dataset_name}'): missing/invalid "
            f"required fields {REQUIRED_FIELDS} or action not in {VALID_ACTIONS}. "
            f"First offender missing fields: {missing[0] if missing else None}"
        )

    d = _sources_dir(dataset_name)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": make_meta(source_name, args, len(entries)),
        "entries": entries,
    }
    with open(d / f"{source_name}.json", "w") as f:
        json.dump(payload, f, indent=2)


def load_source_entries(dataset_name: str, source_name: str) -> list[dict]:
    """Load entries for a single source. Handles both wrapped and bare formats."""
    path = _sources_dir(dataset_name) / f"{source_name}.json"
    if not path.exists():
        return []
    entries, _meta = _read_source_file(path)
    return entries


def save_overrides(dataset_name: str, overrides: list[dict]) -> None:
    """Write manual override entries."""
    path = _overrides_path(dataset_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(overrides, f, indent=2)


def load_overrides(dataset_name: str) -> list[dict]:
    """Load manual override entries."""
    path = _overrides_path(dataset_name)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def compile_exclusions(dataset_name: str, bids_dir: Optional[str] = None) -> list[dict]:
    """Merge all source files and overrides into a compiled exclusion list.

    1. Collect all entries from sources/*.json
    2. Apply overrides: force-include removes, force-exclude adds
    3. Save compiled result
    4. Optionally copy to derivatives
    """
    sources_dir = _sources_dir(dataset_name)
    all_entries: list[dict] = []

    sources_meta: list[dict] = []
    if sources_dir.exists():
        for source_file in sorted(sources_dir.glob("*.json")):
            entries, meta = _read_source_file(source_file)
            all_entries.extend(entries)
            if meta is not None:
                sources_meta.append(meta)

    overrides = load_overrides(dataset_name)

    # Separate override types
    force_includes = {_scan_key(o) for o in overrides if o.get("action") == "force-include"}
    force_excludes = [o for o in overrides if o.get("action") == "force-exclude"]

    # Remove force-included scans
    if force_includes:
        all_entries = [e for e in all_entries if _scan_key(e) not in force_includes]

    # Add force-excluded scans
    for fe in force_excludes:
        all_entries.append({
            "subject": fe["subject"],
            "session": fe["session"],
            "task": fe["task"],
            "run": fe["run"],
            "source": "override",
            "action": "exclude",
            "reason": fe.get("reason", "Manual force-exclude"),
            "metrics": fe.get("metrics", {}),
        })

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


def load_compiled_exclusions(dataset_name: str) -> list[dict]:
    """Load the compiled exclusion list for a dataset."""
    path = _compiled_path(dataset_name)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def is_excluded(subject: str, session: str, task: str, run: str, compiled: list[dict]) -> bool:
    """Check if a scan is excluded (action == 'exclude' or 'trim')."""
    key = (subject, session, task, run)
    return any(_scan_key(e) == key for e in compiled if e["action"] in ("exclude", "trim"))


def get_trim_info(subject: str, session: str, task: str, run: str, compiled: list[dict]) -> Optional[dict]:
    """Get trim metrics for a scan, or None if not a trim action."""
    key = (subject, session, task, run)
    for e in compiled:
        if _scan_key(e) == key and e["action"] == "trim":
            return e.get("metrics", {})
    return None


def _normalise_bids_field(value: str, prefix: str) -> str:
    """Return value with the given BIDS prefix stripped to bare form (idempotent).

    Canonicalises to the BARE form by stripping the prefix when present. This
    allows prefix-insensitive comparison by normalising both the query argument
    and the stored entry field to the same bare representation.

    Examples
    --------
    >>> _normalise_bids_field("sub-s10", "sub-")  # strip prefix → bare
    's10'
    >>> _normalise_bids_field("s10", "sub-")       # already bare → unchanged
    's10'
    >>> _normalise_bids_field("task-goNogo", "task-")  # strip prefix
    'goNogo'
    >>> _normalise_bids_field("goNogo", "task-")       # already bare
    'goNogo'
    """
    if value.startswith(prefix):
        return value[len(prefix):]
    return value


def query_exclusions(
    compiled: list[dict],
    subject: str,
    session: Optional[str] = None,
    task: Optional[str] = None,
) -> list[dict]:
    """Return all compiled entries that match subject (and optionally session/task).

    Matching is prefix-insensitive: ``"s10"`` and ``"sub-s10"`` are treated
    as identical, likewise ``"05"`` / ``"ses-05"`` and ``"goNogo"`` /
    ``"task-goNogo"``. Both the query argument and the stored entry field are
    normalised to bare form before comparison, so it works regardless of
    whether entries were written with or without the BIDS prefix.

    Results are sorted by (session, task, run) for readable output.
    """
    subject_norm = _normalise_bids_field(subject, "sub-")

    session_norm: Optional[str] = None
    if session is not None:
        session_norm = _normalise_bids_field(session, "ses-")

    task_norm: Optional[str] = None
    if task is not None:
        task_norm = _normalise_bids_field(task, "task-")

    matches = []
    for e in compiled:
        if _normalise_bids_field(e["subject"], "sub-") != subject_norm:
            continue
        if session_norm is not None and _normalise_bids_field(e["session"], "ses-") != session_norm:
            continue
        if task_norm is not None and _normalise_bids_field(e["task"], "task-") != task_norm:
            continue
        matches.append(e)

    matches.sort(key=lambda e: (e.get("session", ""), e.get("task", ""), e.get("run", "")))
    return matches
