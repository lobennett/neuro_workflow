# QA Decisions Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plumb `qa_report` decisions (TSV) into the existing exclusion registry via a new `QADecisionsGenerator`, expanding subject-level decisions via BIDS glob.

**Architecture:** Extract `_load_dataset_subjects` from `lev1_outlier.py` to `exclusions/base.py` so it can be shared. Add a single new file `exclusions/qa_decisions.py` defining the generator, which reuses `qa.decisions.load_decisions` to parse the TSV. Scan-level rows produce one entry; subject-level rows expand via `bids_dir.glob('sub-X/ses-*/func/*_bold.nii.gz')`. Only `action="exclude"` produces entries; `pass`/`review` are counted in a stdout summary.

**Tech Stack:** Python 3.13, pytest, argparse, csv, pathlib. Reuses existing `qa.decisions.load_decisions` and `core.exclusions.compile_exclusions`.

**Spec:** `docs/superpowers/specs/2026-05-07-qa-decisions-generator-design.md`

---

## Task 1: Extract `_load_dataset_subjects` to `exclusions/base.py`

Promote the helper from `lev1_outlier.py` to `exclusions/base.py` so the new generator can share it. Drop-in compatibility — same name, signature, behavior.

**Files:**
- Modify: `src/neuro_workflow/exclusions/base.py`
- Modify: `src/neuro_workflow/exclusions/lev1_outlier.py`

- [ ] **Step 1.1: Add the helper to `base.py`**

Append to `src/neuro_workflow/exclusions/base.py`, after the existing `list_generators` function:

```python
from pathlib import Path  # add at top of file with other imports if not present


def load_dataset_subjects(dataset_config: dict) -> set[str] | None:
    """Return the dataset's subject IDs (with `sub-` prefix) from `subjects_file`,
    or None if the config has no resolvable subjects file. Bare IDs in the file
    (e.g. `s10`) are normalised to `sub-s10` to match BIDS-prefixed entity IDs.
    """
    raw = dataset_config.get("subjects_file")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        # subjects_file is stored relative to the cwd at registration time.
        # Try cwd first; the user runs CLI from the repo root.
        path = Path.cwd() / raw
    if not path.is_file():
        return None
    subjects: set[str] = set()
    for line in path.read_text().splitlines():
        sid = line.strip()
        if not sid or sid.startswith("#"):
            continue
        subjects.add(sid if sid.startswith("sub-") else f"sub-{sid}")
    return subjects or None
```

Note the rename: `_load_dataset_subjects` → `load_dataset_subjects` (drop the leading underscore, since it's now a public helper). Add `from pathlib import Path` to the imports if `Path` isn't already imported.

- [ ] **Step 1.2: Update `lev1_outlier.py` to use the shared helper**

In `src/neuro_workflow/exclusions/lev1_outlier.py`:

(a) At the top, change the import line from:

```python
from neuro_workflow.exclusions.base import register_generator
```

to:

```python
from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator
```

(b) Delete the existing `_load_dataset_subjects` function definition (currently lines 53-74, the function body starting from `def _load_dataset_subjects(dataset_config: dict) -> set[str] | None:`).

(c) Find the call site inside `Lev1OutlierGenerator.generate` (currently around line ~178, look for `sample = _load_dataset_subjects(dataset_config)`) and rename to `sample = load_dataset_subjects(dataset_config)`.

- [ ] **Step 1.3: Run the L1OG tests to confirm no regression**

```bash
module load uv
uv run pytest tests/exclusions/test_lev1_outlier.py -v
```

Expected: 14 passed (same count as before).

- [ ] **Step 1.4: Commit**

```bash
git add src/neuro_workflow/exclusions/base.py src/neuro_workflow/exclusions/lev1_outlier.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(exclusions): promote load_dataset_subjects to shared base helper

Move the dataset roster loader out of lev1_outlier.py so qa_decisions
(and any future generator) can share it. Drops the leading underscore
since it's now a public helper. No behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Scaffold `tests/exclusions/test_qa_decisions.py`

Create the test file with one smoke test confirming the generator is importable. Establishes the file for subsequent TDD steps.

**Files:**
- Create: `tests/exclusions/test_qa_decisions.py`

- [ ] **Step 2.1: Create the test file**

```python
"""Tests for src/neuro_workflow/exclusions/qa_decisions.py."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_qa_decisions_generator_importable():
    """The generator module imports and exposes QADecisionsGenerator."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    assert QADecisionsGenerator.name == "qa_decisions"
```

- [ ] **Step 2.2: Run; expect FAIL (module doesn't exist yet)**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_workflow.exclusions.qa_decisions'`.

- [ ] **Step 2.3: Commit**

(Skip commit until Task 3 makes the test pass — the failing import test is part of the next TDD cycle.)

---

## Task 3: Generator skeleton + CLI args (TDD)

Create the generator file with a stub `generate` returning `[]`, the CLI arg, and `register_generator` at module bottom. First green for the import smoke test.

**Files:**
- Create: `src/neuro_workflow/exclusions/qa_decisions.py`
- Modify: `tests/exclusions/test_qa_decisions.py`

- [ ] **Step 3.1: Append helpers + a CLI test**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def _write_tsv(path: Path, rows: list[dict]) -> None:
    """Write a minimal qa decisions TSV (subject, session, task, run, action, reason)."""
    fieldnames = ["subject", "session", "task", "run", "action", "reason"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_args(tsv_path: Path) -> "object":
    """Minimal Namespace stand-in for args (only attributes the generator reads)."""
    from argparse import Namespace
    return Namespace(decisions_tsv=tsv_path)


def test_generator_has_cli_arg_for_decisions_tsv():
    """The generator declares --decisions-tsv on its parser."""
    from argparse import ArgumentParser
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator

    parser = ArgumentParser()
    QADecisionsGenerator().add_cli_args(parser)
    args = parser.parse_args(["--decisions-tsv", "/tmp/whatever.tsv"])
    assert str(args.decisions_tsv) == "/tmp/whatever.tsv"
```

- [ ] **Step 3.2: Run; expect FAIL on missing module**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3.3: Create the generator skeleton**

Create `src/neuro_workflow/exclusions/qa_decisions.py`:

```python
"""QA decisions exclusion generator.

Reads the qa_report decisions TSV (subject|session|task|run|action|reason) and
emits per-scan exclusion entries for action=exclude rows. Subject-level
decisions (session/task/run = '-') are expanded via the BIDS BOLD glob.
pass/review rows are counted in a stdout summary and skipped.
"""
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator


class QADecisionsGenerator:
    name = "qa_decisions"
    description = (
        "Auto-exclude scans flagged action=exclude in the qa_report decisions TSV. "
        "Subject-level decisions are expanded to per-scan entries via BIDS glob."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        # Not argparse-required: every generator's args land on the same shared
        # subparser (lesson from PR #6). Runtime guard in generate() raises a
        # clear FileNotFoundError when this source is selected.
        parser.add_argument(
            "--decisions-tsv", type=Path,
            help="Path to qa_report decisions TSV "
                 "(required when source=qa_decisions).",
        )

    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        if args.decisions_tsv is None:
            raise FileNotFoundError(
                "qa_decisions generator requires --decisions-tsv"
            )
        return []


register_generator(QADecisionsGenerator())
```

- [ ] **Step 3.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: 2 passed (import smoke + CLI arg).

- [ ] **Step 3.5: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py src/neuro_workflow/exclusions/qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): scaffold QADecisionsGenerator + CLI args

Skeleton with --decisions-tsv arg and runtime FileNotFoundError guard.
generate() returns [] for now; row processing in subsequent commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Scan-level exclude → one entry (TDD)

First real behavior: a scan-level `action=exclude` row produces one BIDS-prefixed exclusion entry.

**Files:**
- Modify: `tests/exclusions/test_qa_decisions.py`
- Modify: `src/neuro_workflow/exclusions/qa_decisions.py`

- [ ] **Step 4.1: Append failing test**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def test_scan_level_exclude_emits_one_entry(tmp_path):
    """A single scan-level action=exclude row -> one entry, BIDS-prefixed."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "exclude", "reason": "noisy task data"},
    ])

    entries = QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))

    assert len(entries) == 1
    e = entries[0]
    assert e == {
        "subject": "sub-s03",
        "session": "ses-02",
        "task": "task-cuedTS",
        "run": "run-1",
        "source": "qa_decisions",
        "action": "exclude",
        "reason": "qa_decisions: noisy task data (scan-level)",
    }
```

- [ ] **Step 4.2: Run; expect FAIL**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py::test_scan_level_exclude_emits_one_entry -v
```

Expected: FAIL on `assert len(entries) == 1` (current stub returns []).

- [ ] **Step 4.3: Implement scan-level handling**

Replace the body of `generate` in `src/neuro_workflow/exclusions/qa_decisions.py` and add helpers above the class. Replace the entire current file with:

```python
"""QA decisions exclusion generator.

Reads the qa_report decisions TSV (subject|session|task|run|action|reason) and
emits per-scan exclusion entries for action=exclude rows. Subject-level
decisions (session/task/run = '-') are expanded via the BIDS BOLD glob.
pass/review rows are counted in a stdout summary and skipped.
"""
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator
from neuro_workflow.qa.decisions import ScanKey, load_decisions


def _norm_sub(s: str) -> str:
    return s if s.startswith("sub-") else f"sub-{s}"


def _norm_ent(value: str, prefix: str) -> str:
    """Normalize a BIDS entity to the `<prefix>-<value>` form."""
    return value if value.startswith(f"{prefix}-") else f"{prefix}-{value}"


def _entry_from_scan_key(key: ScanKey, reason: str) -> dict:
    return {
        "subject": _norm_sub(key.subject),
        "session": _norm_ent(key.session, "ses"),
        "task": _norm_ent(key.task, "task"),
        "run": _norm_ent(key.run, "run"),
        "source": "qa_decisions",
        "action": "exclude",
        "reason": f"qa_decisions: {reason} (scan-level)",
    }


class QADecisionsGenerator:
    name = "qa_decisions"
    description = (
        "Auto-exclude scans flagged action=exclude in the qa_report decisions TSV. "
        "Subject-level decisions are expanded to per-scan entries via BIDS glob."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        # Not argparse-required (shared subparser).
        parser.add_argument(
            "--decisions-tsv", type=Path,
            help="Path to qa_report decisions TSV "
                 "(required when source=qa_decisions).",
        )

    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        if args.decisions_tsv is None:
            raise FileNotFoundError(
                "qa_decisions generator requires --decisions-tsv"
            )
        if not args.decisions_tsv.is_file():
            raise FileNotFoundError(
                f"qa_decisions: TSV not found: {args.decisions_tsv}"
            )

        decisions = load_decisions(args.decisions_tsv)
        sample = load_dataset_subjects(dataset_config)

        entries: list[dict] = []
        for key, decision in decisions.items():
            if decision.action != "exclude":
                continue
            if isinstance(key, ScanKey):
                if sample is not None and _norm_sub(key.subject) not in sample:
                    continue
                entries.append(_entry_from_scan_key(key, decision.reason))

        entries.sort(key=lambda e: (e["subject"], e["session"], e["task"], e["run"]))
        return entries


register_generator(QADecisionsGenerator())
```

- [ ] **Step 4.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: 3 passed.

- [ ] **Step 4.5: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py src/neuro_workflow/exclusions/qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): emit scan-level exclude entries from qa decisions TSV

Reads decisions via qa.decisions.load_decisions, filters to
action=exclude, normalizes BIDS entities, and applies the dataset
subject filter on scan-level rows. Subject-level expansion comes next.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Pass + review rows skipped + summary line (TDD)

Action `pass` and `review` rows must not produce entries. The generator prints one stdout summary line so the user knows the counts.

**Files:**
- Modify: `tests/exclusions/test_qa_decisions.py`
- Modify: `src/neuro_workflow/exclusions/qa_decisions.py`

- [ ] **Step 5.1: Append failing test**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def test_pass_and_review_rows_skipped(tmp_path, capsys):
    """Mixed actions: only `exclude` produces entries; summary line counts the others."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "exclude", "reason": "noisy"},
        {"subject": "sub-s10", "session": "ses-01", "task": "task-flanker",
         "run": "run-1", "action": "review", "reason": "borderline RT"},
        {"subject": "sub-s19", "session": "ses-03", "task": "task-goNogo",
         "run": "run-1", "action": "pass", "reason": "looks fine"},
    ])

    entries = QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))
    captured = capsys.readouterr()

    assert len(entries) == 1
    assert entries[0]["subject"] == "sub-s03"
    # Summary line includes the skipped counts.
    assert "1 excluded" in captured.out
    assert "1 review-skipped" in captured.out
    assert "1 pass-skipped" in captured.out
```

- [ ] **Step 5.2: Run; expect FAIL on assertion about summary substring**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py::test_pass_and_review_rows_skipped -v
```

Expected: FAIL because no summary is printed yet.

- [ ] **Step 5.3: Add summary printing**

Edit `src/neuro_workflow/exclusions/qa_decisions.py`. Inside `generate`, after the `decisions = load_decisions(...)` line and before the `entries: list[dict] = []` line, initialize counters. Inside the loop, increment `n_pass` / `n_review` for non-exclude rows. After sorting `entries`, print the summary.

Replace the entire `generate` method body with:

```python
    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        if args.decisions_tsv is None:
            raise FileNotFoundError(
                "qa_decisions generator requires --decisions-tsv"
            )
        if not args.decisions_tsv.is_file():
            raise FileNotFoundError(
                f"qa_decisions: TSV not found: {args.decisions_tsv}"
            )

        decisions = load_decisions(args.decisions_tsv)
        sample = load_dataset_subjects(dataset_config)

        entries: list[dict] = []
        n_scan = n_expanded = n_subj_rows = n_review = n_pass = 0

        for key, decision in decisions.items():
            if decision.action == "review":
                n_review += 1
                continue
            if decision.action == "pass":
                n_pass += 1
                continue
            # decision.action == "exclude"
            if isinstance(key, ScanKey):
                if sample is not None and _norm_sub(key.subject) not in sample:
                    continue
                entries.append(_entry_from_scan_key(key, decision.reason))
                n_scan += 1
            # subject-level expansion follows in Task 6

        entries.sort(key=lambda e: (e["subject"], e["session"], e["task"], e["run"]))

        n_excluded = len(entries)
        print(
            f"qa_decisions: {n_excluded} excluded "
            f"({n_scan} scan-level, {n_expanded} expanded from {n_subj_rows} subject-level), "
            f"{n_review} review-skipped, {n_pass} pass-skipped"
        )
        return entries
```

- [ ] **Step 5.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: 4 passed.

- [ ] **Step 5.5: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py src/neuro_workflow/exclusions/qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): count + report pass/review-skipped rows in stdout

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Subject-level expansion via BIDS glob (TDD)

Subject-level rows (`session/task/run = '-'`) expand to one entry per matching `sub-X/ses-*/func/*_bold.nii.gz` in the dataset's BIDS dir.

**Files:**
- Modify: `tests/exclusions/test_qa_decisions.py`
- Modify: `src/neuro_workflow/exclusions/qa_decisions.py`

- [ ] **Step 6.1: Append failing tests**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def _make_fake_bids(tmp_path, subject: str, scans: list[tuple[str, str, str]]) -> Path:
    """Build a minimal BIDS-like dir with empty BOLD files for the given scans.

    Each scan tuple is (session, task, run), e.g. ('ses-02', 'cuedTS', '1').
    Returns the BIDS dir root.
    """
    bids = tmp_path / "bids"
    for session, task, run in scans:
        func = bids / subject / session / "func"
        func.mkdir(parents=True, exist_ok=True)
        fname = f"{subject}_{session}_task-{task}_run-{run}_bold.nii.gz"
        (func / fname).write_bytes(b"")
    return bids


def test_subject_level_exclude_expands_via_bids_glob(tmp_path, capsys):
    """A subject-level exclude row -> one entry per matched BOLD file in BIDS."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    bids_dir = _make_fake_bids(tmp_path, "sub-s03", [
        ("ses-01", "flanker", "1"),
        ("ses-02", "cuedTS", "1"),
        ("ses-02", "stopSignal", "1"),
    ])
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "-", "task": "-", "run": "-",
         "action": "exclude", "reason": "dropped from cohort"},
    ])

    config = {"bids_dir": str(bids_dir)}
    entries = QADecisionsGenerator().generate("discovery", config, _make_args(tsv))
    captured = capsys.readouterr()

    assert len(entries) == 3
    assert {e["subject"] for e in entries} == {"sub-s03"}
    # Granularity is encoded in the reason string.
    for e in entries:
        assert "(subject-level)" in e["reason"]
        assert "dropped from cohort" in e["reason"]
        assert e["action"] == "exclude"
        assert e["source"] == "qa_decisions"
        assert e["task"].startswith("task-")
        assert e["run"].startswith("run-")
        assert e["session"].startswith("ses-")
    # Sorted deterministically.
    sessions_tasks = [(e["session"], e["task"], e["run"]) for e in entries]
    assert sessions_tasks == sorted(sessions_tasks)
    # Summary reports the expansion count.
    assert "0 scan-level" in captured.out
    assert "3 expanded from 1 subject-level" in captured.out


def test_subject_level_with_no_bids_files_emits_zero(tmp_path, capsys):
    """Subject-level row for a sub with no BOLD scans in BIDS -> 0 entries, no error."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    # Empty BIDS dir.
    bids_dir = tmp_path / "bids"
    bids_dir.mkdir()
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s99", "session": "-", "task": "-", "run": "-",
         "action": "exclude", "reason": "missing data"},
    ])

    config = {"bids_dir": str(bids_dir)}
    entries = QADecisionsGenerator().generate("discovery", config, _make_args(tsv))
    captured = capsys.readouterr()

    assert entries == []
    assert "0 expanded from 1 subject-level" in captured.out
```

- [ ] **Step 6.2: Run; expect FAIL on `len(entries) == 3`**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py::test_subject_level_exclude_expands_via_bids_glob -v
```

Expected: FAIL — entries is currently [] for subject-level rows.

- [ ] **Step 6.3: Implement subject-level expansion**

Edit `src/neuro_workflow/exclusions/qa_decisions.py`. Add a helper that parses a BOLD filename into BIDS entities, and extend `generate` to handle `str` keys (subject-level).

Add this helper above the class definition:

```python
import re

_BOLD_RE = re.compile(
    r"^(?P<subject>sub-[A-Za-z0-9]+)"
    r"_(?P<session>ses-[A-Za-z0-9]+)"
    r"_task-(?P<task>[A-Za-z0-9]+)"
    r"_run-(?P<run>[A-Za-z0-9]+)"
    r"_bold\.nii\.gz$"
)


def _expand_subject_to_entries(
    subject: str, reason: str, bids_dir: Path,
) -> list[dict]:
    """Glob the dataset BIDS dir for `subject`'s BOLD files and emit one
    exclusion entry per matched file."""
    sub = subject if subject.startswith("sub-") else f"sub-{subject}"
    out: list[dict] = []
    for bold in (bids_dir / sub).glob("ses-*/func/*_bold.nii.gz"):
        m = _BOLD_RE.match(bold.name)
        if not m:
            continue
        out.append({
            "subject": m.group("subject"),
            "session": m.group("session"),
            "task": f"task-{m.group('task')}",
            "run": f"run-{m.group('run')}",
            "source": "qa_decisions",
            "action": "exclude",
            "reason": f"qa_decisions: {reason} (subject-level)",
        })
    return out
```

In `generate`, after the existing scan-level branch, add the subject-level branch. Replace the loop body inside `generate`:

```python
        for key, decision in decisions.items():
            if decision.action == "review":
                n_review += 1
                continue
            if decision.action == "pass":
                n_pass += 1
                continue
            # decision.action == "exclude"
            if isinstance(key, ScanKey):
                if sample is not None and _norm_sub(key.subject) not in sample:
                    continue
                entries.append(_entry_from_scan_key(key, decision.reason))
                n_scan += 1
            else:
                # subject-level: key is a bare subject string.
                if sample is not None and _norm_sub(key) not in sample:
                    continue
                n_subj_rows += 1
                bids_dir = Path(dataset_config["bids_dir"])
                expanded = _expand_subject_to_entries(key, decision.reason, bids_dir)
                entries.extend(expanded)
                n_expanded += len(expanded)
```

- [ ] **Step 6.4: Run tests; expect PASS**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: 6 passed.

- [ ] **Step 6.5: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py src/neuro_workflow/exclusions/qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(exclusions): expand subject-level qa decisions via BIDS BOLD glob

Subject-level rows (session/task/run = '-') iterate the dataset's
BIDS func directories for matching BOLD files and emit one entry
per scan, tagged (subject-level) in the reason.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Subject filter on scan-level + subject-level rows (TDD)

The subject filter is already wired into both branches of the loop (see Task 4 + Task 6). Add explicit tests that exercise it end-to-end.

**Files:**
- Modify: `tests/exclusions/test_qa_decisions.py`

- [ ] **Step 7.1: Append two tests**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def test_subject_filter_drops_non_member_scan_level(tmp_path):
    """Scan-level rows whose subject isn't in subjects_file are dropped."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "exclude", "reason": "in dataset"},
        {"subject": "sub-s1035", "session": "ses-02", "task": "task-flanker",
         "run": "run-1", "action": "exclude", "reason": "out of dataset"},
    ])
    subjects_path = tmp_path / "subjects_discovery.txt"
    subjects_path.write_text("s03\ns10\n")

    config = {"subjects_file": str(subjects_path)}
    entries = QADecisionsGenerator().generate("discovery", config, _make_args(tsv))

    assert len(entries) == 1
    assert entries[0]["subject"] == "sub-s03"


def test_subject_filter_drops_subject_level_before_glob(tmp_path):
    """Subject-level row for non-member subject is dropped before BIDS glob fires.

    Even with a populated BIDS dir for the non-member subject, no entries are
    emitted; the only entries come from the in-roster subject.
    """
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    bids_dir = _make_fake_bids(tmp_path, "sub-s03", [
        ("ses-01", "flanker", "1"),
    ])
    # Out-of-dataset subject also has BIDS files — these should be ignored.
    _make_fake_bids(tmp_path, "sub-s1035", [
        ("ses-01", "flanker", "1"),
        ("ses-02", "cuedTS", "1"),
    ])
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "-", "task": "-", "run": "-",
         "action": "exclude", "reason": "in dataset"},
        {"subject": "sub-s1035", "session": "-", "task": "-", "run": "-",
         "action": "exclude", "reason": "out of dataset"},
    ])
    subjects_path = tmp_path / "subjects_discovery.txt"
    subjects_path.write_text("s03\ns10\n")

    config = {"bids_dir": str(bids_dir), "subjects_file": str(subjects_path)}
    entries = QADecisionsGenerator().generate("discovery", config, _make_args(tsv))

    assert len(entries) == 1
    assert entries[0]["subject"] == "sub-s03"
    assert entries[0]["task"] == "task-flanker"
```

- [ ] **Step 7.2: Run; expect PASS without code changes**

The filter logic was wired in Tasks 4 and 6. These tests verify that wiring directly. No implementation changes needed.

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: 8 passed.

- [ ] **Step 7.3: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): cover qa_decisions subject filter (scan + subject-level)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Edge cases — missing / empty / invalid TSV (TDD)

Three small tests for the remaining error paths.

**Files:**
- Modify: `tests/exclusions/test_qa_decisions.py`

- [ ] **Step 8.1: Append the tests**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def test_missing_tsv_raises_file_not_found_error(tmp_path):
    """Bogus TSV path -> FileNotFoundError with the path in the message."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    bogus = tmp_path / "does_not_exist.tsv"
    with pytest.raises(FileNotFoundError, match=str(bogus)):
        QADecisionsGenerator().generate("discovery", {}, _make_args(bogus))


def test_empty_tsv_returns_empty_list(tmp_path):
    """TSV with header only returns []."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [])
    entries = QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))
    assert entries == []


def test_invalid_action_propagates_value_error(tmp_path):
    """Unknown action value (e.g. 'maybe') propagates ValueError from load_decisions."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "maybe", "reason": "uh"},
    ])
    with pytest.raises(ValueError, match="invalid action"):
        QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))
```

- [ ] **Step 8.2: Run; expect PASS without code changes**

The error paths are already in the implementation: `is_file()` check raises `FileNotFoundError`; `load_decisions` raises `ValueError` on invalid actions; an empty TSV returns an empty dict.

```bash
uv run pytest tests/exclusions/test_qa_decisions.py -v
```

Expected: 11 passed.

- [ ] **Step 8.3: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): cover qa_decisions missing/empty/invalid TSV cases

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Compile-pipeline integration (TDD)

Confirm generator output flows through `compile_exclusions` end-to-end.

**Files:**
- Modify: `tests/exclusions/test_qa_decisions.py`

- [ ] **Step 9.1: Append the integration test**

Append to `tests/exclusions/test_qa_decisions.py`:

```python
def test_generator_output_flows_through_compile(tmp_path, monkeypatch):
    """Entries from QADecisionsGenerator appear in compile_exclusions output."""
    from neuro_workflow.exclusions.qa_decisions import QADecisionsGenerator
    from neuro_workflow.core import exclusions as core_excl

    monkeypatch.setattr(core_excl, "EXCLUSIONS_DIR", tmp_path / "exclusions")

    tsv = tmp_path / "decisions.tsv"
    _write_tsv(tsv, [
        {"subject": "sub-s03", "session": "ses-02", "task": "task-cuedTS",
         "run": "run-1", "action": "exclude", "reason": "noisy"},
    ])

    entries = QADecisionsGenerator().generate("discovery", {}, _make_args(tsv))
    assert len(entries) == 1

    core_excl.save_source_entries("discovery", "qa_decisions", entries)
    compiled = core_excl.compile_exclusions("discovery")

    assert len(compiled) == 1
    e = compiled[0]
    assert e["source"] == "qa_decisions"
    assert e["subject"] == "sub-s03"
    assert e["task"] == "task-cuedTS"
    assert e["action"] == "exclude"
    assert "noisy" in e["reason"]
```

- [ ] **Step 9.2: Run; expect PASS**

```bash
uv run pytest tests/exclusions/test_qa_decisions.py::test_generator_output_flows_through_compile -v
```

Expected: PASS.

- [ ] **Step 9.3: Commit**

```bash
git add tests/exclusions/test_qa_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
test(exclusions): qa_decisions output flows through compile_exclusions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Wire into cli.py + verify CLI registration

Add the import line so the CLI subparser picks up the new generator.

**Files:**
- Modify: `src/neuro_workflow/cli.py`

- [ ] **Step 10.1: Add the import line**

In `src/neuro_workflow/cli.py`, find the existing block:

```python
import neuro_workflow.exclusions.motion  # noqa: F401
import neuro_workflow.exclusions.behavioral  # noqa: F401
import neuro_workflow.exclusions.lev1_outlier  # noqa: F401
```

Append:

```python
import neuro_workflow.exclusions.qa_decisions  # noqa: F401
```

- [ ] **Step 10.2: Verify CLI exposes the generator + its arg**

```bash
uv run neuro-run exclusions generate qa_decisions --help 2>&1 | tail -10
```

Expected: argparse help text including `--decisions-tsv DECISIONS_TSV`.

- [ ] **Step 10.3: Run all qa + exclusions + analysis tests to confirm no regression**

```bash
uv run pytest tests/exclusions/ tests/qa/ tests/analysis/ -q --tb=line 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 10.4: Commit**

```bash
git add src/neuro_workflow/cli.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(cli): register QADecisionsGenerator for exclusions generate

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Real-data dry run (operational, manual; optional)

If a real qa_report decisions TSV exists for either dataset, dry-run the generator and confirm the output looks sane.

- [ ] **Step 11.1: Locate a decisions TSV (if any exists)**

```bash
find /home/users/logben/neuro_workflow /scratch/users/logben /oak/stanford/groups/russpold/data/network_grant -maxdepth 6 -name '*decisions*.tsv' 2>/dev/null
```

If no TSV exists yet, skip the rest of this task. The generator is verified by the unit + integration tests.

- [ ] **Step 11.2: Run the generator (if a TSV is found)**

```bash
module load uv
uv run neuro-run exclusions generate qa_decisions discovery \
    --decisions-tsv <path-from-step-11.1>
```

Inspect the summary line and the output JSON at `~/.neuro_workflow/exclusions/discovery/sources/qa_decisions.json`.

- [ ] **Step 11.3: Recompile and confirm propagation**

```bash
uv run neuro-run exclusions compile discovery
```

Expected: stdout shows `qa_decisions: N` in the breakdown.

- [ ] **Step 11.4: No commit needed unless something surfaces a fix.**

---

# Self-Review

**Spec coverage:**
- Goal 1 (generator implements ExclusionGenerator Protocol) → Task 3.
- Goal 2 (reuses qa.decisions.load_decisions) → Task 4.
- Goal 3 (scan-level + subject-level granularity) → Tasks 4 + 6.
- Goal 4 (only `action="exclude"` produces entries; pass/review counted) → Task 5.
- Goal 5 (CLI + sources/<ds>/qa_decisions.json output) → Tasks 3 + 10.
- Goal 6 (subject filter via shared helper) → Tasks 1, 4, 6, 7.
- Goal 7 (edge case test coverage) → Tasks 4–9.
- Edge cases: missing TSV (Task 8), empty TSV (Task 8), invalid action (Task 8), subject-level no-BIDS-match (Task 6 second test), conflicting decisions (handled by `load_decisions`'s last-wins behavior — not separately tested; documented in spec).

**Type consistency:**
- `decisions_tsv` (snake_case) used consistently in the args namespace + tests.
- `_norm_sub`, `_norm_ent`, `_entry_from_scan_key`, `_expand_subject_to_entries` helpers — all referenced consistently.
- Output entry schema (`subject, session, task, run, source, action, reason`) is consistent across scan-level and subject-level branches.

**Placeholder scan:**
- Task 11 step 11.1 includes a `find` command that returns paths; "if no TSV exists, skip" is a real branch, not a placeholder.
- Task 6 Step 6.3's added `import re` should land at the top of the file with the other imports — implementer reorganizes imports per existing file convention. Concrete instruction.
- "implementer reorganizes imports" — not a placeholder. The location is clear (top of file with other imports). Final check: the plan's code blocks in Task 4 didn't include `import re` because subject-level expansion comes in Task 6; consistent.

**Risk notes:**
- Task 1's helper rename (`_load_dataset_subjects` → `load_dataset_subjects`) crosses module boundaries. Verified by re-running L1OG tests (Step 1.3).
- Task 6's `_BOLD_RE` regex has only `[A-Za-z0-9]+` for entity values, which excludes BIDS-like dashes / underscores in entity values. The `cuedTS`-style task names are CamelCase and the run values are pure digits — both fit. If a future task name adds a hyphen, the regex would need to be widened.
